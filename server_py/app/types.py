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
    equipment: dict[str, str] = {}   # slot -> item_id (e.g. {"weapon": "iron_sword"})
    abilities: list[str] = []        # learned ability ids
    ability_cooldowns: dict[str, int] = {}   # ability_id -> ready-at epoch ms
    status_effects: dict[str, dict] = {}     # effect_id -> {"turns", "magnitude"}
    visited_locations: list[str] = []        # location ids the player has discovered
    discovered_monsters: list[str] = []      # monster names recorded in the bestiary
    active_quests: dict[str, Quest] = {}
    completed_quests: dict[str, Quest] = {}
    archived_quests: dict[str, Quest] = {}
    # Deprecated: keeping for backwards compatibility during migration
    quests: dict[str, Quest] = {}
    last_defeated_at: Optional[int] = None
    last_attacked_target: Optional[str] = None
    last_attacked_at: Optional[int] = None
    # Action-point economy (see app/action_points.py)
    action_points: int = 30
    ap_updated_at: Optional[int] = None
    # Login recap: when we last summarized "while you were gone"
    last_recap_at: Optional[int] = None

class AttackArgs(BaseModel):
    target: str


class AttackReq(BaseModel):
    action: Literal["attack"]
    args: AttackArgs


class FightArgs(BaseModel):
    target: str
    stance: Literal["bold", "standard", "cautious"] = "standard"


class FightReq(BaseModel):
    action: Literal["fight"]
    args: FightArgs

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


class ListTradesReq(BaseModel):
    action: Literal["list_trades"]
    args: Optional[dict] = None


class CancelTradeArgs(BaseModel):
    trade_id: str


class CancelTradeReq(BaseModel):
    action: Literal["cancel_trade"]
    args: CancelTradeArgs


class PartyInviteArgs(BaseModel):
    target_player: str = Field(min_length=1, max_length=32)


class PartyInviteReq(BaseModel):
    action: Literal["party_invite"]
    args: PartyInviteArgs


class AcceptPartyInviteArgs(BaseModel):
    invite_id: str


class AcceptPartyInviteReq(BaseModel):
    action: Literal["accept_party_invite"]
    args: AcceptPartyInviteArgs


class LeavePartyReq(BaseModel):
    action: Literal["leave_party"]
    args: Optional[dict] = None


class PartyStatusReq(BaseModel):
    action: Literal["party_status"]
    args: Optional[dict] = None


class ReputationReq(BaseModel):
    action: Literal["reputation"]
    args: Optional[dict] = None


class EquipArgs(BaseModel):
    item: str = Field(min_length=1, max_length=64)


class EquipReq(BaseModel):
    action: Literal["equip"]
    args: EquipArgs


class UnequipArgs(BaseModel):
    slot: str = Field(min_length=1, max_length=32)


class UnequipReq(BaseModel):
    action: Literal["unequip"]
    args: UnequipArgs


class SellArgs(BaseModel):
    item: str = Field(min_length=1, max_length=64)


class SellReq(BaseModel):
    action: Literal["sell"]
    args: SellArgs


class CraftArgs(BaseModel):
    item: str = Field(min_length=1, max_length=64)


class CraftReq(BaseModel):
    action: Literal["craft"]
    args: CraftArgs


class GatherReq(BaseModel):
    action: Literal["gather"]
    args: Optional[dict] = None


class UseAbilityArgs(BaseModel):
    ability: str = Field(min_length=1, max_length=48)
    target: Optional[str] = Field(default=None, max_length=64)


class UseAbilityReq(BaseModel):
    action: Literal["use_ability"]
    args: UseAbilityArgs


class HealReq(BaseModel):
    action: Literal["heal"]
    args: Optional[dict] = None


class MapReq(BaseModel):
    action: Literal["map"]
    args: Optional[dict] = None


class BestiaryReq(BaseModel):
    action: Literal["bestiary"]
    args: Optional[dict] = None


class JournalReq(BaseModel):
    action: Literal["journal"]
    args: Optional[dict] = None


class StoryReq(BaseModel):
    action: Literal["story"]
    args: Optional[dict] = None


class BeginArcArgs(BaseModel):
    arc_id: str = Field(min_length=1, max_length=48)


class BeginArcReq(BaseModel):
    action: Literal["begin_arc"]
    args: BeginArcArgs


class ChooseArgs(BaseModel):
    choice: str = Field(min_length=1, max_length=48)
    arc_id: Optional[str] = Field(default=None, max_length=48)


class ChooseReq(BaseModel):
    action: Literal["choose"]
    args: ChooseArgs


ActionRequest = Union[
    CreatePlayerReq,
    LookReq,
    MoveReq,
    AttackReq,
    FightReq,
    StatsReq,
    InventoryReq,
    UseReq,
    TalkReq,
    BuyReq,
    AcceptQuestReq,
    TurnInQuestReq,
    OfferTradeReq,
    AcceptTradeReq,
    ListTradesReq,
    CancelTradeReq,
    PartyInviteReq,
    AcceptPartyInviteReq,
    LeavePartyReq,
    PartyStatusReq,
    ReputationReq,
    EquipReq,
    UnequipReq,
    SellReq,
    CraftReq,
    GatherReq,
    UseAbilityReq,
    HealReq,
    MapReq,
    BestiaryReq,
    JournalReq,
    StoryReq,
    BeginArcReq,
    ChooseReq,
]


class ActionResponse(BaseModel):
    ok: bool
    messages: List[str] = Field(default_factory=list)
    state: Optional[dict] = None
    error: Optional[str] = None
