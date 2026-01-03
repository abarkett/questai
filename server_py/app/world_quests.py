from __future__ import annotations
from typing import Tuple
from .types_quests import Quest, QuestObjective
from .db import get_world_state
from .engine.entities import get_world_entities_at


QUEST_TEMPLATES = {
    "rat_problem": Quest(
        quest_id="rat_problem",
        name="A Rat Problem",
        description="The forest has been overrun by rats. Deal with them.",
        objectives=[
            QuestObjective(
                type="kill",
                target="Rat",
                required=2,
            )
        ],
        rewards={
            "coin": 5,
            "healing_herb": 1,
        },
        repeatable=True,
    )
}


def is_quest_available(quest_id: str) -> Tuple[bool, str]:
    """
    Check if a quest can be offered based on world state.
    Returns (is_available, reason_if_not_available).
    """
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

    # Default: quest is available
    return True, ""