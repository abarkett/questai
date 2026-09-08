"""
Dig: claim the buried cache a torn map marks.

The loot half of the treasure-map loop (see app/loot.py): a map drop names a
place, the journey builds the anticipation, and the spade pays it off.
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import upsert_player
from ...content import get_location_or_none
from ...loot import dig_payout
from ..state_view import build_action_state


def dig(player: Player) -> ActionResponse:
    if not player.treasure_target or player.inventory.get("torn_map", 0) < 1:
        return ActionResponse(ok=False, error="You have no map worth digging by.")

    if player.location != player.treasure_target:
        target = get_location_or_none(player.treasure_target)
        name = target.name if target else player.treasure_target
        return ActionResponse(
            ok=False,
            error=f"You check the torn map: it marks a spot at {name}, not here.",
        )

    messages = dig_payout(player)
    player.inventory["torn_map"] -= 1
    if player.inventory["torn_map"] <= 0:
        del player.inventory["torn_map"]
    player.treasure_target = None

    from ...echoes import record_deed
    record_deed(player, player.location,
                f"{player.name} dug up a buried cache here", kind="treasure")

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
