"""
Tests for companions: recruiting an ally, their deterministic combat
contribution, loyalty growth, and persistence.

Run from server_py/:  python3 test_companions.py
"""

import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")
# Companion banter is best-effort; with no Miriel key it must fall back to text
# rather than raising, which is exactly what these tests exercise.
os.environ.pop("MIRIEL_API_KEY", None)

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.types import Player, Companion  # noqa: E402
from app.db import upsert_player, get_player, get_monsters_at  # noqa: E402


def monster_hp(instance_id: str, location: str = "forest") -> int:
    for m in get_monsters_at(location):
        if m["instance_id"] == instance_id:
            return m["hp"]
    return 0
from app.companions import (  # noqa: E402
    RECRUIT_COST,
    companion_level,
    companion_attack,
    companion_heal,
    guard_mult,
    gain_loyalty,
    pick_archetype,
    is_recruitable,
    companion_combat_turn,
)
from app.engine.actions.recruit import recruit  # noqa: E402
from app.engine.actions.dismiss import dismiss  # noqa: E402
from app.engine.actions.companion_status import companion_status  # noqa: E402
from app.engine.actions.fight import fight  # noqa: E402


def mk(pid: str, location: str = "forest", **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location=location,
                level=1, xp=0, hp=30, max_hp=30, inventory={"coin": 100})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def vanguard(name="Brann", loyalty=0) -> Companion:
    return Companion(npc_id="x", name=name, archetype="vanguard", loyalty=loyalty)


