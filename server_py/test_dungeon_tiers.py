"""
Offline tests for the deep-dungeon tiers (Phase 4 slice 6).

Covers the two new locations and their connectivity, the new monsters
seeding (and into legacy saves), new gear/material/recipe definitions, the
blacksmith vendor, and gathering the new high-tier resources.

Run from server_py/:  python3 test_dungeon_tiers.py
"""

import json
import os
import tempfile

import app.db as db

_tmps = []


def fresh_db() -> str:
    t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    t.close()
    _tmps.append(t.name)
    db.DB_PATH = t.name
    db.init_db()
    return t.name


fresh_db()

from app.engine.entities import seed_world_monsters  # noqa: E402
from app.db import count_monsters_at, upsert_player  # noqa: E402
from app.world import get_location  # noqa: E402
from app.items import ITEMS, RECIPES, LOCATION_RESOURCES, get_item  # noqa: E402
from app.types import Player  # noqa: E402
from app.engine.actions.move import move  # noqa: E402
from app.engine.actions.gather import gather  # noqa: E402
from app.engine.actions.craft import craft  # noqa: E402
from app.engine.actions.buy import buy  # noqa: E402
from app.engine.actions.equip import equip  # noqa: E402
from app.progression import defense_bonus, weapon_bonus  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="p", location="town_square", level=1, xp=0, hp=300, max_hp=300)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")
    return Player(**base)


def main() -> None:
    seed_world_monsters()

    # New locations exist and chain off the cavern.
    for loc_id in ("underdeep", "magma_core"):
        assert get_location(loc_id) is not None
    p = mk(player_id="x", location="cavern", level=20)
    upsert_player(p)
    move(p, "descend")
    assert p.location == "underdeep", p.location
    # The deep path to the core now runs through several new rooms.
    for label, dest in [("deeper", "abyssal_stair"), ("down", "obsidian_gallery"),
                        ("deeper", "sulfur_vents"), ("deeper", "ashen_waste"),
                        ("forge", "the_great_forge"), ("core", "magma_core")]:
        assert move(p, label).ok and p.location == dest, (label, p.location)
    move(p, "ascend")
    assert p.location == "the_great_forge", p.location
    print("PASS  new dungeon tiers exist and the deep path is traversable")

    # New monsters seeded into the fresh world.
    assert count_monsters_at("underdeep") == 2
    assert count_monsters_at("magma_core") == 2
    print("PASS  deep-tier monsters seeded")

    # New content lands in a legacy save without resurrecting old monsters.
    fresh_db()
    db.set_world_state("monsters_seeded", "true")
    seed_world_monsters()
    assert count_monsters_at("forest") == 0           # legacy rats not revived
    assert count_monsters_at("magma_core") == 2       # new content added
    seeded = set(json.loads(db.get_world_state("seeded_monster_instances")))
    assert {"molten_wyrm_1", "bone_knight_1"} <= seeded, seeded
    print("PASS  deep tiers reach legacy saves; no resurrection")

    # New gear / materials / recipes are defined and tiered correctly.
    for wid in ("knight_blade", "wyrmfang_blade"):
        assert get_item(wid) and get_item(wid).type == "weapon"
    for aid in ("chainmail", "dragonscale_armor"):
        assert get_item(aid) and get_item(aid).type == "armor"
    assert get_item("wyrmfang_blade").damage > get_item("knight_blade").damage > 5
    assert get_item("dragonscale_armor").defense > get_item("chainmail").defense > 4
    for mat in ("mythril_ore", "ember_core"):
        assert get_item(mat) and get_item(mat).type == "material"
    for r in ("knight_blade", "chainmail", "wyrmfang_blade", "dragonscale_armor", "greater_healing_potion"):
        assert r in RECIPES, r
    print("PASS  deep-tier gear, materials, and recipes defined")

    # Gather the new resources in their locations.
    gw = mk(player_id="g", location="underdeep", inventory={})
    upsert_player(gw)
    gather(gw)
    assert gw.inventory.get("mythril_ore") == 1, gw.inventory
    gm = mk(player_id="m", location="magma_core", inventory={})
    upsert_player(gm)
    gather(gm)
    assert gm.inventory.get("ember_core") == 1, gm.inventory
    print("PASS  high-tier resources are gatherable")

    # Craft the endgame weapon from gathered materials and equip it.
    pc = mk(player_id="c", inventory={"ember_core": 3, "mythril_ore": 5})
    upsert_player(pc)
    r = craft(pc, "wyrmfang_blade")
    assert r.ok and pc.inventory.get("wyrmfang_blade") == 1, (r.error, pc.inventory)
    equip(pc, "wyrmfang_blade")
    assert weapon_bonus(pc) == 14
    print("PASS  endgame weapon crafted and equipped")

    # Blacksmith in the market sells mid-tier gear.
    pb = mk(player_id="b", location="market", inventory={"coin": 100})
    upsert_player(pb)
    r = buy(pb, "chainmail")
    assert r.ok and pb.inventory.get("chainmail") == 1 and pb.inventory.get("coin") == 30, (r.error, pb.inventory)
    equip(pb, "chainmail")
    assert defense_bonus(pb) == 6
    print("PASS  blacksmith sells mid-tier gear")

    print("\nALL DUNGEON TIER TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        for path in _tmps:
            try:
                os.unlink(path)
            except OSError:
                pass
