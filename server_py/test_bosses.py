"""
Offline tests for boss mechanics: the Molten Wyrm enrages and summons an add
once it drops below half HP, exactly once.

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


def wyrm():
    return next(m for m in get_monsters_at("magma_core") if m["name"] == "Molten Wyrm")


def main() -> None:
    # Above the threshold: no enrage.
    high = {"name": "Molten Wyrm", "hp": 80, "max_hp": 100, "attack": 18, "location_id": "magma_core"}
    assert trigger_boss_on_hit("nope_high", high) == []
    print("PASS  no enrage while above the HP threshold")

    # Bring the real wyrm below 50% and trigger via the boss hook.
    before_adds = count_monsters_at("magma_core")
    r = damage_monster("molten_wyrm_1", 60)  # 100 -> 40
    assert r and not r["killed"] and r["hp"] == 40 and r["max_hp"] == 100, r
    msgs = trigger_boss_on_hit("molten_wyrm_1", r)
    assert any("ENRAGES" in m for m in msgs) and any("Magma Hound" in m for m in msgs), msgs
    assert get_world_state("boss_enraged_molten_wyrm_1") == "true"
    assert wyrm()["attack"] == int(18 * 1.5)  # attack buffed
    assert count_monsters_at("magma_core") == before_adds + 1  # add summoned
    print("PASS  crossing 50% enrages (attack up) and summons an add")

    # Does not re-trigger.
    r2 = damage_monster("molten_wyrm_1", 5)  # 40 -> 35, still below threshold
    assert trigger_boss_on_hit("molten_wyrm_1", r2) == []
    print("PASS  enrage triggers only once")

    # Clearing state lets a future (respawned) boss enrage again.
    clear_boss_state("molten_wyrm_1", "Molten Wyrm")
    assert get_world_state("boss_enraged_molten_wyrm_1") == "false"
    print("PASS  boss state clears on death")

    # Integration: a tanky hero fights the wyrm and sees it enrage before it dies.
    db.DB_PATH = _t.name
    # fresh boss
    db.spawn_monster(instance_id="molten_wyrm_1", location_id="magma_core", name="Molten Wyrm",
                     hp=100, max_hp=100, attack=18, xp_reward=180,
                     loot={"coin": 120})
    db.set_world_state("boss_enraged_molten_wyrm_1", "false")
    hero = Player(player_id="boss", name="Slayer", location="magma_core", level=10,
                  hp=600, max_hp=600, xp=0, equipment={"armor": "dragonscale_armor"})
    upsert_player(hero)
    saw_enrage = False
    for _ in range(40):
        res = attack(hero, "Molten Wyrm")
        text = " ".join(res.messages)
        if "ENRAGES" in text:
            saw_enrage = True
        if "is defeated" in text or hero.location == "town_square":
            break
    assert saw_enrage, "expected the wyrm to enrage during the fight"
    print("PASS  wyrm enrages mid-fight in real combat")

    print("\nALL BOSS TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
