from __future__ import annotations

from typing import Optional, Any

from pydantic import TypeAdapter

from ..types import ActionRequest, ActionResponse
from ..db import get_player, log_action, increment_world_turn, get_world_turn

from .actions.create_player import create_player
from .actions.look import look
from .actions.move import move
from .actions.attack import attack
from .actions.stats import stats
from .actions.inventory import inventory
from .actions.use import use 
from .actions.talk import talk
from .actions.buy import buy
from .actions.accept_quest import accept_quest
from .actions.turn_in_quest import turn_in_quest
from .actions.offer_trade import offer_trade
from .actions.accept_trade import accept_trade
from .actions.list_trades import list_trades
from .actions.cancel_trade import cancel_trade
from .actions.party_invite import party_invite
from .actions.accept_party_invite import accept_party_invite
from .actions.leave_party import leave_party
from .actions.party_status import party_status
from .actions.reputation import reputation


_action_adapter = TypeAdapter(ActionRequest)


def apply_action(*, player_id: Optional[str], req_json: Any) -> ActionResponse:
    try:
        req = _action_adapter.validate_python(req_json)
    except Exception:
        return ActionResponse(ok=False, error="Invalid action payload.")

    # create_player does not require x-player-id
    if req.action == "create_player":
        result = create_player(req.args.name)
        pid = (
            result.state["player"]["player_id"]
            if result.state and "player" in result.state
            else "unknown"
        )
        if pid != "unknown":
            log_action(
                player_id=pid,
                action=req.action,
                args=req.model_dump().get("args"),
                result=result.model_dump(),
            )
        return result

    if not player_id:
        return ActionResponse(ok=False, error="Missing player_id (x-player-id header).")

    player = get_player(player_id)
    if not player:
        return ActionResponse(ok=False, error="Unknown player_id.")

    if req.action == "look":
        result = look(player)
    elif req.action == "move":
        result = move(player, req.args.to)
    elif req.action == "attack":
        result = attack(player, req.args.target)
    elif req.action == "stats":
        result = stats(player)
    elif req.action == "inventory":
        result = inventory(player)
    elif req.action == "use":
        result = use(player, req.args.item)
    elif req.action == "talk":
        result = talk(player, req.args.target)
    elif req.action == "buy":
        result = buy(player, req.args.item)
    elif req.action == "accept_quest":
        result = accept_quest(player, req.args.quest_id)
    elif req.action == "turn_in_quest":
        result = turn_in_quest(player, req.args.quest_id)
    elif req.action == "offer_trade":
        result = offer_trade(
            player,
            req.args.to_player,
            req.args.offer_items,
            req.args.request_items,
        )
    elif req.action == "accept_trade":
        result = accept_trade(player, req.args.trade_id)
    elif req.action == "list_trades":
        result = list_trades(player)
    elif req.action == "cancel_trade":
        result = cancel_trade(player, req.args.trade_id)
    elif req.action == "party_invite":
        result = party_invite(player, req.args.target_player)
    elif req.action == "accept_party_invite":
        result = accept_party_invite(player, req.args.invite_id)
    elif req.action == "leave_party":
        result = leave_party(player)
    elif req.action == "party_status":
        result = party_status(player)
    elif req.action == "reputation":
        result = reputation(player)
    else:
        result = ActionResponse(ok=False, error="Unhandled action.")

    # Phase 8: Increment world turn on successful actions (except passive ones like look, stats, inventory)
    if result.ok and req.action not in ["look", "stats", "inventory", "party_status", "reputation", "list_trades"]:
        new_turn = increment_world_turn()
        print(f"[TURN] New turn: {new_turn}, Action: {req.action}")

        # Evaluate world evolution rules periodically (every 5 turns)
        if new_turn % 5 == 0:
            print(f"[TURN] Turn {new_turn} is divisible by 5, evaluating world rules")
            from ..world_rules import evaluate_world_rules
            try:
                triggered_rules = evaluate_world_rules()
            except Exception as e:
                from ..db import log_world_event
                print(f"[TURN] World rules error: {e}")
                log_world_event(
                    event_type="world_rule_error",
                    location_id=None,
                    data={"error": str(e)}
                )
                triggered_rules = []
            if triggered_rules and result.messages:
                result.messages.append(f"[World changed: {', '.join(triggered_rules)}]")

    log_action(
        player_id=player.player_id,
        action=req.action,
        args=req.model_dump().get("args"),
        result=result.model_dump(),
    )
    return result