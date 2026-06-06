"""
Offline tests for richer quests: collect/visit objectives, multi-objective
quests, and central progress refresh.

Run from server_py/:  python3 test_quests_rich.py
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

from app.types import Player  # noqa: E402
from app.db import upsert_player  # noqa: E402
from app.engine.actions.accept_quest import accept_quest  # noqa: E402
from app.engine.actions.turn_in_quest import turn_in_quest  # noqa: E402
from app.engine.quest_progress import refresh_quests  # noqa: E402
from app.engine.actions.gather import gather  # noqa: E402
from app.engine.actions.move import move  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="p", location="town_square", level=20, xp=0, hp=300, max_hp=300)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    # Collect objective completes when the player holds enough items.
    p = mk(player_id="a", inventory={})
    upsert_player(p)
    accept_quest(p, "gather_herbs")
    p.inventory["herb_bundle"] = 2
    msgs = refresh_quests(p)
    assert "gather_herbs" in p.active_quests and not msgs  # 2/3, not done
    p.inventory["herb_bundle"] = 3
    msgs = refresh_quests(p)
    assert "gather_herbs" in p.completed_quests, list(p.completed_quests)
    assert any("completed" in m.lower() for m in msgs), msgs
    print("PASS  collect objective completes at the required count")

    # Visit objective completes upon reaching the location.
    v = mk(player_id="v", location="town_square")
    upsert_player(v)
    accept_quest(v, "explore_cavern")
    assert not refresh_quests(v)  # not there yet
    v.visited_locations.append("cavern")
    msgs = refresh_quests(v)
    assert "explore_cavern" in v.completed_quests, list(v.completed_quests)
    print("PASS  visit objective completes on reaching the location")

    # Multi-objective: both kill and collect must be satisfied.
    m = mk(player_id="m", inventory={})
    upsert_player(m)
    accept_quest(m, "thin_the_pack")
    q = m.active_quests["thin_the_pack"]
    # simulate kills (kill progress is set by combat, here we set it directly)
    for o in q.objectives:
        if o.type == "kill":
            o.progress = 2
    refresh_quests(m)
    assert "thin_the_pack" in m.active_quests, "collect not met yet -> still active"
    m.inventory["pelt"] = 3
    refresh_quests(m)
    assert "thin_the_pack" in m.completed_quests, "both objectives met -> completed"
    print("PASS  multi-objective quest needs all objectives")

    # End-to-end via real actions: gather to satisfy a collect quest.
    g = mk(player_id="g", location="forest", inventory={})
    upsert_player(g)
    accept_quest(g, "gather_herbs")
    for _ in range(3):
        gather(g)            # forest -> herb_bundle
        refresh_quests(g)
    assert "gather_herbs" in g.completed_quests, (g.inventory, list(g.completed_quests))
    print(f"PASS  gathering in the world completes the collect quest: {dict(g.inventory)}")

    # Turning in a collect quest consumes the required items (and grants reward).
    c = mk(player_id="cons", inventory={"herb_bundle": 4})  # one spare
    upsert_player(c)
    accept_quest(c, "gather_herbs")
    refresh_quests(c)  # 4 >= 3 -> completed
    assert "gather_herbs" in c.completed_quests
    r = turn_in_quest(c, "gather_herbs")
    assert r.ok, r.error
    assert c.inventory.get("herb_bundle") == 1, c.inventory  # 4 - 3 consumed
    assert c.inventory.get("healing_potion") == 1, c.inventory  # reward granted
    print(f"PASS  turn-in consumes collected items: {dict(c.inventory)}")

    # Accepting a collect quest counts items you ALREADY hold (via the dispatcher).
    from app.engine.apply_action import apply_action
    pre = mk(player_id="pre", inventory={"herb_bundle": 1})
    upsert_player(pre)
    resp = apply_action(player_id="pre", req_json={"action": "accept_quest", "args": {"quest_id": "gather_herbs"}})
    assert resp.ok, resp.error
    q = resp.state["player"]["active_quests"]["gather_herbs"]
    prog = q["objectives"][0]
    assert prog["progress"] == 1 and prog["required"] == 3, prog
    # And it's persisted (not thrown away).
    from app.db import get_player
    reloaded = get_player("pre")
    assert reloaded.active_quests["gather_herbs"].objectives[0].progress == 1
    print("PASS  collect quest counts pre-existing items on accept (persisted)")

    print("\nALL RICH QUEST TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
