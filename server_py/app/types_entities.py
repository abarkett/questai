from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


EntityType = Literal["monster", "item", "npc", "player"]


class Entity(BaseModel):
    entity_id: str
    name: str
    type: EntityType

    # combat-relevant (monsters only)
    hp: int | None = None
    attack: int | None = None
    xp_reward: int | None = None
    loot: dict[str, int] | None = None

    # npc-relevant
    role: str | None = None          # e.g. "shop"
    inventory: dict[str, dict] | None = None
    quests: list[str] | None = None