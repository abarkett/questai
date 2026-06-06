"""
Tests for dynamic location descriptions: time-of-day flavor that shifts with
the world clock, presence-aware prose, and indoor/outdoor handling.
(Miriel is disabled offline, so the deterministic layer is exercised.)

Run from server_py/:  python3 test_descriptions.py
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

from app.descriptions import (  # noqa: E402
    ambient_flavor, presence_flavor, deterministic_description, maybe_ai_description,
)
from app.world import get_location  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player  # noqa: E402
from app.engine.actions.look import look  # noqa: E402


def main() -> None:
    # Time-of-day flavor rotates outdoors and is absent indoors.
    f0 = ambient_flavor("forest", 0)
    f_later = ambient_flavor("forest", 12 * 3)  # a few buckets later
    assert f0 and f_later and f0 != f_later, (f0, f_later)
    assert ambient_flavor("tavern", 0) is None  # indoor: no day/night line
    print(f"PASS  outdoor time-of-day flavor rotates: '{f0}' -> '{f_later}'")

    # Presence flavor reflects who's here and whether they're hostile.
    hostile = presence_flavor([{"type": "monster", "name": "Goblin"}])
    assert hostile and "watches you" in hostile, hostile
    passive = presence_flavor([{"type": "monster", "name": "Rat"}])
    assert passive and "little mind" in passive, passive
    assert presence_flavor([{"type": "npc", "name": "Old Merchant"}]) is None
    print("PASS  presence flavor: hostile vs passive vs none")

    # Deterministic description composes base + ambient + presence.
    d = deterministic_description("A forest.", "forest", [{"type": "monster", "name": "Wolf"}], 0)
    assert d.startswith("A forest.") and "Wolf" in d and "Dawn" in d, d
    print("PASS  deterministic description composes base + flavor")

    # Miriel disabled offline -> AI description returns None (fallback path).
    p = Player(player_id="p", name="P", location="forest", level=3, xp=0, hp=20, max_hp=20)
    assert maybe_ai_description(p, get_location("forest"), [], "A forest.") is None
    print("PASS  AI description is a no-op when Miriel is disabled")

    # look() produces a description that changes as turns pass (different bucket).
    upsert_player(p)
    db.set_world_turn(0) if hasattr(db, "set_world_turn") else None
    desc_a = look(p).messages[1]
    # advance the world clock into another time-of-day bucket
    for _ in range(40):
        db.increment_world_turn()
    desc_b = look(p).messages[1]
    assert desc_a != desc_b, (desc_a, desc_b)
    print("PASS  look description shifts as the world clock advances")

    print("\nALL DESCRIPTION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
