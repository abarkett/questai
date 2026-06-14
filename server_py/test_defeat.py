"""
Tests for defeat stakes: coin scatter, a lingering wound, companion loyalty
loss (and desertion), the 'fallen here' echo, and that every combat defeat path
routes through the one apply_defeat.

Run from server_py/:  python3 test_defeat.py
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
from app.db import upsert_player, get_world_events  # noqa: E402
from app.status_effects import damage_modifier  # noqa: E402
from app.defeat import (  # noqa: E402
    apply_defeat,
    COIN_LOSS_FRAC,
    COMPANION_LOYALTY_LOSS,
    WOUND_MAGNITUDE,
    RESPAWN_LOCATION,
)


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="forest",
                level=3, xp=0, hp=1, max_hp=30, inventory={"coin": 100})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # ---- core stakes ----
    p = mk("fallen", inventory={"coin": 100})
    msgs = apply_defeat(p, "the Wolf")
    assert p.inventory["coin"] == 80, p.inventory          # 20% scattered
    assert any("scatter 20 coins" in m for m in msgs), msgs
    assert p.hp == p.max_hp                                 # recovered
    assert p.location == RESPAWN_LOCATION                   # woke in town
    assert "wounded" in p.status_effects                    # carries a wound
    assert damage_modifier(p) == -WOUND_MAGNITUDE           # blows are dulled
    assert any("wake, wounded" in m for m in msgs), msgs
    print("PASS  defeat scatters coin, wounds you, and wakes you in town")

    # The wound is the one effect that follows you home; others are cleared.
    p2 = mk("poisoned", inventory={"coin": 0})
    p2.status_effects = {"poison": {"magnitude": 3, "turns": 5}}
    apply_defeat(p2, "your lingering wounds")
    assert "poison" not in p2.status_effects and "wounded" in p2.status_effects
    print("PASS  defeat clears other effects but leaves the wound")

    # No coin, no scatter message.
    p3 = mk("broke", inventory={"coin": 0})
    msgs = apply_defeat(p3, "an ambush")
    assert not any("scatter" in m for m in msgs), msgs
    print("PASS  the penniless drop nothing")

    # ---- companion stakes ----
    p = mk("withpal", inventory={"coin": 0})
    p.companion = Companion(npc_id="x", name="Brann", archetype="vanguard", loyalty=30)
    apply_defeat(p, "the Troll")
    assert p.companion is not None and p.companion.loyalty == 30 - COMPANION_LOYALTY_LOSS
    print("PASS  a defeat costs your companion loyalty")

    # A companion with little loyalty left loses heart and deserts.
    p = mk("losepal", inventory={"coin": 0})
    p.companion = Companion(npc_id="x", name="Saoirse", archetype="mender", loyalty=5)
    msgs = apply_defeat(p, "the Troll")
    assert p.companion is None
    assert any("slips away" in m for m in msgs), msgs
    print("PASS  a shaken companion deserts when loyalty breaks")

    # ---- the 'fallen here' echo ----
    deeds = [e for e in get_world_events(limit=50)
             if e["event_type"] == "deed" and e["data"].get("kind") == "defeat"]
    assert deeds and any("fell to" in d["data"]["description"] for d in deeds), deeds
    assert any(d["location_id"] == "forest" for d in deeds), "echo left where they fell"
    print("PASS  defeat leaves a 'fallen here' echo at the spot")

    # ---- every combat path routes through apply_defeat ----
    # Monster retaliation that kills you must apply the wound + town respawn.
    from app.engine.actions.attack import monster_retaliation
    victim = mk("victim", hp=1, max_hp=30, inventory={"coin": 50})
    result = {"name": "Wolf", "attack": 99, "location_id": "forest", "hp": 10, "max_hp": 16}
    monster_retaliation(victim, "wolf_1", result)
    assert victim.location == RESPAWN_LOCATION and "wounded" in victim.status_effects
    assert victim.inventory["coin"] == 40, victim.inventory   # stakes were taken
    print("PASS  monster retaliation defeat carries the same stakes")

    # Raid retaliation likewise.
    from app.raids import _boss_retaliation
    rv = mk("raidvictim", hp=1, max_hp=30, inventory={"coin": 50}, location="warfront")
    out = _boss_retaliation(rv, {"name": "The Ashen Dragon", "attack": 99})
    assert rv.location == RESPAWN_LOCATION and "wounded" in rv.status_effects
    assert any("Ashen Dragon" in m for m in out), out
    print("PASS  raid Warfront defeat carries the same stakes")

    print("\nAll defeat tests passed.")


if __name__ == "__main__":
    main()
