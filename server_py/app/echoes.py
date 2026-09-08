"""
Echoes: traces other players leave in the world.

A single shared universe full of mostly-offline players should still feel
inhabited. Notable deeds (kills, boss falls, bounty claims, discoveries) are
logged as 'deed' world events; when you look at a location you see what
others did there recently. Cheap, asynchronous multiplayer presence.
"""

from __future__ import annotations

from typing import List

from .db import log_world_event, get_recent_deeds_at
from .presence import ago
from .types import Player


def record_deed(player: Player, location_id: str, description: str, *, kind: str = "kill") -> None:
    log_world_event(
        event_type="deed",
        location_id=location_id,
        data={
            "player_id": player.player_id,
            "player_name": player.name,
            "kind": kind,
            "description": description,
        },
    )


def echoes_for(player: Player, limit: int = 3) -> List[dict]:
    """Recent deeds by other players at this player's location."""
    deeds = get_recent_deeds_at(player.location, exclude_player=player.player_id, limit=limit)
    return [
        {
            "description": d["data"].get("description", ""),
            "player_name": d["data"].get("player_name", "Someone"),
            "ago": ago(d["created_at"]),
        }
        for d in deeds
    ]


def echo_lines(player: Player, limit: int = 3) -> List[str]:
    return [f"{e['description']} ({e['ago']})" for e in echoes_for(player, limit) if e["description"]]


# World events worth gossiping about wherever people gather.
_RUMOR_EVENT_TYPES = {
    "region_discovered", "world_evolution", "goal_completed",
    "goal_started", "goal_expired",
    "incident_started", "incident_resolved", "incident_expired",
    "act_authored", "act_complete", "wrong_righted",
}


def rumor_lines(player: Player, limit: int = 2) -> List[str]:
    """
    Recent world-scale news, told as talk of the town. Settlements surface
    these on look, so standing at spawn still shows a universe in motion.
    """
    from .db import get_world_events

    lines: List[str] = []
    for event in get_world_events(25):
        if event.get("event_type") not in _RUMOR_EVENT_TYPES:
            continue
        if (event.get("data") or {}).get("player_id") == player.player_id:
            continue
        text = (event.get("data") or {}).get("description")
        if not text or any(text in line for line in lines):
            continue
        lines.append(f"{text} ({ago(event['created_at'])})")
        if len(lines) >= limit:
            break
    return lines
