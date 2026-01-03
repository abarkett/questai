"""
Phase 9: Reputation status action
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import calculate_reputation, get_all_factions
from ...factions import get_reputation_tier
from ..state_view import build_action_state


def reputation(player: Player) -> ActionResponse:
    """View reputation with all factions."""
    
    factions = get_all_factions()

    if not factions:
        return ActionResponse(
            ok=True,
            messages=["No factions have been established yet."],
            state=build_action_state(player, scene_dirty=False)
        )

    messages = ["Your reputation:"]

    reputation_data = {}
    for faction in factions:
        rep_value = calculate_reputation(player.player_id, faction["faction_id"])
        tier = get_reputation_tier(rep_value)
        reputation_data[faction["faction_id"]] = {
            "name": faction["name"],
            "value": rep_value,
            "tier": tier
        }
        messages.append(f"  {faction['name']}: {tier} ({rep_value})")

    state = build_action_state(player, scene_dirty=False)
    state["reputation"] = reputation_data

    return ActionResponse(
        ok=True,
        messages=messages,
        state=state
    )
