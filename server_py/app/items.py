from __future__ import annotations

from typing import Dict
from pydantic import BaseModel
from typing import Literal


ItemType = Literal["consumable", "currency", "weapon", "armor"]
EquipSlot = Literal["weapon", "armor"]


class Item(BaseModel):
    item_id: str
    name: str
    type: ItemType
    heal: int | None = None
    # Equippable gear
    slot: EquipSlot | None = None    # which equipment slot this fills
    damage: int | None = None        # weapon: bonus to attack damage
    defense: int | None = None       # armor: flat reduction to damage taken
    value: int | None = None         # base coin value (economy slice)


ITEMS: Dict[str, Item] = {
    "coin": Item(
        item_id="coin",
        name="Coin",
        type="currency",
    ),
    "healing_herb": Item(
        item_id="healing_herb",
        name="Healing Herb",
        type="consumable",
        heal=3,
        value=3,
    ),
    # ----- Weapons -----
    "rusty_dagger": Item(
        item_id="rusty_dagger",
        name="Rusty Dagger",
        type="weapon",
        slot="weapon",
        damage=2,
        value=5,
    ),
    "iron_sword": Item(
        item_id="iron_sword",
        name="Iron Sword",
        type="weapon",
        slot="weapon",
        damage=5,
        value=20,
    ),
    # ----- Armor -----
    "leather_armor": Item(
        item_id="leather_armor",
        name="Leather Armor",
        type="armor",
        slot="armor",
        defense=2,
        value=15,
    ),
    "steel_armor": Item(
        item_id="steel_armor",
        name="Steel Armor",
        type="armor",
        slot="armor",
        defense=4,
        value=40,
    ),
}


def get_item(item_id: str) -> Item | None:
    return ITEMS.get(item_id)