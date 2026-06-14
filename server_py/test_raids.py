"""
Tests for co-op raid bosses: a shared world-threat that many players chip down,
pays every contributor on defeat, names the finisher in history, and reseeds.

Run from server_py/:  python3 test_raids.py
"""

import os
import random
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

from app.types import Player  # noqa: E402
from app.db import (  # noqa: E402
    upsert_player,
    get_player,
    get_active_raid_boss,
    get_raid_contributions,
    get_world_events,
)
import app.raids as raids  # noqa: E402
from app.raids import strike_raid, raid_status, ensure_active_raid, raid_summary  # noqa: E402


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="forest",
                level=5, xp=0, hp=40, max_hp=40, inventory={"coin": 0})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


class FixedRng(random.Random):
    """A deterministic rng: randint returns its low bound, random() avoids crits."""
    def randint(self, a, b):
        return a

    def random(self):
        return 0.99


def main() -> None:
    rng = FixedRng()

    # ---- a threat is always looming ----
    ensure_active_raid()
    boss = get_active_raid_boss()
    assert boss is not None and boss["hp"] == boss["max_hp"]
    assert boss["hp"] > 0 and boss["reward_pool"] > 0
    print(f"PASS  a raid boss is seeded ({boss['name']}, {boss['max_hp']} HP)")

    # ---- a strike chips its HP and records the striker's contribution ----
    p = mk("striker", hp=40, max_hp=40)
    before = get_active_raid_boss()["hp"]
    res = strike_raid(p, rng=rng)
    after = get_active_raid_boss()["hp"]
    assert res.ok and after < before, (before, after, res.messages)
    contrib = next(c for c in get_raid_contributions(boss["raid_id"]) if c["player_id"] == "striker")
    assert contrib["damage"] == (before - after), (contrib, before, after)
    assert any("You strike" in m for m in res.messages), res.messages
    print(f"PASS  a strike chips HP ({before}->{after}) and credits the striker")

    # ---- the boss strikes back ----
    p2 = mk("brawler", hp=40, max_hp=40)
    strike_raid(p2, rng=rng)
    reloaded = get_player("brawler")
    assert reloaded.hp < 40, reloaded.hp   # took a counter-blow
    print("PASS  the boss retaliates")

    # ---- a companion adds its damage to the strike ----
    from app.types import Companion
    pc = mk("withpal", hp=40, max_hp=40)
    pc.companion = Companion(npc_id="x", name="Brann", archetype="vanguard", loyalty=100)
    upsert_player(pc)
    hp_before = get_active_raid_boss()["hp"]
    res = strike_raid(pc, rng=rng)
    assert any("Brann adds" in m for m in res.messages), res.messages
    print("PASS  a companion contributes damage to a raid strike")

    # ---- killing blow: everyone paid, finisher crowned & recorded, reseed ----
    boss = get_active_raid_boss()
    raid_id = boss["raid_id"]
    # Two contributors already (striker, brawler, withpal). Add a heavy hitter
    # who will land the finishing blow.
    finisher = mk("finisher", level=99, hp=500, max_hp=500, inventory={"coin": 0})
    # Drive the boss to near-death directly, then let one strike end it.
    db.damage_raid_boss(raid_id, boss["hp"] - 1, "softener", "Softener")
    coins_before = {pid: get_player(pid).inventory.get("coin", 0)
                    for pid in ("striker", "brawler", "withpal")}
    res = strike_raid(finisher, rng=rng)
    assert any("struck the final blow" in m for m in res.messages), res.messages

    # The old boss is defeated and a fresh one has been seeded in its place.
    new_boss = get_active_raid_boss()
    assert new_boss is not None and new_boss["raid_id"] != raid_id
    assert new_boss["hp"] == new_boss["max_hp"]
    print("PASS  defeating the boss reseeds the next threat")

    # Finisher took the trophy and a bonus; earlier contributors were all paid.
    f = get_player("finisher")
    assert f.inventory.get(boss["trophy"], 0) == 1, f.inventory
    assert f.inventory.get("coin", 0) >= raids.FINISHER_BONUS, f.inventory
    for pid, was in coins_before.items():
        now = get_player(pid).inventory.get("coin", 0)
        assert now > was, (pid, was, now)
    print("PASS  every contributor is paid; the finisher claims the trophy")

    # The kill is written into world history, naming the finisher.
    events = get_world_events(limit=20)
    defeated = [e for e in events if e["event_type"] == "raid_defeated"]
    assert defeated and defeated[0]["data"].get("finisher") == "Hero_finisher", defeated
    print("PASS  the defeat enters world history, naming the finisher")

    # ---- status read and web summary ----
    st = raid_status(mk("reader"))
    assert st.ok and any("HP:" in m for m in st.messages), st.messages
    summ = raid_summary(get_player("reader"))
    assert summ and summ["max_hp"] > 0 and "name" in summ
    print("PASS  raid status and web summary render")

    print("\nAll raid tests passed.")


if __name__ == "__main__":
    main()
