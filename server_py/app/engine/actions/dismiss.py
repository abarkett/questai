from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import upsert_player
from ...miriel_companion import companion_line
from ..state_view import build_action_state


def dismiss(player: Player) -> ActionResponse:
    companion = player.companion
    if not companion:
        return ActionResponse(ok=False, error="No one travels with you.")

    line = companion_line(
        player, companion, "farewell",
        fallback="Fair roads, friend. Call on me again if you've need.",
    )

    player.companion = None
    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[
            f"{companion.name} clasps your arm and parts ways.",
            f'{companion.name}: "{line}"',
        ],
        state=build_action_state(player, scene_dirty=False),
    )
