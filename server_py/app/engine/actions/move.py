from __future__ import annotations

from ...types import Player, ActionResponse
from ...world import get_location
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity, get_adjacent_scenes, filter_current_player
from ..state_view import build_action_state


def move(player: Player, to_label_or_id: str) -> ActionResponse:
    from_loc = get_location(player.location)
    needle = to_label_or_id.strip().lower()
    needle_id = needle.replace(" ", "_")

    exit_match = None
    for e in from_loc.exits:
        dest = get_location(e.to)
        if (e.label.lower() == needle
                or e.to.lower() == needle
                or e.to.lower() == needle_id
                or dest.name.lower() == needle):
            exit_match = e
            break

    if not exit_match:
        exits = ", ".join(get_location(e.to).name for e in from_loc.exits) if from_loc.exits else "none"
        return ActionResponse(
            ok=False,
            error=f'You can\'t go to "{to_label_or_id}". You can go to: {exits}'
        )

    # A road held by an incursion is closed until its intruders are slain.
    try:
        from ...incidents import exit_blocked_any
        block = exit_blocked_any(player.location, exit_match.to)
    except Exception as e:
        print(f"[INCIDENTS] block check failed: {e}")
        block = None
    if block:
        return ActionResponse(
            ok=False,
            error=(f"{block['title']} — the {block['data']['creature_name']}s hold the way to "
                   f"{get_location(exit_match.to).name}. Slay them all to open it (`fight {block['data']['creature_name']}`)."),
        )

    # Move player
    player.location = exit_match.to
    from ..visited import mark_visited
    mark_visited(player)
    upsert_player(player)

    to_loc = get_location(player.location)

    # Phase 8: Track monster survival for world evolution
    from ...world_rules import track_monster_survival
    track_monster_survival(player.location)

    # Dynamic, Miriel-authored arrival description (warmed in advance by the
    # neighbor prefetch, so this is usually a cache hit). No fallback.
    from ..state_view import effective_description
    from ...descriptions import describe
    from ...db import get_world_turn
    entities = filter_current_player(get_entities_at(player.location), player.player_id)
    arrival = describe(player, to_loc, entities, effective_description(to_loc), get_world_turn())

    # The road itself rolls dice: caches, shrines, travelers, ambushes, omens.
    from ...encounters import maybe_travel_encounter
    encounter_msgs = maybe_travel_encounter(player)
    if encounter_msgs:
        upsert_player(player)

    return ActionResponse(
        ok=True,
        messages=[
            f"You travel to {to_loc.name}.",
            arrival,
            *encounter_msgs,
        ],
        state=build_action_state(player, scene_dirty=True),
    )