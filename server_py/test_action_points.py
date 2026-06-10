"""
Tests for the action-point economy and collapsed-encounter combat (fight).

Run from server_py/:  python3 test_action_points.py
"""

import os
import tempfile

os.environ["QUESTAI_AP_MAX"] = "5"
os.environ["QUESTAI_AP_REGEN_SECONDS"] = "60"

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
install_test_responder(lambda q: "The scene shifts in the telling.")

from app.action_points import refill, spend, seconds_to_next_ap, ap_max, now_ms  # noqa: E402
from app.engine.apply_action import apply_action  # noqa: E402
from app.engine.parse_command import parse_command  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player  # noqa: E402


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=1, xp=0, hp=20, max_hp=20)
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # --- Lazy regen math ---
    p = mk("ap1")
    now = now_ms()
    refill(p, now)
    assert p.action_points == 5, "first contact grants a full bar"
    assert spend(p, 1) and p.action_points == 4

    # 2.5 regen periods later: +2 AP, remainder carries toward the next point.
    refill(p, now + 150_000)
    assert p.action_points == 5  # capped at 5 (4+2 clamps)
    p.action_points = 1
    p.ap_updated_at = now
    refill(p, now + 150_000)
    assert p.action_points == 3, p.action_points
    assert 0 < seconds_to_next_ap(p, now + 150_000) <= 60
    print("PASS  lazy AP regen accrues over time and clamps at the cap")

    # --- Spending through the dispatcher ---
    p2 = mk("ap2")
    p2.action_points = 0
    import time as _time
    p2.ap_updated_at = int(_time.time() * 1000)
    upsert_player(p2)
    r = apply_action(player_id="ap2", req_json={"action": "move", "args": {"to": "tavern"}})
    assert not r.ok and "action points" in (r.error or ""), r
    r = apply_action(player_id="ap2", req_json={"action": "look"})
    assert r.ok, "passive actions stay free with 0 AP"
    print("PASS  world-changing actions are AP-gated; passive reads stay free")

    # AP is charged on success and persisted.
    p3 = mk("ap3")
    r = apply_action(player_id="ap3", req_json={"action": "move", "args": {"to": "tavern"}})
    assert r.ok
    p3 = get_player("ap3")
    assert p3.action_points == ap_max() - 1, p3.action_points
    print("PASS  successful actions cost 1 AP and persist")

    # --- Fight: collapsed encounters ---
    cmd = parse_command("fight bold rat")
    assert cmd == {"action": "fight", "args": {"target": "rat", "stance": "bold"}}
    assert parse_command("fight rat")["args"]["stance"] == "standard"
    print("PASS  fight command parses with stances")

    f = mk("f1", location="forest", level=5, hp=40, max_hp=40)
    from app.engine.actions.fight import fight
    r = fight(f, "Rat", "bold")
    assert r.ok, r.error
    text = " ".join(r.messages)
    assert "strike" in text, r.messages
    # A level-5 hero pressing a bold attack always finishes a rat.
    assert "defeated" in text, r.messages
    print("PASS  fight resolves a whole encounter in one action")

    # Bad stance / bad target are rejected without charge.
    r = fight(f, "Rat", "reckless")
    assert not r.ok
    r = fight(f, "Unicorn")
    assert not r.ok
    print("PASS  fight validates stance and target")

    print("\nALL ACTION POINT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
