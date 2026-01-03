"""
Phase 10: View party status action
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import get_player_party, get_player
from ..state_view import build_action_state


def party_status(player: Player) -> ActionResponse:
    """View your current party status."""
    
    party = get_player_party(player.player_id)
    if not party:
        return ActionResponse(
            ok=True,
            messages=["You are not in a party."],
            state=build_action_state(player)
        )

    # Get member names
    member_names = []
    for member_id in party["members"]:
        member = get_player(member_id)
        if member:
            name = member.name
            if member_id == party["leader_id"]:
                name += " (Leader)"
            member_names.append(name)

    messages = [
        f"Party: {party.get('name', 'Unnamed Party')}",
        f"Members: {', '.join(member_names)}"
    ]

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player)
    )
