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
