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
    wounded = "wounded" in player.status_effects
    if player.hp >= player.max_hp and not wounded:
        return ActionResponse(ok=False, error="You're already rested and whole.")

    if has_aggressive(player.location):
        return ActionResponse(
            ok=False,
            error="You can't rest with hostile eyes on you. Clear them out or move on.",
        )

    healed = min(REST_HP, player.max_hp - player.hp)
    player.hp += healed

    flavor = _FLAVOR[player.hp % len(_FLAVOR)]
    messages = []
    if healed > 0:
        messages.append(f"{flavor} (+{healed} HP, {player.hp}/{player.max_hp})")
    # Resting is also how you shake off the wound a defeat leaves behind.
    if wounded:
        del player.status_effects["wounded"]
        messages.append("You bind your hurts; the wound's ache fades.")
    elif not messages:
        messages.append(flavor)
    if player.hp < player.max_hp:
        messages.append("You could rest longer.")

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
