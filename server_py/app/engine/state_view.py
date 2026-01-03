from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..types import Player
from ..world import get_location
from ..db import (
    get_pending_trades_for_player,
    get_pending_trades_by_player,
    get_player,
    get_player_party,
    get_player_party_invites,
)
from .entities import get_entities_at, filter_current_player


def build_location_view_for_player(player: Player) -> Dict[str, Any]:
    """
    Canonical snapshot of the world from *this player's* perspective.
    This is the ONE place we:
      - build the location dict
      - attach entities
      - filter the current player out (so UI never shows yourself in People Here)
    """
    loc = get_location(player.location)

    entities = filter_current_player(
        get_entities_at(player.location),
        player.player_id,
    )

    return {
        "location": {
            "id": loc.id,
            "name": loc.name,
            "description": loc.description,
            "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
        },
        "entities": entities,
        "adjacent_scenes": get_adjacent_scenes_for_prefetch(loc.id),
    }


def get_adjacent_scenes_for_prefetch(location_id: str) -> List[Dict[str, Any]]:
    """
    Adjacent scenes for image prefetch.
    Note: This is NOT player-specific and doesn't need to filter "self".
    """
    loc = get_location(location_id)
    scenes: List[Dict[str, Any]] = []

    for ex in loc.exits:
        next_loc = get_location(ex.to)
        scenes.append(
            {
                "location": {
                    "id": next_loc.id,
                    "name": next_loc.name,
                    "description": next_loc.description,
                    "exits": [{"to": e.to, "label": e.label} for e in next_loc.exits],
                },
                "entities": get_entities_at(next_loc.id),
            }
        )

    return scenes


def get_pending_trade_offers(player: Player) -> List[Dict[str, Any]]:
    """
    Get pending trade offers for a player with validation flags.
    Returns list of incoming trades with 'can_accept' flag based on inventory.
    """
    trades = get_pending_trades_for_player(player.player_id)
    result = []

    for trade in trades:
        # Get sender info
        sender = get_player(trade["from_player_id"])
        sender_name = sender.name if sender else "Unknown"

        # Check if player can accept (has requested items)
        can_accept = all(
            player.inventory.get(item, 0) >= qty
            for item, qty in trade["requested_items"].items()
        )

        result.append({
            "trade_id": trade["trade_id"],
            "from_player_name": sender_name,
            "from_player_id": trade["from_player_id"],
            "offered_items": trade["offered_items"],
            "requested_items": trade["requested_items"],
            "can_accept": can_accept,
            "created_at": trade["created_at"],
        })

    return result


def get_pending_trade_offers_sent(player: Player) -> List[Dict[str, Any]]:
    """
    Get pending trade offers sent by the player.
    Returns list of outgoing trades with validation flag for whether recipient can accept.
    """
    trades = get_pending_trades_by_player(player.player_id)
    result = []

    for trade in trades:
        # Get recipient info
        recipient = get_player(trade["to_player_id"])
        recipient_name = recipient.name if recipient else "Unknown"

        # Check if recipient can accept (has requested items)
        can_be_accepted = False
        if recipient:
            can_be_accepted = all(
                recipient.inventory.get(item, 0) >= qty
                for item, qty in trade["requested_items"].items()
            )

        result.append({
            "trade_id": trade["trade_id"],
            "to_player_name": recipient_name,
            "to_player_id": trade["to_player_id"],
            "offered_items": trade["offered_items"],
            "requested_items": trade["requested_items"],
            "can_be_accepted": can_be_accepted,
            "created_at": trade["created_at"],
        })

    return result


def get_party_info(player: Player) -> Optional[Dict[str, Any]]:
    """
    Get current party information with member details.
    Returns None if player is not in a party.
    """
    party = get_player_party(player.player_id)
    if not party:
        return None

    # Get member names and details
    members = []
    for member_id in party["members"]:
        member = get_player(member_id)
        if member:
            members.append({
                "player_id": member_id,
                "name": member.name,
                "is_leader": member_id == party["leader_id"],
            })

    return {
        "party_id": party["party_id"],
        "name": party.get("name", "Unnamed Party"),
        "leader_id": party["leader_id"],
        "members": members,
    }


def get_party_invites_info(player: Player) -> List[Dict[str, Any]]:
    """
    Get pending party invitations with sender details.
    """
    invites = get_player_party_invites(player.player_id)
    result = []

    for invite in invites:
        # Get sender info
        sender = get_player(invite["from_player_id"])
        sender_name = sender.name if sender else "Unknown"

        result.append({
            "invite_id": invite["invite_id"],
            "party_id": invite["party_id"],
            "from_player_id": invite["from_player_id"],
            "from_player_name": sender_name,
            "created_at": invite["created_at"],
        })

    return result


def build_action_state(
    player: Player,
    *,
    scene_dirty: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Full ActionResponse.state builder used by all actions.
    Centralizes: player dump + location view + optional flags like scene_dirty.
    """
    state: Dict[str, Any] = {
        "player": player.model_dump(),
        **build_location_view_for_player(player),
        "pending_trade_offers": get_pending_trade_offers(player),
        "pending_trade_offers_sent": get_pending_trade_offers_sent(player),
        "party": get_party_info(player),
        "party_invites": get_party_invites_info(player),
    }
    if scene_dirty is not None:
        state["scene_dirty"] = scene_dirty
    return state