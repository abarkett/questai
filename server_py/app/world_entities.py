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
            loot={"coin": 3, "healing_herb": 1},
        ),
        Entity(
            entity_id="wolf_1",
            name="Wolf",
            type="monster",
            hp=16,
            attack=4,
            xp_reward=12,
            loot={"coin": 4},
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
            loot={"coin": 6, "healing_herb": 2},
        ),
        Entity(
            entity_id="cave_troll_1",
            name="Cave Troll",
            type="monster",
            hp=40,
            attack=8,
            xp_reward=50,
            loot={"coin": 25, "healing_herb": 3},
        ),
    ],
}