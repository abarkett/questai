from ...types import Player, ActionResponse
from ...items import ITEMS
from ...db import upsert_player


def use(player: Player, item_name: str) -> ActionResponse:
    for item_id, qty in player.inventory.items():
        item = ITEMS.get(item_id)
        if item and item.name.lower() == item_name.lower():
            if qty <= 0:
                break

            if item.type == "consumable" and item.heal:
                player.hp = min(player.max_hp, player.hp + item.heal)
                player.inventory[item_id] -= 1
                if player.inventory[item_id] == 0:
                    del player.inventory[item_id]

                upsert_player(player)
                return ActionResponse(
                    ok=True,
                    messages=[f"You use {item.name}. (+{item.heal} HP)"],
                    state={"player": player.model_dump()},
                )

    return ActionResponse(ok=False, error="You don't have that item.")