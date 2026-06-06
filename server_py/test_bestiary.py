"""
Offline tests for the bestiary (monster discovery) and quest journal.

Run from server_py/:  python3 test_bestiary.py
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
from app.db import upsert_player, get_player  # noqa: E402
from app.bestiary import all_monster_names  # noqa: E402
from app.engine.actions.look import look  # noqa: E402
from app.engine.actions.attack import attack  # noqa: E402
from app.engine.actions.bestiary import bestiary  # noqa: E402
from app.engine.actions.journal import journal  # noqa: E402
from app.engine.actions.accept_quest import accept_quest  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="p", location="forest", level=20, xp=0, hp=300, max_hp=300)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    # Catalog includes monsters from across the world.
    names = all_monster_names()
    for expected in ["Rat", "Goblin", "Cave Troll", "Molten Wyrm", "Venomous Spider"]:
        assert expected in names, (expected, names)
    print(f"PASS  bestiary catalog has {len(names)} monsters")

    # Looking at a location records the monsters present.
    p = mk(player_id="a")
    upsert_player(p)
    look(p)
    assert "Rat" in p.discovered_monsters, p.discovered_monsters
    assert "Rat" in get_player("a").discovered_monsters  # persisted
    print("PASS  look records monsters in the bestiary (persisted)")

    # Attacking a never-before-seen monster also records it.
    pc = mk(player_id="c", location="cavern")
    upsert_player(pc)
    assert "Cave Troll" not in pc.discovered_monsters
    attack(pc, "Cave Troll")
    assert "Cave Troll" in pc.discovered_monsters, pc.discovered_monsters
    print("PASS  attacking records the target in the bestiary")

    # bestiary action reports discovered entries + stats + total.
    r = bestiary(p)
    bdata = r.state["bestiary"]
    assert bdata["total"] == len(names)
    rat = next(e for e in bdata["discovered"] if e["name"] == "Rat")
    assert rat["max_hp"] == 5 and rat["attack"] == 2, rat
    assert any("Rat" in m for m in r.messages)
    print(f"PASS  bestiary action reports {len(bdata['discovered'])}/{bdata['total']}")

    # Undiscovered monsters are not listed.
    fresh = mk(player_id="z", location="town_square")
    upsert_player(fresh)
    assert bestiary(fresh).state["bestiary"]["discovered"] == []
    print("PASS  undiscovered monsters stay hidden")

    # Journal reflects accepted quests with objective progress.
    q = mk(player_id="q", location="town_square")
    upsert_player(q)
    accept_quest(q, "rat_problem")
    jr = journal(q)
    jdata = jr.state["journal"]
    assert len(jdata["active"]) == 1 and jdata["active"][0]["name"] == "A Rat Problem", jdata
    obj = jdata["active"][0]["objectives"][0]
    assert obj["type"] == "kill" and obj["required"] == 2 and obj["progress"] == 0, obj
    print("PASS  journal lists active quests with objective progress")

    print("\nALL BESTIARY/JOURNAL TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
