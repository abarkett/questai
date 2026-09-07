"""
Tests for build identity: archetypes (passives + ability pools), chosen
progression via skill points, and the learn/path actions.

Run from server_py/:  python3 test_archetypes.py
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

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player  # noqa: E402
from app.progression import total_attack_damage, defense_bonus, apply_xp  # noqa: E402
from app.archetypes import cooldown_ms, learnable, pool_for, ARCHETYPES  # noqa: E402
from app.engine.actions.choose_path import choose_path  # noqa: E402
from app.engine.actions.learn import learn  # noqa: E402
from app.engine.actions.create_player import create_player  # noqa: E402


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=2, xp=0, hp=15, max_hp=15, inventory={"coin": 0})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # ---- passives fold into the combat maths ----
    base_atk = total_attack_damage(mk("plain"))
    base_def = defense_bonus(mk("plain2"))
    assert total_attack_damage(mk("t", archetype="trickster")) == base_atk + 3
    assert defense_bonus(mk("w", archetype="warden")) == base_def + 3
    # Warden gets no attack bonus; trickster no defense bonus.
    assert total_attack_damage(mk("w2", archetype="warden")) == base_atk
    # Channeler's cooldowns are 30% shorter; others are unchanged.
    assert cooldown_ms(mk("c", archetype="channeler"), 100) == 70000
    assert cooldown_ms(mk("w3", archetype="warden"), 100) == 100000
    assert cooldown_ms(mk("none"), 100) == 100000          # no archetype
    print("PASS  archetype passives fold into attack, defense, and cooldowns")

    # ---- create with / without a path ----
    r = create_player("Pathed", "channeler")
    assert r.state["player"]["archetype"] == "channeler"
    assert any("Channeler" in m for m in r.messages), r.messages
    r2 = create_player("Open", None)
    assert r2.state["player"]["archetype"] is None
    assert any("path" in m.lower() for m in r2.messages), r2.messages
    print("PASS  create can set a path, or leave it open with a prompt")

    # ---- choose_path: set once, never again ----
    p = mk("chooser", archetype=None)
    assert not choose_path(p, "nonsense").ok
    assert choose_path(p, "warden").ok and p.archetype == "warden"
    assert not choose_path(p, "trickster").ok            # no take-backs
    print("PASS  choose_path sets an open path once, rejects rechoose & nonsense")

    # ---- levelling grants skill points, not auto-abilities ----
    p = mk("climber", level=1, archetype="trickster", abilities=[])
    msgs = apply_xp(p, 10_000)        # jump several levels
    assert p.skill_points == p.level - 1, (p.skill_points, p.level)
    assert p.abilities == []          # nothing auto-learned
    assert any("skill point" in m.lower() for m in msgs), msgs
    print("PASS  level-ups grant skill points; abilities are not auto-granted")

    # ---- learn spends points within your pool and level ----
    p = mk("student", level=2, archetype="trickster", skill_points=2, abilities=[])
    # quick_strike (L2) is on the trickster path; rupture (L4) is too but gated.
    assert learn(p, "rupture").ok is False               # level too low
    assert learn(p, "cleave").ok is False                # not on trickster path
    r = learn(p, "quick_strike")
    assert r.ok and "quick_strike" in p.abilities and p.skill_points == 1
    assert learn(p, "quick_strike").ok is False          # already known
    print("PASS  learn respects pool, level, points, and duplicates")

    # No points left -> refused even for a valid pick.
    p2 = mk("broke", level=8, archetype="trickster", skill_points=0, abilities=[])
    assert learn(p2, "quick_strike").ok is False
    print("PASS  learn refused without skill points")

    # ---- pools are distinct, and a legacy (pathless) player uses generalist ----
    assert dict(pool_for(mk("w4", archetype="warden"))) != dict(pool_for(mk("c2", archetype="channeler")))
    legacy = mk("legacy", level=12, archetype=None)
    gen = {a for a, _ in pool_for(legacy)}
    assert {"power_strike", "second_wind", "rend", "cleave", "rupture"} == gen
    print("PASS  archetype pools differ; pathless players fall back to generalist")

    # ---- deeper pools: six abilities each, reaching L12 ----
    for a in ARCHETYPES.values():
        assert len(a.pool) == 6, (a.id, len(a.pool))
        assert max(req for _, req in a.pool) == 12
    print("PASS  every path now offers six abilities up to level 12")

    # ---- capstones cost 2 points, so end-game builds must choose ----
    from app.abilities import get_ability
    assert get_ability("crushing_blow").cost == 2
    cap = mk("capper", level=12, archetype="warden", skill_points=1, abilities=[])
    r = learn(cap, "crushing_blow")
    assert not r.ok and "costs 2" in r.error, r.error       # can't afford yet
    cap.skill_points = 2
    assert learn(cap, "crushing_blow").ok and cap.skill_points == 0
    assert "crushing_blow" in cap.abilities
    print("PASS  a capstone costs 2 skill points; learning it drains them")

    # ---- a buff ability applies its status effect and starts a cooldown ----
    from app.engine.actions.use_ability import use_ability
    from app.status_effects import damage_modifier
    war = mk("crier", level=10, archetype="warden", abilities=["rallying_cry"])
    r = use_ability(war, "rallying_cry")
    assert r.ok and "strength" in war.status_effects, (r, war.status_effects)
    assert damage_modifier(war) == 3                       # +3 damage while it lasts
    assert war.ability_cooldowns.get("rallying_cry", 0) > 0
    print("PASS  buff abilities apply a self status effect")

    # ---- persistence ----
    p = mk("persist", archetype="channeler", skill_points=3)
    p.abilities = ["firebolt"]
    upsert_player(p)
    lo = get_player("persist")
    assert lo.archetype == "channeler" and lo.skill_points == 3 and lo.abilities == ["firebolt"]
    print("PASS  archetype, skill points, and learned abilities persist")

    print("\nAll archetype tests passed.")


if __name__ == "__main__":
    main()
