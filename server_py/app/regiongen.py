"""
Region minting: the world grows at its frontiers.

Certain locations are frontiers — an unexplored passage leads somewhere no one
has charted. When a player explores one, a whole new themed region is minted:
a handful of connected locations, a monster roster with tier-budgeted stats, a
boss, a new crafting material and gear, and a quest chain from a local NPC.
The region is generated once, validated against stat budgets, persisted to the
gen_* tables, and shared by every player from then on — one universe, one
canon, growing without bound (each region's boss lair is the next frontier).

Generation is deterministic and offline-capable: a seeded procedural generator
builds the structure; Miriel, when configured, re-voices the prose (names and
descriptions only — never the numbers).
"""

from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List, Optional

from . import db
from . import single_flight
from .content import invalidate_cache
from .types import Player

# ---------------------------------------------------------------------------
# Frontiers: where the static world opens into generated space
# ---------------------------------------------------------------------------

# location_id -> (tier of the region behind it, flavor of the unexplored way)
STATIC_FRONTIERS: Dict[str, tuple[int, str]] = {
    "tavern": (1, "a draft rises from behind the ale casks — the cellar door was never locked"),
    "riverside": (1, "a half-sunken towpath winds downriver into mist"),
    "deep_forest": (2, "a game trail vanishes into untrodden dark"),
    "spider_hollow": (2, "a silk-shrouded cleft drops away beneath the webs"),
    "foothills": (3, "a goat track climbs toward an unnamed col"),
    "frozen_cave": (5, "a wind moans from a fissure deep in the glacier"),
    "magma_core": (6, "a crack splits the far wall, breathing strange air"),
}


def frontier_at(location_id: str) -> Optional[Dict[str, Any]]:
    """Frontier info if this location can open into a new region, else None."""
    if location_id in STATIC_FRONTIERS:
        tier, flavor = STATIC_FRONTIERS[location_id]
        return {"tier": tier, "flavor": flavor}
    # Every minted region's boss lair is itself a frontier into deeper space.
    row = db.get_gen_location(location_id)
    if row and row.get("region_id"):
        region = db.get_region(row["region_id"])
        if region and region["data"].get("lair") == location_id:
            return {"tier": region["tier"] + 1,
                    "flavor": "beyond the lair, the dark goes on"}
    return None


# ---------------------------------------------------------------------------
# Theme bank
# ---------------------------------------------------------------------------

