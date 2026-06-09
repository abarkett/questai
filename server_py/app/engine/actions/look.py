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

    # Dynamic prose authored by Miriel (no fallback — Miriel is required).
    from ...db import get_world_turn
    from ...descriptions import describe
    messages.append(describe(player, loc, entities, base, get_world_turn()))

    if entities:
        messages.append(
            "You see: " + ", ".join(e["name"] for e in entities)
        )

    # Echoes: what other players did here recently.
    from ...echoes import echo_lines
    echoes = echo_lines(player)
    if echoes:
        messages.append("Echoes: " + " ".join(echoes))

    # Notes left on the spot by other adventurers.
    from ...db import get_location_notes
    notes = get_location_notes(player.location)
    if notes:
        messages.append("Notes left here:")
        for n in notes:
            messages.append(f"  “{n['text']}” — {n['player_name']}")

    from ...world import get_location as _gl
    exits = ", ".join(_gl(e.to).name for e in loc.exits) if loc.exits else "none"
    messages.append(f"Exits: {exits}")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )