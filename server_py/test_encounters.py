"""
Tests for travel encounters: moving should sometimes produce a moment —
caches, shrines, travelers carrying real world news, omens, ambushes.

Run from server_py/:  python3 test_encounters.py
"""

import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

# Miriel is required (no fallback): stub it for the offline suite.
from app.services.miriel_client import install_test_responder, get_miriel_client  # noqa: E402

get_miriel_client().enabled = True
install_test_responder(lambda q: "The road bends through telling light.")

from app.types import Player  # noqa: E402
from app.db import upsert_player, log_world_event  # noqa: E402
from app.encounters import maybe_travel_encounter, ENCOUNTER_CHANCE  # noqa: E402


class FakeRng:
    """Scripted RNG: random() pops from a list; uniform() returns a fixed roll."""

    def __init__(self, randoms, uniform_val=0.0):
        self.randoms = list(randoms)
        self.uniform_val = uniform_val

    def random(self):
        return self.randoms.pop(0) if self.randoms else 0.0

    def uniform(self, a, b):
        return self.uniform_val

    def randint(self, a, b):
        return a

    def choice(self, seq):
        return seq[0]


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=1, xp=0, hp=20, max_hp=20)
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # Most moves are uneventful: a high gate roll yields nothing.
    p = mk("quiet")
    assert maybe_travel_encounter(p, rng=FakeRng([ENCOUNTER_CHANCE + 0.01])) == []
    print("PASS  most moves stay uneventful")

    # Cache: coins straight into the inventory.
    p = mk("cache")
    msgs = maybe_travel_encounter(p, rng=FakeRng([0.0, 0.5], uniform_val=0.0))
    assert any("coins inside" in m for m in msgs), msgs
    assert p.inventory.get("coin", 0) >= 2
    print("PASS  cache encounters pay out coins")

    # Cache (resource variant): yields the local gatherable.
    p = mk("forager", location="forest")
    msgs = maybe_travel_encounter(p, rng=FakeRng([0.0, 0.9], uniform_val=0.0))
    assert p.inventory.get("herb_bundle", 0) == 1, msgs
    print("PASS  cache encounters can yield the local resource")

    # Shrine: heals a wounded traveler.
    p = mk("pilgrim", hp=12)
    msgs = maybe_travel_encounter(p, rng=FakeRng([0.0, 0.4], uniform_val=31))
    assert any("+4 HP" in m for m in msgs), msgs
    assert p.hp == 16
    print("PASS  shrines mend the wounded")

    # Traveler: carries genuine world news (the rumor pool).
    log_world_event(event_type="world_evolution", location_id=None,
                    data={"description": "The mill wheel turns again."})
    p = mk("listener")
    msgs = maybe_travel_encounter(p, rng=FakeRng([0.0, 0.5], uniform_val=50))
    assert any("mill wheel" in m for m in msgs), msgs
    print("PASS  travelers repeat real world events")

    # Omen at an unopened frontier: points at explore.
    # deep_forest is a sealed frontier and dangerous; the omen band of its
    # weighted table sits around 49-63 of 95.
    p = mk("seer", location="deep_forest")
    msgs = maybe_travel_encounter(p, rng=FakeRng([0.0], uniform_val=60))
    assert any("uncharted" in m for m in msgs), msgs
    print("PASS  omens point at unopened frontiers")

    # Ambush: dangerous country bites.
    p = mk("prey", location="deep_forest", hp=30, max_hp=30)
    msgs = maybe_travel_encounter(p, rng=FakeRng([0.0, 0.0], uniform_val=90))
    assert any("not alone" in m for m in msgs), msgs
    assert p.hp < 30
    print("PASS  dangerous roads can ambush you")

    # Integration: move() survives an encounter roll and persists changes.
    from app.engine.actions.move import move
    p = mk("walker")
    r = move(p, "tavern")
    assert r.ok, r.error
    print("PASS  move() integrates encounters end-to-end")

    print("\nALL ENCOUNTER TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
