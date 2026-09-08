from __future__ import annotations

import time

from ...types import Player, ActionResponse
from ...abilities import get_ability
from ...archetypes import cooldown_ms
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
        from ...archetypes import pool_for
        on_path = ability_id in {pid for pid, _ in pool_for(player)}
        hint = f"`learn {ability_id}` to train it." if on_path else "It isn't on your path."
        return ActionResponse(
            ok=False,
            error=f"You haven't learned {ability.name}. {hint}",
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
        player.ability_cooldowns[ability_id] = now_ms + cooldown_ms(player, ability.cooldown_s)
        upsert_player(player)
        return ActionResponse(
            ok=True,
            messages=[f"{ability.name}! You recover {healed} HP."],
            state=build_action_state(player, scene_dirty=False),
        )

    if ability.kind == "buff":
        from ...status_effects import apply_effect
        msg = apply_effect(
            player, ability.buff_effect or "", ability.buff_magnitude or 0, ability.buff_turns or 0
        )
        player.ability_cooldowns[ability_id] = now_ms + cooldown_ms(player, ability.cooldown_s)
        upsert_player(player)
        return ActionResponse(
            ok=True,
            messages=[f"{ability.name}! {msg}".strip()],
            state=build_action_state(player, scene_dirty=False),
        )

    if ability.kind == "dot":
        if not target:
            return ActionResponse(ok=False, error=f"Use {ability.name} on what?")
        return _resolve_dot(player, target, ability, now_ms)

    if ability.kind == "aoe":
        return _resolve_aoe(player, ability, now_ms)

    return ActionResponse(ok=False, error="You can't use that ability right now.")


def _resolve_dot(player: Player, target: str, ability, now_ms: int) -> ActionResponse:
    from ..entities import find_entity
    from ...dots import apply_bleed

    entity = find_entity(player.location, target)
    if not entity or entity["type"] != "monster":
        return ActionResponse(ok=False, error="There's nothing like that to wound here.")

    apply_bleed(entity["id"], ability.dot_damage or 0, ability.dot_turns or 0)
    player.ability_cooldowns[ability.ability_id] = now_ms + cooldown_ms(player, ability.cooldown_s)
    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"{ability.name}! The {entity['name']} starts to bleed "
                  f"({ability.dot_damage} per strike for {ability.dot_turns})."],
        state=build_action_state(player, scene_dirty=False),
    )


def _resolve_aoe(player: Player, ability, now_ms: int) -> ActionResponse:
    from ...db import get_monsters_at, damage_monster
    from ...combat import roll_damage
    from ...progression import total_attack_damage, apply_xp
    from ...status_effects import damage_modifier
    from ...bestiary import discover
    from ...bosses import clear_boss_state
    from ...dots import clear_bleed
    from ..entities import record_monster_death
    from .attack import update_quest_progress

    monsters = get_monsters_at(player.location)
    if not monsters:
        return ActionResponse(ok=False, error=f"There are no enemies here to {ability.name.lower()}.")

    base = int((total_attack_damage(player) + damage_modifier(player)) * (ability.multiplier or 1.0))
    player.ability_cooldowns[ability.ability_id] = now_ms + cooldown_ms(player, ability.cooldown_s)

    messages = [f"{ability.name}! You strike every enemy here."]
    for m in monsters:
        discover(player, m["name"])
        dmg, _crit = roll_damage(base)
        res = damage_monster(m["instance_id"], dmg)
        if res is None:
            continue
        if res["killed"]:
            clear_boss_state(m["instance_id"], res["name"])
            clear_bleed(m["instance_id"])
            record_monster_death(m["instance_id"])
            messages.append(f"You strike the {res['name']} for {dmg} — defeated!")
            for item, qty in (res.get("loot") or {}).items():
                player.inventory[item] = player.inventory.get(item, 0) + qty
                messages.append(f"You found: {qty}x {item}")
            messages.extend(apply_xp(player, res.get("xp_reward") or 0))
            messages.extend(update_quest_progress(player, res["name"]))
        else:
            messages.append(f"You strike the {res['name']} for {dmg} damage.")

    upsert_player(player)
    return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=True))
