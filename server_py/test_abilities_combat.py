"""
Tests for AoE (cleave), DoT (rupture/bleed), and the second-enemy aggro on
attack.

Run from server_py/:  python3 test_abilities_combat.py
"""

import os
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402
seed_world_monsters()

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_monsters_at, get_world_state, spawn_monster  # noqa: E402
from app.abilities import abilities_for_level  # noqa: E402
from app.dots import tick_bleeds  # noqa: E402
from app.engine.actions.use_ability import use_ability  # noqa: E402
from app.engine.actions.attack import attack  # noqa: E402


def mk(**kw):
    base = dict(player_id="p", location="deep_forest", level=12, xp=0, hp=600, max_hp=600,
                abilities=abilities_for_level(12), equipment={"armor": "dragonscale_armor"})
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def hp_of(loc, name):
    return next((m["hp"] for m in get_monsters_at(loc) if m["name"] == name), None)


def main() -> None:
    assert "cleave" in abilities_for_level(12) and "rupture" in abilities_for_level(12)
    print("PASS  cleave (lvl 8) and rupture (lvl 10) are learnable")

    # AoE: cleave hits every monster in the location.
    p = mk(player_id="a", location="deep_forest")  # Goblin + Wolf
    upsert_player(p)
    gob_before = hp_of("deep_forest", "Goblin")
    wolf_before = hp_of("deep_forest", "Wolf")
    r = use_ability(p, "cleave")
    assert r.ok, r.error
    gob_after = hp_of("deep_forest", "Goblin")
    wolf_after = hp_of("deep_forest", "Wolf")
    # both took damage (or died -> None)
    assert (gob_after is None or gob_after < gob_before)
    assert (wolf_after is None or wolf_after < wolf_before)
    print("PASS  cleave damages all enemies present")

    # DoT: rupture applies bleed; it ticks on subsequent attacks and never kills.
    pd = mk(player_id="d", location="cavern")  # cavern has the Cave Troll (cave_troll_1)
    upsert_player(pd)
    r = use_ability(pd, "rupture", "Cave Troll")
    assert r.ok and get_world_state("bleed_cave_troll_1"), r.error
    hp0 = hp_of("cavern", "Cave Troll")
    msgs = tick_bleeds("cavern")
    hp1 = hp_of("cavern", "Cave Troll")
    assert hp1 < hp0 and any("bleeds" in m for m in msgs), (hp0, hp1, msgs)
    # Bleed never kills: drop to 1 and confirm it floors.
    db.set_monster_hp("cave_troll_1", 1)
    db.set_world_state("bleed_cave_troll_1", "99:3")
    tick_bleeds("cavern")
    assert hp_of("cavern", "Cave Troll") == 1, "bleed must not kill"
    print("PASS  rupture bleeds over time and never kills")

    # Second-enemy aggro: attacking in a 2-monster room can pull the other in.
    def ensure(iid, name, hp, atk):
        if not any(m["instance_id"] == iid for m in get_monsters_at("deep_forest")):
            spawn_monster(instance_id=iid, location_id="deep_forest", name=name,
                          hp=hp, max_hp=hp, attack=atk, xp_reward=8, loot={})

    pa = mk(player_id="g", location="deep_forest", hp=2000)
    upsert_player(pa)
    saw_join = False
    for _ in range(60):
        ensure("goblin_1", "Goblin", 12, 3)
        ensure("wolf_1", "Wolf", 16, 4)  # keep a second aggressive enemy present
        r = attack(pa, "Goblin")
        if any("joins the fight" in m for m in r.messages):
            saw_join = True
            break
        if pa.location != "deep_forest":
            pa.location = "deep_forest"
    assert saw_join, "expected a second enemy to join over many attacks"
    print("PASS  attacking can aggro a second enemy present")

    print("\nALL ABILITY COMBAT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
