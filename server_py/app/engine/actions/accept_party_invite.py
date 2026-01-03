"""
Phase 10: Accept party invite action
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import (
    get_party_invite,
    delete_party_invite,
    add_party_member,
    get_party,
    get_player_party,
)
from ..state_view import build_action_state


def accept_party_invite(player: Player, invite_id: str) -> ActionResponse:
    """Accept a party invitation."""
    
    # Check if player is already in a party
    current_party = get_player_party(player.player_id)
    if current_party:
        return ActionResponse(
            ok=False,
            error="You are already in a party. Leave your current party first."
        )
    
    # Get the invitation
    invite = get_party_invite(invite_id)
    if not invite:
        return ActionResponse(ok=False, error="Invalid or expired invitation.")
    
    # Check if invitation is for this player
    if invite["to_player_id"] != player.player_id:
        return ActionResponse(ok=False, error="This invitation is not for you.")
    
    # Get the party
    party = get_party(invite["party_id"])
    if not party:
        delete_party_invite(invite_id)
        return ActionResponse(ok=False, error="That party no longer exists.")
    
    # Add player to party
    add_party_member(party["party_id"], player.player_id)
    
    # Delete the invitation
    delete_party_invite(invite_id)
    
    # Get updated party with new member
    updated_party = get_party(party["party_id"])
    
    # Get member names
    from ...db import get_player
    member_names = []
    for member_id in updated_party["members"]:
        member = get_player(member_id)
        if member:
            member_names.append(member.name)
    
    return ActionResponse(
        ok=True,
        messages=[
            f"You joined the party!",
            f"Party members: {', '.join(member_names)}"
        ],
        state=build_action_state(player)
    )
