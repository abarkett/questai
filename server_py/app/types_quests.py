from __future__ import annotations
from typing import Literal, Dict, Optional
from pydantic import BaseModel


QuestStatus = Literal["offered", "accepted", "completed", "turned_in", "archived"]


class QuestObjective(BaseModel):
    # kill: defeat N of a monster; collect: possess N of an item;
    # visit: reach a location (target is a location id), required is 1.
    type: Literal["kill", "collect", "visit"]
    target: str
    required: int
    progress: int = 0


class QuestStage(BaseModel):
    """One stage of a multi-stage quest; only the current stage is active."""
    description: str
    objectives: list[QuestObjective]


class Quest(BaseModel):
    quest_id: str
    name: str
    description: str
    objectives: list[QuestObjective] = []   # single-stage quests
    stages: list[QuestStage] = []           # multi-stage quests (overrides objectives)
    current_stage: int = 0
    rewards: Dict[str, int]          # item -> quantity (granted on final completion)
    repeatable: bool = False         # Can be taken again after completion
    status: QuestStatus = "offered"
    giver_npc_id: Optional[str] = None
    accepted_at: Optional[int] = None  # timestamp in ms
    completed_at: Optional[int] = None  # timestamp in ms
    turned_in_at: Optional[int] = None  # timestamp in ms