"""
Character progression: XP, leveling, and level-scaled combat.

A single source of truth for the level curve so combat, the UI, and any future
systems agree. XP is a running total that never resets; level is derived from
it. Leveling raises max HP (and full-heals) and increases attack damage, so
fighting and questing make the character meaningfully stronger.
"""

from __future__ import annotations

from typing import List

from .types import Player

BASE_MAX_HP = 10        # max HP at level 1 (matches new-player creation)
MAX_HP_PER_LEVEL = 5    # +max HP per level gained
BASE_DAMAGE = 3         # attack damage at level 1
XP_CURVE = 10           # total XP to reach level L is XP_CURVE * (L-1) * L


def total_xp_for_level(level: int) -> int:
    """Total accumulated XP required to be at `level` (level 1 == 0 XP)."""
    if level <= 1:
        return 0
    return XP_CURVE * (level - 1) * level


def level_for_xp(xp: int) -> int:
    """Highest level whose XP threshold is satisfied by `xp`."""
    level = 1
    while total_xp_for_level(level + 1) <= xp:
        level += 1
    return level


def max_hp_for_level(level: int) -> int:
    return BASE_MAX_HP + MAX_HP_PER_LEVEL * (level - 1)


def attack_damage(level: int) -> int:
    """Base damage a player deals per hit, scaled by level (before gear)."""
    return BASE_DAMAGE + (level - 1)


def weapon_bonus(player: Player) -> int:
    """Bonus attack damage from the equipped weapon."""
    from .items import get_item

    item = get_item(player.equipment.get("weapon", "")) if player.equipment else None
    return (item.damage or 0) if item else 0


def defense_bonus(player: Player) -> int:
    """Flat damage reduction from the equipped armor."""
    from .items import get_item

    item = get_item(player.equipment.get("armor", "")) if player.equipment else None
    return (item.defense or 0) if item else 0


def total_attack_damage(player: Player) -> int:
    """Full per-hit damage: level scaling plus equipped weapon."""
    return attack_damage(player.level) + weapon_bonus(player)


def xp_to_next_level(player: Player) -> int:
    """XP remaining until the player's next level (0 if already past a boundary)."""
    return max(0, total_xp_for_level(player.level + 1) - player.xp)


def apply_xp(player: Player, amount: int) -> List[str]:
    """
    Award XP and process any level-ups in place. Returns player-facing messages.
    Handles multi-level jumps; a level-up restores HP to the new maximum.
    """
    messages: List[str] = []
    if amount <= 0:
        return messages

    player.xp += amount
    messages.append(f"You gain {amount} XP.")

    new_level = level_for_xp(player.xp)
    if new_level > player.level:
        player.level = new_level
        player.max_hp = max_hp_for_level(new_level)
        player.hp = player.max_hp  # full heal on level up
        messages.append(f"You reached level {new_level}! Max HP is now {player.max_hp}.")
        messages.extend(_learn_new_abilities(player))

    return messages


def _learn_new_abilities(player: Player) -> List[str]:
    """Grant any abilities newly unlocked by the player's level. Returns messages."""
    from .abilities import abilities_for_level, get_ability

    messages: List[str] = []
    for aid in abilities_for_level(player.level):
        if aid not in player.abilities:
            player.abilities.append(aid)
            ability = get_ability(aid)
            if ability:
                messages.append(f"You learned a new ability: {ability.name}!")
    return messages
