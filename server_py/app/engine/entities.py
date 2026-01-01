from __future__ import annotations

from typing import List, Dict, Any

from ..types_entities import Entity
from ..world_entities import WORLD_ENTITIES
from ..world import get_location
from ..db import get_players_at_location
from ..db import get_player_by_name

def find_player_by_name_at(location_id: str, name: str):
    players = get_players_at_location(location_id)
    name = name.lower()

    for p in players:
        if p.name.lower() == name or p.player_id.lower() == name:
            return p

    return None


# -------------------------------------------------
# Player entities (players as world entities)
# -------------------------------------------------

def get_player_entities_at(location_id: str) -> List[Dict[str, Any]]:
    """
    Represent players as world entities so they can be
    seen, targeted, and interacted with.
    """
    players = get_players_at_location(location_id)

    return [
        {
            "type": "player",
            "id": p.player_id,
            "name": p.name,
            "hp": p.hp,
            "level": p.level,
        }
        for p in players
    ]


# -------------------------------------------------
# World entities (monsters, NPCs, etc.)
# -------------------------------------------------

def get_world_entities_at(location_id: str) -> List[Entity]:
    return WORLD_ENTITIES.get(location_id, [])


def get_entities_at(location_id: str) -> List[Dict[str, Any]]:
    """
    Unified entity view for a location:
    - monsters
    - NPCs
    - players
    """
    entities: List[Dict[str, Any]] = []

    # World entities (monsters, NPCs)
    for e in get_world_entities_at(location_id):
        entities.append(serialize_entity(e))

    # Player entities
    entities.extend(get_player_entities_at(location_id))

    return entities


# -------------------------------------------------
# Serialization
# -------------------------------------------------

def serialize_entity(e: Entity) -> Dict[str, Any]:
    """
    Serialize a world entity (monster or NPC) into a
    frontend-safe representation.
    """
    data: Dict[str, Any] = {
        "type": e.type,
        "id": e.entity_id,
        "name": e.name,
    }

    if e.type == "monster":
        data["hp"] = e.hp

    elif e.type == "npc":
        data["role"] = e.role
        if e.role == "shop":
            data["inventory"] = e.inventory
        if e.role == "quest_giver":
            data["quests"] = e.quests

    return data


# -------------------------------------------------
# Lookup helpers
# -------------------------------------------------

def find_entity(location_id: str, name: str) -> Dict[str, Any] | None:
    """
    Find an entity (monster, NPC, or player) by name or ID.
    """
    name = name.lower()

    for e in get_entities_at(location_id):
        if e["name"].lower() == name or e["id"].lower() == name:
            return e

    return None


def remove_entity(location_id: str, entity_id: str) -> None:
    """
    Remove a world entity (monsters/NPCs only).
    Players are not removed this way.
    """
    WORLD_ENTITIES[location_id] = [
        e for e in WORLD_ENTITIES.get(location_id, [])
        if e.entity_id != entity_id
    ]


# -------------------------------------------------
# Adjacent scenes (for image prefetching)
# -------------------------------------------------

def get_adjacent_scenes(location_id: str) -> List[Dict[str, Any]]:
    """
    Returns a list of adjacent scene descriptors suitable
    for scene image prefetching.
    """
    loc = get_location(location_id)
    scenes: List[Dict[str, Any]] = []

    for exit in loc.exits:
        next_loc = get_location(exit.to)

        scenes.append({
            "location": {
                "id": next_loc.id,
                "name": next_loc.name,
                "description": next_loc.description,
                "exits": [{"to": e.to, "label": e.label} for e in next_loc.exits],
            },
            "entities": get_entities_at(next_loc.id),
        })

    return scenes