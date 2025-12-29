from __future__ import annotations

from typing import Dict
from pydantic import BaseModel
from typing import Literal


ItemType = Literal["consumable", "currency"]


class Item(BaseModel):
    item_id: str
    name: str
    type: ItemType
    heal: int | None = None


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
    ),
}