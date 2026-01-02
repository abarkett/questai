from __future__ import annotations
from typing import Literal, Dict, Optional
from pydantic import BaseModel


QuestStatus = Literal["offered", "accepted", "completed", "turned_in", "archived"]


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
    status: QuestStatus = "offered"
    giver_npc_id: Optional[str] = None
    accepted_at: Optional[int] = None  # timestamp in ms
    completed_at: Optional[int] = None  # timestamp in ms
    turned_in_at: Optional[int] = None  # timestamp in ms