def main() -> None:
    # ---- deterministic mechanics ----
    c = vanguard(loyalty=0)
    assert companion_level(c) == 1
    c.loyalty = 25
    assert companion_level(c) == 2
    c.loyalty = 100
    assert companion_level(c) == 5
    print("PASS  loyalty maps to levels 1..5")

    v = Companion(npc_id="x", name="V", archetype="vanguard", loyalty=0)
    m = Companion(npc_id="x", name="M", archetype="mender", loyalty=0)
    o = Companion(npc_id="x", name="O", archetype="outrider", loyalty=0)
    assert companion_attack(v) == 5 and companion_attack(o) == 2 and companion_attack(m) == 0
    assert companion_heal(m) == 3 and companion_heal(v) == 0
    # Everyone gives some cover; the outrider's grows as they level.
    assert guard_mult(v) < 1.0 and guard_mult(m) == 1.0 and guard_mult(None) == 1.0
    o_l5 = Companion(npc_id="x", name="O5", archetype="outrider", loyalty=100)
    assert guard_mult(o_l5) < guard_mult(o) <= guard_mult(v)
    print("PASS  archetypes have distinct, deterministic combat profiles")

    # gain_loyalty reports level-ups and caps at the maximum.
    c = vanguard(loyalty=24)
    assert gain_loyalty(c, 1) is True and c.loyalty == 25  # crossed into L2
    assert gain_loyalty(c, 1) is False
    c.loyalty = 100
    assert gain_loyalty(c, 5) is False and c.loyalty == 100
    print("PASS  gain_loyalty signals level-ups and caps")

    # ---- recruitability rules ----
    assert is_recruitable({"type": "npc", "role": "healer"})
    assert is_recruitable({"type": "npc", "role": "generic"})
    assert not is_recruitable({"type": "npc", "role": "shop"})
    assert not is_recruitable({"type": "npc", "role": "quest_giver"})
    assert pick_archetype({"id": "priest", "role": "healer"}) == "mender"
    # Non-healers get a stable archetype from their id.
    a1 = pick_archetype({"id": "guard_42", "role": "generic"})
    assert a1 == pick_archetype({"id": "guard_42", "role": "generic"})
    print("PASS  recruitability and archetype assignment")

    # ---- recruit action against the real world ----
    p = mk("rec", location="temple", inventory={"coin": 10})  # too poor
    r = recruit(p, "Temple Priest")
    assert not r.ok and "signing bonus" in r.error, r
    assert p.companion is None
    print("PASS  recruit refused when you can't afford the signing bonus")

    p.inventory["coin"] = 100
    r = recruit(p, "Temple Priest")
    assert r.ok, r
    assert p.companion and p.companion.name == "Temple Priest"
    assert p.companion.archetype == "mender"   # a healer joins as a mender
    assert p.inventory["coin"] == 100 - RECRUIT_COST
    print("PASS  recruit hires a real NPC, deducts the fee, sets the archetype")

    # One companion at a time.
    r2 = recruit(p, "Temple Priest")
    assert not r2.ok and "already travels" in r2.error
    print("PASS  only one companion at a time")

    # Can't recruit a world-anchoring NPC.
    p2 = mk("rec2", location="town_square")
    r3 = recruit(p2, "Town Warden")  # quest_giver
    assert not r3.ok and "won't be joining" in r3.error
    print("PASS  world-anchoring NPCs refuse to be recruited")

    # ---- persistence round-trip ----
    reloaded = get_player("rec")
    assert reloaded.companion is not None
    assert reloaded.companion.archetype == "mender"
    assert reloaded.companion.name == "Temple Priest"
    print("PASS  companion survives a save/load round-trip")

    # dismiss clears it.
    d = dismiss(reloaded)
    assert d.ok and reloaded.companion is None
    assert get_player("rec").companion is None
    print("PASS  dismiss parts ways and persists")

    # ---- combat contribution ----
    # A vanguard strikes the monster for exactly its flat attack (Wolf has 16
    # HP, so a 5-damage blow lands without finishing it).
    p = mk("fighter", location="deep_forest")
    p.companion = vanguard(loyalty=0)            # attack 5
    before = monster_hp("wolf_1", "deep_forest")
    msgs, kill = companion_combat_turn(p, "wolf_1")
    after = monster_hp("wolf_1", "deep_forest")
    assert before == 16 and kill is None and (before - after) == 5, (before, after, msgs)
    assert any("strikes the Wolf for 5" in m for m in msgs), msgs
    print("PASS  vanguard companion strikes for its flat attack")

    # ...and lands the finishing blow when its strike would drop the target.
    p = mk("finisher", location="forest")
    p.companion = vanguard(loyalty=0)            # attack 5 == Rat HP
    msgs, kill = companion_combat_turn(p, "rat_1")
    assert kill is not None and kill["name"] == "Rat", (kill, msgs)
    print("PASS  companion can land the killing blow")

    # A mender heals a wounded ally instead of swinging.
    p = mk("wounded", location="forest", hp=10, max_hp=30)
    p.companion = Companion(npc_id="x", name="Saoirse", archetype="mender", loyalty=0)
    msgs, kill = companion_combat_turn(p, "rat_2")
    assert kill is None and p.hp == 13, (p.hp, msgs)   # +3 heal
    assert any("tends your wounds" in m for m in msgs), msgs
    # At full health the mender does nothing.
    p.hp = p.max_hp
    msgs, _ = companion_combat_turn(p, "rat_2")
    assert msgs == []
    print("PASS  mender heals the wounded and idles at full health")

    # ---- full fight: companion is announced and loyalty grows on victory ----
    p = mk("winner", location="forest", level=12, hp=60, max_hp=60)
    p.companion = vanguard(name="Brann", loyalty=24)   # one win from L2
    res = fight(p, "Rat", stance="bold")
    assert res.ok, res
    assert any("Brann stands with you" in m for m in res.messages), res.messages
    # The fight should be won (level-12 hero vs a seeded Rat); loyalty ticks up.
    assert p.companion.loyalty == 25, p.companion.loyalty
    assert p.companion.battles == 1
    assert any("Brann" in m and "good at this" in m for m in res.messages) \
        or companion_level(p.companion) == 2, res.messages
    print("PASS  companion joins the fight and grows loyal on victory")

    print("\nAll companion tests passed.")


if __name__ == "__main__":
    main()
