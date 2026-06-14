"""
Active combat abilities, learned automatically as the player levels up.

Kept as plain data so new abilities are a one-line addition. Offensive
abilities apply a damage multiplier through the normal attack path; support
abilities (e.g. self-heal) resolve in the use_ability action.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel


AbilityKind = Literal["attack", "heal", "aoe", "dot"]


class Ability(BaseModel):
    ability_id: str
    name: str
    learn_level: int
    kind: AbilityKind
    cooldown_s: int
    description: str
    multiplier: Optional[float] = None   # attack/aoe: damage multiplier
    heal_frac: Optional[float] = None    # heal: fraction of max HP restored
    dot_damage: Optional[int] = None     # dot: damage per tick
    dot_turns: Optional[int] = None      # dot: number of ticks


ABILITIES: Dict[str, Ability] = {
    "power_strike": Ability(
        ability_id="power_strike",
        name="Power Strike",
        learn_level=2,
        kind="attack",
        multiplier=1.8,
        cooldown_s=45,
        description="A heavy blow dealing 1.8x damage.",
    ),
    "second_wind": Ability(
        ability_id="second_wind",
        name="Second Wind",
        learn_level=4,
        kind="heal",
        heal_frac=0.4,
        cooldown_s=120,
        description="Catch your breath, restoring 40% of max HP.",
    ),
    "rend": Ability(
        ability_id="rend",
        name="Rend",
        learn_level=6,
        kind="attack",
        multiplier=2.4,
        cooldown_s=75,
        description="A savage strike dealing 2.4x damage.",
    ),
    "cleave": Ability(
        ability_id="cleave",
        name="Cleave",
        learn_level=8,
        kind="aoe",
        multiplier=1.2,
        cooldown_s=60,
        description="Strike every enemy present for 1.2x damage each.",
    ),
    "rupture": Ability(
        ability_id="rupture",
        name="Rupture",
        learn_level=10,
        kind="dot",
        dot_damage=5,
        dot_turns=3,
        cooldown_s=50,
        description="Wound a foe so it bleeds 5 damage on each of your next 3 strikes.",
    ),
    # ----- Archetype-specific abilities (see app/archetypes.py pools) -----
    "bulwark": Ability(
        ability_id="bulwark",
        name="Bulwark",
        learn_level=8,
        kind="heal",
        heal_frac=0.35,
        cooldown_s=90,
        description="Set your feet and weather the storm, restoring 35% of max HP.",
    ),
    "quick_strike": Ability(
        ability_id="quick_strike",
        name="Quick Strike",
        learn_level=2,
        kind="attack",
        multiplier=1.4,
        cooldown_s=25,
        description="A fast, low-cooldown jab dealing 1.4x damage.",
    ),
    "firebolt": Ability(
        ability_id="firebolt",
        name="Firebolt",
        learn_level=2,
        kind="attack",
        multiplier=1.7,
        cooldown_s=35,
        description="Hurl a bolt of fire for 1.7x damage.",
    ),
}


def get_ability(ability_id: str) -> Optional[Ability]:
    return ABILITIES.get(ability_id)


def abilities_for_level(level: int) -> List[str]:
    """All ability ids a character of this level should know."""
    return [aid for aid, a in ABILITIES.items() if a.learn_level <= level]
