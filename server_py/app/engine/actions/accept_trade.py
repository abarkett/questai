from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import (
    get_pending_trade,
    delete_pending_trade,
    get_player,
    upsert_player,
)


def accept_trade(player: Player, trade_id: str) -> ActionResponse:
    """
    Accept a pending trade offer.
    Executes the trade atomically.
    """
    messages: list[str] = []

    # Get the pending trade
    trade = get_pending_trade(trade_id)
    if not trade:
        return ActionResponse(ok=False, error=f"Trade '{trade_id}' not found.")

    # Verify that the current player is the recipient
    if trade["to_player_id"] != player.player_id:
        return ActionResponse(ok=False, error="This trade is not for you.")

    # Get the offering player
    from_player = get_player(trade["from_player_id"])
    if not from_player:
        delete_pending_trade(trade_id)
        return ActionResponse(ok=False, error="The offering player no longer exists.")

    offered_items = trade["offered_items"]
    requested_items = trade["requested_items"]

    # Validate from_player still has the offered items
    for item_name, quantity in offered_items.items():
        if from_player.inventory.get(item_name, 0) < quantity:
            delete_pending_trade(trade_id)
            return ActionResponse(
                ok=False,
                error=f"{from_player.name} no longer has {quantity} {item_name}.",
            )

    # Validate to_player (current player) has the requested items
    for item_name, quantity in requested_items.items():
        if player.inventory.get(item_name, 0) < quantity:
            return ActionResponse(
                ok=False,
                error=f"You don't have {quantity} {item_name} to complete this trade.",
            )

    # Execute the trade atomically
    # Remove offered items from from_player
    for item_name, quantity in offered_items.items():
        from_player.inventory[item_name] -= quantity
        if from_player.inventory[item_name] == 0:
            del from_player.inventory[item_name]

    # Remove requested items from to_player (current player)
    for item_name, quantity in requested_items.items():
        player.inventory[item_name] -= quantity
        if player.inventory[item_name] == 0:
            del player.inventory[item_name]

    # Add offered items to to_player (current player)
    for item_name, quantity in offered_items.items():
        player.inventory[item_name] = player.inventory.get(item_name, 0) + quantity

    # Add requested items to from_player
    for item_name, quantity in requested_items.items():
        from_player.inventory[item_name] = from_player.inventory.get(item_name, 0) + quantity

    # Save both players
    upsert_player(from_player)
    upsert_player(player)

    # Delete the trade
    delete_pending_trade(trade_id)

    # Build messages
    offer_desc = ", ".join(f"{q}x {item}" for item, q in offered_items.items()) if offered_items else "nothing"
    request_desc = ", ".join(f"{q}x {item}" for item, q in requested_items.items()) if requested_items else "nothing"

    messages.append(f"Trade completed with {from_player.name}!")
    messages.append(f"You received: {offer_desc}")
    messages.append(f"You gave: {request_desc}")

    return ActionResponse(
        ok=True,
        messages=messages,
        state={"player": player.model_dump()},
    )
