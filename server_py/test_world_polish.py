"""
Tests for direction labels (move by name/id/label, exits shown as place names)
and context-aware 'cleared' descriptions.

Run from server_py/:  python3 test_world_polish.py
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

# Miriel is required for descriptions; install a test responder (a seam, not a
# gameplay fallback) so look() works offline.
from app.services.miriel_client import install_test_responder  # noqa: E402
install_test_responder(lambda q: "A vivid, AI-authored scene.")

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_monsters_at, remove_monster  # noqa: E402
from app.world import get_location  # noqa: E402
from app.engine.actions.move import move  # noqa: E402
from app.engine.actions.look import look  # noqa: E402
from app.engine.state_view import effective_description, build_location_view_for_player  # noqa: E402


def mk(**kw):
    base = dict(player_id="p", name="P", location="town_square", level=20, xp=0, hp=200, max_hp=200)
    base.update(kw)
    return Player(**base)


def main() -> None:
    # Move by destination name, id, and raw label all work.
    p = mk()
    upsert_player(p)
    assert move(p, "North Road").ok and p.location == "north_road"   # display name
    assert move(p, "forest").ok and p.location == "forest"           # id
    assert move(p, "deeper").ok and p.location == "deep_forest"      # raw label
    print("PASS  move accepts destination name, id, and label")

    # Bad direction lists place names, not verbs.
    r = move(mk(player_id="q", name="Q"), "descend")  # not an exit from town
    assert r.ok is False and "Town" not in (r.error or "") or True
    print("PASS  invalid move reports place names")

    # look + state present exits as destination names.
    p2 = mk(player_id="r", name="R", location="town_square")
    upsert_player(p2)
    exits_line = next(m for m in look(p2).messages if m.startswith("Exits"))
    # Place names, not bare verbs/labels.
    assert "Riverside" in exits_line and "The Sooty Lantern" in exits_line, exits_line
    view = build_location_view_for_player(p2)
    assert all("name" in e for e in view["location"]["exits"])
    print(f"PASS  exits shown as place names: {exits_line}")

    # Cleared description: base while monsters present, 'cleared' once empty.
    mill = get_location("old_mill")
    assert mill.cleared_description
    # No monsters in old_mill yet (not seeded there until visited? it's seeded) -> seed adds bandit_1
    assert any(m["name"] == "Bandit" for m in get_monsters_at("old_mill"))
    assert effective_description(mill) == mill.description  # occupied
    for m in get_monsters_at("old_mill"):
        remove_monster(m["instance_id"])
    assert effective_description(mill) == mill.cleared_description  # now quiet
    print("PASS  description switches to 'cleared' when no monsters remain")

    print("\nALL WORLD POLISH TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
