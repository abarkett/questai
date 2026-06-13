from __future__ import annotations

import time

from ...types import Player, ActionResponse
from ...abilities import get_ability
from ..state_view import build_action_state


def stats(player: Player) -> ActionResponse:
    from ...action_points import ap_enabled, ap_max, seconds_to_next_ap

    messages = [
        f"{player.name}",
        f"HP: {player.hp}/{player.max_hp}",
        f"Level: {player.level}",
        f"XP: {player.xp}",
    ]
    if ap_enabled():
        ap_line = f"AP: {player.action_points}/{ap_max()}"
        wait = seconds_to_next_ap(player)
        if wait:
            ap_line += f" (next in {wait}s)"
        messages.insert(2, ap_line)

    if player.companion:
        from ...companions import companion_level, ARCHETYPE_TITLE
        c = player.companion
        messages.append(
            f"Companion: {c.name}, {ARCHETYPE_TITLE.get(c.archetype, c.archetype)} "
            f"(Lv {companion_level(c)}, loyalty {c.loyalty})"
        )

    if player.status_effects:
        from ...status_effects import describe
        messages.append("Status effects:")
        messages.extend(describe(player))

    if player.abilities:
        now_ms = int(time.time() * 1000)
        messages.append("Abilities:")
        for aid in player.abilities:
            ability = get_ability(aid)
            if not ability:
                continue
            ready_at = player.ability_cooldowns.get(aid, 0)
            if now_ms < ready_at:
                cd = int((ready_at - now_ms) / 1000) + 1
                status = f"cooldown {cd}s"
            else:
                status = "ready"
            messages.append(f"  - {ability.name} ({status}): {ability.description}")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )