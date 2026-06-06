"""
Offline tests for the temple healer (cheap full heal + cure).

Run from server_py/:  python3 test_heal.py
"""

import os
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.types import Player  # noqa: E402
from app.db import upsert_player  # noqa: E402
from app.world import get_location  # noqa: E402
from app.engine.actions.heal import heal, HEAL_COST  # noqa: E402
from app.engine.actions.move import move  # noqa: E402
from app.engine.actions.talk import talk  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="p", location="temple", level=5, xp=0, hp=10, max_hp=50)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    # Temple exists and is reachable from the square.
    assert get_location("temple") is not None
    walker = mk(player_id="w", location="town_square", inventory={})
    upsert_player(walker)
    move(walker, "temple")
    assert walker.location == "temple", walker.location
    print("PASS  temple is reachable from the town square")

    # Full heal + cure for the small offering.
    p = mk(player_id="a", hp=8, inventory={"coin": 5})
    p.status_effects = {"poison": {"magnitude": 2, "turns": 3}}
    upsert_player(p)
    r = heal(p)
    assert r.ok and p.hp == p.max_hp, (r.error, p.hp)
    assert p.status_effects == {}, p.status_effects
    assert p.inventory.get("coin", 0) == 5 - HEAL_COST, p.inventory
    print(f"PASS  heal restores HP, cures ailments, costs {HEAL_COST} coins")

    # Can't afford the offering.
    broke = mk(player_id="b", hp=5, inventory={"coin": 1})
    upsert_player(broke)
    r = heal(broke)
    assert r.ok is False and broke.hp == 5, (r.error, broke.hp)
    print("PASS  heal refused when the offering is unaffordable")

    # Nothing to heal -> free and friendly, no charge.
    whole = mk(player_id="c", hp=50, max_hp=50, inventory={"coin": 5})
    upsert_player(whole)
    r = heal(whole)
    assert r.ok and whole.inventory.get("coin") == 5, (r.error, whole.inventory)
    print("PASS  already-whole player is not charged")

    # No healer elsewhere.
    away = mk(player_id="d", location="forest", hp=5, inventory={"coin": 5})
    upsert_player(away)
    assert heal(away).ok is False
    print("PASS  no healer outside the temple")

    # Priest explains the service on talk.
    t = talk(mk(player_id="e", inventory={}), "priest")
    assert t.ok and "heal" in " ".join(t.messages).lower(), t.messages
    print("PASS  priest offers healing via talk")

    print("\nALL HEAL TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
