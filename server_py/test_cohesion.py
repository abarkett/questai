"""
Cohesion / integration coverage: walk a real session across systems through the
parser + dispatcher (with Miriel stubbed so move/look work), and lock in the
seams found in the polish pass.

Run from server_py/:  python3 test_cohesion.py
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

from app.services.miriel_client import install_test_responder  # noqa: E402
install_test_responder(lambda q: "Test prose for the scene.")

from app.engine.parse_command import parse_command  # noqa: E402
from app.engine.apply_action import apply_action  # noqa: E402
from app.db import get_player, upsert_player  # noqa: E402


def main() -> None:
    # ---- a session through the real request path (parser -> dispatch) ----
    r = apply_action(player_id=None, req_json=parse_command("create Brann"))
    pid = r.state["player"]["player_id"]

    def do(cmd: str):
        return apply_action(player_id=pid, req_json=parse_command(cmd))

    # New players are told about `next`, and `next`/`look`/`talk` all work.
    assert any("next" in m for m in r.messages), r.messages
    assert do("next").ok
    assert do("look").ok                       # Miriel-gated prose path
    assert do("talk warden").ok
    # Movement (also Miriel-gated) resolves by name/label/id.
    assert do("go north").ok and get_player(pid).location == "north_road"
    assert do("go forest").ok and get_player(pid).location == "forest"
    print("PASS  a session walks create -> next -> look -> talk -> move cleanly")

    # ---- SEAM 1: rest tends the wound a defeat leaves, even at full HP ----
    from app.defeat import apply_defeat
    p = get_player(pid)
    p.level = 5                          # high enough to be pointed at the raid
    p.inventory["coin"] = 3000
    apply_defeat(p, "the test")          # full HP + a wound, back in town
    upsert_player(p)
    assert p.hp == p.max_hp and "wounded" in p.status_effects
    rr = do("rest")
    assert rr.ok, rr                      # not refused despite full HP
    assert "wounded" not in get_player(pid).status_effects
    assert do("rest").ok is False         # now whole, nothing to do
    print("PASS  rest clears the post-defeat wound (no dead-end at full HP)")

    # ---- SEAM 2: the raid nudge only offers a click that works ----
    import app.guidance as g
    here = get_player(pid)                # in town_square after respawn
    town_tips = g.suggestions(here)
    assert any(t["command"] == "go warfront" for t in town_tips if "Warfront" in t["text"])
    do("go north")                        # step away from town
    away = [t for t in g.suggestions(get_player(pid)) if "Warfront" in t["text"]]
    assert away and all(t["command"] is None for t in away), away
    print("PASS  the raid nudge is clickable only where `go warfront` works")

    # ---- SEAM 3: crafting points you at the stash when the material is there ----
    do("go south")                        # back to town
    p = get_player(pid)
    p.inventory.update({"coin": 3000, "dragon_heart": 1, "ember_core": 3})
    upsert_player(p)
    assert do("build").ok                 # found a stronghold
    assert do("stash dragon_heart").ok
    cr = do("craft cinderwing_blade")     # trophy is in the stash, not the pack
    assert not cr.ok and "stash" in cr.error.lower(), cr.error
    assert do("unstash dragon_heart").ok
    assert do("craft cinderwing_blade").ok
    assert get_player(pid).inventory.get("cinderwing_blade") == 1
    print("PASS  craft hints at stashed materials, then succeeds once withdrawn")

    # ---- a full raid loop holds together: travel, strike, get credited ----
    do("go warfront")
    rk = do("raid strike")
    assert rk.ok and any("Ashen Dragon" in m for m in rk.messages), rk.messages
    from app.db import get_active_raid_boss, get_raid_contribution
    boss = get_active_raid_boss()
    assert get_raid_contribution(boss["raid_id"], pid) > 0
    print("PASS  the raid loop holds: travel to the Warfront, strike, get credited")

    install_test_responder(None)
    print("\nAll cohesion tests passed.")


if __name__ == "__main__":
    main()
