"""
Phase 9: Faction System

This module defines factions, their properties, and reputation logic.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Faction:
    """Represents a faction in the game world."""
    faction_id: str
    name: str
    alignment: str  # "good", "neutral", "evil", etc.
    influence_locations: List[str]  # Locations where this faction has influence
    npc_members: List[str]  # NPC entity IDs that belong to this faction
    description: str


# Define core factions
FACTIONS: Dict[str, Faction] = {
    "town_guard": Faction(
        faction_id="town_guard",
        name="Town Guard",
        alignment="lawful",
        influence_locations=["town_square", "market"],
        npc_members=["town_guard_captain"],
        description="The protectors of the town, maintaining law and order.",
    ),
    "merchants_guild": Faction(
        faction_id="merchants_guild",
        name="Merchants Guild",
        alignment="neutral",
        influence_locations=["market", "tavern"],
        npc_members=["merchant", "innkeeper"],
        description="A collective of traders and shopkeepers seeking profit.",
    ),
    "outlaws": Faction(
        faction_id="outlaws",
        name="The Outlaws",
        alignment="chaotic",
        influence_locations=["forest", "north_road"],
        npc_members=[],
        description="Bandits and rogues who operate outside the law.",
    ),
    "forest_druids": Faction(
        faction_id="forest_druids",
        name="Forest Druids",
        alignment="neutral",
        influence_locations=["forest"],
        npc_members=["druid_elder"],
        description="Guardians of nature and the forest's secrets.",
    ),
}


def get_faction(faction_id: str) -> Optional[Faction]:
    """Get a faction by ID."""
    return FACTIONS.get(faction_id)


def get_location_factions(location_id: str) -> List[Faction]:
    """Get all factions that have influence at a location."""
    return [f for f in FACTIONS.values() if location_id in f.influence_locations]


def get_npc_faction(npc_id: str) -> Optional[Faction]:
    """Get the faction that an NPC belongs to."""
    for faction in FACTIONS.values():
        if npc_id in faction.npc_members:
            return faction
    return None


# Reputation thresholds and effects
REPUTATION_HOSTILE = -100
REPUTATION_UNFRIENDLY = -50
REPUTATION_NEUTRAL = 0
REPUTATION_FRIENDLY = 50
REPUTATION_HONORED = 100


def get_reputation_tier(reputation: int) -> str:
    """Get the reputation tier name for a given reputation value."""
    if reputation >= REPUTATION_HONORED:
        return "Honored"
    elif reputation >= REPUTATION_FRIENDLY:
        return "Friendly"
    elif reputation >= REPUTATION_NEUTRAL:
        return "Neutral"
    elif reputation >= REPUTATION_UNFRIENDLY:
        return "Unfriendly"
    else:
        return "Hostile"


def get_price_modifier(reputation: int) -> float:
    """Get the price modifier based on reputation (1.0 = normal price)."""
    if reputation >= REPUTATION_HONORED:
        return 0.8  # 20% discount
    elif reputation >= REPUTATION_FRIENDLY:
        return 0.9  # 10% discount
    elif reputation >= REPUTATION_NEUTRAL:
        return 1.0  # Normal price
    elif reputation >= REPUTATION_UNFRIENDLY:
        return 1.2  # 20% markup
    else:
        return 1.5  # 50% markup


def is_faction_hostile(reputation: int) -> bool:
    """Check if a faction is hostile to the player."""
    return reputation < REPUTATION_UNFRIENDLY


def get_reputation_event_value(event_type: str) -> int:
    """Get the reputation change value for different event types."""
    event_values = {
        # Positive events
        "quest_completed": 10,
        "helped_member": 5,
        "trade_completed": 2,
        "defended_location": 15,
        
        # Negative events
        "attacked_member": -20,
        "killed_member": -50,
        "theft": -30,
        "quest_failed": -5,
        "attacked_in_territory": -10,
    }
    return event_values.get(event_type, 0)
