"""
Phase 10: Leave party action
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import (
    get_player_party,
    remove_party_member,
    delete_party,
    get_party,
)
from ..state_view import build_action_state


def leave_party(player: Player) -> ActionResponse:
    """Leave your current party."""
    
    party = get_player_party(player.player_id)
    if not party:
        return ActionResponse(ok=False, error="You are not in a party.")
    
    # Remove player from party
    remove_party_member(party["party_id"], player.player_id)
    
    # If player was the leader, disband the party
    if party["leader_id"] == player.player_id:
        delete_party(party["party_id"])
        return ActionResponse(
            ok=True,
            messages=[
                "You left the party.",
                "As the leader, the party has been disbanded."
            ],
            state=build_action_state(player)
        )

    # Check if party is now empty (shouldn't happen, but safety check)
    updated_party = get_party(party["party_id"])
    if updated_party and len(updated_party["members"]) == 0:
        delete_party(party["party_id"])

    return ActionResponse(
        ok=True,
        messages=["You left the party."],
        state=build_action_state(player)
    )
