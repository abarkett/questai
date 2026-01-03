"""
Phase 8: World Evolution Rules Engine

This module contains the rule-based logic for world state evolution.
Rules are deterministic and run after certain turns or events.
"""

from __future__ import annotations

from typing import Dict, Any, List, Callable
from .db import (
    get_world_state,
    set_world_state,
    get_world_turn,
    log_world_event,
)
from .engine.entities import get_world_entities_at


class WorldRule:
    """Represents a single world evolution rule."""
    
    def __init__(
        self,
        rule_id: str,
        name: str,
        condition: Callable[[], bool],
        action: Callable[[], None],
        description: str,
    ):
        self.rule_id = rule_id
        self.name = name
        self.condition = condition
        self.action = action
        self.description = description
    
    def evaluate(self) -> bool:
        """Check if the rule's condition is met and execute action if so."""
        if self.condition():
            self.action()
            return True
        return False


# Define world evolution rules

def _check_forest_infestation() -> bool:
    """Check if forest should become infested."""
    # Check if rats have been alive in forest for N turns
    state = get_world_state("forest_rat_turns")
    if not state:
        return False
    
    rat_turns = int(state)
    return rat_turns >= 10  # Infestation after 10 turns


def _apply_forest_infestation() -> None:
    """Make forest more dangerous."""
    set_world_state("forest_infested", "true")
    log_world_event(
        event_type="world_evolution",
        location_id="forest",
        data={
            "change": "forest_infested",
            "description": "The forest became more dangerous as rats multiplied."
        }
    )


def _check_forest_cleared() -> bool:
    """Check if forest should be cleared."""
    # Check if enough rats have been killed
    entities = get_world_entities_at("forest")
    rat_count = sum(1 for e in entities if e.type == "monster" and "rat" in e.entity_id.lower())
    
    is_infested = get_world_state("forest_infested") == "true"
    return is_infested and rat_count == 0


def _apply_forest_cleared() -> None:
    """Clear the forest infestation."""
    set_world_state("forest_infested", "false")
    set_world_state("forest_rat_turns", "0")
    log_world_event(
        event_type="world_evolution",
        location_id="forest",
        data={
            "change": "forest_cleared",
            "description": "The forest is now safer after the rats were cleared."
        }
    )


def _check_town_security() -> bool:
    """Check if town security should change based on PvP activity."""
    # This would check action logs for PvP in town
    # For now, return False as placeholder
    return False


def _apply_town_guards() -> None:
    """Spawn guards in town."""
    set_world_state("town_security_level", "high")
    log_world_event(
        event_type="world_evolution",
        location_id="town_square",
        data={
            "change": "guards_deployed",
            "description": "Town guards have been deployed due to recent violence."
        }
    )


# Registry of all world rules
WORLD_RULES: List[WorldRule] = [
    WorldRule(
        rule_id="forest_infestation",
        name="Forest Infestation",
        condition=_check_forest_infestation,
        action=_apply_forest_infestation,
        description="Forest becomes infested if rats survive too long",
    ),
    WorldRule(
        rule_id="forest_cleared",
        name="Forest Cleared",
        condition=_check_forest_cleared,
        action=_apply_forest_cleared,
        description="Forest clears when all rats are defeated",
    ),
    WorldRule(
        rule_id="town_security",
        name="Town Security",
        condition=_check_town_security,
        action=_apply_town_guards,
        description="Guards appear if too much PvP happens in town",
    ),
]


def evaluate_world_rules() -> List[str]:
    """
    Evaluate all world rules and return list of triggered rule names.
    This should be called periodically (e.g., every N turns or after certain actions).
    """
    triggered = []
    for rule in WORLD_RULES:
        if rule.evaluate():
            triggered.append(rule.name)
    return triggered


def track_monster_survival(location_id: str) -> None:
    """Track how long monsters have survived at a location."""
    if location_id == "forest":
        entities = get_world_entities_at(location_id)
        rat_count = sum(1 for e in entities if e.entity_type == "monster" and "rat" in e.entity_id.lower())
        
        if rat_count > 0:
            current = get_world_state("forest_rat_turns")
            turns = int(current) if current else 0
            set_world_state("forest_rat_turns", str(turns + 1))
        else:
            set_world_state("forest_rat_turns", "0")
