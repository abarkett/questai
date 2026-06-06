from __future__ import annotations

import time

from ...types import Player, ActionResponse
from ...abilities import get_ability
from ...db import upsert_player
from ..state_view import build_action_state
from .attack import attack


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def use_ability(player: Player, ability_name: str, target: str | None = None) -> ActionResponse:
    ability_id = _normalize(ability_name)
    ability = get_ability(ability_id)
    if not ability:
        return ActionResponse(ok=False, error="That's not an ability.")

    if ability_id not in player.abilities:
        return ActionResponse(
            ok=False,
            error=f"You haven't learned {ability.name} yet (unlocks at level {ability.learn_level}).",
        )

    now_ms = int(time.time() * 1000)
    ready_at = player.ability_cooldowns.get(ability_id, 0)
    if now_ms < ready_at:
        remaining = int((ready_at - now_ms) / 1000) + 1
        return ActionResponse(ok=False, error=f"{ability.name} is on cooldown ({remaining}s left).")

    if ability.kind == "attack":
        if not target:
            return ActionResponse(ok=False, error=f"Use {ability.name} on what?")
        # attack() applies the multiplier, crit/variance, and starts the cooldown.
        return attack(player, target, ability=ability_id)

    if ability.kind == "heal":
        amount = int(player.max_hp * (ability.heal_frac or 0))
        before = player.hp
        player.hp = min(player.max_hp, player.hp + amount)
        healed = player.hp - before
        player.ability_cooldowns[ability_id] = now_ms + ability.cooldown_s * 1000
        upsert_player(player)
        return ActionResponse(
            ok=True,
            messages=[f"{ability.name}! You recover {healed} HP."],
            state=build_action_state(player, scene_dirty=False),
        )

    return ActionResponse(ok=False, error="You can't use that ability right now.")
