"""
Co-op raid bosses: the realm's great shared threats.

Where a community goal is chipped down by everyone's *ordinary* play, a raid
boss is chipped down by everyone's *deliberate* blows: a single monster with a
huge HP pool that no one player can fell alone in a session. You `raid` to
strike it; the boss strikes back. When it finally falls, **every player who
landed a blow is paid a share of the spoils, the finisher is named in the
world's history, and the realm visibly changes** — then the next threat rises,
so the world always has a great beast on the horizon.

This is the async social layer made loud: the bounty board's escrow-and-pay
and the community goal's contribute-and-reward, aimed at one dramatic target
that a universe of casual, mostly-offline players brings down together.
"""

from __future__ import annotations

import random
import time
from typing import List, Optional

from .db import (
    create_raid_boss,
    get_active_raid_boss,
    count_raid_bosses,
    damage_raid_boss,
    get_raid_contributions,
    get_raid_contribution,
    get_player,
    upsert_player,
    set_world_state,
    log_world_event,
)
from .types import Player, ActionResponse
from .combat import roll_damage
from .progression import total_attack_damage, defense_bonus
from .status_effects import damage_modifier

# Where a felled adventurer wakes — shared with the rest of combat.
RESPAWN_LOCATION = "town_square"

# Smallest payout for anyone who landed a blow, however small their share.
MIN_REWARD = 8
# What the one who lands the final blow earns on top of their share.
FINISHER_BONUS = 50

# The rotation of great threats. HP, attack and the reward pool all scale with
# the world's level (see _scaled) so a raid stays a genuine group effort as the
# shared world grows in power.
RAID_BOSSES = [
    {
        "key": "ashen_dragon",
        "name": "The Ashen Dragon",
        "title": "Cinderwing, the Sky's Ruin",
        "description": (
            "A dragon of cinder and ash wheels over the realm, raining fire on "
            "every road. No blade reaches it alone — but a realm of blades might."
        ),
        "base_hp": 800,
        "base_attack": 14,
        "base_reward": 600,
        "trophy": "dragon_heart",
        "effect": {"ashen_dragon_felled": "true"},
        "completion_text": "The Ashen Dragon falls from the sky in a rain of cinders. The realm exhales.",
    },
    {
        "key": "drowned_king",
        "name": "The Drowned King",
        "title": "He Who Rose From the Deep",
        "description": (
            "A crowned horror walks up out of the floodwaters, the drowned at its "
            "heel. The whole realm must answer, or be pulled under with it."
        ),
        "base_hp": 1000,
        "base_attack": 16,
        "base_reward": 750,
        "trophy": "coral_crown",
        "effect": {"drowned_king_felled": "true"},
        "completion_text": "The Drowned King sinks back beneath still water. The floods recede.",
    },
    {
        "key": "dust_colossus",
        "name": "The Colossus of Dust",
        "title": "The Walking Mountain",
        "description": (
            "A mountain stands up and begins to walk, grinding the wilds to powder "
            "beneath it. It will take every hand in the realm to bring it down."
        ),
        "base_hp": 1300,
        "base_attack": 18,
        "base_reward": 900,
        "trophy": "colossus_core",
        "effect": {"dust_colossus_felled": "true"},
        "completion_text": "The Colossus of Dust crumbles into a hill of sand. The ground stops shaking.",
    },
]


def now_ms() -> int:
    return int(time.time() * 1000)


def _world_level() -> int:
    from .engine.entities import world_level
    try:
        return max(1, world_level())
    except Exception:
        return 1


def _scaled(base: int, level: int, per_level: float) -> int:
    """Scale a base number by the world's level."""
    return int(round(base * (1 + per_level * (level - 1))))


