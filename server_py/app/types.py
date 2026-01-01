from __future__ import annotations

from typing import Literal, Optional, Union, List
from pydantic import BaseModel, Field
from .types_quests import Quest


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
    quests: dict[str, Quest] = {}

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

class UseArgs(BaseModel):
    item: str = Field(min_length=1, max_length=64)

class MoveReq(BaseModel):
    action: Literal["move"]
    args: MoveArgs

class TalkArgs(BaseModel):
    target: str = Field(min_length=1, max_length=64)

class TalkReq(BaseModel):
    action: Literal["talk"]
    args: TalkArgs

class BuyArgs(BaseModel):
    item: str = Field(min_length=1, max_length=64)

class BuyReq(BaseModel):
    action: Literal["buy"]
    args: BuyArgs

class UseReq(BaseModel):
    action: Literal["use"]
    args: UseArgs

class AcceptQuestArgs(BaseModel):
    quest_id: str

class AcceptQuestReq(BaseModel):
    action: Literal["accept_quest"]
    args: AcceptQuestArgs


ActionRequest = Union[
    CreatePlayerReq,
    LookReq,
    MoveReq,
    AttackReq,
    StatsReq,
    InventoryReq,
    UseReq,
    TalkReq,
    BuyReq,
    AcceptQuestReq
]


class ActionResponse(BaseModel):
    ok: bool
    messages: List[str] = Field(default_factory=list)
    state: Optional[dict] = None
    error: Optional[str] = None
