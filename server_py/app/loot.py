"""
Bonus loot: the slot-machine sparkle on top of fixed drop tables.

Every kill has a small chance of a trinket (sellable curios) and a much rarer
chance of a relic — and finding a relic is world news: it leaves an echo at
the spot and enters the rumor pool, so one player's lucky drop is everyone's
story. Deterministic and RNG-injectable like the rest of the engine.
"""

from __future__ import annotations

import random
from typing import List, Optional

from .items import get_item
from .types import Player

TRINKET_CHANCE = 0.06
RELIC_CHANCE = 0.01

TRINKETS = [
    "bent_locket", "carved_die", "tin_whistle",
    "moonstone_ring", "silvered_button", "glass_eye",
]
RELICS = ["tarnished_crown", "dragonbone_idol", "star_metal_shard"]


def roll_bonus_loot(player: Player, monster_name: str,
                    *, rng: Optional[random.Random] = None) -> List[str]:
    """Roll trinket/relic drops for a kill. Mutates inventory; returns messages."""
    r = rng or random.Random()
    roll = r.random()

    if roll < RELIC_CHANCE:
        relic_id = r.choice(RELICS)
        relic = get_item(relic_id)
        player.inventory[relic_id] = player.inventory.get(relic_id, 0) + 1
        from .echoes import record_deed
        from .db import log_world_event
        record_deed(player, player.location,
                    f"{player.name} unearthed the {relic.name} here", kind="relic")
        log_world_event(
            event_type="world_evolution",
            location_id=player.location,
            data={
                "player_id": player.player_id,
                "player_name": player.name,
                "description": f"{player.name} unearthed the {relic.name}!",
            },
        )
        return [
            f"Something gleams among the {monster_name}'s leavings... the {relic.name}!",
            "A relic! Word of this will travel.",
        ]

    if roll < RELIC_CHANCE + TRINKET_CHANCE:
        trinket_id = r.choice(TRINKETS)
        trinket = get_item(trinket_id)
        player.inventory[trinket_id] = player.inventory.get(trinket_id, 0) + 1
        return [f"Tucked in the {monster_name}'s leavings: a {trinket.name}."]

    return []
