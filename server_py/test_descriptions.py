"""
Tests for Miriel-authored location descriptions. There is NO fallback: with
Miriel down, describing a location must raise. The offline suite installs a
Miriel test responder (a seam, not a gameplay fallback) to exercise the path.

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

from app.services.miriel_client import install_test_responder, get_miriel_client  # noqa: E402
from app.descriptions import time_of_day, present_creatures, describe, MirielUnavailable  # noqa: E402
from app.world import get_location  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player  # noqa: E402
from app.engine.actions.look import look  # noqa: E402


def main() -> None:
    # Context helpers (used to build the prompt) are deterministic.
    assert time_of_day("forest", 0) != time_of_day("forest", 12 * 3)
    assert time_of_day("tavern", 0) is None
    assert present_creatures([{"type": "monster", "name": "Wolf"}, {"type": "npc", "name": "X"}]) == ["Wolf"]
    print("PASS  prompt-context helpers (time of day, present creatures)")

    p = Player(player_id="p", name="P", location="forest", level=3, xp=0, hp=20, max_hp=20)
    upsert_player(p)
    loc = get_location("forest")

    # With Miriel down (no key, no stub): describing MUST raise — no fallback.
    install_test_responder(None)
    get_miriel_client().enabled = False
    raised = False
    try:
        describe(p, loc, [], "A forest.", 0)
    except MirielUnavailable:
        raised = True
    assert raised, "describe must raise when Miriel is unavailable (no fallback)"
    # And look() propagates the failure (the game crashes hard).
    crashed = False
    try:
        look(p)
    except MirielUnavailable:
        crashed = True
    assert crashed, "look() must fail hard when Miriel is down"
    print("PASS  no fallback: describe/look fail hard when Miriel is down")

    # With Miriel working (stubbed), the prose comes from Miriel and reaches look.
    get_miriel_client().enabled = True
    seen = {}
    def responder(q):
        seen["query"] = q
        return "Mist curls between the pines as a wolf watches from the dark."
    install_test_responder(responder)

    text = describe(p, loc, [{"type": "monster", "name": "Wolf"}], "A forest.", 0)
    assert "Mist curls" in text
    assert "Wolf" in seen["query"] and "forest" in seen["query"].lower()
    r = look(p)
    assert any("Mist curls" in m for m in r.messages), r.messages
    print("PASS  descriptions come from Miriel and surface in look()")

    install_test_responder(None)
    print("\nALL DESCRIPTION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