THEMES: List[Dict[str, Any]] = [
    {
        "key": "drowned_catacombs",
        "name": "Drowned Catacombs",
        "outdoor": False,
        "loc_names": ["Flooded Vault", "Bone Cloister", "Sunken Chapel",
                      "Weeping Gallery", "Silt Crypt", "Black Reliquary",
                      "Tide-Worn Ossuary", "Pilgrims' Descent"],
        "scenery": ["Black water laps at carved stone.",
                    "Candle stubs float past half-drowned effigies.",
                    "Every breath tastes of silt and old incense.",
                    "Coffin niches gape empty in the walls."],
        "monsters": ["Drowned Acolyte", "Crypt Eel", "Pale Leech", "Rust Husk"],
        "boss": "The Drowned Abbot",
        "boss_inflicts": {"effect": "weaken", "magnitude": 3, "turns": 3},
        "material": ("relic_shard", "Relic Shard"),
        "weapon": ("abbots_crook", "Abbot's Crook"),
        "armor": ("tideplate", "Tideplate Vestment"),
        "npc": "Keeper of the Sunken Door",
        "entry_flavor": "Stairs descend into water the color of ink.",
    },
    {
        "key": "verdant_maze",
        "name": "Verdant Maze",
        "outdoor": True,
        "loc_names": ["Hedge of Knives", "Blossom Court", "Strangler Grove",
                      "Pollen Hollow", "Root-Choked Stair", "The Green Heart",
                      "Trellis Ruin", "Briar Gate"],
        "scenery": ["Vines knot overhead into a living ceiling.",
                    "Petals drift down though nothing blooms in sight.",
                    "The hedges creak and shift when unwatched.",
                    "Sweet rot and birdsong fill the air."],
        "monsters": ["Briar Stalker", "Sporeling", "Thorn Cat", "Vine Strangler"],
        "boss": "The Gardener",
        "boss_inflicts": {"effect": "poison", "magnitude": 3, "turns": 3},
        "material": ("heartwood_sap", "Heartwood Sap"),
        "weapon": ("thorn_scimitar", "Thorn Scimitar"),
        "armor": ("barkweave", "Barkweave Mail"),
        "npc": "The Lost Topiarist",
        "entry_flavor": "A wall of green parts just enough to admit one person.",
    },
    {
        "key": "howling_steppe",
        "name": "Howling Steppe",
        "outdoor": True,
        "loc_names": ["Windbreak Cairns", "Saltgrass Flats", "Skull Totem Rise",
                      "Thunder Wallow", "The Long Barrow", "Khan's Fall",
                      "Whistling Gulch", "Stone Horse Field"],
        "scenery": ["The wind never stops; it only changes its mind.",
                    "Grass runs to the horizon like a grey-green sea.",
                    "Old totems rattle with hung bones.",
                    "Hoofprints the size of cartwheels dent the sod."],
        "monsters": ["Steppe Howler", "Dust Raptor", "Horned Brute", "Carrion Kite"],
        "boss": "Matriarch of the Howl",
        "boss_inflicts": None,
        "material": ("howler_fang", "Howler Fang"),
        "weapon": ("khans_saber", "Khan's Saber"),
        "armor": ("raptorhide", "Raptorhide Coat"),
        "npc": "Outrider of the Lost Khanate",
        "entry_flavor": "The land opens wide and the sky leans close.",
    },
    {
        "key": "gloaming_mire",
        "name": "Gloaming Mire",
        "outdoor": True,
        "loc_names": ["Lantern Shallows", "Leech Pool", "Hanging Cypress Hall",
                      "Mudwitch Stilts", "Sunken Palisade", "The Breathing Fen",
                      "Foxfire Crossing", "Drowner's Rest"],
        "scenery": ["Foxfire winks between the cypress knees.",
                    "The mud sighs and settles as if something turned over.",
                    "Moths the size of hands bump against your light.",
                    "Water and sky share the same bruised color."],
        "monsters": ["Bog Lurker", "Marsh Wraith", "Snapjaw", "Will-o-Husk"],
        "boss": "The Mudwitch",
        "boss_inflicts": {"effect": "poison", "magnitude": 4, "turns": 3},
        "material": ("witchpeat", "Witchpeat"),
        "weapon": ("snagroot_flail", "Snagroot Flail"),
        "armor": ("wraithcloak", "Wraithcloak"),
        "npc": "Ferryman of the Mire",
        "entry_flavor": "Planks half-rotted into the water mark a forgotten way.",
    },
    {
        "key": "shattered_observatory",
        "name": "Shattered Observatory",
        "outdoor": False,
        "loc_names": ["Cracked Lens Hall", "Orrery Pit", "Star Chart Vault",
                      "The Tilted Dome", "Brass Stairwell", "Comet Scriptorium",
                      "Eclipse Gallery", "The Silent Array"],
        "scenery": ["Brass gears the size of millstones lie seized mid-turn.",
                    "Star charts peel from the walls like dead leaves.",
                    "Something hums in the walls at the edge of hearing.",
                    "Shattered lenses scatter the lamplight into ghosts."],
        "monsters": ["Clockwork Warden", "Glass Revenant", "Star-Touched Husk", "Gear Gremlin"],
        "boss": "The Last Astronomer",
        "boss_inflicts": {"effect": "burn", "magnitude": 3, "turns": 3},
        "material": ("star_glass", "Star Glass"),
        "weapon": ("meridian_blade", "Meridian Blade"),
        "armor": ("orrery_plate", "Orrery Plate"),
        "npc": "Apprentice of the Array",
        "entry_flavor": "A toppled brass door opens on rooms that smell of storms.",
    },
    {
        "key": "cinder_warrens",
        "name": "Cinder Warrens",
        "outdoor": False,
        "loc_names": ["Soot Run", "Ember Nursery", "Slag Heap Hall",
                      "The Bellows Throat", "Charred Chapel", "Ashfall Gallery",
                      "Coalheart Pit", "The Smoldering Seam"],
        "scenery": ["Heat shimmers over beds of dozing coals.",
                    "Soot falls in slow black snow.",
                    "The walls glow faintly, like banked hearths.",
                    "Somewhere below, bellows breathe without hands."],
        "monsters": ["Cinder Imp", "Slag Crawler", "Ash Ghoul", "Coal Hound"],
        "boss": "Mother of Embers",
        "boss_inflicts": {"effect": "burn", "magnitude": 5, "turns": 3},
        "material": ("living_cinder", "Living Cinder"),
        "weapon": ("emberfang", "Emberfang"),
        "armor": ("slagplate", "Slagplate"),
        "npc": "Smith Who Fled the Heat",
        "entry_flavor": "Warm air rises from a seam in the rock, smelling of forges.",
    },
    {
        "key": "pale_reach",
        "name": "Pale Reach",
        "outdoor": True,
        "loc_names": ["Frostbitten Quay", "The White Causeway", "Seal Bone Camp",
                      "Aurora Field", "The Cracking Shelf", "Whaleback Rise",
                      "Hoarfrost Maze", "The Still Lagoon"],
        "scenery": ["The ice groans underfoot like a living ship's hull.",
                    "An aurora wavers over everything, green and silent.",
                    "Frost flowers bloom across black, glassy ice.",
                    "Your breath falls as glittering dust."],
        "monsters": ["Pale Prowler", "Ice-Bound Shade", "Walrus Bull", "Frost Mite Swarm"],
        "boss": "The Shelf-Breaker",
        "boss_inflicts": {"effect": "weaken", "magnitude": 4, "turns": 3},
        "material": ("glacier_pearl", "Glacier Pearl"),
        "weapon": ("shardpick", "Shardpick"),
        "armor": ("sealskin_aegis", "Sealskin Aegis"),
        "npc": "Hunter of the White Road",
        "entry_flavor": "Cold light spills through a throat of blue ice.",
    },
    {
        "key": "umbral_archive",
        "name": "Umbral Archive",
        "outdoor": False,
        "loc_names": ["Ink-Dark Stacks", "The Misfiled Wing", "Whisper Carrels",
                      "Index of Lost Names", "The Bindery", "Margin Walk",
                      "Restricted Depths", "The Card Catalog Abyss"],
        "scenery": ["Shelves climb out of lantern reach and keep going.",
                    "Loose pages drift by on no wind at all.",
                    "Every whisper is answered, slightly wrong.",
                    "Ink pools in the aisles like shallow tidewater."],
        "monsters": ["Inkspill Shade", "Paper Golem", "Silverfish Tide", "Unbound Codex"],
        "boss": "The Head Librarian",
        "boss_inflicts": {"effect": "weaken", "magnitude": 3, "turns": 4},
        "material": ("bound_vellum", "Bound Vellum"),
        "weapon": ("letter_opener", "The Letter Opener"),
        "armor": ("lexicon_shell", "Lexicon Shell"),
        "npc": "The Overdue Borrower",
        "entry_flavor": "A reading lamp burns at the mouth of endless stacks.",
    },
]


