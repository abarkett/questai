from __future__ import annotations

import uuid

from ...types import Player, ActionResponse
from ...db import upsert_player
from ...world import get_location


def create_player(name: str) -> ActionResponse:
    player = Player(
        player_id=str(uuid.uuid4()),
        name=name,
        location="town_square",
        level=1,
        xp=0,
        hp=10,
        max_hp=10,
    )
    upsert_player(player)

    loc = get_location(player.location)
    return ActionResponse(
        ok=True,
        messages=[f"Welcome, {player.name}.", f"You arrive at {loc.name}."],
        state={
            "player": player.model_dump(),
            "location": {
                "id": loc.id,
                "name": loc.name,
                "description": loc.description,
                "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
            },
        },
    )

