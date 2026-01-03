from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import get_pending_trade, delete_pending_trade
from ..state_view import build_action_state


def cancel_trade(player: Player, trade_id: str) -> ActionResponse:
    """
    Cancel a pending trade offer.
    Only the sender can cancel their own trade.
    """
    trade = get_pending_trade(trade_id)

    if not trade:
        return ActionResponse(ok=False, error=f"Trade '{trade_id}' not found.")

    # Only the sender can cancel
    if trade["from_player_id"] != player.player_id:
        return ActionResponse(ok=False, error="You can only cancel trades you've offered.")

    delete_pending_trade(trade_id)

    return ActionResponse(
        ok=True,
        messages=[f"Trade '{trade_id}' has been cancelled."],
        state=build_action_state(player),
    )
