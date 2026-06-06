"""
Offline tests for boss mechanics: phase transitions (enrage / heal / summon)
and per-hit regeneration. Each phase fires once and state resets on death.

Run from server_py/:  python3 test_bosses.py
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

from app.db import (  # noqa: E402
    damage_monster, get_monsters_at, count_monsters_at, get_world_state, upsert_player,
)
from app.bosses import trigger_boss_on_hit, clear_boss_state  # noqa: E402
from app.types import Player  # noqa: E402
from app.engine.actions.attack import attack  # noqa: E402


def mon(loc, name):
    return next(m for m in get_monsters_at(loc) if m["name"] == name)


def main() -> None:
    # Above threshold: nothing happens.
    high = {"name": "Molten Wyrm", "hp": 80, "max_hp": 100, "attack": 18, "location_id": "magma_core"}
    assert trigger_boss_on_hit("nope", high) == []
    print("PASS  no phase fires above the threshold")

    # Molten Wyrm phase 1 at 50%: enrage (+attack) and summon an add.
    adds0 = count_monsters_at("magma_core")
    r = damage_monster("molten_wyrm_1", 60)  # 100 -> 40
    msgs = trigger_boss_on_hit("molten_wyrm_1", r)
    assert any("ENRAGES" in m for m in msgs), msgs
    assert mon("magma_core", "Molten Wyrm")["attack"] == int(18 * 1.5)
    assert count_monsters_at("magma_core") == adds0 + 1
    assert get_world_state("boss_phases_molten_wyrm_1") == "1"
    print("PASS  Wyrm phase 1: enrage + summon")

    # Between phases: nothing new.
    r = damage_monster("molten_wyrm_1", 5)   # 40 -> 35
    assert trigger_boss_on_hit("molten_wyrm_1", r) == []
    print("PASS  no re-trigger between phases")

    # Phase 2 at 25%: heal (HP goes UP), enrage again, summon again.
    adds1 = count_monsters_at("magma_core")
    r = damage_monster("molten_wyrm_1", 15)  # 35 -> 20
    msgs = trigger_boss_on_hit("molten_wyrm_1", r)
    assert msgs, "phase 2 should fire"
    assert mon("magma_core", "Molten Wyrm")["hp"] > 20, "should self-heal"
    assert mon("magma_core", "Molten Wyrm")["attack"] == int(int(18 * 1.5) * 1.4)
    assert count_monsters_at("magma_core") == adds1 + 1
    assert get_world_state("boss_phases_molten_wyrm_1") == "2"
    print("PASS  Wyrm phase 2: self-heal + enrage + summon")

    # Cave Troll regenerates after each hit, and enrages below 40%.
    r = damage_monster("cave_troll_1", 10)   # 40 -> 30
    msgs = trigger_boss_on_hit("cave_troll_1", r)
    assert any("knit closed" in m for m in msgs), msgs
    assert mon("cavern", "Cave Troll")["hp"] == 33, mon("cavern", "Cave Troll")["hp"]
    r = damage_monster("cave_troll_1", 20)   # 33 -> 13 (regen -> 16, == 40% threshold)
    msgs = trigger_boss_on_hit("cave_troll_1", r)
    assert any("fury" in m for m in msgs), msgs
    assert mon("cavern", "Cave Troll")["attack"] == int(8 * 1.5)
    print("PASS  Cave Troll regenerates and enrages")

    # Bone Knight raises an add at 50%.
    before = count_monsters_at("underdeep")
    r = damage_monster("bone_knight_1", 30)  # 55 -> 25
    msgs = trigger_boss_on_hit("bone_knight_1", r)
    assert any("raises" in m for m in msgs), msgs
    assert count_monsters_at("underdeep") == before + 1
    print("PASS  Bone Knight summons a skeleton")

    # State clears on death.
    clear_boss_state("molten_wyrm_1", "Molten Wyrm")
    assert get_world_state("boss_phases_molten_wyrm_1") == "0"
    print("PASS  boss phase state clears on death")

    # Integration: a tanky hero sees the wyrm enrage during a real fight.
    db.spawn_monster(instance_id="molten_wyrm_1", location_id="magma_core", name="Molten Wyrm",
                     hp=100, max_hp=100, attack=18, xp_reward=180, loot={"coin": 120})
    db.set_world_state("boss_phases_molten_wyrm_1", "0")
    hero = Player(player_id="boss", name="Slayer", location="magma_core", level=10,
                  hp=800, max_hp=800, xp=0, equipment={"armor": "dragonscale_armor"})
    upsert_player(hero)
    saw = False
    for _ in range(60):
        res = attack(hero, "Molten Wyrm")
        if "ENRAGES" in " ".join(res.messages):
            saw = True
        if "is defeated" in " ".join(res.messages) or hero.location == "town_square":
            break
    assert saw, "expected the wyrm to enrage in a real fight"
    print("PASS  wyrm enrages mid-fight")

    print("\nALL BOSS TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
