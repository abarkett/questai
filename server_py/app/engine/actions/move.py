from __future__ import annotations

from ...types import Player, ActionResponse
from ...world import get_location
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity, get_adjacent_scenes


def move(player: Player, to_label_or_id: str) -> ActionResponse:
    from_loc = get_location(player.location)
    needle = to_label_or_id.strip().lower()

    exit_match = None
    for e in from_loc.exits:
        if e.label.lower() == needle or e.to.lower() == needle:
            exit_match = e
            break

    if not exit_match:
        exits = ", ".join([e.label for e in from_loc.exits]) if from_loc.exits else "none"
        return ActionResponse(
            ok=False,
            error=f'No exit matching "{to_label_or_id}". Exits: {exits}'
        )

    # Move player
    player.location = exit_match.to
    upsert_player(player)

    to_loc = get_location(player.location)

    # NEW: fetch entities at destination
    entities = get_entities_at(player.location)
    
    # Filter out the current player from entities
    entities = [e for e in entities if not (e.get("type") == "player" and e.get("id") == player.player_id)]
    
    # Phase 8: Track monster survival for world evolution
    from ...world_rules import track_monster_survival
    track_monster_survival(player.location)

    return ActionResponse(
        ok=True,
        messages=[
            f"You travel to {to_loc.name}.",
            to_loc.description,
        ],
        state={
            "player": player.model_dump(),
            "location": {
                "id": to_loc.id,
                "name": to_loc.name,
                "description": to_loc.description,
                "exits": [{"to": e.to, "label": e.label} for e in to_loc.exits],
            },
            "entities": entities,
            "adjacent_scenes": get_adjacent_scenes(to_loc.id),
        },
    )