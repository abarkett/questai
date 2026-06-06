"""
Offline tests for the world-content expansion (Phase 4 slice 2).

Covers:
  - fresh seed populates the new dungeon locations and expands quest targets
  - version-aware seeding: new content lands in an existing (legacy) save
    without resurrecting slain originals
  - new exits are traversable
  - tough monsters retaliate with their own attack and can defeat/respawn a player

Run from server_py/:  python3 test_world_content.py
"""

import json
import os
import tempfile

import app.db as db

_tmps = []


def fresh_db() -> str:
    t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    t.close()
    _tmps.append(t.name)
    db.DB_PATH = t.name
    db.init_db()
    return t.name


fresh_db()  # set a DB before importing modules that touch it at call time

from app.engine.entities import seed_world_monsters, get_world_entities_at  # noqa: E402
from app.db import count_monsters_at, upsert_player  # noqa: E402
from app.world_quests import get_valid_quest_targets  # noqa: E402
from app.world import get_location  # noqa: E402
from app.types import Player  # noqa: E402
from app.engine.actions.attack import attack  # noqa: E402
from app.engine.actions.move import move  # noqa: E402


def test_fresh_seed():
    fresh_db()
    seed_world_monsters()
    assert count_monsters_at("forest") == 2
    assert count_monsters_at("deep_forest") == 2
    assert count_monsters_at("cavern") == 2
    vt = get_valid_quest_targets()["monsters"]
    for m in ["Rat", "Goblin", "Wolf", "Cave Spider", "Cave Troll"]:
        assert m in vt, (m, vt)
    print(f"PASS  fresh seed populates dungeon; quest targets = {vt}")


def test_legacy_migration():
    fresh_db()
    # Simulate an existing pre-content save: legacy flag set, rats already
    # dealt with (none in table), no instance tracking yet.
    db.set_world_state("monsters_seeded", "true")
    seed_world_monsters()
    assert count_monsters_at("forest") == 0, "legacy rats must NOT be resurrected"
    assert count_monsters_at("deep_forest") == 2, "new content should spawn"
    assert count_monsters_at("cavern") == 2
    seeded = set(json.loads(db.get_world_state("seeded_monster_instances")))
    assert {"rat_1", "rat_2", "goblin_1", "cave_troll_1"} <= seeded, seeded
    # Idempotent: running again spawns nothing new.
    seed_world_monsters()
    assert count_monsters_at("deep_forest") == 2
    print("PASS  legacy migration: new content added, no resurrection, idempotent")


def test_new_exits():
    fresh_db()
    seed_world_monsters()
    p = Player(player_id="m", name="M", location="forest", level=9, xp=9999, hp=99, max_hp=99)
    upsert_player(p)
    move(p, "deeper")
    assert p.location == "deep_forest", p.location
    move(p, "cave")
    assert p.location == "cavern", p.location
    print("PASS  new dungeon exits are traversable")


def test_tough_monster_danger():
    fresh_db()
    seed_world_monsters()
    p = Player(player_id="d", name="D", location="cavern", level=1, xp=0, hp=5, max_hp=5)
    upsert_player(p)
    r = attack(p, "Cave Troll")  # troll attack 8 vs 5 hp -> defeat + respawn
    assert p.location == "town_square", p.location
    assert p.hp == p.max_hp
    assert any("defeated" in m.lower() for m in r.messages), r.messages
    print("PASS  tough monster retaliates and can defeat/respawn the player")


def main():
    test_fresh_seed()
    test_legacy_migration()
    test_new_exits()
    test_tough_monster_danger()
    print("\nALL WORLD CONTENT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        for path in _tmps:
            try:
                os.unlink(path)
            except OSError:
                pass
