"""
Ambush risk: doing something careless (e.g. gathering) near a hostile monster
may provoke an attack. Reusable so other "vulnerable" actions can opt in.
"""

from __future__ import annotations

import random
import time
from typing import List, Optional

from .db import get_monsters_at, get_world_state
from .content import monster_aggro, monster_inflicts
from .progression import defense_bonus
from .status_effects import apply_effect
from .types import Player

AMBUSH_CHANCE = 0.5
RESPAWN_LOCATION = "town_square"


def aggressive_monsters_at(location_id: str) -> list:
    return [m for m in get_monsters_at(location_id) if monster_aggro(m["name"])]


def has_aggressive(location_id: str) -> bool:
    return bool(aggressive_monsters_at(location_id))


def maybe_ambush(
    player: Player,
    *,
    rng: Optional[random.Random] = None,
    exclude_id: Optional[str] = None,
    chance: float = AMBUSH_CHANCE,
) -> List[str]:
    """
    With some chance, a hostile monster present (other than `exclude_id`)
    strikes the player. Mutates the player (hp, effects, possible respawn).
    Returns player-facing messages.
    """
    r = rng or random
    hostiles = [m for m in aggressive_monsters_at(player.location)
                if m["instance_id"] != exclude_id]
    if not hostiles or r.random() >= chance:
        return []

    mon = hostiles[0]
    dmg = max(1, mon["attack"] - defense_bonus(player))
    player.hp -= dmg
    messages = [f"The {mon['name']} catches you off guard for {dmg} damage!"]

    inflict = monster_inflicts(mon["name"])
    if inflict and player.hp > 0:
        msg = apply_effect(player, inflict["effect"], inflict.get("magnitude", 1), inflict.get("turns", 1))
        if msg:
            messages.append(msg)

    if player.hp <= 0:
        from .defeat import apply_defeat
        messages.extend(apply_defeat(player, f"the {mon['name']}"))

    return messages
