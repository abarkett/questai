from __future__ import annotations

from typing import Dict, List
from .types_entities import Entity

# location_id -> list[Entity]
WORLD_ENTITIES: Dict[str, List[Entity]] = {
    "town_square": [
        Entity(
            entity_id="merchant",
            name="Old Merchant",
            type="npc",
            role="shop",
            inventory={
                "healing_herb": {"price": 5},
                "torch": {"price": 2},
                "leather_armor": {"price": 15},
                "iron_sword": {"price": 20},
            },
        ),
        Entity(
            entity_id="warden",
            name="Town Warden",
            type="npc",
            role="quest_giver",
            quests=["rat_problem"],
        ),
    ],
    "market": [
        Entity(
            entity_id="blacksmith",
            name="Blacksmith",
            type="npc",
            role="shop",
            inventory={
                "steel_armor": {"price": 40},
                "chainmail": {"price": 70},
                "knight_blade": {"price": 60},
                "greater_healing_potion": {"price": 25},
            },
        ),
    ],
    "forest": [
        Entity(
            entity_id="rat_1",
            name="Rat",
            type="monster",
            hp=5,
            attack=2,
            xp_reward=2,
            loot={"coin": 1, "healing_herb": 1},
        ),
        Entity(
            entity_id="rat_2",
            name="Rat",
            type="monster",
            hp=5,
            attack=2,
            xp_reward=2,
            loot={"coin": 1, "healing_herb": 1},
        ),
    ],
    "deep_forest": [
        Entity(
            entity_id="goblin_1",
            name="Goblin",
            type="monster",
            hp=12,
            attack=3,
            xp_reward=8,
            loot={"coin": 3, "healing_herb": 1, "rusty_dagger": 1},
        ),
        Entity(
            entity_id="wolf_1",
            name="Wolf",
            type="monster",
            hp=16,
            attack=4,
            xp_reward=12,
            loot={"coin": 4, "leather_armor": 1},
        ),
    ],
    "cavern": [
        Entity(
            entity_id="cave_spider_1",
            name="Cave Spider",
            type="monster",
            hp=20,
            attack=5,
            xp_reward=18,
            loot={"coin": 6, "healing_herb": 2, "iron_sword": 1},
        ),
        Entity(
            entity_id="cave_troll_1",
            name="Cave Troll",
            type="monster",
            hp=40,
            attack=8,
            xp_reward=50,
            loot={"coin": 25, "healing_herb": 3, "steel_armor": 1},
        ),
    ],
    "underdeep": [
        Entity(
            entity_id="shadow_wisp_1",
            name="Shadow Wisp",
            type="monster",
            hp=30,
            attack=7,
            xp_reward=30,
            loot={"coin": 10, "mythril_ore": 1},
        ),
        Entity(
            entity_id="bone_knight_1",
            name="Bone Knight",
            type="monster",
            hp=55,
            attack=10,
            xp_reward=65,
            loot={"coin": 20, "mythril_ore": 2, "knight_blade": 1},
        ),
    ],
    "magma_core": [
        Entity(
            entity_id="magma_hound_1",
            name="Magma Hound",
            type="monster",
            hp=50,
            attack=12,
            xp_reward=70,
            loot={"coin": 18, "ember_core": 1},
        ),
        Entity(
            entity_id="molten_wyrm_1",
            name="Molten Wyrm",
            type="monster",
            hp=100,
            attack=18,
            xp_reward=180,
            loot={"coin": 120, "ember_core": 2, "dragonscale_armor": 1, "wyrmfang_blade": 1},
        ),
    ],
}