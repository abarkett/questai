from __future__ import annotations

from ...types import Player, ActionResponse
from ..entities import find_entity, remove_entity
from ...db import upsert_player


def attack(player: Player, target_name: str) -> ActionResponse:
    entity = find_entity(player.location, target_name)

    if not entity:
        return ActionResponse(ok=False, error=f"No '{target_name}' here to attack.")

    if entity.type != "monster":
        return ActionResponse(ok=False, error=f"You can't attack the {entity.name}.")

    messages: list[str] = []

    # ---- Player attacks ----
    player_damage = 3
    entity.hp -= player_damage
    messages.append(f"You attack the {entity.name} for {player_damage} damage.")

    # ---- Monster defeated ----
    if entity.hp <= 0:
        remove_entity(player.location, entity)

        player.xp += entity.xp_reward or 0
        messages.append(f"The {entity.name} is defeated.")
        messages.append(f"You gain {entity.xp_reward} XP.")

        if entity.loot:
            for item_id, qty in entity.loot.items():
                player.inventory[item_id] = player.inventory.get(item_id, 0) + qty
                messages.append(f"You loot {qty} {item_id}.")

        upsert_player(player)
        return ActionResponse(
            ok=True,
            messages=messages,
            state={"player": player.model_dump()},
        )

    # ---- Monster retaliates ----
    retaliation = entity.attack or 0
    player.hp -= retaliation
    messages.append(f"The {entity.name} hits you for {retaliation} damage.")

    # ---- Player death ----
    if player.hp <= 0:
        lost_coins = player.inventory.get("coin", 0) // 2
        if lost_coins > 0:
            player.inventory["coin"] -= lost_coins
            messages.append(f"You drop {lost_coins} coins.")

        player.hp = player.max_hp
        player.location = "town_square"
        messages.append("You collapse and wake up back in the Town Square.")

    upsert_player(player)

    return ActionResponse(
        ok=True,
        messages=messages,
        state={"player": player.model_dump()},
    )