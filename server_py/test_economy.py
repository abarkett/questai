"""
Offline tests for the economy + crafting loop (Phase 4 slice 4).

Covers gather-by-location, crafting from recipes (incl. missing-material
errors), selling at a shop, and buying gear with coin.

Run from server_py/:  python3 test_economy.py
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
from app.engine.actions.gather import gather  # noqa: E402
from app.engine.actions.craft import craft  # noqa: E402
from app.engine.actions.sell import sell  # noqa: E402
from app.engine.actions.buy import buy  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="p", location="town_square", level=1, xp=0, hp=20, max_hp=20)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    # Gather yields the location's resource; barren spots refuse.
    pf = mk(player_id="g", location="forest", inventory={})
    upsert_player(pf)
    gather(pf)
    assert pf.inventory.get("herb_bundle") == 1, pf.inventory
    pc = mk(player_id="c", location="cavern", inventory={})
    upsert_player(pc)
    gather(pc)
    assert pc.inventory.get("iron_ore") == 1, pc.inventory
    assert gather(mk(player_id="t", location="town_square", inventory={})).ok is False
    print("PASS  gather yields location resource; barren spots refuse")

    # Craft consumes materials and produces output; missing -> error.
    pk = mk(player_id="k", inventory={"herb_bundle": 3})
    upsert_player(pk)
    r = craft(pk, "healing_potion")
    assert r.ok and pk.inventory.get("healing_potion") == 1, (r.error, pk.inventory)
    assert "herb_bundle" not in pk.inventory, pk.inventory
    assert craft(mk(player_id="k2", inventory={"iron_ore": 1}), "iron_sword").ok is False
    print("PASS  craft consumes materials; missing materials rejected")

    # Sell at a shop converts loot to coin; non-shop / junk refused.
    ps = mk(player_id="s", location="town_square", inventory={"pelt": 1})
    upsert_player(ps)
    r = sell(ps, "pelt")
    assert r.ok and ps.inventory.get("coin") == 4 and "pelt" not in ps.inventory, (r.error, ps.inventory)
    assert sell(mk(player_id="s2", location="forest", inventory={"pelt": 1}), "pelt").ok is False
    print("PASS  sell at shop -> coin; no shop -> refused")

    # Buy gear with coin (normalized name with a space).
    pb = mk(player_id="b", location="town_square", inventory={"coin": 25})
    upsert_player(pb)
    r = buy(pb, "iron sword")
    assert r.ok and pb.inventory.get("iron_sword") == 1 and pb.inventory.get("coin") == 5, (r.error, pb.inventory)
    print(f"PASS  buy gear with coin: {dict(pb.inventory)}")

    print("\nALL ECONOMY TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
