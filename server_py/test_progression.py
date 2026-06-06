"""
Offline tests for XP/leveling and combat rewards (Phase 4, slice 1).

Run from server_py/:  python3 test_progression.py
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
from app.progression import (  # noqa: E402
    total_xp_for_level,
    level_for_xp,
    max_hp_for_level,
    attack_damage,
    apply_xp,
)
from app.engine.actions.attack import attack  # noqa: E402
from app.db import upsert_player  # noqa: E402


def main() -> None:
    # Curve / level / damage formulas
    assert (total_xp_for_level(1), total_xp_for_level(2), total_xp_for_level(3)) == (0, 20, 60)
    assert [level_for_xp(x) for x in (0, 19, 20, 59, 60)] == [1, 1, 2, 2, 3]
    assert (max_hp_for_level(1), max_hp_for_level(2)) == (10, 15)
    assert (attack_damage(1), attack_damage(2), attack_damage(5)) == (3, 4, 7)
    print("PASS  curve / level / damage formulas")

    # Level-up restores HP to the new max
    p = Player(player_id="x", name="X", location="town_square", level=1, xp=0, hp=10, max_hp=10)
    msgs = apply_xp(p, 20)
    assert (p.level, p.max_hp, p.hp) == (2, 15, 15), (p.level, p.max_hp, p.hp)
    assert any("level 2" in m for m in msgs), msgs
    print("PASS  apply_xp levels up and full-heals")

    # Multi-level jump
    p2 = Player(player_id="y", name="Y", location="town_square", level=1, xp=0, hp=10, max_hp=10)
    apply_xp(p2, 60)
    assert p2.level == 3, p2.level
    print("PASS  apply_xp handles multi-level jumps")

    # Combat grants xp + loot on kill
    pf = Player(player_id="f", name="F", location="forest", level=1, xp=0, hp=10, max_hp=10)
    upsert_player(pf)
    attack(pf, "Rat")          # first hit (rat 5 -> 2)
    r = attack(pf, "Rat")      # second hit kills (2 -> -1)
    assert pf.xp == 2, pf.xp
    assert pf.inventory.get("coin", 0) >= 1 and pf.inventory.get("healing_herb", 0) >= 1, pf.inventory
    assert any("defeated" in m for m in r.messages) and any("XP" in m for m in r.messages), r.messages
    print(f"PASS  kill grants xp + loot: inv={dict(pf.inventory)} xp={pf.xp}")

    print("\nALL PROGRESSION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
