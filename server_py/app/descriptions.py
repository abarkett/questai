"""
Dynamic, Miriel-authored location prose — with a deterministic fallback.

When Miriel is configured, location prose is AI-authored from live context
(time of day, what's present, world state). When it isn't, the location's
authored description is used instead: every game surface (web, CLI, SMS) must
stay playable text-first with no AI configured.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

# Roughly outdoor places get time-of-day context; indoor ones don't.
_OUTDOOR = {
    "town_square", "north_road", "forest", "deep_forest", "riverside",
    "thornwood", "spider_hollow", "foothills", "mountain_pass", "ashen_waste",
}

_TIME_OF_DAY = ["dawn", "midday", "afternoon", "dusk", "night"]


from .services.miriel_client import MirielUnavailable  # re-exported for callers


def time_of_day(location_id: str, world_turn: int) -> Optional[str]:
    if location_id not in _OUTDOOR:
        from .content import is_outdoor

        if not is_outdoor(location_id):
            return None
    return _TIME_OF_DAY[(world_turn // 12) % len(_TIME_OF_DAY)]


def present_creatures(entities: List[dict]) -> List[str]:
    return sorted({e["name"] for e in entities if e.get("type") == "monster"})


def describe(player, loc, entities: List[dict], base: str, world_turn: int) -> str:
    """
    Return a description of the location as it is right now: Miriel-authored
    prose when the AI is configured, the authored `base` text otherwise.
    """
    from .services.miriel_client import is_miriel_enabled, get_miriel_client
    from .db import get_cached_miriel_content, cache_miriel_content

    if not is_miriel_enabled():
        return base

    creatures = present_creatures(entities)
    tod = time_of_day(loc.id, world_turn)
    bucket = world_turn // 12  # refresh prose a few times per "day"
    sig = hashlib.sha256(f"{loc.id}|{','.join(creatures)}|{tod}|{bucket}".encode()).hexdigest()[:16]
    cache_key = f"desc_{sig}"

    cached = get_cached_miriel_content(cache_key)
    if cached:
        return cached

    context = (
        f"Location: {loc.name}. {base}"
        + (f" Time of day: {tod}." if tod else "")
        + (f" Present: {', '.join(creatures)}." if creatures else " No creatures are present.")
    )
    query = (
        "In 1-2 vivid sentences, describe this fantasy RPG location as the player sees "
        "it right now. Reflect the time of day and what is present; set the mood. "
        "Scene-setting prose only — no lists, no UI.\n\n" + context
    )

    # The Miriel query is single-flighted in the client, so a concurrent warm +
    # look for the same scene share one round-trip. Not wrapped in try/except: a
    # Miriel outage propagates and the request fails hard (by design).
    resp = get_miriel_client().query(query=query, project="questai")
    answer = ((resp or {}).get("results", {}) or {}).get("answer", "")
    answer = (answer or "").strip()
    if not answer:
        # Miriel reachable but produced nothing for this scene — show the
        # location's own authored description rather than 500 the request.
        return base

    cache_miriel_content(cache_key, "dialogue", answer, ttl_seconds=600)
    return answer
