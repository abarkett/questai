"""
Tests for world dynamics: monster respawn timers, monster aggression, the
safe-gather cooldown, and ambush risk near hostiles.

Run from server_py/:  python3 test_world_dynamics.py
"""

import os
import random
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import (  # noqa: E402
    seed_world_monsters, record_monster_death, respawn_due_monsters, MONSTER_RESPAWN_MS,
)
seed_world_monsters()

from app.types import Player  # noqa: E402
from app.db import (  # noqa: E402
    upsert_player, monster_exists, remove_monster, get_world_state, set_world_state,
    count_monsters_at,
)
from app.world_entities import MONSTER_AGGRO  # noqa: E402
from app.ambush import maybe_ambush, has_aggressive  # noqa: E402
from app.engine.actions.gather import gather, GATHER_COOLDOWN_MS  # noqa: E402


def mk(**kw):
    base = dict(player_id="p", location="forest", level=20, xp=0, hp=300, max_hp=300)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


class AlwaysRng:
    def random(self):
        return 0.0  # always below AMBUSH_CHANCE


class NeverRng:
    def random(self):
        return 1.0  # never triggers


def main() -> None:
    # Aggression flags: most monsters hostile, rats/beetles passive.
    assert MONSTER_AGGRO.get("Wolf") and MONSTER_AGGRO.get("Cave Troll")
    assert not MONSTER_AGGRO.get("Rat") and not MONSTER_AGGRO.get("Giant Beetle")
    print("PASS  aggression flags (hostiles vs passive)")

    # Respawn: a dead monster comes back once its timer elapses.
    assert monster_exists("goblin_1")
    remove_monster("goblin_1")
    record_monster_death("goblin_1")
    assert respawn_due_monsters() == 0 and not monster_exists("goblin_1")  # too soon
    # Backdate death beyond the respawn window.
    set_world_state("died_goblin_1", str(int(__import__("time").time() * 1000) - MONSTER_RESPAWN_MS - 1000))
    assert respawn_due_monsters() >= 1 and monster_exists("goblin_1")
    print("PASS  monsters respawn after their timer elapses")

    # Rats are excluded from generic respawn (handled by infestation rules).
    remove_monster("rat_1")
    record_monster_death("rat_1")
    set_world_state("died_rat_1", str(int(__import__("time").time() * 1000) - MONSTER_RESPAWN_MS - 1000))
    respawn_due_monsters()
    assert not monster_exists("rat_1")
    print("PASS  rats excluded from generic respawn")

    # Ambush: deterministic with injected RNG.
    p = mk(location="deep_forest")  # has Goblin + Wolf (aggressive)
    upsert_player(p)
    assert has_aggressive("deep_forest")
    before = p.hp
    msgs = maybe_ambush(p, rng=AlwaysRng())
    assert msgs and p.hp < before, (msgs, p.hp)
    assert maybe_ambush(p, rng=NeverRng()) == []
    print(f"PASS  ambush triggers near hostiles ({before - p.hp} dmg) / can miss")

    # No ambush where everything is passive.
    rats = mk(player_id="r", location="forest")
    upsert_player(rats)
    assert maybe_ambush(rats, rng=AlwaysRng()) == []  # rats are passive
    print("PASS  passive areas never ambush")

    # Safe gather cooldown: second immediate gather is refused.
    g = mk(player_id="g", location="forest", inventory={})
    upsert_player(g)
    set_world_state(f"gather_cd_{g.player_id}", "0")
    r1 = gather(g)
    assert r1.ok and g.inventory.get("herb_bundle") == 1
    r2 = gather(g)  # immediately again
    assert r2.ok is False and "recover" in (r2.error or ""), r2.error
    print("PASS  safe gather has a cooldown")

    # Risky gather: near hostiles there's no cooldown but ambush risk; you still
    # collect if you survive.
    gr = mk(player_id="gr", location="deep_forest", hp=300, inventory={})
    upsert_player(gr)
    r = gather(gr)
    assert r.ok and gr.inventory.get("pelt") == 1, (r.error, gr.inventory)
    # And again immediately (no cooldown when risky).
    assert gather(gr).ok and gr.inventory.get("pelt") == 2
    print("PASS  risky gather: no cooldown, collects when you survive")

    print("\nALL WORLD DYNAMICS TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
