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

    # Check if forest was previously populated with rats
    cleared_turn = get_world_state("forest_cleared_turn")

    # Trigger if rats are all dead and we haven't already recorded this clear
    # (cleared_turn being set means we already handled this clear event)
    return rat_count == 0 and not cleared_turn


def _apply_forest_cleared() -> None:
    """Clear the forest infestation."""
    set_world_state("forest_infested", "false")
    set_world_state("forest_rat_turns", "0")
    # Record when forest was cleared for respawn timer
    current_turn = get_world_turn()
    set_world_state("forest_cleared_turn", str(current_turn))
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


def _check_rat_respawn() -> bool:
    """Check if rats should respawn in the forest."""
    # Check if forest is clear and enough turns have passed
    entities = get_world_entities_at("forest")
    rat_count = sum(1 for e in entities if e.type == "monster" and "rat" in e.entity_id.lower())

    print(f"[RAT RESPAWN CHECK] Rat count: {rat_count}")

    if rat_count > 0:
        print(f"[RAT RESPAWN CHECK] Rats exist, not respawning")
        return False  # Rats already exist

    # Check how long rats have been gone
    cleared_state = get_world_state("forest_cleared_turn")
    if not cleared_state:
        print(f"[RAT RESPAWN CHECK] No cleared_turn set")
        return False  # Forest hasn't been cleared yet

    cleared_turn = int(cleared_state)
    current_turn = get_world_turn()
    turns_since_clear = current_turn - cleared_turn

    print(f"[RAT RESPAWN CHECK] Current turn: {current_turn}, Cleared turn: {cleared_turn}, Turns since: {turns_since_clear}")

    # Respawn after 20 turns
    should_respawn = turns_since_clear >= 20
    print(f"[RAT RESPAWN CHECK] Should respawn: {should_respawn}")
    return should_respawn


def _apply_rat_respawn() -> None:
    """Respawn rats in the forest."""
    from .world_entities import WORLD_ENTITIES
    from .types_entities import Entity

    # Add new rats back to the forest
    if "forest" not in WORLD_ENTITIES:
        WORLD_ENTITIES["forest"] = []

    WORLD_ENTITIES["forest"].extend([
        Entity(
            entity_id="rat_1",
            name="Rat",
            type="monster",
            hp=5,
            attack=2,
            xp_reward=2,
            loot={"coin": 1, "healing_herb": 1},
        ),
        Entity(
            entity_id="rat_2",
            name="Rat",
            type="monster",
            hp=5,
            attack=2,
            xp_reward=2,
            loot={"coin": 1, "healing_herb": 1},
        ),
    ])

    # Reset the cleared turn tracker
    set_world_state("forest_cleared_turn", "")
    set_world_state("forest_rat_turns", "0")

    log_world_event(
        event_type="world_evolution",
        location_id="forest",
        data={
            "change": "rats_respawned",
            "description": "Rats have returned to the forest."
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
        rule_id="rat_respawn",
        name="Rat Respawn",
        condition=_check_rat_respawn,
        action=_apply_rat_respawn,
        description="Rats respawn after 20 turns",
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
    print(f"[WORLD RULES] Evaluating {len(WORLD_RULES)} rules")
    triggered = []
    for rule in WORLD_RULES:
        print(f"[WORLD RULES] Checking rule: {rule.name}")
        if rule.evaluate():
            print(f"[WORLD RULES] Rule triggered: {rule.name}")
            triggered.append(rule.name)
    print(f"[WORLD RULES] Triggered rules: {triggered}")
    return triggered


def track_monster_survival(location_id: str) -> None:
    """Track how long monsters have survived at a location."""
    if location_id == "forest":
        entities = get_world_entities_at(location_id)
        rat_count = sum(1 for e in entities if e.type == "monster" and "rat" in e.entity_id.lower())
        
        if rat_count > 0:
            current = get_world_state("forest_rat_turns")
            turns = int(current) if current else 0
            set_world_state("forest_rat_turns", str(turns + 1))
        else:
            set_world_state("forest_rat_turns", "0")
