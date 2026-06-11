"""
Tests for rare bonus loot: trinket drops, and relic drops that enter world
history (echoes + rumor pool).

Run from server_py/:  python3 test_loot.py
"""

import os
import random
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.types import Player  # noqa: E402
from app.db import upsert_player  # noqa: E402
from app.loot import roll_bonus_loot, TRINKETS, RELICS, TRINKET_CHANCE, RELIC_CHANCE  # noqa: E402


class FakeRng:
    def __init__(self, roll):
        self.roll = roll

    def random(self):
        return self.roll

    def choice(self, seq):
        return seq[0]


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="forest",
                level=1, xp=0, hp=20, max_hp=20)
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # Most kills drop nothing extra.
    p = mk("plain")
    assert roll_bonus_loot(p, "Rat", rng=FakeRng(0.5)) == []
    print("PASS  most kills have no bonus drop")

    # Trinket band: a curio lands in the inventory.
    p = mk("lucky")
    msgs = roll_bonus_loot(p, "Wolf", rng=FakeRng(RELIC_CHANCE + 0.001))
    assert any("Bent Locket" in m for m in msgs), msgs
    assert p.inventory.get("bent_locket") == 1
    print("PASS  trinkets drop inside the trinket band")

    # Relic band: the drop enters world history.
    p = mk("blessed")
    msgs = roll_bonus_loot(p, "Goblin", rng=FakeRng(0.0))
    assert any("Tarnished Crown" in m for m in msgs), msgs
    assert p.inventory.get("tarnished_crown") == 1

    # ...as an echo at the spot, visible to others:
    witness = mk("witness")
    from app.echoes import echo_lines, rumor_lines
    assert any("unearthed the Tarnished Crown" in line for line in echo_lines(witness)), \
        echo_lines(witness)
    # ...and as a rumor anyone can hear:
    assert any("unearthed the Tarnished Crown" in line for line in rumor_lines(witness, limit=5))
    print("PASS  relic finds become echoes and rumors")

    # Trinkets and relics are all sellable (defined with values).
    from app.items import get_item
    for iid in TRINKETS + RELICS:
        item = get_item(iid)
        assert item and item.value and item.value > 0, iid
    print("PASS  every trinket and relic is a defined, sellable item")

    # Statistical sanity with the real RNG: rates land near the constants.
    p = mk("grinder")
    rng = random.Random(7)
    hits = sum(1 for _ in range(8000) if roll_bonus_loot(p, "Rat", rng=rng))
    expected = 8000 * (TRINKET_CHANCE + RELIC_CHANCE)
    assert 0.5 * expected < hits < 1.6 * expected, (hits, expected)
    print(f"PASS  drop rate sanity ({hits} bonus drops in 8000 kills)")

    print("\nALL LOOT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
