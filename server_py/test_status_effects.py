"""
Offline tests for the status-effect system (Phase 4 slice 8).

Covers DoT/HoT ticking, buff/debuff damage modifiers, expiry, cures, the
elixir buff via `use`, monsters inflicting effects in combat, DoT killing a
player between fights, and persistence.

Run from server_py/:  python3 test_status_effects.py
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
from app.db import upsert_player, get_player  # noqa: E402
from app.status_effects import (  # noqa: E402
    apply_effect, tick_effects, damage_modifier, clear_negative,
)
from app.engine.actions.use import use  # noqa: E402
from app.engine.actions.attack import attack  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="p", location="town_square", level=1, xp=0, hp=40, max_hp=40)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    # DoT ticks damage and expires after its duration.
    p = mk(player_id="a")
    apply_effect(p, "poison", 3, 2)
    m = tick_effects(p)
    assert p.hp == 37 and "Poison" in " ".join(m), (p.hp, m)
    m = tick_effects(p)  # second (final) tick -> expires
    assert p.hp == 34 and "wears off" in " ".join(m), (p.hp, m)
    assert "poison" not in p.status_effects
    print("PASS  DoT ticks damage and wears off on schedule")

    # HoT heals up to max; buff/debuff shift damage; clear removes negatives.
    h = mk(player_id="h", hp=10)
    apply_effect(h, "regen", 5, 3)
    tick_effects(h)
    assert h.hp == 15, h.hp
    b = mk(player_id="b")
    apply_effect(b, "strength", 3, 5)
    apply_effect(b, "weaken", 1, 5)
    assert damage_modifier(b) == 2, damage_modifier(b)  # +3 - 1
    assert clear_negative(b) and "weaken" not in b.status_effects and "strength" in b.status_effects
    print("PASS  HoT heals, buffs/debuffs net out, cure removes only negatives")

    # Antidote cures; elixir applies the strength buff (via `use`).
    pa = mk(player_id="c", inventory={"antidote": 1})
    apply_effect(pa, "poison", 2, 3)
    upsert_player(pa)
    r = use(pa, "antidote")
    assert r.ok and "poison" not in pa.status_effects, (r.messages, pa.status_effects)
    pe = mk(player_id="e", inventory={"elixir_of_strength": 1})
    upsert_player(pe)
    r = use(pe, "elixir of strength")
    assert r.ok and pe.status_effects.get("strength", {}).get("magnitude") == 3, pe.status_effects
    print("PASS  antidote cures and elixir buffs via use")

    # A monster that inflicts poison applies it on retaliation in combat.
    pf = mk(player_id="f", location="cavern", level=3, hp=200, max_hp=200)
    upsert_player(pf)
    r = attack(pf, "Cave Spider")  # spider survives a level-3 hit and bites back
    assert "poison" in pf.status_effects, (pf.status_effects, r.messages)
    print("PASS  monster inflicts a status effect on retaliation")

    # A lingering DoT can defeat a player at the start of their next action.
    pd = mk(player_id="d", location="cavern", level=20, hp=3, max_hp=120)
    apply_effect(pd, "burn", 10, 3)
    upsert_player(pd)
    r = attack(pd, "Cave Troll")
    assert pd.location == "town_square" and pd.hp == pd.max_hp, (pd.location, pd.hp)
    assert pd.status_effects == {}, pd.status_effects  # cleared on respawn
    assert any("overcome" in msg.lower() for msg in r.messages), r.messages
    print("PASS  lingering DoT can defeat and respawn the player")

    # Effects persist through the DB.
    ps = mk(player_id="s")
    apply_effect(ps, "poison", 2, 4)
    upsert_player(ps)
    loaded = get_player("s")
    assert loaded.status_effects.get("poison", {}).get("turns") == 4, loaded.status_effects
    print("PASS  status effects persist through the DB")

    print("\nALL STATUS EFFECT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
