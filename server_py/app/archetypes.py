"""
Character archetypes: the shape of who you are in a fight.

Where the rest of progression is shared, your archetype is the one early choice
that makes two characters play differently. It does two things:

  * a **passive** that colours every fight (a Warden shrugs off blows, a
    Trickster hits harder, a Channeler's powers come back faster), and
  * an **ability pool** — the moves you're allowed to learn. You don't get them
    all for free with levels any more; levelling grants *skill points*, and you
    spend them (via `learn`) on the abilities your path offers, at your pace.

Code is the referee: the passives fold into the existing combat maths
(`total_attack_damage`, `defense_bonus`) and a single cooldown helper, so an
archetype's effect is exact and lives in one place.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

from .types import Player


class Archetype(BaseModel):
    id: str
    name: str
    description: str
    passive: str                       # human-readable passive summary
    attack_bonus: int = 0
    defense_bonus: int = 0
    cooldown_mult: float = 1.0         # <1.0 = abilities recharge faster
    # Abilities this path can learn, paired with the level they unlock at.
    pool: List[Tuple[str, int]] = []


ARCHETYPES: Dict[str, Archetype] = {
    "warden": Archetype(
        id="warden",
        name="Warden",
        description="A stalwart who stands the line — soaks blows and grinds foes down.",
        passive="Stalwart: +3 defense to every blow you take.",
        defense_bonus=3,
        pool=[("power_strike", 2), ("second_wind", 4), ("rend", 6), ("bulwark", 8)],
    ),
    "trickster": Archetype(
        id="trickster",
        name="Trickster",
        description="A quick, vicious fighter who opens wounds and presses the advantage.",
        passive="Deadly: +3 damage to every blow you land.",
        attack_bonus=3,
        pool=[("quick_strike", 2), ("rupture", 4), ("power_strike", 6), ("rend", 8)],
    ),
    "channeler": Archetype(
        id="channeler",
        name="Channeler",
        description="A wielder of raw power — fire, force, and the breath to fight on.",
        passive="Attuned: your abilities recharge 30% faster.",
        cooldown_mult=0.7,
        pool=[("firebolt", 2), ("second_wind", 4), ("cleave", 6), ("rupture", 8)],
    ),
}

# Players from before archetypes (archetype = None) fall back to a generalist
# pool of the original auto-granted abilities, so nothing they had breaks.
_GENERALIST_POOL: List[Tuple[str, int]] = [
    ("power_strike", 2), ("second_wind", 4), ("rend", 6), ("cleave", 8), ("rupture", 10),
]


def get_archetype(archetype_id: Optional[str]) -> Optional[Archetype]:
    if not archetype_id:
        return None
    return ARCHETYPES.get(archetype_id)


def archetype_attack_bonus(player: Player) -> int:
    a = get_archetype(getattr(player, "archetype", None))
    return a.attack_bonus if a else 0


def archetype_defense_bonus(player: Player) -> int:
    a = get_archetype(getattr(player, "archetype", None))
    return a.defense_bonus if a else 0


def cooldown_ms(player: Player, cooldown_s: int) -> int:
    """An ability's cooldown for this player, in ms, after the archetype passive."""
    a = get_archetype(getattr(player, "archetype", None))
    mult = a.cooldown_mult if a else 1.0
    return int(cooldown_s * 1000 * mult)


def pool_for(player: Player) -> List[Tuple[str, int]]:
    a = get_archetype(getattr(player, "archetype", None))
    return a.pool if a else _GENERALIST_POOL


def learnable(player: Player) -> List[Tuple[str, int]]:
    """Abilities the player could learn right now: in their pool, level met,
    not already known. Returns (ability_id, level_req)."""
    known = set(player.abilities or [])
    out = []
    for aid, req in pool_for(player):
        if aid not in known and player.level >= req:
            out.append((aid, req))
    return out


def next_unlock(player: Player) -> Optional[Tuple[str, int]]:
    """The next pool ability gated by level (not yet reachable), for nudges."""
    known = set(player.abilities or [])
    for aid, req in pool_for(player):
        if aid not in known and player.level < req:
            return (aid, req)
    return None
