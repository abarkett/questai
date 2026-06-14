from __future__ import annotations

import uuid

from ...types import Player, ActionResponse
from ...db import upsert_player, get_player_by_name
from ...world import get_location
from ..entities import get_entities_at, get_adjacent_scenes, filter_current_player
from ..state_view import build_action_state


def create_player(name: str, archetype: str | None = None) -> ActionResponse:
    # Check if player with this name already exists
    existing_player = get_player_by_name(name)
    
    if existing_player:
        # Resume existing player
        player = existing_player
        loc = get_location(player.location)

        return ActionResponse(
            ok=True,
            messages=[f"Welcome back, {player.name}!", f"You are at {loc.name}."],
            state=build_action_state(player, scene_dirty=True),
        )
    
    # A valid archetype chosen up front sets the player's path; otherwise it's
    # left open for them to pick with `path` (the guidance nudges this).
    from ...archetypes import get_archetype
    chosen = get_archetype((archetype or "").strip().lower())

    player = Player(
        player_id=str(uuid.uuid4()),
        name=name,
        location="town_square",
        level=1,
        xp=0,
        hp=10,
        max_hp=10,
        visited_locations=["town_square"],
        archetype=chosen.id if chosen else None,
    )
    upsert_player(player)

    loc = get_location(player.location)

    messages = [f"Welcome, {player.name}.", f"You arrive at {loc.name}."]

    # New arrivals land in a world already in motion: lead with the season.
    from ...db import get_active_world_goals
    goals = get_active_world_goals()
    if goals:
        g = goals[0]
        messages.append(
            f"The town talks of one thing: {g['name']}. {g['description']} "
            f"({min(g['progress'], g['required'])}/{g['required']} so far — every blow counts.)"
        )

    # Surface the path choice — the one early decision that shapes how you fight.
    if chosen:
        messages.append(f"You walk the path of the {chosen.name}. {chosen.passive}")
    else:
        from ...archetypes import ARCHETYPES
        names = " / ".join(a.name for a in ARCHETYPES.values())
        messages.append(f"Choose how you'll fight: `path <{ ' | '.join(ARCHETYPES) }>` ({names}).")

    # Point a brand-new player at their first steps.
    messages.append("New here? Type `next` any time for what to do.")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=True),
    )

