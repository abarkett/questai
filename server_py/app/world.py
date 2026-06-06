from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


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
    # Shown instead of `description` when no monsters are present, so a place
    # reads differently once you've cleared it.
    cleared_description: Optional[str] = None


WORLD: Dict[str, Location] = {
    "town_square": Location(
        id="town_square",
        name="Town Square",
        description="A cobblestone plaza with a fountain. People bustle about.",
        exits=[
            Exit(to="tavern", label="tavern"),
            Exit(to="market", label="market"),
            Exit(to="temple", label="temple"),
            Exit(to="north_road", label="north"),
            Exit(to="riverside", label="east"),
        ],
    ),
    "riverside": Location(
        id="riverside",
        name="Riverside",
        description="A reedy bank where a slow river glints in the sun. An old waterwheel creaks downstream.",
        exits=[Exit(to="town_square", label="west"), Exit(to="old_mill", label="mill")],
    ),
    "old_mill": Location(
        id="old_mill",
        name="Abandoned Mill",
        description="A rotting mill leans over the water. Rope and sacks hint that someone is squatting here.",
        cleared_description="A rotting mill leans over the water, empty now but for rope, sacks, and the slap of the current.",
        exits=[Exit(to="riverside", label="out")],
    ),
    "temple": Location(
        id="temple",
        name="Temple of the Dawn",
        description="A quiet sanctuary of white stone and candlelight. A priest tends the wounded beneath a sunburst altar.",
        exits=[Exit(to="town_square", label="out")],
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
        cleared_description="Tall pines and dappled light. The wood is calm for now.",
        exits=[
            Exit(to="north_road", label="south"),
            Exit(to="deep_forest", label="deeper"),
            Exit(to="thornwood", label="west"),
        ],
    ),
    "thornwood": Location(
        id="thornwood",
        name="Thornwood",
        description="A tangle of black brambles and broken light. Something skitters among the thorns.",
        cleared_description="A tangle of black brambles and broken light, still now but for the wind.",
        exits=[Exit(to="forest", label="back"), Exit(to="spider_hollow", label="hollow")],
    ),
    "spider_hollow": Location(
        id="spider_hollow",
        name="Spider Hollow",
        description="A web-choked gully thick with silk that twitches with hidden movement. A dark tunnel breathes cold cave air at the far end.",
        cleared_description="A web-choked gully thick with old silk. A dark tunnel breathes cold cave air at the far end.",
        exits=[Exit(to="thornwood", label="back"), Exit(to="cavern", label="tunnel")],
    ),
    "deep_forest": Location(
        id="deep_forest",
        name="Deep Forest",
        description="The canopy closes overhead. Twisted roots and the growls of larger beasts fill the gloom.",
        cleared_description="The canopy closes overhead over twisted roots. The gloom is quiet, the beasts gone for now.",
        exits=[Exit(to="forest", label="back"), Exit(to="cavern", label="cave")],
    ),
    "cavern": Location(
        id="cavern",
        name="Echoing Cavern",
        description="A damp cave mouth breathes cold air. Bones litter the floor and something massive stirs in the dark.",
        cleared_description="A damp cave mouth breathes cold air over bone-littered stone. Whatever stirred here is still.",
        exits=[
            Exit(to="deep_forest", label="out"),
            Exit(to="spider_hollow", label="hollow"),
            Exit(to="underdeep", label="descend"),
        ],
    ),
    "underdeep": Location(
        id="underdeep",
        name="Sunless Depths",
        description="A lightless warren of tunnels. Pale fungus glows on mythril-veined walls, and the dead do not rest here.",
        cleared_description="A lightless warren of tunnels lit by pale fungus on mythril-veined walls. The dead lie still.",
        exits=[Exit(to="cavern", label="up"), Exit(to="magma_core", label="deeper")],
    ),
    "magma_core": Location(
        id="magma_core",
        name="Magma Core",
        description="The air shimmers with heat above rivers of molten rock. Something ancient and burning coils in the glow.",
        cleared_description="The air shimmers with heat above rivers of molten rock. The glow is empty now.",
        exits=[Exit(to="underdeep", label="ascend")],
    ),
}


def get_location(loc_id: str) -> Location:
    loc = WORLD.get(loc_id)
    if not loc:
        raise ValueError(f"Unknown location: {loc_id}")
    return loc

