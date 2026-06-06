from __future__ import annotations

from ...types import Player, ActionResponse
from ...items import get_item
from ...db import upsert_player
from ..entities import get_entities_at
from ..state_view import build_action_state


def normalize_item_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _shop_at(location_id: str):
    for e in get_entities_at(location_id):
        if e["type"] == "npc" and e.get("role") == "shop":
            return e
    return None


def sell(player: Player, item_name: str) -> ActionResponse:
    key = normalize_item_key(item_name)

    if _shop_at(player.location) is None:
        return ActionResponse(ok=False, error="There is no shop here to sell to.")

    if player.inventory.get(key, 0) <= 0:
        return ActionResponse(ok=False, error="You don't have that to sell.")

    item = get_item(key)
    if not item or item.type == "currency" or not item.value:
        return ActionResponse(ok=False, error="The shopkeeper won't buy that.")

    price = item.value
    player.inventory[key] -= 1
    if player.inventory[key] <= 0:
        del player.inventory[key]
    player.inventory["coin"] = player.inventory.get("coin", 0) + price

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"You sell {item.name} for {price} coins."],
        state=build_action_state(player, scene_dirty=False),
    )
