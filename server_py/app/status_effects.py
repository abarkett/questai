"""
Combat status effects: damage-over-time, heal-over-time, and damage buffs/
debuffs that tick as the player takes combat actions.

Stored on the player as {effect_id: {"turns": int, "magnitude": int}} and
ticked at the start of each combat action, so a lingering poison can chase a
fleeing player and a sipped elixir empowers the next few swings.
"""

from __future__ import annotations

from typing import Dict, List

from .types import Player


# kind: "dot" (damage/tick), "hot" (heal/tick),
#       "buff_damage" (+dmg while active), "debuff_damage" (-dmg while active)
EFFECT_DEFS: Dict[str, Dict] = {
    "poison": {"name": "Poison", "kind": "dot", "negative": True},
    "burn": {"name": "Burn", "kind": "dot", "negative": True},
    "weaken": {"name": "Weaken", "kind": "debuff_damage", "negative": True},
    "regen": {"name": "Regeneration", "kind": "hot", "negative": False},
    "strength": {"name": "Strength", "kind": "buff_damage", "negative": False},
}


def is_known(effect_id: str) -> bool:
    return effect_id in EFFECT_DEFS


def is_negative(effect_id: str) -> bool:
    d = EFFECT_DEFS.get(effect_id)
    return bool(d and d["negative"])


def apply_effect(player: Player, effect_id: str, magnitude: int, turns: int) -> str:
    """Apply or refresh an effect (keeps the stronger magnitude and longer duration)."""
    if not is_known(effect_id):
        return ""
    existing = player.status_effects.get(effect_id)
    if existing:
        magnitude = max(magnitude, int(existing.get("magnitude", 0)))
        turns = max(turns, int(existing.get("turns", 0)))
    player.status_effects[effect_id] = {"magnitude": magnitude, "turns": turns}
    return f"You are afflicted with {EFFECT_DEFS[effect_id]['name']}!" if is_negative(effect_id) \
        else f"You feel {EFFECT_DEFS[effect_id]['name']}!"


def tick_effects(player: Player) -> List[str]:
    """
    Advance all effects one tick: apply DoT/HoT, decrement durations, drop
    expired ones. Does NOT handle death; the caller checks hp afterward.
    """
    messages: List[str] = []
    for effect_id in list(player.status_effects.keys()):
        state = player.status_effects[effect_id]
        d = EFFECT_DEFS.get(effect_id)
        if not d:
            del player.status_effects[effect_id]
            continue

        mag = int(state.get("magnitude", 0))
        if d["kind"] == "dot":
            player.hp = max(0, player.hp - mag)
            messages.append(f"{d['name']} deals {mag} damage.")
        elif d["kind"] == "hot":
            healed = min(mag, player.max_hp - player.hp)
            player.hp += healed
            if healed > 0:
                messages.append(f"{d['name']} restores {healed} HP.")

        state["turns"] = int(state.get("turns", 0)) - 1
        if state["turns"] <= 0:
            del player.status_effects[effect_id]
            messages.append(f"{d['name']} wears off.")

    return messages


def damage_modifier(player: Player) -> int:
    """Net damage change from active buffs/debuffs."""
    total = 0
    for effect_id, state in player.status_effects.items():
        d = EFFECT_DEFS.get(effect_id)
        if not d:
            continue
        if d["kind"] == "buff_damage":
            total += int(state.get("magnitude", 0))
        elif d["kind"] == "debuff_damage":
            total -= int(state.get("magnitude", 0))
    return total


def clear_negative(player: Player) -> List[str]:
    """Remove all negative effects (used by antidotes/cures)."""
    removed = [eid for eid in player.status_effects if is_negative(eid)]
    for eid in removed:
        del player.status_effects[eid]
    return [f"{EFFECT_DEFS[eid]['name']} is cured." for eid in removed]


def describe(player: Player) -> List[str]:
    """Human-readable lines for the stats screen."""
    lines = []
    for effect_id, state in player.status_effects.items():
        d = EFFECT_DEFS.get(effect_id)
        if not d:
            continue
        mag = int(state.get("magnitude", 0))
        turns = int(state.get("turns", 0))
        lines.append(f"  - {d['name']} ({mag}, {turns} turns)")
    return lines