# ---------------------------------------------------------------------------
# Stat budgets (the procedural generator must stay inside these; the validator
# enforces them on every minted region, AI-flavored or not)
# ---------------------------------------------------------------------------

def budget(tier: int) -> Dict[str, int]:
    t = max(1, tier)
    return {
        "monster_hp_max": 14 + 16 * t,
        "monster_attack_max": 4 + 3 * t,
        "monster_xp_max": 20 + 22 * t,
        "boss_hp_max": int((14 + 16 * t) * 2.6),
        "boss_attack_max": int((4 + 3 * t) * 1.7),
        "boss_xp_max": int((20 + 22 * t) * 3),
        "weapon_damage_max": 3 + 3 * t,
        "armor_defense_max": 2 + 2 * t,
        "coin_loot_max": 8 + 10 * t,
    }


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def generate_region_spec(*, index: int, tier: int, origin_location: str,
                         discovered_by: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a complete, self-consistent region spec. Deterministic for a given
    (index, tier, origin) so a re-mint after a crash lands identically.
    """
    rng = random.Random(f"{index}|{tier}|{origin_location}")
    theme = THEMES[index % len(THEMES)]
    region_id = f"region_{index}"
    b = budget(tier)

    suffix = f"_{region_id}"
    material_id = theme["material"][0] + suffix
    weapon_id = theme["weapon"][0] + suffix
    armor_id = theme["armor"][0] + suffix

    # ---- Locations: a spine of 4-6 rooms ending at the boss lair ----
    n_locs = rng.randint(4, 6)
    names = rng.sample(theme["loc_names"], n_locs)
    loc_ids = [f"{region_id}_{_slug(n)}" for n in names]
    entry_id, lair_id = loc_ids[0], loc_ids[-1]

    locations: List[Dict[str, Any]] = []
    for i, (lid, lname) in enumerate(zip(loc_ids, names)):
        exits = []
        if i == 0:
            exits.append({"to": origin_location, "label": "back"})
        else:
            exits.append({"to": loc_ids[i - 1], "label": "back"})
        if i < n_locs - 1:
            exits.append({"to": loc_ids[i + 1], "label": "onward"})
        scenery = rng.sample(theme["scenery"], 2)
        desc = f"{theme['entry_flavor']} {scenery[0]}" if i == 0 else f"{scenery[0]} {scenery[1]}"
        locations.append({
            "location_id": lid,
            "name": lname,
            "description": desc,
            "cleared_description": f"{scenery[0]} For now, it is quiet.",
            "exits": exits,
            "outdoor": theme["outdoor"],
            "resource": material_id if (0 < i < n_locs - 1 and rng.random() < 0.6) else None,
        })

    # ---- Monsters: 1-2 per interior room, boss in the lair ----
    entities: List[Dict[str, Any]] = []
    common = theme["monsters"]
    mono = 0
    for i, lid in enumerate(loc_ids):
        if i == 0:
            continue  # the entry room is the safe foothold
        if lid == lair_id:
            break
        for _ in range(rng.randint(1, 2)):
            mono += 1
            name = rng.choice(common)
            hp = rng.randint(int(b["monster_hp_max"] * 0.55), b["monster_hp_max"])
            attack = rng.randint(max(1, int(b["monster_attack_max"] * 0.6)), b["monster_attack_max"])
            xp = min(b["monster_xp_max"], int(hp * 0.7))
            loot = {"coin": rng.randint(2, max(3, b["coin_loot_max"] // 2)), material_id: 1}
            data: Dict[str, Any] = {
                "hp": hp, "attack": attack, "xp_reward": xp, "loot": loot,
                "aggressive": True,
            }
            if rng.random() < 0.25:
                data["inflicts"] = {"effect": rng.choice(["poison", "weaken"]),
                                    "magnitude": min(3, 1 + tier // 2), "turns": 3}
            entities.append({
                "entity_id": f"{region_id}_{_slug(name)}_{mono}",
                "location_id": lid,
                "name": name,
                "type": "monster",
                "data": data,
            })

    boss_name = theme["boss"]
    boss_hp = rng.randint(int(b["boss_hp_max"] * 0.8), b["boss_hp_max"])
    boss_attack = rng.randint(int(b["boss_attack_max"] * 0.8), b["boss_attack_max"])
    boss_data: Dict[str, Any] = {
        "hp": boss_hp, "attack": boss_attack,
        "xp_reward": min(b["boss_xp_max"], int(boss_hp * 1.2)),
        "loot": {"coin": b["coin_loot_max"] * 3, weapon_id: 1, material_id: 2},
        "aggressive": True,
    }
    if theme["boss_inflicts"]:
        boss_data["inflicts"] = theme["boss_inflicts"]
    entities.append({
        "entity_id": f"{region_id}_boss",
        "location_id": lair_id,
        "name": boss_name,
        "type": "monster",
        "data": boss_data,
    })

    # ---- The local NPC quest-giver waits at the entry ----
    quest_ids = [f"{region_id}_scout", f"{region_id}_cull", f"{region_id}_boss_hunt"]
    entities.append({
        "entity_id": f"{region_id}_guide",
        "location_id": entry_id,
        "name": theme["npc"],
        "type": "npc",
        "data": {"role": "quest_giver", "quests": quest_ids},
    })

    # ---- Items: a material plus craftable gear within budget ----
    items = [
        {
            "item_id": material_id,
            "data": {"item_id": material_id, "name": theme["material"][1],
                     "type": "material", "value": 3 + 4 * tier},
            "recipe": None,
        },
        {
            "item_id": weapon_id,
            "data": {"item_id": weapon_id, "name": theme["weapon"][1],
                     "type": "weapon", "slot": "weapon",
                     "damage": b["weapon_damage_max"], "value": 25 * tier},
            "recipe": {"inputs": {material_id: 4}, "qty": 1},
        },
        {
            "item_id": armor_id,
            "data": {"item_id": armor_id, "name": theme["armor"][1],
                     "type": "armor", "slot": "armor",
                     "defense": b["armor_defense_max"], "value": 25 * tier},
            "recipe": {"inputs": {material_id: 5}, "qty": 1},
        },
    ]

    # ---- Quest chain: scout it, thin it, end it ----
    common_target = entities[0]["name"] if entities[0]["type"] == "monster" else common[0]
    mid_loc = loc_ids[len(loc_ids) // 2]
    region_name = theme["name"]
    quests = [
        {
            "quest_id": quest_ids[0],
            "data": {
                "quest_id": quest_ids[0],
                "name": f"Into the {region_name}",
                "description": f"Scout deeper into the {region_name} and return alive.",
                "objectives": [{"type": "visit", "target": mid_loc, "required": 1}],
                "rewards": {"coin": 8 * tier, "healing_potion": 1},
                "repeatable": False,
            },
        },
        {
            "quest_id": quest_ids[1],
            "data": {
                "quest_id": quest_ids[1],
                "name": f"Thin the {region_name}",
                "description": f"The {common_target}s grow bold. Cull three of them.",
                "objectives": [{"type": "kill", "target": common_target, "required": 3}],
                "rewards": {"coin": 12 * tier, material_id: 2},
                "repeatable": True,
            },
        },
        {
            "quest_id": quest_ids[2],
            "data": {
                "quest_id": quest_ids[2],
                "name": f"The Fall of {boss_name}",
                "description": f"{boss_name} rules the {region_name}. See it ended.",
                "stages": [
                    {"description": f"Find the heart of the {region_name}.",
                     "objectives": [{"type": "visit", "target": lair_id, "required": 1}]},
                    {"description": f"Gather 3 {theme['material'][1]}.",
                     "objectives": [{"type": "collect", "target": material_id, "required": 3}]},
                    {"description": f"Slay {boss_name}.",
                     "objectives": [{"type": "kill", "target": boss_name, "required": 1}]},
                ],
                "rewards": {"coin": 30 * tier, armor_id: 1},
                "repeatable": False,
            },
        },
    ]

    return {
        "region_id": region_id,
        "name": region_name,
        "theme": theme["key"],
        "tier": tier,
        "origin_location": origin_location,
        "entry_location": entry_id,
        "lair": lair_id,
        "discovered_by": discovered_by,
        "locations": locations,
        "entities": entities,
        "items": items,
        "quests": quests,
    }


# ---------------------------------------------------------------------------
# Validation: no region reaches the world unless it is sound
# ---------------------------------------------------------------------------

class RegionValidationError(ValueError):
    pass


def validate_region(spec: Dict[str, Any]) -> None:
    b = budget(spec["tier"])
    loc_ids = {l["location_id"] for l in spec["locations"]}
    if spec["entry_location"] not in loc_ids or spec["lair"] not in loc_ids:
        raise RegionValidationError("entry/lair must be region locations")

    # Exits stay inside the region (plus the way back to the origin) and the
    # whole region is reachable from the entry.
    adjacency: Dict[str, List[str]] = {}
    for loc in spec["locations"]:
        for e in loc["exits"]:
            if e["to"] not in loc_ids and e["to"] != spec["origin_location"]:
                raise RegionValidationError(f"exit to unknown location {e['to']}")
            adjacency.setdefault(loc["location_id"], []).append(e["to"])
    seen, stack = set(), [spec["entry_location"]]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in loc_ids:
            continue
        seen.add(cur)
        stack.extend(adjacency.get(cur, []))
    if seen != loc_ids:
        raise RegionValidationError("region graph is not connected from the entry")

    item_ids = {i["item_id"] for i in spec["items"]}
    monster_names = set()
    for ent in spec["entities"]:
        if ent["location_id"] not in loc_ids:
            raise RegionValidationError("entity placed outside the region")
        data = ent["data"]
        if ent["type"] == "monster":
            monster_names.add(ent["name"])
            is_boss = ent["entity_id"].endswith("_boss")
            hp_cap = b["boss_hp_max"] if is_boss else b["monster_hp_max"]
            atk_cap = b["boss_attack_max"] if is_boss else b["monster_attack_max"]
            xp_cap = b["boss_xp_max"] if is_boss else b["monster_xp_max"]
            if not (1 <= data["hp"] <= hp_cap):
                raise RegionValidationError(f"{ent['name']} HP {data['hp']} out of budget")
            if not (1 <= data["attack"] <= atk_cap):
                raise RegionValidationError(f"{ent['name']} attack out of budget")
            if not (0 <= data["xp_reward"] <= xp_cap):
                raise RegionValidationError(f"{ent['name']} XP out of budget")
            for item in (data.get("loot") or {}):
                if item != "coin" and item not in item_ids:
                    from .items import ITEMS
                    if item not in ITEMS:
                        raise RegionValidationError(f"loot references unknown item {item}")

    for item in spec["items"]:
        d = item["data"]
        if d.get("damage") and d["damage"] > b["weapon_damage_max"]:
            raise RegionValidationError(f"{item['item_id']} damage over budget")
        if d.get("defense") and d["defense"] > b["armor_defense_max"]:
            raise RegionValidationError(f"{item['item_id']} defense over budget")

    # Quests must be completable with what the region (or the core game) has.
    for quest in spec["quests"]:
        data = quest["data"]
        objectives = list(data.get("objectives") or [])
        for stage in data.get("stages") or []:
            objectives.extend(stage["objectives"])
        for obj in objectives:
            if obj["type"] == "kill" and obj["target"] not in monster_names:
                raise RegionValidationError(f"quest kills unknown monster {obj['target']}")
            if obj["type"] == "visit" and obj["target"] not in loc_ids:
                raise RegionValidationError(f"quest visits unknown location {obj['target']}")
            if obj["type"] == "collect" and obj["target"] not in item_ids:
                from .items import ITEMS
                if obj["target"] not in ITEMS:
                    raise RegionValidationError(f"quest collects unknown item {obj['target']}")


# ---------------------------------------------------------------------------
# Optional Miriel enrichment (prose only, never numbers)
# ---------------------------------------------------------------------------

def _enrich_with_miriel(spec: Dict[str, Any]) -> Dict[str, Any]:
    from .services.miriel_client import is_miriel_enabled, get_miriel_client

    if not is_miriel_enabled():
        return spec
    try:
        names = [l["name"] for l in spec["locations"]]
        query = (
            "You are the loremaster of a fantasy MMO. A new region named "
            f"'{spec['name']}' (theme: {spec['theme']}) was just discovered. "
            "Write a JSON object mapping each location name to one vivid, "
            "atmospheric sentence describing it. Locations: "
            + json.dumps(names)
            + ". Reply with ONLY the JSON object."
        )
        resp = get_miriel_client().query(query=query, project="questai")
        answer = (((resp or {}).get("results", {}) or {}).get("answer", "") or "").strip()
        match = re.search(r"\{.*\}", answer, re.DOTALL)
        if not match:
            return spec
        prose = json.loads(match.group(0))
        for loc in spec["locations"]:
            text = prose.get(loc["name"])
            if isinstance(text, str) and 20 < len(text) < 400:
                loc["description"] = text.strip()
    except Exception as e:
        print(f"[REGIONGEN] Miriel enrichment skipped: {e}")
    return spec


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------

def _persist_region(spec: Dict[str, Any]) -> None:
    for item in spec["items"]:
        db.upsert_gen_item(item_id=item["item_id"], data=item["data"], recipe=item["recipe"])
    for loc in spec["locations"]:
        db.upsert_gen_location(
            location_id=loc["location_id"],
            region_id=spec["region_id"],
            name=loc["name"],
            description=loc["description"],
            cleared_description=loc.get("cleared_description"),
            exits=loc["exits"],
            outdoor=loc["outdoor"],
            resource=loc.get("resource"),
        )
    for ent in spec["entities"]:
        db.upsert_gen_entity(
            entity_id=ent["entity_id"],
            location_id=ent["location_id"],
            name=ent["name"],
            type=ent["type"],
            data=ent["data"],
        )
    for quest in spec["quests"]:
        db.upsert_gen_quest(quest_id=quest["quest_id"], region_id=spec["region_id"],
                            data=quest["data"])
    db.create_region(
        region_id=spec["region_id"],
        name=spec["name"],
        theme=spec["theme"],
        tier=spec["tier"],
        entry_location=spec["entry_location"],
        origin_location=spec["origin_location"],
        discovered_by=spec.get("discovered_by"),
        data={"lair": spec["lair"]},
    )
    # Open the way: graft the frontier exit onto the origin location.
    db.add_gen_exit(spec["origin_location"], spec["entry_location"], "unexplored path")


def _install_region_rules(spec: Dict[str, Any]) -> None:
    """
    Give the region its own world-evolution behavior via data-driven rules
    (see world_rules.py): clearing every room is a recorded world event, and
    a region left quiet too long stirs back to life on its own.
    """
    from .db import upsert_world_rule

    rid, name = spec["region_id"], spec["name"]
    interior = [l["location_id"] for l in spec["locations"][1:]]
    cleared_key = f"{rid}_cleared"

    upsert_world_rule(
        rule_id=f"{rid}_cleared",
        name=f"{name} Falls Quiet",
        description=f"Fires once when every room of the {name} stands empty.",
        conditions=(
            [{"monster_count": {"location": lid, "op": "eq", "value": 0}} for lid in interior]
            + [{"world_state_ne": {"key": cleared_key, "value": "true"}}]
        ),
        effects=[
            {"set_state": {"key": cleared_key, "value": "true"}},
            {"set_state_turn": {"key": f"{rid}_cleared_turn"}},
            {"log_event": {
                "type": "world_evolution",
                "location": spec["entry_location"],
                "description": f"The {name} falls quiet — every den and hall stands empty.",
            }},
        ],
        cooldown_turns=0,
    )

    # The resurgent beast reuses a budget-validated monster from the region.
    template = next(e for e in spec["entities"] if e["type"] == "monster")
    mid_loc = spec["locations"][len(spec["locations"]) // 2]["location_id"]
    upsert_world_rule(
        rule_id=f"{rid}_resurgence",
        name=f"The {name} Stirs",
        description=f"A cleared {name} does not stay quiet forever.",
        conditions=[
            {"world_state_eq": {"key": cleared_key, "value": "true"}},
            {"turns_since_state": {"key": f"{rid}_cleared_turn", "gte": 10}},
        ],
        effects=[
            {"spawn_monster": {
                "instance_id": f"{rid}_resurgent",
                "location": mid_loc,
                "name": template["name"],
                "hp": template["data"]["hp"],
                "attack": template["data"]["attack"],
                "xp_reward": template["data"]["xp_reward"],
                "loot": template["data"].get("loot") or {},
            }},
            {"set_state": {"key": cleared_key, "value": "false"}},
            {"log_event": {
                "type": "world_evolution",
                "location": mid_loc,
                "description": f"The {name} stirs again — something prowls its depths.",
            }},
        ],
        cooldown_turns=10,
    )


def mint_region_from(origin_location: str, player: Optional[Player]) -> Optional[Dict[str, Any]]:
    """
    Mint (or return the already-minted) region behind a frontier. Single-
    flighted and idempotent: concurrent explorers get one region, and the
    discoverer's name is canonized exactly once. With `player=None` this is a
    system mint (e.g. startup pre-minting): no discoverer is recorded.
    """
    frontier = frontier_at(origin_location)
    if not frontier:
        return None

    def _mint() -> Dict[str, Any]:
        existing = db.get_region_by_origin(origin_location)
        if existing:
            return existing

        index = db.count_regions() + 1
        spec = generate_region_spec(
            index=index,
            tier=frontier["tier"],
            origin_location=origin_location,
            discovered_by=player.name if player else None,
        )
        spec = _enrich_with_miriel(spec)
        validate_region(spec)

        # The discoverer enters the canon: their name lives in the entry text.
        if player:
            spec["locations"][0]["description"] += f" First charted by {player.name}."
        _persist_region(spec)
        invalidate_cache()

        # New catalog monsters take the field immediately.
        from .engine.entities import seed_world_monsters
        seed_world_monsters()

        # The region runs itself from here: its own evolution rules, and its
        # AI assets (prose + scene art) warmed in the background so the first
        # visitor walks into a finished place.
        _install_region_rules(spec)
        from .pregen import pregenerate_region_assets
        pregenerate_region_assets(spec)

        db.log_world_event(
            event_type="region_discovered",
            location_id=origin_location,
            data={
                "region_id": spec["region_id"],
                "player_id": player.player_id if player else None,
                "player_name": player.name if player else None,
                "description": (
                    f"{player.name} discovered the {spec['name']}!"
                    if player else f"The way to the {spec['name']} stands open."
                ),
            },
        )
        if player:
            from .echoes import record_deed
            record_deed(player, origin_location,
                        f"{player.name} opened the way to the {spec['name']}",
                        kind="discovery")
        return db.get_region(spec["region_id"]) or spec

    return single_flight.run(f"mint_{origin_location}", _mint)


# Frontiers opened by the world itself at first boot, so a brand-new universe
# already reaches beyond the hand-authored core. The rest stay sealed for
# players to discover (and be canonized for). Override with QUESTAI_PREMINT
# (comma-separated frontier location ids; empty string disables).
DEFAULT_PREMINT = "tavern,riverside"


def pre_mint_regions() -> int:
    """Mint the configured starter regions (idempotent). Returns count minted."""
    import os

    raw = os.getenv("QUESTAI_PREMINT", DEFAULT_PREMINT)
    minted = 0
    for origin in [o.strip() for o in raw.split(",") if o.strip()]:
        if origin not in STATIC_FRONTIERS:
            print(f"[REGIONGEN] premint: {origin} is not a frontier, skipping")
            continue
        if db.get_region_by_origin(origin):
            continue
        try:
            if mint_region_from(origin, None):
                minted += 1
        except Exception as e:  # a failed premint must never block startup
            print(f"[REGIONGEN] premint from {origin} failed: {e}")
    return minted
