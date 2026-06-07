"""
Tests for the mountain region (areas/monsters/gear/recipes), the Ice Troll
boss, and multi-stage quests (advance through stages, reward only at the end).

Run from server_py/:  python3 test_content_mountains.py
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

# move() now uses Miriel descriptions; install a test responder (a seam, not a
# gameplay fallback) so move/look work offline.
from app.services.miriel_client import install_test_responder  # noqa: E402
install_test_responder(lambda q: "A vivid, AI-authored scene.")

from app.types import Player  # noqa: E402
from app.db import upsert_player, count_monsters_at  # noqa: E402
from app.world import get_location  # noqa: E402
from app.items import get_item, RECIPES, LOCATION_RESOURCES  # noqa: E402
from app.bosses import BOSS_MECHANICS  # noqa: E402
from app.engine.actions.move import move  # noqa: E402
from app.engine.actions.accept_quest import accept_quest  # noqa: E402
from app.engine.actions.turn_in_quest import turn_in_quest  # noqa: E402
from app.engine.quest_progress import refresh_quests, current_objectives  # noqa: E402


def mk(**kw):
    base = dict(player_id="p", location="town_square", level=30, xp=0, hp=600, max_hp=600)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    # New region exists and connects from the North Road.
    for loc_id in ("foothills", "mountain_pass", "frozen_cave"):
        assert get_location(loc_id) is not None
    p = mk(player_id="x", location="north_road")
    upsert_player(p)
    assert move(p, "hills").ok and p.location == "foothills"
    assert move(p, "up").ok and p.location == "mountain_pass"
    assert move(p, "cave").ok and p.location == "frozen_cave"
    print("PASS  mountain region reachable from North Road")

    # Monsters seeded; new gear/material/recipes defined; Ice Troll is a boss.
    assert count_monsters_at("frozen_cave") == 2 and count_monsters_at("mountain_pass") == 2
    assert get_item("frost_brand").damage == 12 and get_item("frostguard_plate").defense == 8
    assert get_item("frost_crystal").type == "material"
    assert "frost_brand" in RECIPES and "frostguard_plate" in RECIPES
    assert LOCATION_RESOURCES.get("frozen_cave") == "frost_crystal"
    assert "Ice Troll" in BOSS_MECHANICS
    print("PASS  mountain monsters/gear/recipes/boss defined")

    # Multi-stage quest: advances stage by stage, completes only at the end.
    q = mk(player_id="q", location="town_square", inventory={})
    upsert_player(q)
    accept_quest(q, "the_frozen_throne")
    quest = q.active_quests["the_frozen_throne"]
    assert quest.current_stage == 0 and current_objectives(quest)[0].type == "visit"

    # Stage 1: visit the frozen cave.
    q.visited_locations.append("frozen_cave")
    refresh_quests(q)
    quest = q.active_quests["the_frozen_throne"]
    assert quest.current_stage == 1, "should advance to the collect stage"
    assert "the_frozen_throne" not in q.completed_quests

    # Stage 2: gather 3 frost crystals.
    q.inventory["frost_crystal"] = 3
    refresh_quests(q)
    quest = q.active_quests["the_frozen_throne"]
    assert quest.current_stage == 2, "should advance to the kill stage"

    # Stage 3: kill the Ice Troll (set the kill progress, then refresh completes it).
    kobj = current_objectives(quest)[0]
    assert kobj.type == "kill" and kobj.target == "Ice Troll"
    kobj.progress = kobj.required
    refresh_quests(q)
    assert "the_frozen_throne" in q.completed_quests, "final stage completes the quest"

    # Reward only on final turn-in; collected crystals consumed.
    r = turn_in_quest(q, "the_frozen_throne")
    assert r.ok and q.inventory.get("frostguard_plate") == 1 and q.inventory.get("coin") == 120
    assert q.inventory.get("frost_crystal") is None  # 3 consumed
    print("PASS  multi-stage quest advances per stage, rewards once, consumes items")

    print("\nALL MOUNTAIN CONTENT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
