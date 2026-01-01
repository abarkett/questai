from __future__ import annotations
from .types_quests import Quest, QuestObjective


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
    )
}