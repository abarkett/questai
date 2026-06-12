"""
Tests for rest: free HP recovery anywhere safe — the floor under the
survival economy for wounded, broke players.

Run from server_py/:  python3 test_rest.py
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

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player  # noqa: E402
from app.engine.actions.rest import rest, REST_HP  # noqa: E402
from app.engine.parse_command import parse_command  # noqa: E402


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=1, xp=0, hp=20, max_hp=20)
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # Wounded and broke: resting recovers HP for free, and persists.
    p = mk("weary", hp=5)
    r = rest(p)
    assert r.ok and p.hp == 5 + REST_HP, (r.messages, p.hp)
    assert "could rest longer" in " ".join(r.messages)
    assert get_player("weary").hp == p.hp, "rest persists"
    print("PASS  resting heals the wounded for free")

    # Repeated rests reach full and then refuse (no charge for a no-op).
    while p.hp < p.max_hp:
        assert rest(p).ok
    assert not rest(p).ok
    print("PASS  rest caps at full HP and refuses past it")

    # No rest with hostile eyes on you (deep_forest has aggressive monsters).
    w = mk("watched", location="deep_forest", hp=5)
    r = rest(w)
    assert not r.ok and "hostile eyes" in r.error, r.error
    print("PASS  dangerous locations refuse rest")

    # Parser: 'rest' is its own action now; temple verbs still heal.
    assert parse_command("rest") == {"action": "rest"}
    assert parse_command("camp") == {"action": "rest"}
    assert parse_command("pray") == {"action": "heal"}
    assert parse_command("heal") == {"action": "heal"}
    print("PASS  rest has its own verb; temple healing keeps its verbs")

    print("\nALL REST TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
