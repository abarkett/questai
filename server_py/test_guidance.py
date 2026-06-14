"""
Tests for onboarding guidance: the stateless, self-resolving 'what now?' nudges.
Each suggestion appears only while its condition holds and vanishes once acted on.

Run from server_py/:  python3 test_guidance.py
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

from app.types import Player, Companion  # noqa: E402
from app.db import upsert_player  # noqa: E402
from app.guidance import suggestions, guide  # noqa: E402


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=1, xp=0, hp=30, max_hp=30, inventory={"coin": 0})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def texts(p) -> str:
    return " || ".join(t["text"] for t in suggestions(p))


def cmds(p) -> list:
    return [t["command"] for t in suggestions(p)]


def main() -> None:
    # ---- always returns something actionable ----
    p = mk("fresh")
    tips = suggestions(p)
    assert tips and all("text" in t for t in tips)
    g = guide(p)
    assert g.ok and g.messages[0] == "What now?" and len(g.messages) > 1
    print("PASS  guidance always offers at least one next step")

    # ---- a quest giver in the room is surfaced (town_square has the Warden) ----
    assert "talk" in texts(p).lower() and any(c and c.startswith("talk ") for c in cmds(p))
    print("PASS  a nearby quest giver is suggested")

    # ---- wounded trumps most things (survival first) ----
    pw = mk("hurt", location="forest")
    pw.status_effects = {"wounded": {"magnitude": 2, "turns": 3}}
    upsert_player(pw)
    assert suggestions(pw)[0]["command"] == "rest", suggestions(pw)[0]
    print("PASS  a wound surfaces 'rest' above everything else")

    # ---- equip nudge appears, then self-resolves once equipped ----
    pe = mk("armed", location="forest", inventory={"coin": 0, "iron_sword": 1})
    assert any(c == "equip iron_sword" for c in cmds(pe))
    pe.equipment = {"weapon": "iron_sword"}
    assert not any(c == "equip iron_sword" for c in cmds(pe))
    print("PASS  the equip nudge appears, then disappears once you wield it")

    # ---- a recruitable ally present is suggested; self-resolves with a companion ----
    pr = mk("lonely", location="temple")  # Temple Priest is recruitable
    assert any(c and c.startswith("recruit ") for c in cmds(pr))
    pr.companion = Companion(npc_id="x", name="Pal", archetype="mender", loyalty=0)
    assert not any(c and c.startswith("recruit ") for c in cmds(pr))
    print("PASS  a recruitable ally is suggested until you have a companion")

    # ---- stronghold: build when affordable, then collect, self-resolving ----
    ps = mk("rich", location="forest", inventory={"coin": 80})
    assert any(c == "build" for c in cmds(ps)), cmds(ps)
    ps.stronghold_level = 1
    ps.inventory["coin"] = 80
    import app.stronghold as sh
    ps.stronghold_collected_at = sh.now_ms() - 6 * 3600 * 1000  # tribute waiting
    assert any(c == "collect" for c in cmds(ps)), cmds(ps)
    assert not any(c == "build" for c in cmds(ps))  # already founded
    print("PASS  stronghold nudges advance from build -> collect")

    # ---- the raid is surfaced for an able player, context-aware ----
    from app.raids import ensure_active_raid
    ensure_active_raid()
    # From the Town Square (which the Warfront opens off) the nudge is clickable.
    ptown = mk("ready", location="town_square", level=5)
    assert any(c == "go warfront" for c in cmds(ptown)), cmds(ptown)
    # From elsewhere the raid is still mentioned, but with no command that would
    # fail (the Warfront isn't reachable in one step) — only text.
    pfar = mk("faraway", location="forest", level=5)
    raid_tips = [t for t in suggestions(pfar) if "Warfront" in t["text"]]
    assert raid_tips and all(t["command"] is None for t in raid_tips), raid_tips
    # ...and at the Warfront it becomes a strike.
    pat = mk("atlair", location="warfront", level=5)
    assert any(c == "raid strike" for c in cmds(pat)), cmds(pat)
    # A low-level player isn't pushed at the raid yet.
    plow = mk("green", location="town_square", level=1)
    assert not any(c in ("go warfront", "raid strike") for c in cmds(plow))
    print("PASS  the raid is surfaced by level and travel state")

    # ---- craftable nudge when you hold the materials ----
    pc = mk("smith", location="forest", inventory={"coin": 0, "pelt": 3})
    assert any(c == "craft leather_armor" for c in cmds(pc)), cmds(pc)
    print("PASS  a craftable recipe you can afford is suggested")

    # ---- a frontier underfoot suggests explore ----
    pf = mk("scout", location="riverside", level=2)  # riverside is a static frontier
    assert any(c == "explore" for c in cmds(pf)), cmds(pf)
    print("PASS  an uncharted frontier suggests explore")

    print("\nAll guidance tests passed.")


if __name__ == "__main__":
    main()
