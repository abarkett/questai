from ...types import Player, ActionResponse
from ...items import ITEMS
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity, get_adjacent_scenes
from ...world import get_location


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

        loc = get_location(player.location)
        entities = get_entities_at(player.location)

        return ActionResponse(
            ok=True,
            messages=[f"You use {item.name}. (+{item.heal} HP)"],
            state={
                "player": player.model_dump(),
                "location": {
                    "id": loc.id,
                    "name": loc.name,
                    "description": loc.description,
                    "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
                },
                "entities": [serialize_entity(e) for e in entities],
                "adjacent_scenes": get_adjacent_scenes(loc.id),
            },
        )

    return ActionResponse(ok=False, error="You can't use that item.")