def _seed_raid(index: int) -> None:
    spec = RAID_BOSSES[index % len(RAID_BOSSES)]
    level = _world_level()
    raid_id = f"raid_{index}"
    hp = _scaled(spec["base_hp"], level, 0.4)
    attack = _scaled(spec["base_attack"], level, 0.25)
    reward = _scaled(spec["base_reward"], level, 0.4)
    create_raid_boss(
        raid_id=raid_id,
        name=spec["name"],
        title=spec["title"],
        description=spec["description"],
        hp=hp,
        attack=attack,
        reward_pool=reward,
        trophy=spec["trophy"],
        effect=spec["effect"],
        completion_text=spec["completion_text"],
    )
    log_world_event(
        event_type="raid_started",
        location_id=None,
        data={
            "raid_id": raid_id,
            "description": f"A great threat rises over the realm: {spec['name']} — {spec['title']}.",
        },
    )


def ensure_active_raid() -> None:
    """Keep one great threat looming: seed the next boss whenever none is active."""
    if not get_active_raid_boss():
        _seed_raid(count_raid_bosses())


def _strike_damage(player: Player, rng: random.Random) -> tuple[int, bool, int]:
    """The player's blow against the boss, plus any companion contribution.
    Returns (player_damage, is_crit, companion_damage)."""
    base = total_attack_damage(player) + damage_modifier(player)
    dmg, is_crit = roll_damage(base, rng=rng)
    comp = 0
    if player.companion:
        from .companions import companion_attack
        comp = companion_attack(player.companion)
    return dmg, is_crit, comp


# A single counter-blow can never take more than this fraction of your health,
# so a raid is a fight you withdraw from to heal — not one that two-shots you.
# It keeps the threat real while leaving room for many players to chip in.
RETALIATION_CAP_FRAC = 0.25


def _boss_retaliation(player: Player, boss: dict) -> List[str]:
    """The boss answers a blow. It can throw a player down (no loot loss — that's
    a stake for a later system), which sends them home to recover."""
    raw = max(1, int(boss["attack"]) - defense_bonus(player))
    hit = min(raw, max(1, int(player.max_hp * RETALIATION_CAP_FRAC)))
    player.hp -= hit
    if player.hp <= 0:
        player.hp = player.max_hp
        player.location = RESPAWN_LOCATION
        player.last_defeated_at = now_ms()
        player.status_effects.clear()
        return [f"{boss['name']} hurls you down. You wake, battered, back in the Town Square."]
    return [f"{boss['name']} answers, raking you for {hit} damage."]


