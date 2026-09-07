"""
Active combat abilities, learned automatically as the player levels up.

Kept as plain data so new abilities are a one-line addition. Offensive
abilities apply a damage multiplier through the normal attack path; support
abilities (e.g. self-heal) resolve in the use_ability action.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel


AbilityKind = Literal["attack", "heal", "aoe", "dot", "buff"]


class Ability(BaseModel):
    ability_id: str
    name: str
    learn_level: int
    kind: AbilityKind
    cooldown_s: int
    description: str
    cost: int = 1                        # skill points to learn (capstones cost more)
    multiplier: Optional[float] = None   # attack/aoe: damage multiplier
    heal_frac: Optional[float] = None    # heal: fraction of max HP restored
    dot_damage: Optional[int] = None     # dot: damage per tick
    dot_turns: Optional[int] = None      # dot: number of ticks
    buff_effect: Optional[str] = None    # buff: status effect id to apply to self
    buff_magnitude: Optional[int] = None
    buff_turns: Optional[int] = None


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
    # ----- Deeper pool: mid-tier picks (L10) and capstones (L12, cost 2) -----
    "rallying_cry": Ability(
        ability_id="rallying_cry",
        name="Rallying Cry",
        learn_level=10,
        kind="buff",
        buff_effect="strength",
        buff_magnitude=3,
        buff_turns=4,
        cooldown_s=90,
        description="Steel yourself: +3 damage to your blows for your next 4 strikes.",
    ),
    "crushing_blow": Ability(
        ability_id="crushing_blow",
        name="Crushing Blow",
        learn_level=12,
        kind="attack",
        multiplier=3.0,
        cooldown_s=100,
        cost=2,
        description="A shattering strike dealing 3.0x damage. (Capstone — costs 2 skill points.)",
    ),
    "lacerate": Ability(
        ability_id="lacerate",
        name="Lacerate",
        learn_level=10,
        kind="dot",
        dot_damage=8,
        dot_turns=4,
        cooldown_s=60,
        description="Open a deep wound: 8 bleed on each of your next 4 strikes.",
    ),
    "eviscerate": Ability(
        ability_id="eviscerate",
        name="Eviscerate",
        learn_level=12,
        kind="attack",
        multiplier=3.2,
        cooldown_s=110,
        cost=2,
        description="A killing thrust dealing 3.2x damage. (Capstone — costs 2 skill points.)",
    ),
    "chain_lightning": Ability(
        ability_id="chain_lightning",
        name="Chain Lightning",
        learn_level=10,
        kind="aoe",
        multiplier=1.7,
        cooldown_s=70,
        description="Arc lightning through every enemy present for 1.7x damage each.",
    ),
    "inferno": Ability(
        ability_id="inferno",
        name="Inferno",
        learn_level=12,
        kind="aoe",
        multiplier=2.2,
        cooldown_s=120,
        cost=2,
        description="Engulf every enemy in fire for 2.2x damage each. (Capstone — costs 2 skill points.)",
    ),
}


def get_ability(ability_id: str) -> Optional[Ability]:
    return ABILITIES.get(ability_id)


def abilities_for_level(level: int) -> List[str]:
    """All ability ids a character of this level should know."""
    return [aid for aid, a in ABILITIES.items() if a.learn_level <= level]
