"""
Travel encounters: the road itself rolls dice.

Movement used to be a pure state transition — the most-repeated action in the
game, and perfectly predictable. Now roughly one move in five produces a
moment: a hidden cache, a wayside shrine, an ambush in dangerous country, a
traveler carrying news of the living world, or an omen. Encounters are
deterministic-engine content (RNG-injectable like combat); their *material*
ties into the other systems — caches yield local resources, travelers repeat
real world events, omens point at unopened frontiers.
"""

from __future__ import annotations

import random
from typing import List, Optional

from .ambush import has_aggressive, maybe_ambush
from .content import resource_at
from .items import get_item
from .status_effects import apply_effect
from .types import Player

ENCOUNTER_CHANCE = 0.22

_CACHE_FLAVOR = [
    "You spot a hollow beneath a root",
    "A loose stone shifts underfoot, revealing a nook",
    "Something glints in the mud off the path",
    "An abandoned pack lies half-buried nearby",
]

_SHRINE_FLAVOR = [
    "A weathered wayside shrine leans here, garlanded with old ribbon",
    "A small stone idol watches the path, its features worn smooth",
    "Someone has stacked a cairn here and left wildflowers",
]

_TRAVELER_KINDS = ["tinker", "pilgrim", "peddler", "deserter", "gravedigger"]

_OMEN_FLAVOR = [
    "A cold wind moves against the weather.",
    "Birds go quiet all at once, then resume as if embarrassed.",
    "For a moment, your shadow falls the wrong way.",
]


def _cache(player: Player, rng: random.Random) -> List[str]:
    flavor = rng.choice(_CACHE_FLAVOR)
    if rng.random() < 0.6:
        coins = rng.randint(2, 4 + player.level)
        player.inventory["coin"] = player.inventory.get("coin", 0) + coins
        return [f"{flavor} — {coins} coins inside!"]
    resource = resource_at(player.location) or "healing_herb"
    item = get_item(resource)
    name = item.name if item else resource
    player.inventory[resource] = player.inventory.get(resource, 0) + 1
    return [f"{flavor} — someone stashed a {name} here."]


def _shrine(player: Player, rng: random.Random) -> List[str]:
    flavor = rng.choice(_SHRINE_FLAVOR)
    messages = [f"{flavor}."]
    if player.hp < player.max_hp and rng.random() < 0.5:
        healed = min(4, player.max_hp - player.hp)
        player.hp += healed
        messages.append(f"You rest a moment in its calm. (+{healed} HP)")
    else:
        msg = apply_effect(player, "strength", 2, 5)
        messages.append("You leave a small offering and feel steadier for it."
                        + (f" {msg}" if msg else ""))
    return messages


def _traveler(player: Player, rng: random.Random) -> List[str]:
    kind = rng.choice(_TRAVELER_KINDS)
    from .echoes import rumor_lines

    rumors = rumor_lines(player, limit=5)
    if rumors and rng.random() < 0.7:
        rumor = rng.choice(rumors)
        return [f"A passing {kind} slows just long enough to talk: “{rumor}”"]
    player.inventory["healing_herb"] = player.inventory.get("healing_herb", 0) + 1
    return [f"A passing {kind} presses a healing herb into your hand. “For the road.”"]


def _omen(player: Player, rng: random.Random) -> List[str]:
    from .regiongen import frontier_at
    from .db import get_region_by_origin

    if frontier_at(player.location) and not get_region_by_origin(player.location):
        return ["The air here pulls at you, as if the land is holding a door shut. "
                "Something remains uncharted... (explore)"]
    return [rng.choice(_OMEN_FLAVOR)]


def maybe_travel_encounter(player: Player, *, rng: Optional[random.Random] = None) -> List[str]:
    """
    Roll for a moment on the road. Mutates the player (inventory, HP,
    effects — possibly a respawn, via ambush). Returns player-facing messages,
    or [] (most of the time).
    """
    r = rng or random.Random()
    if r.random() >= ENCOUNTER_CHANCE:
        return []

    dangerous = has_aggressive(player.location)
    # (encounter, weight) — danger shifts the odds toward trouble.
    table = [
        (_cache, 30),
        (_shrine, 18 if not dangerous else 10),
        (_traveler, 27 if not dangerous else 8),
        (_omen, 15),
    ]
    if dangerous:
        table.append((None, 32))  # ambush

    total = sum(w for _, w in table)
    roll = r.uniform(0, total)
    for encounter, weight in table:
        roll -= weight
        if roll <= 0:
            if encounter is None:
                msgs = maybe_ambush(player, rng=r, chance=1.0)
                return (["You are not alone on this path."] + msgs) if msgs else []
            return encounter(player, r)
    return []
