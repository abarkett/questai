"""
Offline tests for the persistent, DB-backed world entities (Phase 3).

Covers:
  - seeding monsters from the static catalog (once)
  - NPCs stay static; monsters come from the DB
  - atomic damage: no double-kill, no lost damage
  - monsters stay dead across re-seeding (true persistence)
  - remove_entity deletes a monster instance

Run from server_py/:  python3 test_world_persistence.py
"""

import os
import tempfile

import app.db as db

_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp.close()
db.DB_PATH = _tmp.name
db.init_db()

from app.engine.entities import (  # noqa: E402
    seed_world_monsters,
    get_world_entities_at,
    get_entities_at,
    remove_entity,
)
from app.db import damage_monster, count_monsters_at, spawn_monster  # noqa: E402


def _names(ents):
    return sorted(e.name for e in ents)


def main() -> None:
    seed_world_monsters()

    # Forest seeded with 2 rats (monsters from DB)
    forest = get_world_entities_at("forest")
    monsters = [e for e in forest if e.type == "monster"]
    assert len(monsters) == 2 and all(m.name == "Rat" for m in monsters), forest
    print("PASS  seeded 2 forest rats")

    # Town square: static NPCs only, no monsters
    town = get_world_entities_at("town_square")
    assert town and all(e.type == "npc" for e in town), town
    assert count_monsters_at("town_square") == 0
    print(f"PASS  town_square npc-only: {_names(town)}")

    # Serialized view exposes monster hp
    serialized = get_entities_at("forest")
    rat = next(e for e in serialized if e["type"] == "monster")
    assert rat["hp"] == 5, serialized
    print("PASS  serialized monster hp present")

    # Atomic damage: partial, then kill, then gone (no double-kill)
    r1 = damage_monster("rat_1", 3)
    assert r1 and r1["killed"] is False and r1["hp"] == 2, r1
    r2 = damage_monster("rat_1", 3)
    assert r2 and r2["killed"] is True, r2
    r3 = damage_monster("rat_1", 3)
    assert r3 is None, r3
    print("PASS  atomic damage: no double-kill, no lost damage")

    # Kill the other rat -> forest clears
    killed = damage_monster("rat_2", 99)
    assert killed and killed["killed"], killed
    assert count_monsters_at("forest") == 0
    assert [e for e in get_world_entities_at("forest") if e.type == "monster"] == []
    print("PASS  forest cleared after kills")

    # Persistence: re-seeding must NOT resurrect slain monsters
    seed_world_monsters()
    assert count_monsters_at("forest") == 0, "re-seed must not resurrect"
    print("PASS  re-seed does not resurrect (persistent across restarts)")

    # remove_entity deletes a monster instance
    spawn_monster("test_goblin", "forest", "Goblin", 8, 8, 3, 5, {"coin": 2})
    assert count_monsters_at("forest") == 1
    remove_entity("forest", "test_goblin")
    assert count_monsters_at("forest") == 0
    print("PASS  remove_entity deletes monster")

    print("\nALL WORLD PERSISTENCE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_tmp.name)
