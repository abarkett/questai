"""
Rest: the free floor under the survival economy.

Wounded and broke is the classic early-game corner — every other recovery
path needs coins, materials, levels, or luck. Resting trades the one currency
every player always has (action points and time) for steady recovery, anywhere
it's safe enough to close your eyes.
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import upsert_player
from ...ambush import has_aggressive
from ..state_view import build_action_state

REST_HP = 4

_FLAVOR = [
    "You find a quiet spot and let your breathing slow.",
    "You sit a while, working the ache out of your limbs.",
    "You close your eyes and let the world hold still.",
]


def rest(player: Player) -> ActionResponse:
    if player.hp >= player.max_hp:
        return ActionResponse(ok=False, error="You're already rested and whole.")

    if has_aggressive(player.location):
        return ActionResponse(
            ok=False,
            error="You can't rest with hostile eyes on you. Clear them out or move on.",
        )

    healed = min(REST_HP, player.max_hp - player.hp)
    player.hp += healed

    flavor = _FLAVOR[player.hp % len(_FLAVOR)]
    messages = [f"{flavor} (+{healed} HP, {player.hp}/{player.max_hp})"]
    if player.hp < player.max_hp:
        messages.append("You could rest longer.")

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