def _resolve_defeat(boss: dict, finisher: Player, rng: random.Random) -> List[str]:
    """Pay every contributor a share of the spoils, crown the finisher, flip the
    world, and write the kill into history. The finisher is mutated in-memory;
    the caller persists them."""
    messages: List[str] = []
    contributions = get_raid_contributions(boss["raid_id"])
    total_damage = sum(c["damage"] for c in contributions) or 1
    pool = int(boss.get("reward_pool") or 0)

    for c in contributions:
        share = max(MIN_REWARD, pool * c["damage"] // total_damage)
        is_finisher = c["player_id"] == finisher.player_id
        if is_finisher:
            finisher.inventory["coin"] = finisher.inventory.get("coin", 0) + share
            messages.append(f"Your share of the spoils: {share} coins.")
            continue
        p = get_player(c["player_id"])
        if p:
            p.inventory["coin"] = p.inventory.get("coin", 0) + share
            upsert_player(p)

    # The finisher's reward: a bonus and the boss's trophy.
    finisher.inventory["coin"] = finisher.inventory.get("coin", 0) + FINISHER_BONUS
    trophy = boss.get("trophy")
    if trophy:
        finisher.inventory[trophy] = finisher.inventory.get(trophy, 0) + 1
        messages.append(f"For the killing blow you claim {FINISHER_BONUS} coins and a {trophy}.")
    else:
        messages.append(f"For the killing blow you claim {FINISHER_BONUS} coins.")

    # The world changes, and remembers.
    for key, value in (boss.get("effect") or {}).items():
        set_world_state(key, value)

    text = boss.get("completion_text") or f"{boss['name']} is defeated!"
    messages.append(text)
    messages.append(f"{boss['name']} falls — and {finisher.name} struck the final blow!")
    log_world_event(
        event_type="raid_defeated",
        location_id=None,
        data={
            "raid_id": boss["raid_id"],
            "finisher": finisher.name,
            "contributors": len(contributions),
            "description": f"{text} Felled by {len(contributions)} hands; {finisher.name} struck it down.",
        },
    )
    from .echoes import record_deed
    record_deed(finisher, finisher.location, f"{finisher.name} struck down {boss['name']}!", kind="raid")

    # The horizon is never empty for long.
    ensure_active_raid()
    return messages


def strike_raid(player: Player, *, rng: Optional[random.Random] = None) -> ActionResponse:
    """Loose a blow at the realm's great threat."""
    from .engine.state_view import build_action_state

    ensure_active_raid()
    boss = get_active_raid_boss()
    if not boss:
        return ActionResponse(ok=False, error="No great threat looms over the realm right now.")

    rng = rng or random
    dmg, is_crit, comp = _strike_damage(player, rng)
    total = dmg + comp

    result = damage_raid_boss(boss["raid_id"], total, player.player_id, player.name)
    if result is None:
        # Someone else landed the final blow between our read and our strike.
        return ActionResponse(
            ok=True,
            messages=[f"{boss['name']} has already fallen. You lower your blade."],
            state=build_action_state(player, scene_dirty=False),
        )

    crit = " (CRITICAL HIT!)" if is_crit else ""
    messages = [f"You strike {boss['name']} for {dmg} damage.{crit}"]
    if comp and player.companion:
        messages.append(f"{player.companion.name} adds {comp} damage.")

    if result["finisher"]:
        messages.extend(_resolve_defeat(boss, player, rng))
    elif result["killed"]:
        # The boss died, but another striker's call flipped it — credit stands.
        messages.append(f"{boss['name']} falls as your blow lands among many!")
    else:
        messages.extend(_boss_retaliation(player, boss))
        messages.append(
            f"{boss['name']}: {result['hp']}/{result['max_hp']} HP — "
            f"your blows so far: {get_raid_contribution(boss['raid_id'], player.player_id)}."
        )

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )


def raid_summary(player: Player) -> Optional[dict]:
    """Compact raid state for the web client. Seeds the looming threat if none
    is active, so the realm always has a great beast on the horizon."""
    ensure_active_raid()
    boss = get_active_raid_boss()
    if not boss:
        return None
    contribs = get_raid_contributions(boss["raid_id"])
    return {
        "raid_id": boss["raid_id"],
        "name": boss["name"],
        "title": boss["title"],
        "hp": boss["hp"],
        "max_hp": boss["max_hp"],
        "your_damage": get_raid_contribution(boss["raid_id"], player.player_id),
        "reward_pool": boss["reward_pool"],
        "top": [{"name": c["player_name"], "damage": c["damage"]} for c in contribs[:3]],
    }


def raid_status(player: Player) -> ActionResponse:
    """Player-facing overview of the looming threat (a passive read)."""
    from .engine.state_view import build_action_state

    ensure_active_raid()
    boss = get_active_raid_boss()
    messages: List[str]
    if not boss:
        messages = ["The realm is at peace. No great threat looms... for now."]
    else:
        pct = min(100, 100 * boss["hp"] // max(1, boss["max_hp"]))
        contribs = get_raid_contributions(boss["raid_id"])
        messages = [
            f"{boss['name']} — {boss['title']}",
            boss["description"],
            f"HP: {boss['hp']}/{boss['max_hp']} ({pct}%). "
            f"Your blows: {get_raid_contribution(boss['raid_id'], player.player_id)}. "
            f"Spoils pool: {boss['reward_pool']} coins, split by damage done.",
            "Strike it with `raid strike`.",
        ]
        if contribs:
            top = ", ".join(f"{c['player_name']} ({c['damage']})" for c in contribs[:3])
            messages.append(f"Most damage: {top}.")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
