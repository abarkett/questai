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
                "antidote": {"price": 8},
                "leather_armor": {"price": 15},
                "iron_sword": {"price": 20},
            },
        ),
        Entity(
            entity_id="warden",
            name="Town Warden",
            type="npc",
            role="quest_giver",
            quests=["rat_problem", "explore_cavern"],
        ),
        Entity(
            entity_id="wanderer",
            name="The Wanderer",
            type="npc",
            role="arc_giver",
        ),
    ],
    "temple": [
        Entity(
            entity_id="priest",
            name="Temple Priest",
            type="npc",
            role="healer",
        ),
    ],
    "tavern": [
        Entity(
            entity_id="scholar",
            name="Wandering Scholar",
            type="npc",
            role="quest_giver",
            quests=["gather_herbs", "arm_yourself"],
        ),
    ],
    "north_road": [
        Entity(
            entity_id="huntmaster",
            name="Huntmaster",
            type="npc",
            role="quest_giver",
            quests=["thin_the_pack"],
        ),
    ],
    "old_mill": [
        Entity(
            entity_id="bandit_1",
            name="Bandit",
            type="monster",
            hp=14,
            attack=4,
            xp_reward=10,
            loot={"coin": 8, "healing_herb": 1},
        ),
    ],
    "thornwood": [
        Entity(
            entity_id="giant_beetle_1",
            name="Giant Beetle",
            type="monster",
            hp=18,
            attack=4,
            xp_reward=12,
            loot={"coin": 4, "iron_ore": 1},
        ),
    ],
    "spider_hollow": [
        Entity(
            entity_id="venomous_spider_1",
            name="Venomous Spider",
            type="monster",
            hp=22,
            attack=5,
            xp_reward=16,
            loot={"coin": 6, "herb_bundle": 1},
            inflicts={"effect": "poison", "magnitude": 2, "turns": 3},
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
                "elixir_of_strength": {"price": 20},
            },
        ),
    ],
    "forest": [
        Entity(
            entity_id="wanderer",
            name="The Wanderer",
            type="npc",
            role="arc_giver",
        ),
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
            entity_id="wanderer",
            name="The Wanderer",
            type="npc",
            role="arc_giver",
        ),
        Entity(
            entity_id="cave_spider_1",
            name="Cave Spider",
            type="monster",
            hp=20,
            attack=5,
            xp_reward=18,
            loot={"coin": 6, "healing_herb": 2, "iron_sword": 1},
            inflicts={"effect": "poison", "magnitude": 2, "turns": 3},
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
            inflicts={"effect": "weaken", "magnitude": 2, "turns": 3},
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
            inflicts={"effect": "burn", "magnitude": 4, "turns": 3},
        ),
        Entity(
            entity_id="molten_wyrm_1",
            name="Molten Wyrm",
            type="monster",
            hp=100,
            attack=18,
            xp_reward=180,
            loot={"coin": 120, "ember_core": 2, "dragonscale_armor": 1, "wyrmfang_blade": 1},
            inflicts={"effect": "burn", "magnitude": 6, "turns": 4},
        ),
    ],
    "foothills": [
        Entity(
            entity_id="ranger",
            name="Mountain Ranger",
            type="npc",
            role="quest_giver",
            quests=["cull_harpies", "the_frozen_throne"],
        ),
        Entity(
            entity_id="rock_hound_1",
            name="Rock Hound",
            type="monster",
            hp=16,
            attack=4,
            xp_reward=12,
            loot={"coin": 5, "iron_ore": 1},
        ),
        Entity(
            entity_id="mountain_goat_1",
            name="Mountain Goat",
            type="monster",
            hp=10,
            attack=2,
            xp_reward=4,
            loot={"coin": 1, "pelt": 1},
        ),
    ],
    "mountain_pass": [
        Entity(
            entity_id="harpy_1",
            name="Harpy",
            type="monster",
            hp=28,
            attack=7,
            xp_reward=28,
            loot={"coin": 10, "pelt": 1},
        ),
        Entity(
            entity_id="yeti_1",
            name="Yeti",
            type="monster",
            hp=45,
            attack=10,
            xp_reward=50,
            loot={"coin": 14, "frost_crystal": 1},
        ),
    ],
    "frozen_cave": [
        Entity(
            entity_id="frost_wisp_1",
            name="Frost Wisp",
            type="monster",
            hp=30,
            attack=8,
            xp_reward=32,
            loot={"coin": 10, "frost_crystal": 1},
            inflicts={"effect": "weaken", "magnitude": 2, "turns": 3},
        ),
        Entity(
            entity_id="ice_troll_1",
            name="Ice Troll",
            type="monster",
            hp=90,
            attack=16,
            xp_reward=160,
            loot={"coin": 90, "frost_crystal": 3, "frostguard_plate": 1, "frost_brand": 1},
            inflicts={"effect": "weaken", "magnitude": 3, "turns": 3},
        ),
    ],
}


# Lookup: monster name -> the status effect it inflicts on retaliation.
MONSTER_INFLICTS: Dict[str, dict] = {
    e.name: e.inflicts
    for ents in WORLD_ENTITIES.values()
    for e in ents
    if e.type == "monster" and e.inflicts
}

# Most monsters are hostile; a few are passive and won't ambush you.
_PASSIVE_MONSTERS = {"Rat", "Giant Beetle", "Mountain Goat"}
for _ents in WORLD_ENTITIES.values():
    for _e in _ents:
        if _e.type == "monster" and _e.name not in _PASSIVE_MONSTERS:
            _e.aggressive = True

# Lookup: monster name -> whether it's aggressive (will ambush).
MONSTER_AGGRO: Dict[str, bool] = {
    e.name: e.aggressive
    for ents in WORLD_ENTITIES.values()
    for e in ents
    if e.type == "monster"
}