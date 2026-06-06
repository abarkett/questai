from __future__ import annotations

from typing import List, Dict, Any

from ..types_entities import Entity
from ..world_entities import WORLD_ENTITIES
from ..db import (
    get_players_at_location,
    get_monsters_at,
    spawn_monster,
    remove_monster,
    get_world_state,
    set_world_state,
)
from ..world import get_location


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

def _static_npcs_at(location_id: str) -> List[Entity]:
    """NPCs are static definitions kept in code (they don't change at runtime)."""
    return [e for e in WORLD_ENTITIES.get(location_id, []) if e.type == "npc"]


def _monster_row_to_entity(row: Dict[str, Any]) -> Entity:
    return Entity(
        entity_id=row["instance_id"],
        name=row["name"],
        type="monster",
        hp=row["hp"],
        attack=row.get("attack"),
        xp_reward=row.get("xp_reward"),
        loot=row.get("loot") or {},
    )


def get_world_entities_at(location_id: str) -> List[Entity]:
    """Static NPCs (from code) + live monster instances (from the DB)."""
    entities: List[Entity] = list(_static_npcs_at(location_id))
    for row in get_monsters_at(location_id):
        entities.append(_monster_row_to_entity(row))
    return entities


def seed_world_monsters() -> None:
    """
    Populate the persistent monster table from the static catalog, once.

    Guarded by a world_state flag so monsters persist across restarts (a slain
    monster stays slain until the respawn rules bring it back).
    """
    if get_world_state("monsters_seeded") == "true":
        return
    for location_id, entity_list in WORLD_ENTITIES.items():
        for e in entity_list:
            if e.type == "monster":
                spawn_monster(
                    instance_id=e.entity_id,
                    location_id=location_id,
                    name=e.name,
                    hp=e.hp or 1,
                    max_hp=e.hp or 1,
                    attack=e.attack or 1,
                    xp_reward=e.xp_reward or 0,
                    loot=e.loot or {},
                )
    set_world_state("monsters_seeded", "true")


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


def filter_current_player(entities: List[Dict[str, Any]], player_id: str) -> List[Dict[str, Any]]:
    """
    Filter out the current player from the entity list.
    
    Args:
        entities: List of entity dictionaries
        player_id: ID of the player to filter out
        
    Returns:
        List of entities excluding the current player
    """
    return [e for e in entities if not (e.get("type") == "player" and e.get("id") == player_id)]


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
    Remove a monster instance from the world (NPCs are static and never removed,
    players are not removed this way).
    """
    remove_monster(entity_id)


def get_adjacent_scenes(location_id: str) -> List[Dict[str, Any]]:
    """
    Get adjacent scenes for image prefetch.
    Returns a list of location+entity snapshots for each connected exit.
    """
    loc = get_location(location_id)
    scenes: List[Dict[str, Any]] = []

    for ex in loc.exits:
        next_loc = get_location(ex.to)
        scenes.append(
            {
                "location": {
                    "id": next_loc.id,
                    "name": next_loc.name,
                    "description": next_loc.description,
                    "exits": [{"to": e.to, "label": e.label} for e in next_loc.exits],
                },
                "entities": get_entities_at(next_loc.id),
            }
        )

    return scenes