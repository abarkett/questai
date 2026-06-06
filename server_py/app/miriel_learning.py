"""
Miriel learning system for comprehensive game event tracking.
Learns player actions, world events, and reputation changes to build context for AI generation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .services.miriel_client import get_miriel_client
from .types import Player
from .db import (
    get_world_state,
    get_world_turn,
    get_player_party,
    calculate_reputation,
    get_all_factions,
    get_all_world_state,
)


def learn_player_action(
    player: Player,
    action: str,
    args: Dict[str, Any],
    result: Dict[str, Any],
    turn: int
) -> bool:
    """
    Learn a player action with full game context.
    Called after each successful action in apply_action.py.

    Args:
        player: The player who performed the action
        action: Action name (e.g., 'move', 'attack', 'talk')
        args: Action arguments
        result: Action result
        turn: Current world turn

    Returns:
        True if learning succeeded, False otherwise
    """
    client = get_miriel_client()
    if not client.enabled:
        return False

    try:
        # Build comprehensive context
        context = {
            "event_type": "player_action",
            "player_id": player.player_id,
            "player_name": player.name,
            "player_level": player.level,
            "location": player.location,
            "action": action,
            "world_turn": turn,
            "timestamp": int(time.time() * 1000)
        }

        # Enrich with quest context
        if player.active_quests:
            context["active_quests"] = [q.quest_id for q in player.active_quests.values()]
        if player.completed_quests:
            context["completed_quests"] = [q.quest_id for q in player.completed_quests.values()]

        # Enrich with party context
        try:
            party = get_player_party(player.player_id)
            if party:
                context["party_id"] = party["party_id"]
                context["party_members"] = party["members"]
        except Exception:
            pass  # Party context is optional

        # Enrich with reputation context
        try:
            reputations = {}
            for faction in get_all_factions():
                rep = calculate_reputation(player.player_id, faction["faction_id"])
                if rep != 0:
                    reputations[faction["faction_id"]] = rep
            if reputations:
                context["reputations"] = reputations
        except Exception:
            pass  # Reputation context is optional

        # Build knowledge entry
        knowledge = {
            "action": action,
            "args": args,
            "result_ok": result.get("ok", False),
            "messages": result.get("messages", []),
            "context": context
        }

        # Learn with metadata for filtering
        metadata = {
            "player_id": player.player_id,
            "action_type": action,
            "location": player.location,
            "turn": turn
        }

        client.learn(
            input_data=knowledge,
            metadata=metadata,
            force_string=False,
            priority=100
        )

        return True

    except Exception as e:
        print(f"[MIRIEL] Failed to learn player action: {e}")
        return False


def learn_world_event(
    event_type: str,
    location_id: Optional[str],
    data: Dict[str, Any]
) -> bool:
    """
    Learn world evolution events (forest infestation, rat respawn, etc.).

    Args:
        event_type: Type of world event
        location_id: Location where event occurred (optional)
        data: Event data

    Returns:
        True if learning succeeded, False otherwise
    """
    client = get_miriel_client()
    if not client.enabled:
        return False

    try:
        knowledge = {
            "event_type": "world_event",
            "world_event_type": event_type,
            "location": location_id or "world",
            "data": data,
            "world_state": get_all_world_state(),
            "turn": get_world_turn(),
            "timestamp": int(time.time() * 1000)
        }

        metadata = {
            "event_type": "world_event",
            "world_event_type": event_type,
            "location": location_id or "world"
        }

        client.learn(
            input_data=knowledge,
            metadata=metadata,
            force_string=False,
            priority=150  # Higher priority for world events
        )

        return True

    except Exception as e:
        print(f"[MIRIEL] Failed to learn world event: {e}")
        return False


def learn_reputation_change(
    player_id: str,
    faction_id: str,
    event_type: str,
    value: int,
    description: str
) -> bool:
    """
    Learn reputation-affecting events.

    Args:
        player_id: Player whose reputation changed
        faction_id: Faction involved
        event_type: Type of reputation event
        value: Reputation change value
        description: Description of the event

    Returns:
        True if learning succeeded, False otherwise
    """
    client = get_miriel_client()
    if not client.enabled:
        return False

    try:
        knowledge = {
            "event_type": "reputation_change",
            "player_id": player_id,
            "faction_id": faction_id,
            "change_type": event_type,
            "value": value,
            "description": description,
            "turn": get_world_turn(),
            "timestamp": int(time.time() * 1000)
        }

        metadata = {
            "event_type": "reputation_change",
            "player_id": player_id,
            "faction_id": faction_id
        }

        client.learn(
            input_data=knowledge,
            metadata=metadata,
            force_string=False,
            priority=120  # Medium-high priority for reputation
        )

        return True

    except Exception as e:
        print(f"[MIRIEL] Failed to learn reputation change: {e}")
        return False
