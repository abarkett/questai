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
    active_quests: dict[str, Quest] = {}
    completed_quests: dict[str, Quest] = {}
    archived_quests: dict[str, Quest] = {}
    # Deprecated: keeping for backwards compatibility during migration
    quests: dict[str, Quest] = {}
    last_defeated_at: Optional[int] = None
    last_attacked_target: Optional[str] = None
    last_attacked_at: Optional[int] = None

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

class TurnInQuestArgs(BaseModel):
    quest_id: str

class TurnInQuestReq(BaseModel):
    action: Literal["turn_in_quest"]
    args: TurnInQuestArgs


class OfferTradeArgs(BaseModel):
    to_player: str = Field(min_length=1, max_length=32)
    offer_items: dict[str, int]
    request_items: dict[str, int]


class OfferTradeReq(BaseModel):
    action: Literal["offer_trade"]
    args: OfferTradeArgs


class AcceptTradeArgs(BaseModel):
    trade_id: str


class AcceptTradeReq(BaseModel):
    action: Literal["accept_trade"]
    args: AcceptTradeArgs


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
    AcceptQuestReq,
    TurnInQuestReq,
    OfferTradeReq,
    AcceptTradeReq
]


class ActionResponse(BaseModel):
    ok: bool
    messages: List[str] = Field(default_factory=list)
    state: Optional[dict] = None
    error: Optional[str] = None
