from __future__ import annotations

from typing import Literal, Optional, Union, List
from pydantic import BaseModel, Field


LocationId = str
PlayerId = str


class Exit(BaseModel):
    to: LocationId
    label: str


class LocationView(BaseModel):
    id: str
    name: str
    description: str
    exits: List[Exit]


class Player(BaseModel):
    player_id: PlayerId
    name: str
    location: LocationId
    level: int
    xp: int
    hp: int
    max_hp: int
    inventory: dict[str, int] = {}

class AttackArgs(BaseModel):
    target: str


class AttackReq(BaseModel):
    action: Literal["attack"]
    args: AttackArgs

class InventoryReq(BaseModel):
    action: Literal["inventory"]




# ----- Action Requests (discriminated union) -----

class CreatePlayerArgs(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class CreatePlayerReq(BaseModel):
    action: Literal["create_player"]
    args: CreatePlayerArgs


class LookReq(BaseModel):
    action: Literal["look"]
    args: Optional[dict] = None


class MoveArgs(BaseModel):
    to: str = Field(min_length=1, max_length=64)

class StatsReq(BaseModel):
    action: Literal["stats"]


class MoveReq(BaseModel):
    action: Literal["move"]
    args: MoveArgs




ActionRequest = Union[
    CreatePlayerReq,
    LookReq,
    MoveReq,
    AttackReq,
    StatsReq
]


class ActionResponse(BaseModel):
    ok: bool
    messages: List[str] = Field(default_factory=list)
    state: Optional[dict] = None
    error: Optional[str] = None
