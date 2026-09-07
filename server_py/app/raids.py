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
    modify_raid_boss,
    get_raid_contributions,
    get_raid_contribution,
    get_player,
    upsert_player,
    set_world_state,
    get_world_state,
    log_world_event,
    spawn_monster,
    get_world_turn,
)
from .types import Player, ActionResponse
from .combat import roll_damage
from .progression import total_attack_damage, defense_bonus
from .status_effects import damage_modifier

# Where a felled adventurer wakes — shared with the rest of combat.
RESPAWN_LOCATION = "town_square"

# The realm musters here against its great threats. The active raid boss
# manifests at this location, and you must be present to strike it — a beat of
# travel and gathering, not a button you can mash from a tavern.
WARFRONT_LOC = "warfront"

# Smallest payout for anyone who landed a blow, however small their share.
MIN_REWARD = 8
# What the one who lands the final blow earns on top of their share.
FINISHER_BONUS = 50

# The rotation of great threats. HP, attack and the reward pool all scale with
# the world's level (see _scaled) so a raid stays a genuine group effort as the
# shared world grows in power.
# Adds summoned during a boss's phases. They spawn at the Warfront as ordinary
# monsters, so players cut them down with the normal `fight` verb.
_CINDER_WHELP = {"name": "Cinder Whelp", "hp": 18, "attack": 6, "xp_reward": 14, "loot": {"coin": 6}}
_DROWNED_THRALL = {"name": "Drowned Thrall", "hp": 24, "attack": 7, "xp_reward": 16, "loot": {"coin": 7}}
_DUST_SHARD = {"name": "Animate Shard", "hp": 28, "attack": 8, "xp_reward": 18, "loot": {"coin": 8}}

