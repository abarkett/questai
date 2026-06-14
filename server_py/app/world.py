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
            Exit(to="warfront", label="warfront"),
        ],
    ),
    "warfront": Location(
        id="warfront",
        name="The Warfront",
        description=(
            "A windswept rise just beyond the town walls where the realm musters "
            "against its great threats. Banners snap; the ground is churned by the "
            "feet of everyone who has come to make a stand here."
        ),
        cleared_description=(
            "A quiet, churned rise beyond the walls. Tattered banners mark where "
            "the realm last made its stand."
        ),
        exits=[Exit(to="town_square", label="back")],
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
        exits=[
            Exit(to="town_square", label="south"),
            Exit(to="forest", label="north"),
            Exit(to="foothills", label="hills"),
        ],
    ),
    "foothills": Location(
        id="foothills",
        name="Windy Foothills",
        description="Grassy slopes rise toward jagged peaks. Loose scree shifts underfoot and shapes move among the rocks.",
        cleared_description="Grassy slopes rise toward jagged peaks under a wide, empty sky.",
        exits=[Exit(to="north_road", label="down"), Exit(to="mountain_pass", label="up")],
    ),
    "mountain_pass": Location(
        id="mountain_pass",
        name="Mountain Pass",
        description="A knife-edge trail between cliffs. Wind screams through the gap and wings beat somewhere above.",
        cleared_description="A knife-edge trail between cliffs, silent now but for the wind.",
        exits=[Exit(to="foothills", label="down"), Exit(to="frozen_cave", label="cave")],
    ),
    "frozen_cave": Location(
        id="frozen_cave",
        name="Frozen Cave",
        description="Walls of blue ice glitter in the dark. The cold bites deep, and something vast shifts in the glacier.",
        cleared_description="Walls of blue ice glitter in the dark, still and silent.",
        exits=[Exit(to="mountain_pass", label="out")],
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
        exits=[Exit(to="cavern", label="up"), Exit(to="abyssal_stair", label="deeper")],
    ),
    "abyssal_stair": Location(
        id="abyssal_stair",
        name="Abyssal Stair",
        description="A vast spiral stair plunges into blackness. Things with too many wings flit past in the dark.",
        cleared_description="A vast spiral stair plunges into blackness, silent and still.",
        exits=[Exit(to="underdeep", label="up"), Exit(to="obsidian_gallery", label="down")],
    ),
    "obsidian_gallery": Location(
        id="obsidian_gallery",
        name="Obsidian Gallery",
        description="A hall of black glass pillars reflects a hundred warped images of you. Something heavy moves between them.",
        cleared_description="A hall of black glass pillars stands quiet, reflecting only you.",
        exits=[Exit(to="abyssal_stair", label="up"), Exit(to="sulfur_vents", label="deeper")],
    ),
    "sulfur_vents": Location(
        id="sulfur_vents",
        name="Sulfur Vents",
        description="Scalding steam hisses from cracks in the rock and the stink of sulfur claws the throat. Shapes coil in the haze.",
        cleared_description="Scalding steam hisses from cracks in the rock; the haze is otherwise empty.",
        exits=[Exit(to="obsidian_gallery", label="back"), Exit(to="ashen_waste", label="deeper")],
    ),
    "ashen_waste": Location(
        id="ashen_waste",
        name="Ashen Waste",
        description="A grey plain of ash stretches under a rain of cinders. Burnt figures stir where they fell.",
        cleared_description="A grey plain of ash stretches under a slow rain of cinders, undisturbed.",
        exits=[Exit(to="sulfur_vents", label="back"), Exit(to="the_great_forge", label="forge")],
    ),
    "the_great_forge": Location(
        id="the_great_forge",
        name="The Great Forge",
        description="A titanic ruined forge straddles a river of fire. Its guardian has not slept in an age.",
        cleared_description="A titanic ruined forge straddles a river of fire, its guardian finally still.",
        exits=[Exit(to="ashen_waste", label="back"), Exit(to="magma_core", label="core")],
    ),
    "magma_core": Location(
        id="magma_core",
        name="Magma Core",
        description="The air shimmers with heat above rivers of molten rock. Something ancient and burning coils in the glow.",
        cleared_description="The air shimmers with heat above rivers of molten rock. The glow is empty now.",
        exits=[Exit(to="the_great_forge", label="ascend")],
    ),
}


def get_location(loc_id: str) -> Location:
    # The content registry merges this static map with generated regions and
    # any exits grafted onto static locations (e.g. frontiers into new regions).
    from .content import get_location_or_none

    loc = get_location_or_none(loc_id)
    if not loc:
        raise ValueError(f"Unknown location: {loc_id}")
    return loc

