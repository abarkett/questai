from __future__ import annotations

import time
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

# Protection and cooldown constants (in seconds)
RESPAWN_PROTECTION_SECONDS = 300  # 5 minutes protection after defeat
ATTACK_COOLDOWN_SECONDS = 30  # 30 seconds before attacking same target again


def update_quest_progress(player: Player, target_name: str) -> list[str]:
    """
    Update quest progress for kill objectives.
    Returns list of quest completion messages.
    """
    messages = []
    completed_quest_ids = []
    
    for quest_id, quest in player.active_quests.items():
        if quest.status != "accepted":
            continue
            
        for objective in quest.objectives:
            if objective.type == "kill" and objective.target.lower() == target_name.lower():
                if objective.progress < objective.required:
                    objective.progress += 1
                    messages.append(f"Quest progress: {quest.name} ({objective.progress}/{objective.required})")
                    
                    # Check if all objectives are complete
                    if all(obj.progress >= obj.required for obj in quest.objectives):
                        quest.status = "completed"
                        quest.completed_at = int(time.time() * 1000)
                        completed_quest_ids.append(quest_id)
                        messages.append(f"Quest completed: {quest.name}! Return to the quest giver to turn it in.")
                    break
    
    # Move completed quests after iteration
    for quest_id in completed_quest_ids:
        player.completed_quests[quest_id] = player.active_quests[quest_id]
        del player.active_quests[quest_id]
    
    return messages


def is_player_attackable(target: Player, attacker: Player, current_time_ms: int) -> tuple[bool, str | None]:
    """
    Check if a player can be attacked.
    Returns (is_attackable, error_message)
    """
    # Check if target just respawned (defeated recently)
    if target.last_defeated_at:
        time_since_defeat = (current_time_ms - target.last_defeated_at) / 1000
        if time_since_defeat < RESPAWN_PROTECTION_SECONDS:
            remaining = int(RESPAWN_PROTECTION_SECONDS - time_since_defeat)
            return False, f"That player has just respawned. Protected for {remaining} more seconds."
    
    # Check if attacker is on cooldown for attacking this specific target
    if (attacker.last_attacked_target == target.name and 
        attacker.last_attacked_at):
        time_since_attack = (current_time_ms - attacker.last_attacked_at) / 1000
        if time_since_attack < ATTACK_COOLDOWN_SECONDS:
            remaining = int(ATTACK_COOLDOWN_SECONDS - time_since_attack)
            return False, f"You must wait {remaining} more seconds before attacking {target.name} again."
    
    return True, None


def attack(player: Player, target_name: str) -> ActionResponse:
    messages: list[str] = []
    current_time_ms = int(time.time() * 1000)

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
            
            # Update quest progress
            quest_messages = update_quest_progress(player, entity["name"])
            messages.extend(quest_messages)
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

    # Check if target is attackable
    attackable, error_msg = is_player_attackable(target_player, player, current_time_ms)
    if not attackable:
        return ActionResponse(ok=False, error=error_msg)

    messages.append(f"You attack {target_player.name} for {PLAYER_DAMAGE} damage.")

    target_player.hp -= PLAYER_DAMAGE

    if target_player.hp <= 0:
        messages.append(f"{target_player.name} is defeated!")
        target_player.hp = target_player.max_hp
        target_player.location = RESPAWN_LOCATION
        target_player.last_defeated_at = current_time_ms
        messages.append(f"{target_player.name} is sent back to the Town Square.")

    # Update attacker's last attack info
    player.last_attacked_target = target_player.name
    player.last_attacked_at = current_time_ms

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