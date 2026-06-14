"""
Tests for the personal stronghold: founding and upgrading tiers, the stash
(with per-tier capacity), tribute accrual/collection, and persistence.

Run from server_py/:  python3 test_stronghold.py
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

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player  # noqa: E402
import app.stronghold as sh  # noqa: E402
from app.stronghold import (  # noqa: E402
    build, deposit, withdraw, collect, status, summary,
    UPGRADE_COST, STASH_SLOTS, TRIBUTE_PER_HOUR, TRIBUTE_CAP_HOURS, tier_name,
)


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=3, xp=0, hp=30, max_hp=30, inventory={"coin": 0})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # ---- founding requires coin; the first build is a Campsite ----
    p = mk("a", inventory={"coin": 40})
    r = build(p)
    assert not r.ok and "costs 50" in r.error, r
    p.inventory["coin"] = 50
    r = build(p)
    assert r.ok and p.stronghold_level == 1 and p.inventory["coin"] == 0, (r.messages, p.stronghold_level)
    assert p.stronghold_collected_at is not None      # tribute clock starts
    assert any("Campsite" in m for m in r.messages), r.messages
    print("PASS  found a Campsite for coin; tribute clock starts")

    # ---- stash respects per-tier capacity ----
    p = mk("b", inventory={"coin": 0})
    r = deposit(p, "pelt", 1)
    assert not r.ok and "build" in r.error.lower(), r   # no stronghold yet
    p.stronghold_level = 1
    p.stronghold_collected_at = sh.now_ms()
    # Fill the Campsite's 6 kinds, then a 7th is refused.
    for i in range(STASH_SLOTS[1]):
        p.inventory[f"mat_{i}"] = 2
        assert deposit(p, f"mat_{i}", 1).ok
    p.inventory["overflow"] = 1
    r = deposit(p, "overflow", 1)
    assert not r.ok and "full" in r.error, r
    assert len(p.stash) == STASH_SLOTS[1]
    print("PASS  stash holds up to the tier's capacity, then refuses new kinds")

    # Topping up an existing stack is always allowed; coin can't be stashed.
    assert deposit(p, "mat_0", 1).ok and p.stash["mat_0"] == 2
    p.inventory["coin"] = 100
    assert not deposit(p, "coin", 10).ok
    print("PASS  existing stacks top up freely; coin can't be stashed")

    # ---- withdraw returns goods to the pack ----
    r = withdraw(p, "mat_0", 1)
    assert r.ok and p.inventory.get("mat_0", 0) == 1 and p.stash["mat_0"] == 1
    r = withdraw(p, "mat_0", 5)   # more than held -> takes what's there
    assert r.ok and "mat_0" not in p.stash
    assert not withdraw(p, "nothing", 1).ok
    print("PASS  withdraw moves goods back, clamped to what's stored")

    # ---- tribute accrues over real time and is capped ----
    p = mk("c", inventory={"coin": 0}, stronghold_level=3)
    # Pretend the last collection was 5 hours ago.
    p.stronghold_collected_at = sh.now_ms() - 5 * 3600 * 1000
    expected = TRIBUTE_PER_HOUR[3] * 5
    assert sh.accrued_tribute(p) == expected, (sh.accrued_tribute(p), expected)
    # ...and 100 hours ago is capped at the 24h ceiling.
    p.stronghold_collected_at = sh.now_ms() - 100 * 3600 * 1000
    assert sh.accrued_tribute(p) == TRIBUTE_PER_HOUR[3] * TRIBUTE_CAP_HOURS
    r = collect(p)
    assert r.ok and p.inventory["coin"] == TRIBUTE_PER_HOUR[3] * TRIBUTE_CAP_HOURS
    assert sh.accrued_tribute(p) == 0           # clock reset on collect
    print("PASS  tribute accrues by tier, caps at 24h, and resets on collect")

    # ---- upgrade path and max tier ----
    p = mk("d", inventory={"coin": 10_000})
    levels = []
    for _ in range(sh.MAX_LEVEL):
        assert build(p).ok
        levels.append(p.stronghold_level)
    assert levels == [1, 2, 3, 4, 5]
    r = build(p)
    assert not r.ok and "grand as it gets" in r.error
    spent = 10_000 - p.inventory["coin"]
    assert spent == sum(UPGRADE_COST.values())
    print("PASS  upgrades climb Campsite -> Citadel, then cap out")

    # ---- persistence ----
    p = mk("e", inventory={"coin": 50})
    build(p)
    p.inventory["dragon_heart"] = 1
    deposit(p, "dragon_heart", 1)
    loaded = get_player("e")
    assert loaded.stronghold_level == 1
    assert loaded.stash.get("dragon_heart") == 1
    assert loaded.stronghold_collected_at is not None
    print("PASS  stronghold level, stash, and tribute clock persist")

    # ---- web summary ----
    s0 = summary(mk("f"))
    assert s0["level"] == 0 and s0["next_cost"] == UPGRADE_COST[1]
    s1 = summary(loaded)
    assert s1["level"] == 1 and s1["tier"] == tier_name(1) and "stash" in s1
    print("PASS  web summary renders for founded and unfounded strongholds")

    print("\nAll stronghold tests passed.")


if __name__ == "__main__":
    main()
