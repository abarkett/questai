from __future__ import annotations

import json
from typing import List, Dict, Any

from ..types_entities import Entity
from ..world_entities import WORLD_ENTITIES
import time

from ..db import (
    get_players_at_location,
    get_monsters_at,
    spawn_monster,
    remove_monster,
    monster_exists,
    get_world_state,
    set_world_state,
)
from ..world import get_location


# How long after death a (non-rat) monster comes back. Rats use the separate
# forest-infestation rules.
MONSTER_RESPAWN_MS = 5 * 60 * 1000


def _death_key(instance_id: str) -> str:
    return f"died_{instance_id}"


def record_monster_death(instance_id: str) -> None:
    """Stamp when a catalog monster died so it can respawn later."""
    set_world_state(_death_key(instance_id), str(int(time.time() * 1000)))


def respawn_due_monsters() -> int:
    """
    Respawn catalog monsters whose death was long enough ago. Returns the count
    respawned. Cheap to call each action: only dead, timer-stamped monsters do
    any work.
    """
    now = int(time.time() * 1000)
    respawned = 0
    for location_id, entity_list in WORLD_ENTITIES.items():
        for e in entity_list:
            if e.type != "monster" or e.entity_id.startswith("rat"):
                continue
            if monster_exists(e.entity_id):
                continue
            died_raw = get_world_state(_death_key(e.entity_id))
            if died_raw:
                # Tracked death: respawn once the timer elapses.
                try:
                    died = int(died_raw)
                except ValueError:
                    died = 0
                if died and now - died < MONSTER_RESPAWN_MS:
                    continue
            # No death stamp (killed before respawn tracking, or otherwise
            # untracked): it's been gone a while, so bring it back now.
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
            set_world_state(_death_key(e.entity_id), "")
            respawned += 1
    return respawned


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


# Monsters that existed before instance-tracked seeding. Used only to migrate
# older saves so their (possibly slain) rats are never resurrected.
_LEGACY_SEEDED_IDS = {"rat_1", "rat_2"}


def seed_world_monsters() -> None:
    """
    Spawn any catalog monster instance that has never been seeded before.

    Tracking *which instances* have been seeded (rather than a single boolean)
    lets new content land in existing worlds while guaranteeing a slain monster
    is never resurrected: a killed instance stays in the seeded set, so it is
    only ever brought back by the respawn rules.
    """
    seeded_raw = get_world_state("seeded_monster_instances")
    if seeded_raw:
        try:
            seeded = set(json.loads(seeded_raw))
        except Exception:
            seeded = set()
    elif get_world_state("monsters_seeded") == "true":
        # Migrate older saves: original rats are already accounted for.
        seeded = set(_LEGACY_SEEDED_IDS)
    else:
        seeded = set()

    changed = False
    for location_id, entity_list in WORLD_ENTITIES.items():
        for e in entity_list:
            if e.type == "monster" and e.entity_id not in seeded:
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
                seeded.add(e.entity_id)
                changed = True

    if changed or seeded_raw is None:
        set_world_state("seeded_monster_instances", json.dumps(sorted(seeded)))


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