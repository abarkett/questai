"""
Tests for the day-one experience: pre-minted starter regions, the session
world-pulse, ambient world rules in the old areas, and the season-aware
welcome — a fresh universe must not feel like the static 22 rooms.

Run from server_py/:  python3 test_day_one.py
"""

import os
import tempfile
import time

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")
os.environ["QUESTAI_PREMINT"] = "tavern,riverside"

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.regiongen import pre_mint_regions  # noqa: E402
from app.world import get_location  # noqa: E402
from app.world_goals import ensure_active_goal  # noqa: E402
from app.world_rules import seed_default_db_rules, evaluate_db_rules  # noqa: E402
from app.recap import recap_messages, world_pulse, PULSE_GAP_MS, RECAP_GAP_MS  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_monsters_at  # noqa: E402


def main() -> None:
    # --- Startup pre-minting: the world is bigger than the core on day one ---
    minted = pre_mint_regions()
    assert minted == 2, minted
    assert pre_mint_regions() == 0, "premint is idempotent"

    for origin in ("tavern", "riverside"):
        region = db.get_region_by_origin(origin)
        assert region, f"no starter region behind {origin}"
        assert region["discovered_by"] is None, "system mints have no discoverer"
        exits = get_location(origin).exits
        assert any(e.to == region["entry_location"] for e in exits), \
            f"{origin} should open into its starter region"
        entry = get_location(region["entry_location"])
        assert "First charted" not in entry.description
        # Starter regions are live: monsters on the field, NPC waiting.
        spec_locs = [l["location_id"] for l in db.get_all_gen_locations()
                     if l["region_id"] == region["region_id"]]
        assert sum(len(get_monsters_at(lid)) for lid in spec_locs) >= 2
    n_locs = len(db.get_all_gen_locations())
    assert n_locs >= 8, n_locs
    print(f"PASS  two starter regions pre-minted ({n_locs} new areas) and playable")

    # Discovery still belongs to players: unminted frontiers stay sealed.
    assert db.get_region_by_origin("deep_forest") is None
    assert db.get_region_by_origin("magma_core") is None
    print("PASS  remaining frontiers stay sealed for player discovery")

    # --- Ambient rules make the old areas less predictable ---
    seed_default_db_rules()
    # Clear the forest wolves... (none live there; the prowler rule fills it)
    triggered = evaluate_db_rules()
    assert "A Prowler in the Pines" in triggered, triggered
    assert any(m["name"] == "Wolf" for m in get_monsters_at("forest"))
    assert "Brigands on the Towpath" in triggered, triggered
    assert any(m["name"] == "Bandit" for m in get_monsters_at("riverside"))
    print("PASS  ambient rules drop surprises into the hand-authored areas")

    # --- World pulse: short absences still open with world motion ---
    ensure_active_goal()
    p = Player(player_id="pulse", name="Pulse", location="town_square",
               level=1, xp=0, hp=10, max_hp=10)
    upsert_player(p)
    now = int(time.time() * 1000)
    msgs = recap_messages(p, now - PULSE_GAP_MS - 1000, now)
    assert msgs and "Season:" in msgs[0], msgs
    assert len(msgs) == 1, "pulse is one line"
    # Long absences still get the full recap (falls back to pulse if quiet).
    long_msgs = recap_messages(p, now - RECAP_GAP_MS - 1000, now)
    assert long_msgs, long_msgs
    # Tiny gaps stay silent.
    assert recap_messages(p, now - 1000, now) == []
    assert world_pulse(p), "pulse always has the season"
    print("PASS  sessions open with a one-line world pulse")

    # --- New players are told what the world is fighting ---
    from app.engine.actions.create_player import create_player
    r = create_player("Newcomer")
    text = " ".join(r.messages)
    assert "The town talks of one thing" in text and "Blight" in text, r.messages
    print("PASS  the welcome leads with the running season")

    # --- The hub broadcasts the world's motion ---
    newcomer = db.get_player_by_name("Newcomer")
    from app.engine.actions.look import look
    r = look(newcomer)
    text = " ".join(r.messages)
    assert "Word going around:" in text, r.messages
    assert r.state.get("rumors"), "rumors surface in state for the UI"
    # The full rumor pool reaches back to the premint discoveries.
    from app.echoes import rumor_lines
    pool = rumor_lines(newcomer, limit=10)
    assert any("stands open" in line for line in pool), pool
    print("PASS  town square gossip carries world news (premint, events)")

    # Even authored prose moves with the clock when Miriel is off.
    from app.descriptions import fallback_description
    a = fallback_description("A plaza.", "town_square", 0)
    b = fallback_description("A plaza.", "town_square", 12 * 3)
    assert a != b and a.startswith("A plaza."), (a, b)
    print("PASS  fallback descriptions change with the time of day")

    print("\nALL DAY-ONE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
