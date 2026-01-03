from __future__ import annotations

from ...types import Player, ActionResponse
from ..entities import get_entities_at, serialize_entity
from ...world import get_location
from ...db import upsert_player
from ..state_view import build_action_state


def buy(player: Player, item_name: str) -> ActionResponse:
    # Find a shop NPC at this location
    shop = None
    for e in get_entities_at(player.location):
        if e["type"] == "npc" and e.get("role") == "shop":
            shop = e
            break

    if not shop:
        return ActionResponse(ok=False, error="There is no shop here.")

    if not shop.get("inventory") or item_name not in shop["inventory"]:
        return ActionResponse(ok=False, error="That item is not for sale.")

    price = shop["inventory"][item_name]["price"]

    coins = player.inventory.get("coin", 0)
    if coins < price:
        return ActionResponse(ok=False, error="You can’t afford that.")

    # Perform transaction
    player.inventory["coin"] = coins - price
    player.inventory[item_name] = player.inventory.get(item_name, 0) + 1

    upsert_player(player)

    return ActionResponse(
        ok=True,
        messages=[f"You buy a {item_name} for {price} coins."],
        state=build_action_state(player, scene_dirty=False),
    )