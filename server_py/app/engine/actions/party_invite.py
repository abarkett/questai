"""
Phase 10: Party invite action
"""

from __future__ import annotations

import uuid
from ...types import Player, ActionResponse
from ...db import (
    get_player,
    create_party,
    get_player_party,
    create_party_invite,
    get_party,
)
from ..state_view import build_action_state


def party_invite(player: Player, target_player_name: str) -> ActionResponse:
    """Invite another player to join your party."""
    
    # Check if target player exists and is in the same location
    from ...db import get_players_at_location
    players_here = get_players_at_location(player.location)
    target = None
    for p in players_here:
        if p.name.lower() == target_player_name.lower():
            target = p
            break
    
    if not target:
        return ActionResponse(
            ok=False,
            error=f"There is no player named '{target_player_name}' here."
        )
    
    if target.player_id == player.player_id:
        return ActionResponse(ok=False, error="You cannot invite yourself.")
    
    # Check if inviter is in a party
    inviter_party = get_player_party(player.player_id)
    
    # Check if target is already in a party
    target_party = get_player_party(target.player_id)
    if target_party:
        return ActionResponse(
            ok=False,
            error=f"{target.name} is already in a party."
        )
    
    # If inviter is not in a party, create one
    if not inviter_party:
        party_id = str(uuid.uuid4())
        create_party(party_id, player.player_id, name=f"{player.name}'s Party")
        inviter_party = get_party(party_id)
    else:
        # Check if inviter is the party leader
        if inviter_party["leader_id"] != player.player_id:
            return ActionResponse(
                ok=False,
                error="Only the party leader can invite new members."
            )
    
    # Create the invitation
    invite_id = str(uuid.uuid4())
    create_party_invite(
        invite_id=invite_id,
        party_id=inviter_party["party_id"],
        from_player_id=player.player_id,
        to_player_id=target.player_id,
    )
    
    return ActionResponse(
        ok=True,
        messages=[
            f"You invite {target.name} to join your party.",
            f"They can accept with: accept_party_invite {invite_id}"
        ],
        state=build_action_state(player)
    )
