"""
Dynamic, Miriel-authored location prose.

Demonstrating Miriel is a core aim of the project, so there is NO deterministic
fallback: if Miriel is unavailable — or reachable but producing no usable
prose — describing a location raises and the request fails hard. Silent
degradation to authored text is worse than a crash: it hides a broken AI
integration behind a working-looking game. The deterministic helpers below
only build *context* for the prompt (time of day, what's present); the prose
itself always comes from Miriel.
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


def cache_family_for(loc, entities: List[dict], base: str) -> str:
    """
    The part of the description cache key that identifies *what* is described:
    the place, the creatures in it, and the base text. Everything else in the
    key (time of day, the refresh bucket) only varies the prose for the same
    situation — so any cached entry in the family is a truthful, if slightly
    stale, description of it.
    """
    creatures = present_creatures(entities)
    base_sig = hashlib.sha256(base.encode()).hexdigest()[:8]
    return hashlib.sha256(f"{loc.id}|{','.join(creatures)}|{base_sig}".encode()).hexdigest()[:12]


def cache_key_for(loc, entities: List[dict], world_turn: int, base: str) -> str:
    """
    The description cache key for a location *as it is right now*.

    This is the ONE place the key is derived — describe(), the prefetch warmer,
    and the tests all use it, so the formula can't drift between them. The base
    text is part of the key on purpose: when a righted wrong re-describes a
    place (see app/restoration.py), its prose refreshes at once instead of
    serving the pre-restoration text from the cache.

    Shape: ``desc_<family>_<variant>`` — the family (see cache_family_for)
    groups every rendering of the same situation, which is what lets a stale
    entry be served instantly while a fresh one is written in the background.
    """
    family = cache_family_for(loc, entities, base)
    tod = time_of_day(loc.id, world_turn)
    bucket = world_turn // 12  # refresh prose a few times per "day"
    variant = hashlib.sha256(f"{tod}|{bucket}".encode()).hexdigest()[:8]
    return f"desc_{family}_{variant}"


# How long a freshly authored description stays "fresh". Past this (or once
# the refresh bucket turns over) the entry is still *served* — instantly, as
# the stale copy — while Miriel writes the new one in the background.
DESCRIPTION_TTL_SECONDS = 24 * 3600


def _author(loc, creatures: List[str], tod: Optional[str], base: str) -> str:
    """One Miriel round-trip for the prose. Raises (no fallback) on nothing usable."""
    from .services.miriel_client import get_miriel_client, extract_answer, describe_shape

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
    answer = extract_answer(resp)
    if not answer:
        # Reachable but no usable prose anywhere in the response. This is the
        # failure mode that silent fallbacks hide for weeks — fail hard, and
        # print the response structure so the fix is one log line away.
        raise MirielUnavailable(
            f"Miriel returned no prose for '{loc.id}' "
            f"(response shape: {describe_shape(resp)}). The game requires Miriel."
        )
    return answer


def _author_and_cache(loc, creatures: List[str], tod: Optional[str], base: str, cache_key: str) -> str:
    from .db import cache_miriel_content

    answer = _author(loc, creatures, tod, base)
    cache_miriel_content(cache_key, "dialogue", answer, ttl_seconds=DESCRIPTION_TTL_SECONDS)
    return answer


def describe(player, loc, entities: List[dict], base: str, world_turn: int) -> str:
    """
    Return a Miriel-authored description of the location as it is right now.
    Raises MirielUnavailable if Miriel is unconfigured OR answers with nothing
    usable — by design, there is no fallback.

    Stale-while-revalidate: a place already described once (same creatures,
    same base text) answers instantly from the cache even after the prose is
    due a refresh — the refreshed version is written in the background and
    served next time. Only a place never described before waits on Miriel.
    """
    from .services.miriel_client import is_miriel_enabled
    from .db import get_cached_miriel_content, get_latest_miriel_content_by_prefix

    if not is_miriel_enabled():
        raise MirielUnavailable(
            "Miriel is not configured (set MIRIEL_API_KEY). The game requires Miriel."
        )

    creatures = present_creatures(entities)
    tod = time_of_day(loc.id, world_turn)
    cache_key = cache_key_for(loc, entities, world_turn, base)

    cached = get_cached_miriel_content(cache_key)
    if cached:
        return cached

    stale = get_latest_miriel_content_by_prefix(f"desc_{cache_family_for(loc, entities, base)}_")
    if stale:
        from . import warmer
        warmer.submit(
            f"refresh:{cache_key}",
            lambda: _author_and_cache(loc, creatures, tod, base, cache_key),
            priority=2,
        )
        return stale

    return _author_and_cache(loc, creatures, tod, base, cache_key)
