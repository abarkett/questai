from __future__ import annotations

from ...types import Player, ActionResponse
from ..state_view import build_action_state


def stats(player: Player) -> ActionResponse:
    return ActionResponse(
        ok=True,
        messages=[
            f"{player.name}",
            f"HP: {player.hp}/{player.max_hp}",
            f"Level: {player.level}",
            f"XP: {player.xp}",
        ],
        state=build_action_state(player, scene_dirty=False),
    )