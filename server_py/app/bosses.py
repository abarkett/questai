"""
Boss mechanics. Bosses are ordinary monsters with extra behavior triggered
during combat — currently a one-time enrage (stronger attacks) plus a summoned
add once they drop below a HP threshold. State is tracked in world_state keyed
by the boss's instance id, so it survives restarts and never re-triggers.
"""

from __future__ import annotations

from typing import Dict, List

from .db import (
    get_world_state,
    set_world_state,
    set_monster_attack,
    spawn_monster,
    get_world_turn,
)


BOSS_MECHANICS: Dict[str, dict] = {
    "Molten Wyrm": {
        "enrage_at": 0.5,          # fraction of max HP
        "attack_mult": 1.5,
        "summon": {
            "name": "Magma Hound",
            "hp": 50,
            "attack": 12,
            "xp_reward": 70,
            "loot": {"coin": 18, "ember_core": 1},
        },
    },
}


def _flag(instance_id: str) -> str:
    return f"boss_enraged_{instance_id}"


def trigger_boss_on_hit(instance_id: str, result: dict) -> List[str]:
    """
    Called after a non-lethal hit on a monster. If it's a boss that just crossed
    its enrage threshold (and hasn't enraged yet), enrage it and summon an add.
    Returns player-facing messages (empty if nothing happened).
    """
    name = result.get("name")
    mech = BOSS_MECHANICS.get(name or "")
    if not mech:
        return []

    hp = result.get("hp", 0)
    max_hp = result.get("max_hp") or 0
    if max_hp <= 0 or hp > mech["enrage_at"] * max_hp:
        return []
    if get_world_state(_flag(instance_id)) == "true":
        return []

    set_world_state(_flag(instance_id), "true")
    messages = [f"The {name} ENRAGES, its blows growing fiercer!"]

    new_attack = int(result.get("attack", 1) * mech["attack_mult"])
    set_monster_attack(instance_id, new_attack)

    summon = mech.get("summon")
    if summon:
        add_id = f"{instance_id}_add_{get_world_turn()}"
        spawn_monster(
            instance_id=add_id,
            location_id=result["location_id"],
            name=summon["name"],
            hp=summon["hp"],
            max_hp=summon["hp"],
            attack=summon["attack"],
            xp_reward=summon["xp_reward"],
            loot=summon.get("loot", {}),
        )
        messages.append(f"A {summon['name']} erupts from the molten rock to defend it!")

    return messages


def clear_boss_state(instance_id: str, name: str) -> None:
    """Reset a boss's enrage flag (call on death so a respawn can enrage again)."""
    if name in BOSS_MECHANICS:
        set_world_state(_flag(instance_id), "false")
