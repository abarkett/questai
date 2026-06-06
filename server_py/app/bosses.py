"""
Boss mechanics. Bosses are ordinary monsters with extra combat behavior:

  - regen_per_hit: heal a little after each non-lethal hit (a DPS check).
  - phases: ordered HP thresholds that each trigger once — enrage (stronger
    attacks), a self-heal, and/or a summoned add.

State is tracked in world_state keyed by the boss instance id (how many phases
have fired), so mechanics never re-trigger, survive restarts, and reset on
death so a respawn behaves the same.
"""

from __future__ import annotations

from typing import Dict, List

from .db import (
    get_world_state,
    set_world_state,
    set_monster_attack,
    set_monster_hp,
    spawn_monster,
    get_world_turn,
    get_monsters_at,
)

_MAGMA_HOUND = {"name": "Magma Hound", "hp": 50, "attack": 12, "xp_reward": 70,
                "loot": {"coin": 18, "ember_core": 1}}
_SKELETON = {"name": "Risen Skeleton", "hp": 22, "attack": 6, "xp_reward": 12,
             "loot": {"coin": 4}}

BOSS_MECHANICS: Dict[str, dict] = {
    "Molten Wyrm": {
        "phases": [
            {"at": 0.5, "enrage_mult": 1.5, "summon": _MAGMA_HOUND,
             "message": "The Molten Wyrm ENRAGES, its blows growing fiercer! A Magma Hound erupts to defend it!"},
            {"at": 0.25, "enrage_mult": 1.4, "heal_frac": 0.15, "summon": _MAGMA_HOUND,
             "message": "The Wyrm blazes white-hot, searing its own wounds shut and calling another hound!"},
        ],
    },
    "Cave Troll": {
        "regen_per_hit": 3,
        "phases": [
            {"at": 0.4, "enrage_mult": 1.5,
             "message": "The Cave Troll roars and flails in a wounded fury!"},
        ],
    },
    "Bone Knight": {
        "phases": [
            {"at": 0.5, "summon": _SKELETON,
             "message": "The Bone Knight raises a fallen warrior to fight at its side!"},
        ],
    },
}


def _phase_key(instance_id: str) -> str:
    return f"boss_phases_{instance_id}"


def _phases_done(instance_id: str) -> int:
    try:
        return int(get_world_state(_phase_key(instance_id)) or "0")
    except (TypeError, ValueError):
        return 0


def _current_attack(instance_id: str, location_id: str, fallback: int) -> int:
    for m in get_monsters_at(location_id):
        if m["instance_id"] == instance_id:
            return m["attack"]
    return fallback


def trigger_boss_on_hit(instance_id: str, result: dict) -> List[str]:
    """
    Called after a non-lethal hit on a monster. Applies regen and any phase
    transitions whose HP threshold was just crossed. Returns player-facing
    messages (empty if nothing happened).
    """
    name = result.get("name")
    mech = BOSS_MECHANICS.get(name or "")
    if not mech:
        return []

    hp = result.get("hp", 0)
    max_hp = result.get("max_hp") or 0
    if hp <= 0 or max_hp <= 0:
        return []

    messages: List[str] = []

    # Regeneration: heal a little after surviving a hit.
    regen = mech.get("regen_per_hit", 0)
    if regen:
        new_hp = min(max_hp, hp + regen)
        if new_hp > hp:
            set_monster_hp(instance_id, new_hp)
            hp = new_hp
            messages.append(f"The {name}'s wounds knit closed (+{regen} HP).")

    # Phase transitions (ordered; each fires once).
    phases = mech.get("phases", [])
    done = _phases_done(instance_id)
    for idx in range(done, len(phases)):
        phase = phases[idx]
        if hp > phase["at"] * max_hp:
            break  # not low enough for this (or later) phase yet

        set_world_state(_phase_key(instance_id), str(idx + 1))

        if "enrage_mult" in phase:
            cur = _current_attack(instance_id, result["location_id"], result.get("attack", 1))
            set_monster_attack(instance_id, int(cur * phase["enrage_mult"]))

        if "heal_frac" in phase:
            healed_hp = min(max_hp, hp + int(max_hp * phase["heal_frac"]))
            set_monster_hp(instance_id, healed_hp)
            hp = healed_hp

        summon = phase.get("summon")
        if summon:
            add_id = f"{instance_id}_add_{get_world_turn()}_{idx}"
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

        messages.append(phase["message"])

    return messages


def clear_boss_state(instance_id: str, name: str) -> None:
    """Reset phase tracking on death so a respawn behaves the same."""
    if name in BOSS_MECHANICS:
        set_world_state(_phase_key(instance_id), "0")
