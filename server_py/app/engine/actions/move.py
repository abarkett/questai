from __future__ import annotations

from ...types import Player, ActionResponse
from ...world import get_location
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity, get_adjacent_scenes, filter_current_player
from ..state_view import build_action_state


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

    # Phase 8: Track monster survival for world evolution
    from ...world_rules import track_monster_survival
    track_monster_survival(player.location)

    return ActionResponse(
        ok=True,
        messages=[
            f"You travel to {to_loc.name}.",
            to_loc.description,
        ],
        state=build_action_state(player, scene_dirty=True),
    )