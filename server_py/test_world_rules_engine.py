"""
Tests for the data-driven world rule engine: rules stored as JSON
condition/effect lists in the world_rules table, run by the interpreter.

Run from server_py/:  python3 test_world_rules_engine.py
"""

import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.db import (  # noqa: E402
    upsert_world_rule, get_world_state, set_world_state, get_monsters_at,
    increment_world_turn, get_world_events,
)
from app.world_rules import evaluate_db_rules, seed_default_db_rules  # noqa: E402


def main() -> None:
    # A rule with a met condition fires its effects.
    upsert_world_rule(
        rule_id="t_omen",
        name="Omen",
        description=None,
        conditions=[{"world_state_ne": {"key": "omen_seen", "value": "true"}}],
        effects=[
            {"set_state": {"key": "omen_seen", "value": "true"}},
            {"log_event": {"description": "Strange lights dance over the forest."}},
        ],
        cooldown_turns=0,
    )
    triggered = evaluate_db_rules()
    assert "Omen" in triggered, triggered
    assert get_world_state("omen_seen") == "true"
    assert any("Strange lights" in (e["data"].get("description") or "")
               for e in get_world_events(20))
    # Condition now false: it must not fire again.
    assert "Omen" not in evaluate_db_rules()
    print("PASS  conditions gate effects; effects mutate state and log events")

    # Cooldowns hold a rule down for N turns after it triggers.
    upsert_world_rule(
        rule_id="t_tide",
        name="Tide",
        description=None,
        conditions=[{"world_state_ne": {"key": "never", "value": "set"}}],
        effects=[{"set_state_turn": {"key": "tide_turn"}}],
        cooldown_turns=5,
    )
    assert "Tide" in evaluate_db_rules()
    assert "Tide" not in evaluate_db_rules(), "cooldown holds"
    for _ in range(5):
        increment_world_turn()
    assert "Tide" in evaluate_db_rules(), "cooldown elapsed"
    print("PASS  cooldown_turns throttles re-triggering")

    # Monster-count conditions + spawn effects: the seeded wandering beast.
    seed_default_db_rules()
    triggered = evaluate_db_rules()
    assert "A Wandering Beast" in triggered, triggered
    beasts = [m for m in get_monsters_at("north_road") if m["name"] == "Wandering Beast"]
    assert beasts, "beast spawned on the North Road"
    # While it lives, the count condition blocks a respawn.
    assert "A Wandering Beast" not in evaluate_db_rules()
    print("PASS  seeded wandering-beast rule spawns and self-limits")

    # turns_since_state condition.
    set_world_state("ritual_started", str(0))
    upsert_world_rule(
        rule_id="t_ritual",
        name="Ritual",
        description=None,
        conditions=[{"turns_since_state": {"key": "ritual_started", "gte": 3}}],
        effects=[{"set_state": {"key": "ritual_done", "value": "true"}}],
        cooldown_turns=0,
    )
    evaluate_db_rules()
    assert get_world_state("ritual_done") == "true"
    print("PASS  turns_since_state condition works")

    print("\nALL WORLD RULE ENGINE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
