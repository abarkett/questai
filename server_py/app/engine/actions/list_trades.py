from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import get_pending_trades_for_player, get_pending_trades_by_player, get_player
from ..state_view import build_action_state


def list_trades(player: Player) -> ActionResponse:
    """
    List all pending trades (sent and received).
    """
    messages: list[str] = []

    # Get trades sent by this player
    sent_trades = get_pending_trades_by_player(player.player_id)

    # Get trades received by this player
    received_trades = get_pending_trades_for_player(player.player_id)

    if not sent_trades and not received_trades:
        messages.append("You have no pending trades.")
        return ActionResponse(
            ok=True,
            messages=messages,
            state=build_action_state(player),
        )

    # Display sent trades
    if sent_trades:
        messages.append("=== Trades You've Offered ===")
        for trade in sent_trades:
            recipient = get_player(trade["to_player_id"])
            recipient_name = recipient.name if recipient else "Unknown"

            offer_desc = ", ".join(f"{item}:{q}" for item, q in trade["offered_items"].items()) if trade["offered_items"] else "nothing"
            request_desc = ", ".join(f"{item}:{q}" for item, q in trade["requested_items"].items()) if trade["requested_items"] else "nothing"

            messages.append(f"  [{trade['trade_id']}] To {recipient_name}: {offer_desc} for {request_desc}")
        messages.append("")

    # Display received trades
    if received_trades:
        messages.append("=== Trades Offered to You ===")
        for trade in received_trades:
            sender = get_player(trade["from_player_id"])
            sender_name = sender.name if sender else "Unknown"

            offer_desc = ", ".join(f"{item}:{q}" for item, q in trade["offered_items"].items()) if trade["offered_items"] else "nothing"
            request_desc = ", ".join(f"{item}:{q}" for item, q in trade["requested_items"].items()) if trade["requested_items"] else "nothing"

            # Check if player can accept (has requested items)
            can_accept = all(
                player.inventory.get(item, 0) >= qty
                for item, qty in trade["requested_items"].items()
            )
            status = "" if can_accept else " [Cannot accept - missing items]"

            messages.append(f"  [{trade['trade_id']}] From {sender_name}: {offer_desc} for {request_desc}{status}")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player),
    )
