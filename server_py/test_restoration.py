"""
Tests for the Restoration campaign — the game's spine: wrongs righted by deeds
that permanently change the world, a Chronicle that names who did it, a
personal Legend of titles, acts that complete, and raids that stay felled.

Run from server_py/:  python3 test_restoration.py
"""

import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")
os.environ.pop("MIRIEL_API_KEY", None)

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.services.miriel_client import install_test_responder  # noqa: E402
install_test_responder(lambda q: "Test prose.")

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player, get_world_state, get_world_events  # noqa: E402
from app.world import get_location  # noqa: E402
from app.engine.state_view import effective_description  # noqa: E402
from app.engine.parse_command import parse_command  # noqa: E402
from app.engine.apply_action import apply_action  # noqa: E402
import app.restoration as R  # noqa: E402
from app.restoration import (  # noqa: E402
    get_acts, undertake, settle_deeds, right_wrong, is_righted, current_act,
    is_act_complete, next_wrong_for, campaign_summary, patron_lines,
)


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=5, xp=0, hp=40, max_hp=40, inventory={"coin": 50})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def do(pid, cmd):
    return apply_action(player_id=pid, req_json=parse_command(cmd))


def main() -> None:
    # ---- the realm starts fallen, in Act I ----
    act = current_act()
    assert act is not None and act.index == 0 and act.name == "The Town Besieged"
    assert not is_righted("granary_rats")
    assert effective_description(get_location("old_mill")) == get_location("old_mill").description
    print("PASS  the realm starts fallen, in Act I, nothing righted")

    # ---- undertake: gates ----
    p = mk("a")
    assert not undertake(p, "nonsense").ok
    assert not undertake(p, "goblin_warband").ok            # Act II — not yet
    assert not undertake(p, "ashen_dragon").ok              # climaxes aren't undertaken alone
    r = undertake(p, "mill_bandits")
    assert r.ok and "deed__mill_bandits" in p.active_quests, r
    assert not undertake(p, "mill_bandits").ok              # already taken
    print("PASS  undertake respects act, climax, and duplicates")

    # ---- a deed done rights the wrong: world change, Chronicle, Legend ----
    # Simulate completing the deed quest (a kill deed) and settling it.
    q = p.active_quests["deed__mill_bandits"]
    q.objectives[0].progress = q.objectives[0].required
    q.status = "completed"
    p.completed_quests["deed__mill_bandits"] = p.active_quests.pop("deed__mill_bandits")
    msgs = settle_deeds(p)
    upsert_player(p)
    assert is_righted("mill_bandits")
    assert get_world_state("mill_reclaimed") == "true"                     # flag flipped
    assert "Keeper of the Mill" in p.titles                                 # Legend title
    assert "deed__mill_bandits" in p.archived_quests                        # quest settled, no turn-in
    assert any("Chronicle" in m for m in msgs), msgs
    # The world changed for good: the mill now reads restored, everywhere.
    assert "turns again" in effective_description(get_location("old_mill"))
    ev = [e for e in get_world_events(20) if e["event_type"] == "wrong_righted"]
    assert ev and ev[0]["data"]["player_name"] == "Hero_a"
    print("PASS  a deed rights its wrong: flag, restored place, Chronicle, title")

    # ---- first righter wins; a second finisher gets no title ----
    p2 = mk("b")
    msgs2 = right_wrong("mill_bandits", p2)
    assert "Keeper of the Mill" not in p2.titles
    assert any("while you worked" in m for m in msgs2), msgs2
    print("PASS  the Chronicle credits the first righter only")

    # ---- a collect deed delivers its goods, through the real request path ----
    ph = mk("herbalist", inventory={"coin": 0, "herb_bundle": 3})
    assert do("herbalist", "undertake temple_stores").ok
    # Any non-passive action refreshes collect quests and settles the deed.
    res = do("herbalist", "rest")  # refused at full HP -> use a real action instead
    if not res.ok:
        ph = get_player("herbalist"); ph.hp = 1; upsert_player(ph)
        res = do("herbalist", "rest")
    assert res.ok, res
    ph = get_player("herbalist")
    assert is_righted("temple_stores") and "Temple's Provider" in ph.titles
    assert ph.inventory.get("herb_bundle", 0) == 0                          # herbs delivered
    print("PASS  a collect deed settles via the request path and delivers its goods")

    # ...and the restoration is FELT: the temple now heals for free.
    from app.engine.actions.heal import heal_cost
    assert heal_cost() == 0
    hurt = mk("hurt", location="temple", hp=5, max_hp=40, inventory={"coin": 0})
    hr = do("hurt", "heal")
    assert hr.ok and get_player("hurt").hp == 40, hr
    assert any("asks nothing" in m for m in hr.messages), hr.messages
    print("PASS  the restocked temple heals for free — a change you can feel")

    # ---- patrons are the doorway: they speak of their wrongs ----
    lines = patron_lines("Town Warden", mk("c"))
    assert any("granary" in l.lower() and "undertake granary_rats" in l for l in lines), lines
    done_lines = patron_lines("Old Merchant", get_player("a"))
    assert any("put right" in l for l in done_lines), done_lines
    print("PASS  patron NPCs point at open wrongs and acknowledge righted ones")

    # ---- guidance points at the spine; the raid is the climax ----
    nw = next_wrong_for(mk("d"))
    assert nw and nw[1] == "open" and nw[0].deed_type != "climax"
    print("PASS  guidance points at the next open wrong, climax last")

    # ---- act completion: titles for every righter, next act unlocks ----
    fin = mk("fin")
    for w in get_acts()[0].wrongs:
        if not is_righted(w.id):
            right_wrong(w.id, fin)
    upsert_player(fin)
    assert is_act_complete(0)
    assert "Defender of the Town" in get_player("fin").titles
    assert "Defender of the Town" in get_player("a").titles              # earlier righter too
    assert "Defender of the Town" not in get_player("b").titles          # righted nothing
    assert current_act().index == 1
    assert undertake(mk("e"), "goblin_warband").ok                        # Act II now open
    print("PASS  completing an act crowns its righters and opens the next act")

    # ---- the web summary and the campaign command ----
    s = campaign_summary(get_player("a"))
    assert s["act_index"] == 1 and any(w["command"] for w in s["wrongs"])
    cs = do("a", "campaign")
    assert cs.ok and any("Legend" in m for m in cs.messages)
    print("PASS  campaign status and web summary render")

    # ---- persistence: titles survive a reload ----
    # (Compare against what SHOULD be there, not the stale in-memory `p`: the
    # act-completion step loaded player "a" fresh and added the act title.)
    persisted = set(get_player("a").titles)
    assert {"Keeper of the Mill", "Defender of the Town"} <= persisted, persisted
    print("PASS  the Legend persists")

    install_test_responder(None)
    print("\nAll restoration tests passed.")


if __name__ == "__main__":
    main()
