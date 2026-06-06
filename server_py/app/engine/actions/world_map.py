from __future__ import annotations

from ...types import Player, ActionResponse
from ...world import WORLD
from ..state_view import build_action_state


def world_map(player: Player) -> ActionResponse:
    """
    Build the player's discovered map: every visited location (with its exits),
    plus the immediate unexplored frontier (neighbors of visited places, shown
    without their own exits to preserve a sense of the unknown).
    """
    visited = set(player.visited_locations) | {player.location}

    nodes: dict[str, dict] = {}
    for loc_id in visited:
        loc = WORLD.get(loc_id)
        if not loc:
            continue
        nodes[loc_id] = {
            "id": loc.id,
            "name": loc.name,
            "visited": True,
            "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
        }

    # Frontier: destinations reachable from visited rooms but not yet entered.
    for loc_id in list(nodes.keys()):
        for e in WORLD[loc_id].exits:
            if e.to not in nodes:
                nloc = WORLD.get(e.to)
                if nloc:
                    nodes[e.to] = {
                        "id": nloc.id,
                        "name": nloc.name,
                        "visited": False,
                        "exits": [],
                    }

    map_payload = {"current": player.location, "locations": list(nodes.values())}

    discovered = len(player.visited_locations)
    frontier = sum(1 for n in nodes.values() if not n["visited"])
    msg = f"Map opened — {discovered} areas discovered"
    if frontier:
        msg += f", {frontier} unexplored nearby"
    messages = [msg + "."]

    state = build_action_state(player, scene_dirty=False)
    state["map"] = map_payload

    return ActionResponse(ok=True, messages=messages, state=state)
