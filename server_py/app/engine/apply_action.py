from __future__ import annotations

from typing import Optional, Any

from pydantic import TypeAdapter

from ..types import ActionRequest, ActionResponse
from ..db import get_player, log_action

from .actions.create_player import create_player
from .actions.look import look
from .actions.move import move
from .actions.attack import attack
from .actions.stats import stats
from .actions.inventory import inventory


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
    else:
        result = ActionResponse(ok=False, error="Unhandled action.")

    log_action(
        player_id=player.player_id,
        action=req.action,
        args=req.model_dump().get("args"),
        result=result.model_dump(),
    )
    return result