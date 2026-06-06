from __future__ import annotations

import time

from ..types import Player


def consume_quest_items(player: Player, quest) -> list[str]:
    """
    Remove the items a quest's collect objectives required, on turn-in.
    Returns messages naming what was handed over.
    """
    messages: list[str] = []
    for o in quest.objectives:
        if o.type == "collect":
            have = player.inventory.get(o.target, 0)
            remaining = have - o.required
            if remaining > 0:
                player.inventory[o.target] = remaining
            else:
                player.inventory.pop(o.target, None)
            messages.append(f"Handed over: {o.required}x {o.target}")
    return messages


def refresh_quests(player: Player) -> list[str]:
    """
    Recompute progress for collect/visit objectives from the player's current
    state and complete any quest whose objectives are all met. Kill objectives
    are handled at the moment of the kill (in attack), so they're left as-is.

    Returns player-facing messages for newly completed quests.
    """
    messages: list[str] = []
    newly_completed: list[str] = []
    visited = set(player.visited_locations) | {player.location}

    for quest_id, quest in player.active_quests.items():
        if quest.status != "accepted":
            continue

        for obj in quest.objectives:
            if obj.type == "collect":
                obj.progress = min(obj.required, player.inventory.get(obj.target, 0))
            elif obj.type == "visit":
                if obj.target in visited:
                    obj.progress = obj.required

        if all(o.progress >= o.required for o in quest.objectives):
            quest.status = "completed"
            quest.completed_at = int(time.time() * 1000)
            newly_completed.append(quest_id)
            if quest_id.startswith("arc__"):
                messages.append(f"Story task complete: {quest.name}. Continue with `choose`.")
            else:
                messages.append(
                    f"Quest completed: {quest.name}! Return to the quest giver to turn it in."
                )

    for quest_id in newly_completed:
        player.completed_quests[quest_id] = player.active_quests.pop(quest_id)

    return messages
