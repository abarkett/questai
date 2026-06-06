"""
Monster damage-over-time (bleed), stored in world_state keyed by instance id
so it survives restarts. Bleed never kills (floors HP at 1) so the player still
lands the finishing blow and gets the loot/XP.
"""

from __future__ import annotations

from typing import List

from .db import get_monsters_at, set_monster_hp, get_world_state, set_world_state


def _key(instance_id: str) -> str:
    return f"bleed_{instance_id}"


def apply_bleed(instance_id: str, dmg: int, turns: int) -> None:
    set_world_state(_key(instance_id), f"{dmg}:{turns}")


def clear_bleed(instance_id: str) -> None:
    set_world_state(_key(instance_id), "")


def tick_bleeds(location_id: str) -> List[str]:
    """Apply one bleed tick to every bleeding monster at the location."""
    messages: List[str] = []
    for m in get_monsters_at(location_id):
        raw = get_world_state(_key(m["instance_id"]))
        if not raw:
            continue
        try:
            dmg_s, turns_s = raw.split(":")
            dmg, turns = int(dmg_s), int(turns_s)
        except (ValueError, AttributeError):
            clear_bleed(m["instance_id"])
            continue
        new_hp = max(1, m["hp"] - dmg)  # bleed weakens but never kills
        set_monster_hp(m["instance_id"], new_hp)
        turns -= 1
        if turns <= 0:
            clear_bleed(m["instance_id"])
        else:
            set_world_state(_key(m["instance_id"]), f"{dmg}:{turns}")
        messages.append(f"The {m['name']} bleeds for {dmg} damage.")
    return messages
