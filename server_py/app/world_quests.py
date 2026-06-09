from __future__ import annotations
from typing import Tuple, Optional, Dict, List
from .types_quests import Quest, QuestObjective, QuestStage
from .db import get_world_state
from .engine.entities import get_world_entities_at
from .types import Player
from .world_entities import WORLD_ENTITIES


QUEST_TEMPLATES = {
    "rat_problem": Quest(
        quest_id="rat_problem",
        name="A Rat Problem",
        description="The forest has been overrun by rats. Deal with them.",
        objectives=[
            QuestObjective(type="kill", target="Rat", required=2),
        ],
        rewards={"coin": 5, "healing_herb": 1},
        repeatable=True,
    ),
    # ----- Collect -----
    "gather_herbs": Quest(
        quest_id="gather_herbs",
        name="Healer's Request",
        description="The temple needs herbs. Gather 3 herb bundles from the wilds.",
        objectives=[
            QuestObjective(type="collect", target="herb_bundle", required=3),
        ],
        rewards={"coin": 10, "healing_potion": 1},
        repeatable=True,
    ),
    "arm_yourself": Quest(
        quest_id="arm_yourself",
        name="Arm Yourself",
        description="A real adventurer needs steel. Acquire an iron sword (loot or craft one).",
        objectives=[
            QuestObjective(type="collect", target="iron_sword", required=1),
        ],
        rewards={"coin": 25},
    ),
    # ----- Visit -----
    "explore_cavern": Quest(
        quest_id="explore_cavern",
        name="Into the Deep",
        description="Scout the Echoing Cavern and report back.",
        objectives=[
            QuestObjective(type="visit", target="cavern", required=1),
        ],
        rewards={"coin": 20, "healing_herb": 2},
    ),
    # ----- Multi-objective -----
    "thin_the_pack": Quest(
        quest_id="thin_the_pack",
        name="Thin the Pack",
        description="The wolves grow bold. Cull 2 wolves and bring back 3 pelts.",
        objectives=[
            QuestObjective(type="kill", target="Wolf", required=2),
            QuestObjective(type="collect", target="pelt", required=3),
        ],
        rewards={"coin": 30, "steel_armor": 1},
        repeatable=True,
    ),
    # ----- Mountains -----
    "cull_harpies": Quest(
        quest_id="cull_harpies",
        name="Skies of Talon",
        description="Harpies harry the mountain pass. Bring one down.",
        objectives=[
            QuestObjective(type="kill", target="Harpy", required=1),
        ],
        rewards={"coin": 20, "frost_crystal": 1},
        repeatable=True,
    ),
    # ----- Multi-stage (no per-stage reward) -----
    "the_frozen_throne": Quest(
        quest_id="the_frozen_throne",
        name="The Frozen Throne",
        description="An ancient cold stirs in the peaks. See it ended.",
        stages=[
            QuestStage(
                description="Climb to the Frozen Cave.",
                objectives=[QuestObjective(type="visit", target="frozen_cave", required=1)],
            ),
            QuestStage(
                description="Gather 3 frost crystals from the heights.",
                objectives=[QuestObjective(type="collect", target="frost_crystal", required=3)],
            ),
            QuestStage(
                description="Slay the Ice Troll that guards the glacier.",
                objectives=[QuestObjective(type="kill", target="Ice Troll", required=1)],
            ),
        ],
        rewards={"coin": 120, "frostguard_plate": 1},
    ),
}


def is_quest_available(quest_id: str, player: Optional[Player] = None) -> Tuple[bool, str]:
    """
    Check if a quest can be offered based on world state.
    Now supports both template and AI-generated quests.

    Args:
        quest_id: Quest identifier
        player: Optional player context for AI-generated quests

    Returns:
        (is_available, reason_if_not_available)
    """
    # Check template-specific availability
    if quest_id == "rat_problem":
        # Check if there are rats in the forest
        entities = get_world_entities_at("forest")
        rat_count = sum(1 for e in entities if e.type == "monster" and "rat" in e.entity_id.lower())

        if rat_count == 0:
            # Check if forest was recently cleared
            is_cleared = get_world_state("forest_infested") == "false"
            if is_cleared or get_world_state("forest_rat_turns") == "0":
                return False, "The forest is much safer now. The rats have been dealt with, at least for the time being."
            else:
                return False, "The forest is clear at the moment. Perhaps check back later."

        return True, ""

    # AI-generated quests (not in templates) are always "available" to generate
    # Prerequisites are checked via Miriel context during generation
    # Templates take priority, so if we reach here, it's an AI quest
    return True, ""


def _snapshot_quest_targets() -> Tuple[List[str], List[str]]:
    """
    Snapshot the monsters and obtainable items defined in the world *at import
    time*, so generated quests only ever reference targets that actually exist
    (and so runtime mutation of WORLD_ENTITIES can't shrink the catalog).
    """
    monsters: set[str] = set()
    items: set[str] = set()
    for entity_list in WORLD_ENTITIES.values():
        for e in entity_list:
            if getattr(e, "type", None) == "monster":
                monsters.add(e.name)
                for item in (getattr(e, "loot", None) or {}).keys():
                    items.add(item)
            elif getattr(e, "role", None) == "shop":
                for item in (getattr(e, "inventory", None) or {}).keys():
                    items.add(item)
    return sorted(monsters), sorted(items)


_VALID_MONSTERS, _VALID_ITEMS = _snapshot_quest_targets()


def get_valid_quest_targets() -> Dict[str, List[str]]:
    """Monsters/items that generated quests may reference so they stay completable."""
    return {"monsters": list(_VALID_MONSTERS), "items": list(_VALID_ITEMS)}