RAID_BOSSES = [
    {
        "key": "ashen_dragon",
        "name": "The Ashen Dragon",
        "title": "Cinderwing, the Sky's Ruin",
        "description": (
            "A dragon of cinder and ash wheels over the realm, raining fire on "
            "every road. No blade reaches it alone — but a realm of blades might."
        ),
        "lair_name": "The Warfront — under the Ashen Dragon",
        "lair_desc": (
            "The Ashen Dragon wheels low over the muster-ground, ash falling like "
            "grey snow. Spears bristle skyward. This is where the realm makes its stand."
        ),
        "base_hp": 800,
        "base_attack": 14,
        "base_reward": 600,
        "trophy": "dragon_heart",
        "effect": {"ashen_dragon_felled": "true"},
        "completion_text": "The Ashen Dragon falls from the sky in a rain of cinders. The realm exhales.",
        "phases": [
            {"at": 0.66, "enrage_add": 4, "summon": _CINDER_WHELP,
             "message": "The Ashen Dragon shrieks and beats its wings — embers fall, and a Cinder Whelp claws its way up to defend it!"},
            {"at": 0.33, "enrage_add": 6, "heal_frac": 0.10, "summon": _CINDER_WHELP,
             "message": "The Dragon banks hard, searing its own wounds shut with fire and spitting forth another Cinder Whelp!"},
        ],
    },
    {
        "key": "drowned_king",
        "name": "The Drowned King",
        "title": "He Who Rose From the Deep",
        "description": (
            "A crowned horror walks up out of the floodwaters, the drowned at its "
            "heel. The whole realm must answer, or be pulled under with it."
        ),
        "lair_name": "The Warfront — before the Drowned King",
        "lair_desc": (
            "Black floodwater laps over the muster-ground, and the Drowned King "
            "stands waist-deep in it, crown streaming. The drowned shamble at his heel."
        ),
        "base_hp": 1000,
        "base_attack": 16,
        "base_reward": 750,
        "trophy": "coral_crown",
        "effect": {"drowned_king_felled": "true"},
        "completion_text": "The Drowned King sinks back beneath still water. The floods recede.",
        "phases": [
            {"at": 0.66, "enrage_add": 4, "summon": _DROWNED_THRALL,
             "message": "The Drowned King raises a hand and the water gives up a Drowned Thrall to fight at his side!"},
            {"at": 0.33, "enrage_add": 6, "heal_frac": 0.12, "summon": _DROWNED_THRALL,
             "message": "The King sinks beneath the flood, rising healed and furious — and another Thrall surfaces beside him!"},
        ],
    },
    {
        "key": "dust_colossus",
        "name": "The Colossus of Dust",
        "title": "The Walking Mountain",
        "description": (
            "A mountain stands up and begins to walk, grinding the wilds to powder "
            "beneath it. It will take every hand in the realm to bring it down."
        ),
        "lair_name": "The Warfront — beneath the Colossus",
        "lair_desc": (
            "The Colossus of Dust looms over the muster-ground, each step a "
            "thunderclap that throws up choking clouds. Shards of it break loose and move."
        ),
        "base_hp": 1300,
        "base_attack": 18,
        "base_reward": 900,
        "trophy": "colossus_core",
        "effect": {"dust_colossus_felled": "true"},
        "completion_text": "The Colossus of Dust crumbles into a hill of sand. The ground stops shaking.",
        "phases": [
            {"at": 0.66, "enrage_add": 5, "summon": _DUST_SHARD,
             "message": "A great crack runs up the Colossus — a piece of it shears off as an Animate Shard and lurches at you!"},
            {"at": 0.33, "enrage_add": 7, "heal_frac": 0.10, "summon": _DUST_SHARD,
             "message": "The Colossus draws the dust back into itself, mending — and sheds another Animate Shard as it does!"},
        ],
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


def _spec_for(boss: dict) -> dict:
    for spec in RAID_BOSSES:
        if spec["name"] == boss["name"]:
            return spec
    return {}


def lair_location_view(loc_id: str) -> Optional[tuple[str, str]]:
    """Name/description for the Warfront reflecting whichever boss now holds it.
    Returns None for any other location (or when no raid is active)."""
    if loc_id != WARFRONT_LOC:
        return None
    # Standing at the muster-ground itself: make sure a threat is present so the
    # ground never reads as empty when the panel says a boss looms.
    ensure_active_raid()
    boss = get_active_raid_boss()
    if not boss:
        return None
    spec = _spec_for(boss)
    return (
        spec.get("lair_name") or f"The Warfront — {boss['name']}",
        spec.get("lair_desc") or boss["description"],
    )


def _phase_key(raid_id: str) -> str:
    return f"raid_phases_{raid_id}"


def _phases_done(raid_id: str) -> int:
    try:
        return int(get_world_state(_phase_key(raid_id)) or "0")
    except (TypeError, ValueError):
        return 0


def _trigger_raid_phases(boss: dict, current_hp: int) -> List[str]:
    """Fire any phase whose HP threshold was just crossed (each fires once):
    enrage the boss, let it self-heal, and summon adds to the Warfront."""
    spec = _spec_for(boss)
    phases = spec.get("phases", [])
    max_hp = int(boss["max_hp"])
    if not phases or current_hp <= 0 or max_hp <= 0:
        return []

    raid_id = boss["raid_id"]
    done = _phases_done(raid_id)
    messages: List[str] = []
    hp = current_hp

    for idx in range(done, len(phases)):
        phase = phases[idx]
        if hp > phase["at"] * max_hp:
            break  # not low enough for this (or any later) phase yet

        set_world_state(_phase_key(raid_id), str(idx + 1))

        attack_add = int(phase.get("enrage_add", 0))
        heal = int(max_hp * phase["heal_frac"]) if "heal_frac" in phase else 0
        if attack_add or heal:
            new = modify_raid_boss(raid_id, attack_add=attack_add, heal=heal)
            if new:
                hp = new["hp"]

        summon = phase.get("summon")
        if summon:
            add_id = f"{raid_id}_add_{get_world_turn()}_{idx}"
            spawn_monster(
                instance_id=add_id,
                location_id=WARFRONT_LOC,
                name=summon["name"],
                hp=summon["hp"],
                max_hp=summon["hp"],
                attack=summon["attack"],
                xp_reward=summon["xp_reward"],
                loot=summon.get("loot", {}),
            )

        messages.append(phase["message"])

    return messages


def _strike_damage(player: Player, rng: random.Random) -> tuple[int, bool, int]:
    """The player's blow against the boss, plus any companion contribution.
    Returns (player_damage, is_crit, companion_damage)."""
    base = total_attack_damage(player) + damage_modifier(player)
    dmg, is_crit = roll_damage(base, rng=rng)
    comp = 0
    if player.companion:
        from .companions import companion_attack
        comp = companion_attack(player.companion, player)
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
        from .defeat import apply_defeat
        return apply_defeat(player, boss["name"])
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

    # With the boss down, its leftover summoned adds disperse from the Warfront.
    messages.extend(_clear_raid_adds(boss["raid_id"]))

    # The horizon is never empty for long.
    ensure_active_raid()
    return messages


def _clear_raid_adds(raid_id: str) -> List[str]:
    """Remove any of this raid's still-living summoned adds from the Warfront."""
    from .db import get_monsters_at, remove_monster
    prefix = f"{raid_id}_add_"
    leftover = [m for m in get_monsters_at(WARFRONT_LOC)
                if str(m["instance_id"]).startswith(prefix)]
    for m in leftover:
        remove_monster(m["instance_id"])
    if leftover:
        return [f"With the boss fallen, {len(leftover)} of its remaining minions scatter."]
    return []


def strike_raid(player: Player, *, rng: Optional[random.Random] = None) -> ActionResponse:
    """Loose a blow at the realm's great threat."""
    from .engine.state_view import build_action_state

    ensure_active_raid()
    boss = get_active_raid_boss()
    if not boss:
        return ActionResponse(ok=False, error="No great threat looms over the realm right now.")

    if player.location != WARFRONT_LOC:
        return ActionResponse(
            ok=False,
            error=(
                f"{boss['name']} holds the Warfront. Travel there to make your "
                "stand — `go warfront` from the Town Square."
            ),
        )

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
        # The wounded boss may rage, heal, or call up adds — then it strikes back.
        messages.extend(_trigger_raid_phases(boss, result["hp"]))
        messages.extend(_boss_retaliation(player, boss))
        fresh = get_active_raid_boss()
        hp_now = fresh["hp"] if fresh else result["hp"]
        messages.append(
            f"{boss['name']}: {hp_now}/{result['max_hp']} HP — "
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
        "location": WARFRONT_LOC,
        "at_lair": player.location == WARFRONT_LOC,
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
        at_lair = player.location == WARFRONT_LOC
        call = (
            "You stand at the Warfront — strike it with `raid strike`."
            if at_lair else
            "It holds the Warfront — `go warfront` to make your stand."
        )
        messages = [
            f"{boss['name']} — {boss['title']}",
            boss["description"],
            f"HP: {boss['hp']}/{boss['max_hp']} ({pct}%). "
            f"Your blows: {get_raid_contribution(boss['raid_id'], player.player_id)}. "
            f"Spoils pool: {boss['reward_pool']} coins, split by damage done.",
            call,
        ]
        if contribs:
            top = ", ".join(f"{c['player_name']} ({c['damage']})" for c in contribs[:3])
            messages.append(f"Most damage: {top}.")

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
