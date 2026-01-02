from __future__ import annotations

import time
from ...types import Player, ActionResponse
from ...db import upsert_player
from ..entities import get_entities_at, get_adjacent_scenes
from ...world import get_location


def turn_in_quest(player: Player, quest_id: str) -> ActionResponse:
    """
    Turn in a completed quest to receive rewards.
    """
    # Check if quest is in completed_quests
    if quest_id not in player.completed_quests:
        if quest_id in player.active_quests:
            return ActionResponse(ok=False, error="That quest is not yet completed.")
        if quest_id in player.archived_quests:
            return ActionResponse(ok=False, error="That quest is already turned in.")
        return ActionResponse(ok=False, error="You don't have that quest.")

    quest = player.completed_quests[quest_id]
    
    # Verify quest is completed
    if quest.status != "completed":
        return ActionResponse(ok=False, error="That quest is not yet completed.")

    # Award rewards
    messages = [f"Quest turned in: {quest.name}"]
    
    for item, quantity in quest.rewards.items():
        if item in player.inventory:
            player.inventory[item] += quantity
        else:
            player.inventory[item] = quantity
        messages.append(f"Received: {quantity}x {item}")

    # Update quest status
    quest.status = "turned_in"
    quest.turned_in_at = int(time.time() * 1000)
    
    # Move to archived quests
    player.archived_quests[quest_id] = quest
    del player.completed_quests[quest_id]

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
