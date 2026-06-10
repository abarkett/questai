"""
Tests for the living-world systems: echoes, location notes, bounties,
community goals, and the login recap.

Run from server_py/:  python3 test_living_world.py
"""

import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")  # AP off for these tests

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

# Miriel is required (no fallback): stub it for the offline suite. The
# responder echoes the query tail so narrated output (e.g. recaps) carries
# the real event content through to assertions.
from app.services.miriel_client import install_test_responder, get_miriel_client  # noqa: E402

get_miriel_client().enabled = True
install_test_responder(lambda q: "[stub] " + q[-200:])

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player  # noqa: E402
from app.engine.actions.fight import fight  # noqa: E402
from app.engine.actions.post_note import post_note  # noqa: E402
from app.engine.actions.bounty import post_bounty, list_bounties  # noqa: E402
from app.engine.actions.look import look  # noqa: E402
from app.echoes import echo_lines, record_deed  # noqa: E402
from app.world_goals import ensure_active_goal, record_kill_progress, goals_overview  # noqa: E402
from app.recap import recap_messages, RECAP_GAP_MS  # noqa: E402


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=1, xp=0, hp=20, max_hp=20)
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # --- Echoes: kills leave traces other players can see ---
    slayer = mk("slayer", location="forest", level=8, hp=60, max_hp=60)
    r = fight(slayer, "Rat", "bold")
    assert r.ok and "defeated" in " ".join(r.messages), r.messages

    witness = mk("witness", location="forest")
    lines = echo_lines(witness)
    assert any("Hero_slayer slew a Rat" in line for line in lines), lines
    assert echo_lines(slayer) == [] or all("Hero_slayer" not in l for l in echo_lines(slayer)), \
        "you don't see your own echoes"
    print("PASS  kills leave echoes visible to other players")

    # --- Notes ---
    r = post_note(witness, "Beware the deep forest wolves!")
    assert r.ok, r.error
    r = look(slayer)
    text = " ".join(r.messages)
    assert "Beware the deep forest wolves!" in text, r.messages
    assert not post_note(witness, "x").ok, "too-short notes rejected"
    print("PASS  notes posted at a location show up in look")

    # --- Bounties: escrowed, claimed by another player's kill ---
    poster = mk("poster", inventory={"coin": 30})
    r = post_bounty(poster, "rat", 10)
    assert r.ok, r.error
    assert poster.inventory["coin"] == 20, "reward escrowed"
    r = list_bounties(witness)
    assert any("10 coins" in m and "Rat" in m for m in r.messages), r.messages

    # The poster's own kill must NOT claim their bounty.
    poster.location = "forest"
    poster.level, poster.hp, poster.max_hp = 8, 60, 60
    upsert_player(poster)
    hunter = mk("hunter", location="forest", level=8, hp=60, max_hp=60)

    # Kill rats until the bounty is claimed by the hunter.
    from app.db import get_open_bounties, spawn_monster
    claimed = None
    for i in range(3, 10):
        spawn_monster(instance_id=f"trat_{i}", location_id="forest", name="Rat",
                      hp=4, max_hp=4, attack=1, xp_reward=1, loot={})
        r = fight(hunter, "Rat", "bold")
        msgs = " ".join(r.messages)
        if "Bounty claimed!" in msgs:
            claimed = msgs
            break
    assert claimed and "10 coins" in claimed, claimed
    assert hunter.inventory.get("coin", 0) >= 10
    assert not get_open_bounties(), "bounty closed after claim"
    print("PASS  bounties escrow coins and pay the claiming hunter")

    # --- Community goals ---
    ensure_active_goal()
    overview = goals_overview(hunter)
    assert any("The Blight" in line for line in overview), overview
    msgs = record_kill_progress(hunter, "Wolf")
    assert any("The Blight" in m for m in msgs), msgs
    print("PASS  community goal tracks kills and reports progress")

    # Completing a goal pays contributors and flips world state.
    from app.db import get_active_world_goals, get_world_state
    goal = get_active_world_goals()[0]
    # Push the goal to the brink, then land the final blow.
    for _ in range(goal["required"] - goal["progress"] - 1):
        db.increment_world_goal(goal["goal_id"], "slayer", "Hero_slayer")
    coins_before = hunter.inventory.get("coin", 0)
    msgs = record_kill_progress(hunter, "Wolf")
    assert any("recedes" in m for m in msgs), msgs
    assert get_world_state("blight_cleansed") == "true"
    assert hunter.inventory.get("coin", 0) > coins_before, "contributor payout"
    slayer_after = get_player("slayer")
    assert slayer_after.inventory.get("coin", 0) >= 20, "offline contributor paid"
    assert get_active_world_goals(), "next seasonal goal seeds itself"
    print("PASS  goal completion pays contributors, sets world state, rotates")

    # --- Recap ---
    away = mk("away")
    import time
    last_seen = int(time.time() * 1000) - RECAP_GAP_MS - 1000
    msgs = recap_messages(away, last_seen, int(time.time() * 1000))
    text = " ".join(msgs)
    assert msgs and "While you were away" in text, msgs
    assert "Hero_slayer" in text or "Blight" in text, msgs
    # Too-short absences stay quiet.
    assert recap_messages(away, int(time.time() * 1000) - 1000, int(time.time() * 1000)) == []
    print("PASS  returning players get a while-you-were-gone recap")

    print("\nALL LIVING WORLD TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
