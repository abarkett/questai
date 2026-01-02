from __future__ import annotations

from ...types import Player, ActionResponse
from ...world import get_location
from ...db import get_world_state
from ..entities import get_entities_at, serialize_entity, get_adjacent_scenes


def look(player: Player) -> ActionResponse:
    loc = get_location(player.location)
    entities = get_entities_at(player.location)

    messages = [
        f"You are at {loc.name}.",
    ]
    
    # Phase 8: Add world state flavor to location descriptions
    description = loc.description
    if loc.id == "forest":
        is_infested = get_world_state("forest_infested") == "true"
        if is_infested:
            description += " The forest feels particularly dangerous today."
    
    messages.append(description)

    if entities:
        messages.append(
            "You see: " + ", ".join(e["name"] for e in entities)
        )

    exits = ", ".join(e.label for e in loc.exits) if loc.exits else "none"
    messages.append(f"Exits: {exits}")

    return ActionResponse(
        ok=True,
        messages=messages,
        state={
            "player": player.model_dump(),
            "location": {
                "id": loc.id,
                "name": loc.name,
                "description": loc.description,
                "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
            },
            "entities": entities,
            "adjacent_scenes": get_adjacent_scenes(loc.id),
        },
    )