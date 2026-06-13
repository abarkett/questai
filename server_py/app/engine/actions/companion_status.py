from __future__ import annotations

from ...types import Player, ActionResponse
from ...companions import (
    MAX_LOYALTY,
    ARCHETYPE_TITLE,
    ARCHETYPE_BLURB,
    companion_level,
)
from ..state_view import build_action_state


def companion_status(player: Player) -> ActionResponse:
    c = player.companion
    if not c:
        messages = [
            "No one travels with you.",
            "Find someone out in the world and `recruit` them to fight at your side.",
        ]
    else:
        messages = [
            f"{c.name} — {ARCHETYPE_TITLE.get(c.archetype, c.archetype)} "
            f"(Level {companion_level(c)})",
            ARCHETYPE_BLURB.get(c.archetype, ""),
            f"Loyalty: {c.loyalty}/{MAX_LOYALTY}   Battles won at your side: {c.battles}",
        ]

    return ActionResponse(
        ok=True,
        messages=[m for m in messages if m],
        state=build_action_state(player, scene_dirty=False),
    )
