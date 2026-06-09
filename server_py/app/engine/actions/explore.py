"""
Explore: open a frontier into a brand-new region.

At a frontier location, exploring mints the region behind it (procedurally
generated, AI-flavored when Miriel is configured) and opens a permanent exit
for every player. The discoverer's name is written into the new region's
canon forever.
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import get_region_by_origin, upsert_player
from ...regiongen import frontier_at, mint_region_from
from ..state_view import build_action_state


def explore(player: Player) -> ActionResponse:
    frontier = frontier_at(player.location)
    if not frontier:
        return ActionResponse(
            ok=False,
            error="You search, but every path from here is already known.",
        )

    existing = get_region_by_origin(player.location)
    if existing:
        return ActionResponse(
            ok=True,
            messages=[
                f"The way to the {existing['name']} already stands open"
                + (f" — first charted by {existing['discovered_by']}." if existing.get("discovered_by") else "."),
            ],
            state=build_action_state(player, scene_dirty=False),
        )

    region = mint_region_from(player.location, player)
    if not region:
        return ActionResponse(ok=False, error="The way is shut.")

    upsert_player(player)
    first = region.get("discovered_by") == player.name
    messages = [frontier["flavor"].capitalize() + "."]
    if first:
        messages.append(
            f"You press through — and chart what no one has seen: the {region['name']}!"
        )
        messages.append("Your name enters the region's history.")
    else:
        messages.append(f"The way opens into the {region['name']}.")
    messages.append("A new exit appears: unexplored path.")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=True),
    )
