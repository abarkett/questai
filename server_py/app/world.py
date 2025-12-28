from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Exit:
    to: str
    label: str


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    description: str
    exits: List[Exit]


WORLD: Dict[str, Location] = {
    "town_square": Location(
        id="town_square",
        name="Town Square",
        description="A cobblestone plaza with a fountain. People bustle about.",
        exits=[
            Exit(to="tavern", label="tavern"),
            Exit(to="market", label="market"),
            Exit(to="north_road", label="north"),
        ],
    ),
    "tavern": Location(
        id="tavern",
        name="The Sooty Lantern",
        description="Warm light, wooden tables, and the smell of stew.",
        exits=[Exit(to="town_square", label="out")],
    ),
    "market": Location(
        id="market",
        name="Market",
        description="Stalls packed with produce, trinkets, and gossip.",
        exits=[Exit(to="town_square", label="square")],
    ),
    "north_road": Location(
        id="north_road",
        name="North Road",
        description="A dirt road leading toward darker trees.",
        exits=[Exit(to="town_square", label="south"), Exit(to="forest", label="north")],
    ),
    "forest": Location(
        id="forest",
        name="Forest",
        description="Tall pines and shadows. Something watches from afar.",
        exits=[Exit(to="north_road", label="south")],
    ),
}


def get_location(loc_id: str) -> Location:
    loc = WORLD.get(loc_id)
    if not loc:
        raise ValueError(f"Unknown location: {loc_id}")
    return loc

