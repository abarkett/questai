"""
Tests for level-scaled monster stats: respawns scale to the world level, but
basic foes stay weak-ish (capped, gentle curve).

Run from server_py/:  python3 test_scaling.py
"""

import os
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import (  # noqa: E402
    seed_world_monsters, respawn_due_monsters, record_monster_death, scale_stats,
    MONSTER_RESPAWN_MS,
)
seed_world_monsters()

from app.db import remove_monster, set_world_state, get_monsters_at, monster_exists  # noqa: E402


def hp_of(loc, name):
    return next((m["hp"] for m in get_monsters_at(loc) if m["name"] == name), None)


def main() -> None:
    # Scaling curve: no change at level 1; gentle growth; capped; rats stay weak.
    assert scale_stats(5, 2, 2, 1) == (5, 2, 2)
    hp12, atk12, xp12 = scale_stats(5, 2, 2, 12)
    assert 8 <= hp12 <= 12, hp12          # rat ~8-9 at level 12 (not trivial-zero, not huge)
    hp99, _, _ = scale_stats(5, 2, 2, 99)
    assert hp99 <= 15, hp99               # capped: a rat is never a wall
    big, _, _ = scale_stats(40, 8, 50, 30)
    assert big > 40                       # tougher monsters scale up meaningfully
    print(f"PASS  scaling curve: rat 5 -> {hp12} (lvl 12), {hp99} (lvl 99); troll 40 -> {big} (lvl 30)")

    # A monster respawns scaled to the current world level.
    base = hp_of("deep_forest", "Goblin")
    assert base == 12, base               # seeded at world level 1
    remove_monster("goblin_1")
    record_monster_death("goblin_1")
    set_world_state("died_goblin_1", "1")  # long ago -> due
    set_world_state("world_level", "15")
    respawn_due_monsters()
    scaled = hp_of("deep_forest", "Goblin")
    assert scaled and scaled > base, (base, scaled)
    print(f"PASS  respawn scales to world level: Goblin {base} -> {scaled} at world level 15")

    print("\nALL SCALING TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
