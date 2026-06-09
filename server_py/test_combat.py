"""
Offline tests for combat texture (Phase 4 slice 5): damage variance + crits
and the level-gated active ability system.

Run from server_py/:  python3 test_combat.py
"""

import os
import random
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402
seed_world_monsters()

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player  # noqa: E402
from app.combat import roll_damage, VARIANCE, CRIT_MULT  # noqa: E402
from app.progression import apply_xp, total_xp_for_level  # noqa: E402
from app.abilities import abilities_for_level  # noqa: E402
from app.engine.actions.use_ability import use_ability  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="p", location="town_square", level=1, xp=0, hp=20, max_hp=20)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    # roll_damage stays in-bounds, never below 1, and can crit.
    rng = random.Random(42)
    base = 20
    lo = max(1, int(base * (1 - VARIANCE)))
    hi_crit = int(int(base * (1 + VARIANCE)) * CRIT_MULT)
    saw_crit = False
    for _ in range(2000):
        dmg, crit = roll_damage(base, rng=rng)
        assert 1 <= dmg <= hi_crit, (dmg, lo, hi_crit)
        saw_crit = saw_crit or crit
    assert roll_damage(1, rng=rng)[0] >= 1  # tiny base never underflows
    assert saw_crit, "expected at least one crit across 2000 rolls"
    print("PASS  damage rolls stay in bounds, floor at 1, and crit")

    # Abilities unlock by level via apply_xp.
    p = mk(player_id="a")
    upsert_player(p)
    assert p.abilities == []
    apply_xp(p, total_xp_for_level(2))
    assert "power_strike" in p.abilities and p.level == 2, p.abilities
    apply_xp(p, total_xp_for_level(6) - p.xp)
    assert set(p.abilities) == set(abilities_for_level(6)), p.abilities
    print(f"PASS  abilities unlock on level up: {p.abilities}")

    # Can't use an unknown or unlearned ability.
    lvl1 = mk(player_id="n", location="deep_forest")
    upsert_player(lvl1)
    assert use_ability(lvl1, "fireball").ok is False           # unknown
    assert use_ability(lvl1, "power_strike", "Goblin").ok is False  # not learned yet
    print("PASS  unknown / unlearned abilities are rejected")

    # Offensive ability hits a monster, then goes on cooldown.
    # Level-2 hero vs the 40-HP Cave Troll: small hits that can't kill it mid-test.
    hero = mk(player_id="h", location="cavern", level=2, hp=200, max_hp=200,
              abilities=abilities_for_level(2), equipment={"armor": "steel_armor"})
    upsert_player(hero)
    r = use_ability(hero, "power_strike", "Cave Troll")
    assert r.ok and "Power Strike" in " ".join(r.messages), r.messages
    assert hero.ability_cooldowns.get("power_strike", 0) > 0
    r2 = use_ability(hero, "power_strike", "Cave Troll")
    assert r2.ok is False and "cooldown" in (r2.error or "").lower(), r2.error
    print("PASS  offensive ability hits then enforces cooldown")

    # Cooldown clears once the timer passes.
    hero.ability_cooldowns["power_strike"] = 0
    upsert_player(hero)
    assert use_ability(hero, "power_strike", "Cave Troll").ok is True
    print("PASS  ability usable again after cooldown expires")

    # Support ability heals and respects its own cooldown.
    healer = mk(player_id="z", level=4, hp=5, max_hp=30, abilities=abilities_for_level(4))
    upsert_player(healer)
    r = use_ability(healer, "second_wind")
    assert r.ok and healer.hp > 5, (r.error, healer.hp)
    assert use_ability(healer, "second_wind").ok is False  # now on cooldown
    print(f"PASS  self-heal ability restores HP (now {healer.hp}/{healer.max_hp})")

    # Abilities + cooldowns persist through the DB.
    loaded = get_player("h")
    assert "power_strike" in loaded.abilities, loaded.abilities
    assert "power_strike" in loaded.ability_cooldowns
    print("PASS  abilities and cooldowns persist through the DB")

    print("\nALL COMBAT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
