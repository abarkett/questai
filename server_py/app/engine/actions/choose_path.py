from __future__ import annotations

from ...types import Player, ActionResponse
from ...archetypes import ARCHETYPES, get_archetype
from ...db import upsert_player
from ..state_view import build_action_state


def choose_path(player: Player, archetype: str) -> ActionResponse:
    """Set the player's archetype. A one-time choice — once walked, a path can't
    be unwalked (your abilities grew from it)."""
    if player.archetype:
        cur = get_archetype(player.archetype)
        return ActionResponse(
            ok=False,
            error=f"You already walk the path of the {cur.name if cur else player.archetype}. There's no turning back.",
        )

    key = (archetype or "").strip().lower()
    arch = get_archetype(key)
    if not arch:
        options = ", ".join(f"{a.id} ({a.name})" for a in ARCHETYPES.values())
        return ActionResponse(ok=False, error=f"No such path. Choose one of: {options}.")

    player.archetype = arch.id
    upsert_player(player)
    messages = [
        f"You take up the path of the {arch.name}.",
        arch.description,
        arch.passive,
    ]
    if player.skill_points > 0:
        messages.append(f"You have {player.skill_points} skill point(s) — `learn` an ability of your path.")
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
