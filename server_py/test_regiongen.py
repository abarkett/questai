"""
Tests for region minting: frontiers open into validated, fully playable
generated regions shared by all players.

Run from server_py/:  python3 test_regiongen.py
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

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_monsters_at  # noqa: E402
from app.regiongen import (  # noqa: E402
    frontier_at, generate_region_spec, validate_region,
    RegionValidationError, budget,
)
from app.engine.actions.explore import explore  # noqa: E402
from app.world import get_location  # noqa: E402


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="riverside",
                level=3, xp=0, hp=30, max_hp=30)
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    # Frontier detection.
    assert frontier_at("riverside") and frontier_at("riverside")["tier"] == 1
    assert frontier_at("magma_core")["tier"] == 6
    assert frontier_at("town_square") is None
    print("PASS  frontiers are where they should be")

    # Spec generation is deterministic and self-validating.
    s1 = generate_region_spec(index=1, tier=1, origin_location="riverside")
    s2 = generate_region_spec(index=1, tier=1, origin_location="riverside")
    assert s1 == s2, "same seed, same region"
    validate_region(s1)
    assert 4 <= len(s1["locations"]) <= 6
    assert any(e["entity_id"].endswith("_boss") for e in s1["entities"])
    assert any(e["type"] == "npc" for e in s1["entities"])
    assert len(s1["quests"]) == 3
    print("PASS  region specs are deterministic, validated, complete")

    # The validator rejects out-of-budget content.
    broken = generate_region_spec(index=2, tier=1, origin_location="riverside")
    broken["entities"][0]["data"]["hp"] = budget(1)["boss_hp_max"] * 10
    try:
        validate_region(broken)
        raise AssertionError("validator must reject out-of-budget stats")
    except RegionValidationError:
        pass
    print("PASS  validator rejects out-of-budget regions")

    # Exploring a frontier mints the region for everyone.
    scout = mk("scout")
    r = explore(scout)
    assert r.ok, r.error
    text = " ".join(r.messages)
    assert "chart" in text and "history" in text, r.messages

    riverside = get_location("riverside")
    new_exits = [e for e in riverside.exits if e.label == "unexplored path"]
    assert new_exits, "frontier exit grafted onto riverside"
    entry = get_location(new_exits[0].to)
    assert "First charted by Hero_scout" in entry.description
    print("PASS  exploring mints a region and canonizes the discoverer")

    # The region is live: monsters seeded, NPC present, quests acceptable.
    region = db.get_region_by_origin("riverside")
    spec_locs = [l["location_id"] for l in db.get_all_gen_locations()
                 if l["region_id"] == region["region_id"]]
    seeded = sum(len(get_monsters_at(lid)) for lid in spec_locs)
    assert seeded >= 2, f"region monsters seeded ({seeded})"

    from app.content import get_quest_template
    scout_quest = get_quest_template(f"{region['region_id']}_scout")
    assert scout_quest and scout_quest.objectives[0].type == "visit"
    from app.engine.actions.accept_quest import accept_quest
    assert accept_quest(scout, scout_quest.quest_id).ok
    print("PASS  minted region is fully playable (monsters, NPC, quests)")

    # A second explorer finds the way already open — same shared region.
    second = mk("second")
    r = explore(second)
    assert r.ok and "already stands open" in " ".join(r.messages), r.messages
    print("PASS  one universe: regions are shared, not instanced")

    # The region's boss lair is itself a frontier (the world grows forever).
    lair = region["data"]["lair"]
    f = frontier_at(lair)
    assert f and f["tier"] == region["tier"] + 1, f
    deeper = mk("deeper", location=lair)
    r = explore(deeper)
    assert r.ok, r.error
    region2 = db.get_region_by_origin(lair)
    assert region2 and region2["tier"] == region["tier"] + 1
    print("PASS  regions chain: each lair opens into a deeper region")

    print("\nALL REGION GENERATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
