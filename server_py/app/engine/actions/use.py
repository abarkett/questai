from ...types import Player, ActionResponse
from ...items import ITEMS
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity, get_adjacent_scenes
from ...world import get_location
from ..state_view import build_action_state


def normalize_item_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def use(player: Player, item_name: str) -> ActionResponse:
    item_key = normalize_item_key(item_name)

    qty = player.inventory.get(item_key, 0)
    if qty <= 0:
        return ActionResponse(ok=False, error="You don't have that item.")

    item = ITEMS.get(item_key)
    if not item:
        return ActionResponse(ok=False, error="You can't use that item.")

    if item.type == "consumable" and item.heal:
        player.hp = min(player.max_hp, player.hp + item.heal)
        player.inventory[item_key] -= 1
        if player.inventory[item_key] <= 0:
            del player.inventory[item_key]

        upsert_player(player)

        return ActionResponse(
            ok=True,
            messages=[f"You use {item.name}. (+{item.heal} HP)"],
            state=build_action_state(player, scene_dirty=False),
        )

    return ActionResponse(ok=False, error="You can't use that item.")