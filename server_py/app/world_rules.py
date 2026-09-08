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
    """Respawn rats in the forest (persisted to the DB)."""
    from .db import spawn_monster, get_world_turn

    turn = get_world_turn()
    for i in (1, 2):
        spawn_monster(
            instance_id=f"rat_{i}",
            location_id="forest",
            name="Rat",
            hp=5,
            max_hp=5,
            attack=2,
            xp_reward=2,
            loot={"coin": 1, "healing_herb": 1},
            spawned_turn=turn,
        )

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
    triggered.extend(evaluate_db_rules())
    print(f"[WORLD RULES] Triggered rules: {triggered}")
    return triggered


# ---------------------------------------------------------------------------
# Data-driven rules: rules as content, not code.
#
# Stored in the world_rules table as JSON condition/effect lists and run by
# the interpreter below, so new world behaviors (including ones attached to
# generated regions) can be added without a deploy.
#
# Conditions (all must hold):
#   {"world_state_eq":  {"key": K, "value": V}}
#   {"world_state_ne":  {"key": K, "value": V}}
#   {"monster_count":   {"location": L, "name_contains": S?, "op": "eq|gte|lte", "value": N}}
#   {"turns_since_state": {"key": K, "gte": N}}   # K holds a turn number
#
# Effects (run in order):
#   {"set_state":      {"key": K, "value": V}}
#   {"set_state_turn": {"key": K}}                # stamp the current turn
#   {"spawn_monster":  {"instance_id", "location", "name", "hp", "attack", "xp_reward", "loot"?}}
#   {"log_event":      {"type"?, "location"?, "description"}}
# ---------------------------------------------------------------------------


def _condition_holds(cond: dict) -> bool:
    if "world_state_eq" in cond:
        c = cond["world_state_eq"]
        return get_world_state(c["key"]) == c["value"]
    if "world_state_ne" in cond:
        c = cond["world_state_ne"]
        return get_world_state(c["key"]) != c["value"]
    if "monster_count" in cond:
        c = cond["monster_count"]
        entities = get_world_entities_at(c["location"])
        needle = (c.get("name_contains") or "").lower()
        count = sum(
            1 for e in entities
            if e.type == "monster" and (not needle or needle in e.name.lower())
        )
        op, value = c.get("op", "gte"), int(c["value"])
        return {"eq": count == value, "gte": count >= value, "lte": count <= value}[op]
    if "turns_since_state" in cond:
        c = cond["turns_since_state"]
        raw = get_world_state(c["key"])
        if not raw:
            return False
        try:
            return get_world_turn() - int(raw) >= int(c["gte"])
        except ValueError:
            return False
    return False  # unknown condition: never trigger


def _apply_effect(effect: dict) -> None:
    from .db import spawn_monster, log_world_event as _log

    if "set_state" in effect:
        e = effect["set_state"]
        set_world_state(e["key"], e["value"])
    elif "set_state_turn" in effect:
        set_world_state(effect["set_state_turn"]["key"], str(get_world_turn()))
    elif "spawn_monster" in effect:
        e = effect["spawn_monster"]
        spawn_monster(
            instance_id=e["instance_id"],
            location_id=e["location"],
            name=e["name"],
            hp=int(e["hp"]),
            max_hp=int(e["hp"]),
            attack=int(e["attack"]),
            xp_reward=int(e.get("xp_reward", 0)),
            loot=e.get("loot") or {},
            spawned_turn=get_world_turn(),
        )
    elif "log_event" in effect:
        e = effect["log_event"]
        log_world_event(
            event_type=e.get("type", "world_evolution"),
            location_id=e.get("location"),
            data={"description": e["description"]},
        )


def evaluate_db_rules() -> List[str]:
    """Run every enabled data-driven rule whose cooldown and conditions allow."""
    from .db import get_enabled_world_rules, stamp_world_rule_triggered

    triggered: List[str] = []
    turn = get_world_turn()
    for rule in get_enabled_world_rules():
        last = rule.get("last_triggered_turn")
        if last is not None and turn - last < rule.get("cooldown_turns", 0):
            continue
        try:
            if not all(_condition_holds(c) for c in rule["conditions"]):
                continue
            for effect in rule["effects"]:
                _apply_effect(effect)
            stamp_world_rule_triggered(rule["rule_id"], turn)
            triggered.append(rule["name"])
        except Exception as e:
            print(f"[WORLD RULES] db rule {rule['rule_id']} failed: {e}")
    return triggered


def seed_default_db_rules() -> None:
    """Built-in data-driven rules (idempotent; runs at startup)."""
    from .db import upsert_world_rule

    # A wandering beast prowls the North Road every so often — proof that the
    # world moves on its own, and a recurring community moment.
    upsert_world_rule(
        rule_id="wandering_beast",
        name="A Wandering Beast",
        description="Every ~40 turns a hulking beast wanders onto the North Road.",
        conditions=[
            {"monster_count": {"location": "north_road", "name_contains": "wandering", "op": "eq", "value": 0}},
        ],
        effects=[
            {"spawn_monster": {
                "instance_id": "wandering_beast",
                "location": "north_road",
                "name": "Wandering Beast",
                "hp": 35, "attack": 6, "xp_reward": 30,
                "loot": {"coin": 15, "pelt": 2},
            }},
            {"log_event": {
                "type": "world_evolution",
                "location": "north_road",
                "description": "A hulking beast has wandered onto the North Road.",
            }},
        ],
        cooldown_turns=40,
    )

    # An alpha wolf shadows the forest now and then — the old areas should
    # surprise veterans too. Uses a known monster name so the bestiary,
    # bounty board, and ambush logic all recognize it.
    upsert_world_rule(
        rule_id="forest_prowler",
        name="A Prowler in the Pines",
        description="Every ~25 turns a hardened wolf stalks into the forest.",
        conditions=[
            {"monster_count": {"location": "forest", "name_contains": "wolf", "op": "eq", "value": 0}},
        ],
        effects=[
            {"spawn_monster": {
                "instance_id": "forest_prowler",
                "location": "forest",
                "name": "Wolf",
                "hp": 24, "attack": 5, "xp_reward": 18,
                "loot": {"coin": 6, "pelt": 2},
            }},
            {"log_event": {
                "type": "world_evolution",
                "location": "forest",
                "description": "A lean grey shape has been seen slipping between the pines.",
            }},
        ],
        cooldown_turns=25,
    )

    # Brigands work the riverside road in waves.
    upsert_world_rule(
        rule_id="riverside_brigand",
        name="Brigands on the Towpath",
        description="Every ~30 turns a bandit sets up along the riverside.",
        conditions=[
            {"monster_count": {"location": "riverside", "name_contains": "bandit", "op": "eq", "value": 0}},
        ],
        effects=[
            {"spawn_monster": {
                "instance_id": "riverside_brigand",
                "location": "riverside",
                "name": "Bandit",
                "hp": 18, "attack": 5, "xp_reward": 14,
                "loot": {"coin": 12},
            }},
            {"log_event": {
                "type": "world_evolution",
                "location": "riverside",
                "description": "A bandit has taken to waylaying travelers along the riverside.",
            }},
        ],
        cooldown_turns=30,
    )


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
