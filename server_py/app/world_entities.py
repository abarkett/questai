from __future__ import annotations

from typing import Dict, List
from .types_entities import Entity

# location_id -> list[Entity]
WORLD_ENTITIES: Dict[str, List[Entity]] = {
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
    ]
}