from __future__ import annotations

from ...types import Player, ActionResponse
from ...abilities import get_ability
from ...archetypes import pool_for, learnable, get_archetype
from ...db import upsert_player
from ..state_view import build_action_state


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def learn(player: Player, ability_name: str) -> ActionResponse:
    """Spend a skill point to learn an ability from your archetype's pool."""
    aid = _normalize(ability_name)
    ability = get_ability(aid)
    if not ability:
        return ActionResponse(ok=False, error="That's not an ability.")

    if aid in (player.abilities or []):
        return ActionResponse(ok=False, error=f"You already know {ability.name}.")

    pool = {pid: req for pid, req in pool_for(player)}
    if aid not in pool:
        arch = get_archetype(player.archetype)
        whose = f"the {arch.name}'s path" if arch else "your path"
        return ActionResponse(ok=False, error=f"{ability.name} isn't on {whose}.")

    req = pool[aid]
    if player.level < req:
        return ActionResponse(ok=False, error=f"{ability.name} unlocks at level {req} (you're {player.level}).")

    if player.skill_points <= 0:
        nxt = ", ".join(get_ability(a).name for a, _ in learnable(player)) or "—"
        return ActionResponse(
            ok=False,
            error=f"You have no skill points. Earn them by levelling up. (Available to learn: {nxt})",
        )

    player.skill_points -= 1
    player.abilities.append(aid)
    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[
            f"You learn {ability.name}! {ability.description}",
            f"Skill points left: {player.skill_points}.",
        ],
        state=build_action_state(player, scene_dirty=False),
    )
