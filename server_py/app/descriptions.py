"""
Dynamic location prose. Two layers:

  1. Deterministic ambient flavor that shifts with the world clock (and notes
     what's present), so the same room reads differently over time.
  2. A best-effort Miriel-authored description when the AI is configured,
     cached briefly; falls back to layer 1 on any failure.

Kept out of build_action_state (which feeds the image cache) so scene images
stay stable; this is for the text the player reads on `look`.
"""

from __future__ import annotations

import hashlib
from typing import Any, List, Optional

# Roughly outdoor places get time-of-day flavor; indoor ones don't.
_OUTDOOR = {
    "town_square", "north_road", "forest", "deep_forest", "riverside",
    "thornwood", "spider_hollow", "foothills", "mountain_pass", "ashen_waste",
}

_TIME_FLAVOR = [
    "Dawn light spills pale across the land.",
    "The midday sun stands high and bright.",
    "Long afternoon shadows stretch underfoot.",
    "Dusk bleeds red along the horizon.",
    "Night has fallen, and the stars wheel overhead.",
]


def ambient_flavor(location_id: str, world_turn: int) -> Optional[str]:
    """A time-of-day line for outdoor locations that rotates as turns pass."""
    if location_id not in _OUTDOOR:
        return None
    return _TIME_FLAVOR[(world_turn // 12) % len(_TIME_FLAVOR)]


def presence_flavor(entities: List[dict]) -> Optional[str]:
    """A sentence reflecting which creatures are present right now."""
    from .world_entities import MONSTER_AGGRO

    monsters = [e for e in entities if e.get("type") == "monster"]
    if not monsters:
        return None
    names = sorted({m["name"] for m in monsters})
    listing = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
    hostile = any(MONSTER_AGGRO.get(m["name"]) for m in monsters)
    return f"{listing} {'watches you, hackles raised' if hostile else 'moves about, paying you little mind'}."


def deterministic_description(base: str, location_id: str, entities: List[dict], world_turn: int) -> str:
    parts = [base]
    amb = ambient_flavor(location_id, world_turn)
    if amb:
        parts.append(amb)
    pres = presence_flavor(entities)
    if pres:
        parts.append(pres)
    return " ".join(parts)


def maybe_ai_description(player, loc, entities: List[dict], base: str) -> Optional[str]:
    """
    Ask Miriel for an atmospheric description (cached). Returns None if Miriel
    is disabled or anything goes wrong, so the caller falls back to the
    deterministic text.
    """
    try:
        from .services.miriel_client import is_miriel_enabled, get_miriel_client
        if not is_miriel_enabled():
            return None

        from .db import get_cached_miriel_content, cache_miriel_content, get_world_turn

        names = sorted({e["name"] for e in entities if e.get("type") == "monster"})
        bucket = get_world_turn() // 12  # refresh prose a few times per "day"
        sig = hashlib.sha256(f"{loc.id}|{','.join(names)}|{bucket}".encode()).hexdigest()[:16]
        cache_key = f"desc_{sig}"

        cached = get_cached_miriel_content(cache_key)
        if cached:
            return cached

        creatures = f" Present: {', '.join(names)}." if names else " No creatures are present."
        query = (
            "In 1-2 vivid sentences, describe this fantasy RPG location as the player "
            "sees it right now. Reflect what's present and the mood. No lists, no UI, "
            "second person or scene-setting prose only.\n\n"
            f"Location: {loc.name}. {base}{creatures}"
        )
        resp = get_miriel_client().query(query=query, project="questai")
        answer = ((resp or {}).get("results", {}) or {}).get("answer", "")
        answer = (answer or "").strip()
        if answer:
            cache_miriel_content(cache_key, "dialogue", answer, ttl_seconds=600)
            return answer
    except Exception:
        return None
    return None
