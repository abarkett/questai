from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel
from typing import Literal


ItemType = Literal["consumable", "currency", "weapon", "armor", "material"]
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
    # Status-effect consumables
    cure: bool = False               # removes negative status effects when used
    effect: str | None = None        # status effect to apply when used
    effect_magnitude: int | None = None
    effect_turns: int | None = None


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
    # ----- Consumables -----
    "healing_potion": Item(
        item_id="healing_potion",
        name="Healing Potion",
        type="consumable",
        heal=8,
        value=10,
    ),
    "greater_healing_potion": Item(
        item_id="greater_healing_potion",
        name="Greater Healing Potion",
        type="consumable",
        heal=20,
        value=25,
    ),
    "antidote": Item(
        item_id="antidote",
        name="Antidote",
        type="consumable",
        cure=True,
        value=6,
    ),
    "elixir_of_strength": Item(
        item_id="elixir_of_strength",
        name="Elixir of Strength",
        type="consumable",
        effect="strength",
        effect_magnitude=3,
        effect_turns=5,
        value=15,
    ),
    # ----- Weapons (deep-dungeon tiers) -----
    "knight_blade": Item(
        item_id="knight_blade",
        name="Knight's Blade",
        type="weapon",
        slot="weapon",
        damage=8,
        value=60,
    ),
    "wyrmfang_blade": Item(
        item_id="wyrmfang_blade",
        name="Wyrmfang Blade",
        type="weapon",
        slot="weapon",
        damage=14,
        value=200,
    ),
    # ----- Armor (deep-dungeon tiers) -----
    "chainmail": Item(
        item_id="chainmail",
        name="Chainmail",
        type="armor",
        slot="armor",
        defense=6,
        value=70,
    ),
    "dragonscale_armor": Item(
        item_id="dragonscale_armor",
        name="Dragonscale Armor",
        type="armor",
        slot="armor",
        defense=9,
        value=250,
    ),
    # ----- Crafting materials -----
    "herb_bundle": Item(item_id="herb_bundle", name="Herb Bundle", type="material", value=2),
    "pelt": Item(item_id="pelt", name="Wolf Pelt", type="material", value=4),
    "iron_ore": Item(item_id="iron_ore", name="Iron Ore", type="material", value=5),
    "mythril_ore": Item(item_id="mythril_ore", name="Mythril Ore", type="material", value=12),
    "ember_core": Item(item_id="ember_core", name="Ember Core", type="material", value=20),
}


# Crafting recipes: output_id -> {"inputs": {material: qty}, "qty": output_count}
RECIPES: Dict[str, Dict[str, Any]] = {
    "healing_potion": {"inputs": {"herb_bundle": 3}, "qty": 1},
    "leather_armor": {"inputs": {"pelt": 3}, "qty": 1},
    "iron_sword": {"inputs": {"iron_ore": 3}, "qty": 1},
    "steel_armor": {"inputs": {"iron_ore": 5, "pelt": 2}, "qty": 1},
    "antidote": {"inputs": {"herb_bundle": 2}, "qty": 1},
    "elixir_of_strength": {"inputs": {"herb_bundle": 2, "iron_ore": 1}, "qty": 1},
    # Deep-dungeon recipes
    "greater_healing_potion": {"inputs": {"herb_bundle": 5}, "qty": 1},
    "knight_blade": {"inputs": {"mythril_ore": 4}, "qty": 1},
    "chainmail": {"inputs": {"mythril_ore": 3, "iron_ore": 3}, "qty": 1},
    "wyrmfang_blade": {"inputs": {"ember_core": 3, "mythril_ore": 5}, "qty": 1},
    "dragonscale_armor": {"inputs": {"ember_core": 4, "mythril_ore": 4}, "qty": 1},
}

# What each location yields when gathered.
LOCATION_RESOURCES: Dict[str, str] = {
    "forest": "herb_bundle",
    "riverside": "herb_bundle",
    "thornwood": "pelt",
    "deep_forest": "pelt",
    "cavern": "iron_ore",
    "underdeep": "mythril_ore",
    "magma_core": "ember_core",
}


def get_item(item_id: str) -> Item | None:
    return ITEMS.get(item_id)


def get_recipe(item_id: str) -> Dict[str, Any] | None:
    return RECIPES.get(item_id)