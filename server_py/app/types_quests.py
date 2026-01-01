from __future__ import annotations
from typing import Literal, Dict
from pydantic import BaseModel


QuestStatus = Literal["not_started", "active", "completed"]


class QuestObjective(BaseModel):
    type: Literal["kill", "collect"]
    target: str
    required: int
    progress: int = 0


class Quest(BaseModel):
    quest_id: str
    name: str
    description: str
    objectives: list[QuestObjective]
    rewards: Dict[str, int]          # item -> quantity
    status: QuestStatus = "not_started"