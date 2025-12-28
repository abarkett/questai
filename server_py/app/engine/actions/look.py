from __future__ import annotations

from ...types import Player, ActionResponse
from ...world import get_location


def look(player: Player) -> ActionResponse:
    loc = get_location(player.location)
    exits = ", ".join([e.label for e in loc.exits]) if loc.exits else "none"

    return ActionResponse(
        ok=True,
        messages=[
            f"You are at {loc.name}.",
            loc.description,
            f"Exits: {exits}",
        ],
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

