"""
Login recap: "while you were gone" narration.

When a player returns after a real absence, the world has moved without them —
other players' deeds, world evolution, community goals. The recap turns the
event log since their last visit into a short summary, AI-narrated when Miriel
is configured, plain text otherwise. Absence becomes part of the story
instead of dead time.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from .db import (
    get_world_events_since,
    cache_miriel_content,
    get_cached_miriel_content,
)
from .types import Player

# Only recap after a genuine absence, not a coffee break.
RECAP_GAP_MS = 6 * 60 * 60 * 1000
# Shorter absences still get a one-line pulse so every session opens with
# proof the world moved without you.
PULSE_GAP_MS = 30 * 60 * 1000
MAX_EVENTS = 8


def _event_line(event: dict) -> Optional[str]:
    data = event.get("data") or {}
    etype = event.get("event_type")
    if etype == "deed":
        return data.get("description")
    if etype in ("world_evolution", "region_discovered", "goal_completed"):
        return data.get("description")
    return None


def build_recap_lines(player: Player, since_ms: int) -> List[str]:
    lines: List[str] = []
    for event in get_world_events_since(since_ms, limit=200):
        # Don't recap the player to themselves.
        if (event.get("data") or {}).get("player_id") == player.player_id:
            continue
        line = _event_line(event)
        if line and line not in lines:
            lines.append(line)
        if len(lines) >= MAX_EVENTS:
            break
    return lines


def _narrate(player: Player, lines: List[str]) -> Optional[str]:
    """Ask Miriel to fold the raw events into 2-3 sentences (cached)."""
    from .services.miriel_client import is_miriel_enabled, get_miriel_client

    if not is_miriel_enabled():
        return None
    sig = hashlib.sha256(("recap|" + player.player_id + "|" + "|".join(lines)).encode()).hexdigest()[:16]
    cache_key = f"recap_{sig}"
    cached = get_cached_miriel_content(cache_key)
    if cached:
        return cached
    query = (
        "The player returns to a fantasy RPG world after time away. In 2-3 "
        "warm, vivid sentences, recap what happened in the world while they "
        "were gone, addressed to them. Mention other adventurers by name where "
        "given. No lists, no UI.\n\nEvents:\n- " + "\n- ".join(lines)
    )
    try:
        resp = get_miriel_client().query(query=query, project="questai")
        from .services.miriel_client import extract_answer
        answer = extract_answer(resp)
        if answer:
            cache_miriel_content(cache_key, "dialogue", answer, ttl_seconds=3600)
            return answer
    except Exception:
        pass
    return None


def world_pulse(player: Player) -> List[str]:
    """One line of world heartbeat: the season's progress + the latest event."""
    from .world_goals import get_active_world_goals

    parts: List[str] = []
    goals = get_active_world_goals()
    if goals:
        g = goals[0]
        parts.append(f"Season: {g['name']} {min(g['progress'], g['required'])}/{g['required']}")
    from .db import get_world_events
    for event in get_world_events(10):
        if (event.get("data") or {}).get("player_id") == player.player_id:
            continue
        line = _event_line(event)
        if line:
            parts.append(line)
            break
    return [" · ".join(parts)] if parts else []


def recap_messages(player: Player, last_seen_ms: int, now_ms: int) -> List[str]:
    """
    Messages to prepend to a returning player's first action: a full recap
    after a real absence, a one-line pulse after a shorter one, [] otherwise.
    """
    if not last_seen_ms:
        return []
    gap = now_ms - last_seen_ms
    if gap < PULSE_GAP_MS:
        return []
    if gap < RECAP_GAP_MS:
        return world_pulse(player)
    lines = build_recap_lines(player, last_seen_ms)
    if not lines:
        return world_pulse(player)
    narrated = _narrate(player, lines)
    if narrated:
        return [f"While you were away: {narrated}"]
    return ["While you were away:"] + [f"  - {line}" for line in lines]
