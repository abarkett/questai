from __future__ import annotations

import uuid
from ...types import Player, ActionResponse
from ...db import create_pending_trade, get_player
from ..entities import find_player_by_name_at
from ..state_view import build_action_state


def offer_trade(
    player: Player,
    to_player_name: str,
    offer_items: dict[str, int],
    request_items: dict[str, int],
) -> ActionResponse:
    """
    Create a pending trade offer to another player.
    """
    messages: list[str] = []

    # Validate that offer and request are not both empty
    if not offer_items and not request_items:
        return ActionResponse(ok=False, error="Trade must include offered or requested items.")

    # Find the target player in the same location
    target_player = find_player_by_name_at(player.location, to_player_name)
    
    if not target_player:
        return ActionResponse(ok=False, error=f"Player '{to_player_name}' is not here.")

    if target_player.player_id == player.player_id:
        return ActionResponse(ok=False, error="You can't trade with yourself.")

    # Validate player has the offered items
    for item_name, quantity in offer_items.items():
        if player.inventory.get(item_name, 0) < quantity:
            return ActionResponse(
                ok=False,
                error=f"You don't have {quantity} {item_name} to offer.",
            )

    # Create the trade
    trade_id = str(uuid.uuid4())[:16]  # Use 16 chars for better collision resistance
    create_pending_trade(
        trade_id=trade_id,
        from_player_id=player.player_id,
        to_player_id=target_player.player_id,
        offered_items=offer_items,
        requested_items=request_items,
    )

    # Build message
    offer_desc = ", ".join(f"{q}x {item}" for item, q in offer_items.items()) if offer_items else "nothing"
    request_desc = ", ".join(f"{q}x {item}" for item, q in request_items.items()) if request_items else "nothing"

    messages.append(f"Trade offer created (ID: {trade_id})")
    messages.append(f"You offer: {offer_desc}")
    messages.append(f"You request: {request_desc}")
    messages.append(f"{target_player.name} can accept with: accept_trade {trade_id}")

    # Build complete state including pending trades
    state = build_action_state(player)
    state["trade_id"] = trade_id

    return ActionResponse(
        ok=True,
        messages=messages,
        state=state,
    )
