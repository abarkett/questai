"""
Companions: recruited allies who travel and fight alongside you.

Design split, consistent with the rest of the overhaul:

  * **Code is the referee.** Combat contribution, loyalty and levelling are
    deterministic and injectable-free, so a companion's effect on a fight is
    exactly reproducible and unit-testable.
  * **Miriel is the personality.** What a companion *says* (joining, parting,
    growing closer) is AI-voiced — but best-effort, with a written fallback,
    because an ally's banter is flavour, not the hard-required location prose.

A companion is a *personal* ally inspired by a world NPC; the original stays
in place for everyone else. One companion at a time.
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional, Tuple

from .types import Player, Companion

# A signing bonus, paid in coin — recruiting an ally should cost something so
# the choice has weight and wealth has one more place to go.
RECRUIT_COST = 25
MAX_LOYALTY = 100

# NPCs whose job anchors the world stay put — you can't walk off with the
# shopkeeper or the quest giver. Everyone else is fair game.
NON_RECRUITABLE_ROLES = {"shop", "quest_giver", "arc_giver"}

ARCHETYPE_TITLE = {
    "vanguard": "Vanguard",
    "mender": "Mender",
    "outrider": "Outrider",
}

ARCHETYPE_BLURB = {
    "vanguard": "Fights at the front — lands a solid blow every round you press an attack.",
    "mender": "Keeps you standing — tends your wounds each round of a fight.",
    "outrider": "Watches your flank — turns aside some of every blow, and harries the enemy.",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def is_recruitable(npc: dict) -> bool:
    return bool(npc) and npc.get("type") == "npc" and npc.get("role") not in NON_RECRUITABLE_ROLES


def pick_archetype(npc: dict) -> str:
    """Stable for a given NPC: the same person always joins as the same kind of
    ally. Healers mend; everyone else is split deterministically by id."""
    if npc.get("role") == "healer":
        return "mender"
    h = int(hashlib.sha1(npc["id"].encode()).hexdigest(), 16)
    return "vanguard" if h % 2 == 0 else "outrider"


def companion_level(c: Companion) -> int:
    """Loyalty 0..100 maps to levels 1..5."""
    return 1 + min(c.loyalty, MAX_LOYALTY) // 25


# --- Player-archetype synergies (see app/archetypes.py) ---
# Your own path colours what your ally can do: a Warden's steadiness bolsters
# their support, a Trickster's aggression drives their blows, a Channeler's
# attunement quickens the bond. One signature bonus per path, applied here.
SYNERGY_BLURB = {
    "warden": "Your steadfastness bolsters them: their healing is +50% and their guard is firmer.",
    "trickster": "Your aggression drives them: their strikes hit +50% harder.",
    "channeler": "Your attunement quickens the bond: their loyalty grows twice as fast.",
}


def _path(player: Optional[Player]) -> Optional[str]:
    return getattr(player, "archetype", None) if player is not None else None


def synergy_line(player: Optional[Player]) -> Optional[str]:
    return SYNERGY_BLURB.get(_path(player) or "")


def companion_attack(c: Companion, player: Optional[Player] = None) -> int:
    """Flat damage the ally deals to a monster each round (no crits)."""
    lvl = companion_level(c)
    if c.archetype == "vanguard":
        base = 3 + 2 * lvl
    elif c.archetype == "outrider":
        base = 1 + lvl
    else:
        return 0  # menders don't strike
    if _path(player) == "trickster":
        base = int(base * 1.5 + 0.5)  # half-up: a +50% bonus must never round down
    return base


def companion_heal(c: Companion, player: Optional[Player] = None) -> int:
    if c.archetype != "mender":
        return 0
    base = 2 + companion_level(c)
    if _path(player) == "warden":
        base = int(base * 1.5 + 0.5)  # half-up: a +50% bonus must never round down
    return base


def guard_mult(c: Optional[Companion], player: Optional[Player] = None) -> float:
    """Multiplier applied to the damage the player takes while this ally is at
    their side. Outriders soak the most; a vanguard's presence covers a little.
    A Warden's steadiness makes any ally's guard firmer."""
    if not c:
        return 1.0
    if c.archetype == "outrider":
        mult = max(0.5, 1.0 - 0.08 * companion_level(c))
    elif c.archetype == "vanguard":
        mult = 0.92
    else:
        mult = 1.0
    if _path(player) == "warden" and mult < 1.0:
        mult = max(0.4, mult - 0.08)
    return mult


def gain_loyalty(c: Companion, amount: int = 1) -> bool:
    """Raise loyalty (capped). Returns True if the companion gained a level."""
    before = companion_level(c)
    c.loyalty = min(MAX_LOYALTY, c.loyalty + amount)
    return companion_level(c) > before


def companion_combat_turn(player: Player, entity_id: str) -> Tuple[list[str], Optional[dict]]:
    """
    The companion's action for one round, taken after the player's own strike
    (and only while the monster still lives).

    Returns (messages, kill_result) — kill_result is the `damage_monster`
    result dict when the ally lands the finishing blow, else None.
    """
    c = player.companion
    if not c:
        return [], None

    # Menders mend instead of swinging — but only when there's a wound to close.
    heal = companion_heal(c, player)
    if heal:
        if player.hp < player.max_hp:
            healed = min(heal, player.max_hp - player.hp)
            player.hp += healed
            return [f"{c.name} tends your wounds (+{healed} HP)."], None
        return [], None

    atk = companion_attack(c, player)
    if atk <= 0:
        return [], None

    from .db import damage_monster
    result = damage_monster(entity_id, atk)
    if result is None:
        return [], None  # the monster was already gone
    msg = f"{c.name} strikes the {result['name']} for {atk} damage."
    return [msg], (result if result["killed"] else None)


def reward_after_victory(player: Player) -> list[str]:
    """Bump the companion's loyalty after a won fight; voice a line on level-up."""
    c = player.companion
    if not c:
        return []
    c.battles += 1
    # A Channeler's bond deepens twice as fast.
    gain = 2 if _path(player) == "channeler" else 1
    if gain_loyalty(c, gain):
        from .miriel_companion import companion_line
        line = companion_line(
            player, c, "level_up",
            fallback=f"{c.name} meets your eye. \"We're getting good at this.\"",
        )
        return [f'{c.name}: "{line}"' if line else f"{c.name} stands a little prouder at your side."]
    return []
