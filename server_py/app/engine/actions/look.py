from __future__ import annotations

from ...types import Player, ActionResponse
from ...world import get_location
from ...db import get_world_state, upsert_player
from ..entities import get_entities_at, serialize_entity, filter_current_player
from ..visited import mark_visited
from ..state_view import build_action_state, effective_description


def look(player: Player) -> ActionResponse:
    loc = get_location(player.location)
    changed = mark_visited(player)
    entities = get_entities_at(player.location)
    entities = filter_current_player(entities, player.player_id)

    # Record any monsters present in the bestiary.
    from ...bestiary import discover
    for e in entities:
        if e.get("type") == "monster" and discover(player, e["name"]):
            changed = True
    if changed:
        upsert_player(player)

    messages = [
        f"You are at {loc.name}.",
    ]
    
    # Context-aware description (quiet once cleared), plus world-state flavor.
    base = effective_description(loc)
    if loc.id == "forest" and get_world_state("forest_infested") == "true":
        base += " The forest feels particularly dangerous today."

    # Dynamic prose: AI-authored when Miriel is configured, else a deterministic
    # description that shifts with the world clock and what's present.
    from ...db import get_world_turn
    from ...descriptions import deterministic_description, maybe_ai_description
    turn = get_world_turn()
    description = (
        maybe_ai_description(player, loc, entities, base)
        or deterministic_description(base, loc.id, entities, turn)
    )
    messages.append(description)

    if entities:
        messages.append(
            "You see: " + ", ".join(e["name"] for e in entities)
        )

    from ...world import get_location as _gl
    exits = ", ".join(_gl(e.to).name for e in loc.exits) if loc.exits else "none"
    messages.append(f"Exits: {exits}")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )