"""
Content registry: one lookup layer over hand-authored and generated content.

The static Python catalogs (world.py, world_entities.py, items.py,
world_quests.py) are the hand-authored seed of the universe. Regions minted at
runtime (procedurally generated, optionally AI-flavored) are persisted in the
gen_* tables. This module merges the two so the rest of the engine never needs
to care where a location, item, monster, or quest came from.

Single shared world, single server process: lookups that would be hot in a
request (monster trait maps, generated item/location maps) are cached in
memory and invalidated explicitly by the code that writes generated content
(see invalidate_cache()).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import db
from .types_entities import Entity
from .types_quests import Quest


# ---------------------------------------------------------------------------
# Cache (invalidated whenever generated content is written)
# ---------------------------------------------------------------------------

_cache: Dict[str, Any] = {}


def invalidate_cache() -> None:
    """Call after writing any gen_* content so lookups see it immediately."""
    _cache.clear()


def _gen_locations_by_id() -> Dict[str, Dict[str, Any]]:
    if "gen_locations" not in _cache:
        _cache["gen_locations"] = {l["location_id"]: l for l in db.get_all_gen_locations()}
    return _cache["gen_locations"]


def _gen_items_by_id() -> Dict[str, Dict[str, Any]]:
    if "gen_items" not in _cache:
        _cache["gen_items"] = {i["item_id"]: i for i in db.get_all_gen_items()}
    return _cache["gen_items"]


def _gen_entities() -> List[Dict[str, Any]]:
    if "gen_entities" not in _cache:
        _cache["gen_entities"] = db.get_all_gen_entities()
    return _cache["gen_entities"]


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

def _gen_row_to_location(row: Dict[str, Any]):
    from .world import Location, Exit

    exits = [Exit(to=e["to"], label=e["label"]) for e in row["exits"]]
    exits += [
        Exit(to=e["to"], label=e["label"])
        for e in db.get_gen_exits(row["location_id"])
        if e["to"] not in {x.to for x in exits}
    ]
    return Location(
        id=row["location_id"],
        name=row["name"],
        description=row["description"],
        cleared_description=row.get("cleared_description"),
        exits=exits,
    )


def get_location_or_none(loc_id: str):
    """Static location (with any grafted exits) or a generated one, else None."""
    from .world import WORLD, Location, Exit

    static = WORLD.get(loc_id)
    if static:
        grafted = db.get_gen_exits(loc_id)
        if not grafted:
            return static
        merged = list(static.exits)
        have = {e.to for e in merged}
        merged += [Exit(to=e["to"], label=e["label"]) for e in grafted if e["to"] not in have]
        return Location(
            id=static.id,
            name=static.name,
            description=static.description,
            cleared_description=static.cleared_description,
            exits=merged,
        )

    row = _gen_locations_by_id().get(loc_id)
    return _gen_row_to_location(row) if row else None


def all_location_ids() -> List[str]:
    from .world import WORLD

    return list(WORLD.keys()) + [lid for lid in _gen_locations_by_id() if lid not in WORLD]


def is_outdoor(loc_id: str) -> bool:
    row = _gen_locations_by_id().get(loc_id)
    return bool(row and row.get("outdoor"))


def resource_at(loc_id: str) -> Optional[str]:
    """What gathering yields here (static table first, then generated)."""
    from .items import LOCATION_RESOURCES

    static = LOCATION_RESOURCES.get(loc_id)
    if static:
        return static
    row = _gen_locations_by_id().get(loc_id)
    return row.get("resource") if row else None


# ---------------------------------------------------------------------------
# Entities (monster catalog + NPCs)
# ---------------------------------------------------------------------------

def _gen_entity_to_entity(row: Dict[str, Any]) -> Entity:
    data = dict(row.get("data") or {})
    data.update(
        entity_id=row["entity_id"],
        name=row["name"],
        type=row["type"],
    )
    return Entity(**data)


def generated_npcs_at(loc_id: str) -> List[Entity]:
    return [
        _gen_entity_to_entity(r)
        for r in _gen_entities()
        if r["location_id"] == loc_id and r["type"] == "npc"
    ]


def monster_catalog() -> List[tuple[str, Entity]]:
    """
    Every catalog monster (static + generated) as (location_id, Entity).
    This is the source of truth for seeding and respawning.
    """
    from .world_entities import WORLD_ENTITIES

    out: List[tuple[str, Entity]] = []
    for location_id, entity_list in WORLD_ENTITIES.items():
        for e in entity_list:
            if e.type == "monster":
                out.append((location_id, e))
    for r in _gen_entities():
        if r["type"] == "monster":
            out.append((r["location_id"], _gen_entity_to_entity(r)))
    return out


def monster_inflicts(name: str) -> Optional[dict]:
    """Status effect a monster applies when it lands a blow, if any."""
    from .world_entities import MONSTER_INFLICTS

    static = MONSTER_INFLICTS.get(name)
    if static:
        return static
    if "monster_inflicts" not in _cache:
        _cache["monster_inflicts"] = {
            r["name"]: (r.get("data") or {}).get("inflicts")
            for r in _gen_entities()
            if r["type"] == "monster" and (r.get("data") or {}).get("inflicts")
        }
    return _cache["monster_inflicts"].get(name)


def monster_aggro(name: str) -> bool:
    """Whether a monster is hostile enough to ambush careless players."""
    from .world_entities import MONSTER_AGGRO

    if name in MONSTER_AGGRO:
        return MONSTER_AGGRO[name]
    if "monster_aggro" not in _cache:
        _cache["monster_aggro"] = {
            r["name"]: bool((r.get("data") or {}).get("aggressive", True))
            for r in _gen_entities()
            if r["type"] == "monster"
        }
    return _cache["monster_aggro"].get(name, False)


# ---------------------------------------------------------------------------
# Items & recipes
# ---------------------------------------------------------------------------

def get_generated_item(item_id: str):
    from .items import Item

    row = _gen_items_by_id().get(item_id)
    if not row:
        return None
    data = dict(row["data"])
    data.setdefault("item_id", item_id)
    return Item(**data)


def get_generated_recipe(item_id: str) -> Optional[Dict[str, Any]]:
    row = _gen_items_by_id().get(item_id)
    return row.get("recipe") if row else None


# ---------------------------------------------------------------------------
# Quests
# ---------------------------------------------------------------------------

def get_quest_template(quest_id: str) -> Optional[Quest]:
    """Hand-authored template first, then a minted (generated) quest."""
    from .world_quests import QUEST_TEMPLATES

    template = QUEST_TEMPLATES.get(quest_id)
    if template:
        return template
    row = db.get_gen_quest(quest_id)
    if not row:
        return None
    data = dict(row["data"])
    data.setdefault("quest_id", quest_id)
    return Quest(**data)
