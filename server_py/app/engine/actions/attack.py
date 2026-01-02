from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import upsert_player
from ...world import get_location
from ..entities import (
    find_entity,
    find_player_by_name_at,
    get_entities_at,
    serialize_entity,
    remove_entity,
    get_adjacent_scenes,
    get_world_entities_at,
)


# Simple shared combat constants
PLAYER_DAMAGE = 3
RESPAWN_LOCATION = "town_square"


def attack(player: Player, target_name: str) -> ActionResponse:
    messages: list[str] = []

    # -------------------------------------------------
    # Try PvE first (monsters)
    # -------------------------------------------------
    entity = find_entity(player.location, target_name)
    if entity and entity["type"] == "monster":
        # Monster combat (unchanged)
        monster_hp = entity["hp"] - PLAYER_DAMAGE
        messages.append(f"You attack the {entity['name']} for {PLAYER_DAMAGE} damage.")

        if monster_hp <= 0:
            remove_entity(player.location, entity["id"])
            messages.append(f"The {entity['name']} is defeated.")
        else:
            # Update monster HP in world state
            for e in get_world_entities_at(player.location):
                if e.entity_id == entity["id"]:
                    e.hp = monster_hp
                    break

            retaliation = 2
            player.hp -= retaliation
            messages.append(f"The {entity['name']} hits you for {retaliation} damage.")

        upsert_player(player)

        loc = get_location(player.location)
        entities = get_entities_at(player.location)

        return ActionResponse(
            ok=True,
            messages=messages,
            state={
                "player": player.model_dump(),
                "location": {
                    "id": loc.id,
                    "name": loc.name,
                    "description": loc.description,
                    "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
                },
                "entities": entities,
                "adjacent_scenes": get_adjacent_scenes(loc.id),
            },
        )

    # -------------------------------------------------
    # PvP combat
    # -------------------------------------------------
    target_player = find_player_by_name_at(player.location, target_name)

    if not target_player:
        return ActionResponse(ok=False, error="There is no one here by that name.")

    if target_player.player_id == player.player_id:
        return ActionResponse(ok=False, error="You can't attack yourself.")

    messages.append(f"You attack {target_player.name} for {PLAYER_DAMAGE} damage.")

    target_player.hp -= PLAYER_DAMAGE

    if target_player.hp <= 0:
        messages.append(f"{target_player.name} is defeated!")
        target_player.hp = target_player.max_hp
        target_player.location = RESPAWN_LOCATION
        messages.append(f"{target_player.name} is sent back to the Town Square.")

    upsert_player(target_player)
    upsert_player(player)

    loc = get_location(player.location)
    entities = get_entities_at(player.location)

    return ActionResponse(
        ok=True,
        messages=messages,
        state={
            "player": player.model_dump(),
            "location": {
                "id": loc.id,
                "name": loc.name,
                "description": loc.description,
                "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
            },
            "entities": entities,
            "adjacent_scenes": get_adjacent_scenes(loc.id),
        },
    )