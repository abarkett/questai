"""
Tests for the content registry (app/content.py): generated locations, items,
entities, and quests stored in the gen_* tables must be served through the
same accessors as the hand-authored catalogs.

Run from server_py/:  python3 test_content_registry.py
"""

import os
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app import content  # noqa: E402
from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.world import get_location  # noqa: E402
from app.items import get_item, get_recipe  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_monsters_at  # noqa: E402


def main() -> None:
    # Static content resolves untouched.
    loc = get_location("town_square")
    assert loc.name == "Town Square"
    assert get_item("iron_sword").damage == 5
    print("PASS  static content resolves through the registry")

    # A generated location becomes a first-class location.
    db.upsert_gen_location(
        location_id="gloom_hollow",
        region_id="r_test",
        name="Gloom Hollow",
        description="A sunken hollow of grey trees.",
        cleared_description="A sunken hollow, quiet now.",
        exits=[{"to": "forest", "label": "out"}],
        outdoor=True,
        resource="gloom_moss",
    )
    content.invalidate_cache()
    gen = get_location("gloom_hollow")
    assert gen.name == "Gloom Hollow"
    assert any(e.to == "forest" for e in gen.exits)
    assert content.is_outdoor("gloom_hollow")
    assert content.resource_at("gloom_hollow") == "gloom_moss"
    assert content.resource_at("forest") == "herb_bundle"  # static still wins
    print("PASS  generated location resolves with exits, outdoor flag, resource")

    # Exits graft onto static locations (frontier -> new region).
    db.add_gen_exit("forest", "gloom_hollow", "hollow")
    merged = get_location("forest")
    assert any(e.to == "gloom_hollow" for e in merged.exits)
    print("PASS  generated exits graft onto static locations")

    # Generated items (with recipes) fall through items.get_item/get_recipe.
    db.upsert_gen_item(
        item_id="gloom_moss",
        data={"item_id": "gloom_moss", "name": "Gloom Moss", "type": "material", "value": 6},
        recipe=None,
    )
    db.upsert_gen_item(
        item_id="mossblade",
        data={"item_id": "mossblade", "name": "Mossblade", "type": "weapon",
              "slot": "weapon", "damage": 7, "value": 50},
        recipe={"inputs": {"gloom_moss": 4}, "qty": 1},
    )
    content.invalidate_cache()
    assert get_item("gloom_moss").name == "Gloom Moss"
    assert get_item("mossblade").damage == 7
    assert get_recipe("mossblade")["inputs"] == {"gloom_moss": 4}
    assert get_item("iron_sword").damage == 5  # static unaffected
    print("PASS  generated items and recipes fall through item accessors")

    # Generated NPCs and monsters surface at their location.
    db.upsert_gen_entity(
        entity_id="moss_keeper",
        location_id="gloom_hollow",
        name="Moss Keeper",
        type="npc",
        data={"role": "quest_giver", "quests": ["gloom_rats"]},
    )
    db.upsert_gen_entity(
        entity_id="gloom_stalker_1",
        location_id="gloom_hollow",
        name="Gloom Stalker",
        type="monster",
        data={"hp": 20, "attack": 5, "xp_reward": 15, "loot": {"coin": 5},
              "inflicts": {"effect": "poison", "magnitude": 2, "turns": 2},
              "aggressive": True},
    )
    content.invalidate_cache()
    seed_world_monsters()  # picks up the new catalog monster
    monsters = get_monsters_at("gloom_hollow")
    assert any(m["name"] == "Gloom Stalker" for m in monsters), monsters
    assert content.monster_inflicts("Gloom Stalker")["effect"] == "poison"
    assert content.monster_aggro("Gloom Stalker") is True
    from app.engine.entities import get_world_entities_at
    ents = get_world_entities_at("gloom_hollow")
    assert any(e.type == "npc" and e.name == "Moss Keeper" for e in ents)
    print("PASS  generated NPCs and monsters live at their location")

    # Generated monsters appear in the bestiary catalog.
    from app.bestiary import known_monster, catalog_entry
    assert known_monster("Gloom Stalker")
    assert catalog_entry("Gloom Stalker")["attack"] == 5
    print("PASS  generated monsters join the bestiary")

    # Generated quests resolve through the template lookup and can be accepted.
    db.upsert_gen_quest(
        quest_id="gloom_rats",
        region_id="r_test",
        data={
            "quest_id": "gloom_rats",
            "name": "Stalkers in the Gloom",
            "description": "Cull the gloom stalkers.",
            "objectives": [{"type": "kill", "target": "Gloom Stalker", "required": 1}],
            "rewards": {"coin": 10},
            "repeatable": True,
        },
    )
    content.invalidate_cache()
    q = content.get_quest_template("gloom_rats")
    assert q and q.name == "Stalkers in the Gloom"

    p = Player(player_id="p", name="P", location="gloom_hollow", level=1, xp=0, hp=20, max_hp=20)
    upsert_player(p)
    from app.engine.actions.accept_quest import accept_quest
    r = accept_quest(p, "gloom_rats")
    assert r.ok and "gloom_rats" in p.active_quests, r.error
    print("PASS  generated quests are offered and acceptable")

    print("\nALL CONTENT REGISTRY TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
