"""
Offline tests for the world map: visited tracking, branching/looping layout,
and the map action's discovered-graph payload.

Run from server_py/:  python3 test_map.py
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
from app.world import get_location  # noqa: E402
from app.engine.actions.create_player import create_player  # noqa: E402
from app.engine.actions.move import move  # noqa: E402
from app.engine.actions.look import look  # noqa: E402
from app.engine.actions.world_map import world_map  # noqa: E402


def main() -> None:
    # New branching areas exist, and there's a loop down to the cavern
    # (forest -> thornwood -> spider_hollow -> cavern) parallel to the main route.
    for loc_id in ("riverside", "old_mill", "thornwood", "spider_hollow"):
        assert get_location(loc_id) is not None
    p = Player(player_id="x", name="Pathfinder", location="forest", level=20, xp=0, hp=200, max_hp=200)
    upsert_player(p)
    move(p, "west")
    assert p.location == "thornwood", p.location
    move(p, "hollow")
    assert p.location == "spider_hollow", p.location
    move(p, "tunnel")
    assert p.location == "cavern", p.location  # alternate route reaches the cavern
    print("PASS  branching areas exist with an alternate loop to the cavern")

    # A second branch off the town.
    t = Player(player_id="t", name="Wayfarer", location="town_square", level=1, xp=0, hp=20, max_hp=20)
    upsert_player(t)
    move(t, "east")
    assert t.location == "riverside", t.location
    move(t, "mill")
    assert t.location == "old_mill", t.location
    print("PASS  riverside branch reachable from the town")

    # Visited tracking: new players start knowing the square; moving discovers more.
    r = create_player("Mapper")
    pid = r.state["player"]["player_id"]
    mp = get_player(pid)
    assert mp.visited_locations == ["town_square"], mp.visited_locations
    move(mp, "north")
    move(mp, "north")  # forest
    saved = get_player(pid)
    assert {"town_square", "north_road", "forest"} <= set(saved.visited_locations), saved.visited_locations
    print(f"PASS  visited locations tracked + persisted: {saved.visited_locations}")

    # look also records discovery and persists it.
    walker = Player(player_id="w", name="Stroller", location="market", level=1, xp=0, hp=10, max_hp=10)
    upsert_player(walker)
    look(walker)
    assert "market" in get_player("w").visited_locations
    print("PASS  look records the current location")

    # map action returns visited nodes (with exits) + the unexplored frontier.
    r = world_map(saved)
    payload = r.state["map"]
    assert payload["current"] == saved.location
    by_id = {n["id"]: n for n in payload["locations"]}
    assert by_id["forest"]["visited"] and by_id["forest"]["exits"], by_id["forest"]
    # deep_forest is a frontier neighbor of forest: present, not visited, no exits revealed.
    assert "deep_forest" in by_id and by_id["deep_forest"]["visited"] is False
    assert by_id["deep_forest"]["exits"] == []
    assert any("Map" in m for m in r.messages)
    print(f"PASS  map payload: {len(by_id)} nodes, current={payload['current']}")

    print("\nALL MAP TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
