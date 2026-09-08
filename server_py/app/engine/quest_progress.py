from __future__ import annotations

import time

from ..types import Player


def current_objectives(quest) -> list:
    """The objectives that are currently active (the current stage, if staged)."""
    if getattr(quest, "stages", None):
        if 0 <= quest.current_stage < len(quest.stages):
            return quest.stages[quest.current_stage].objectives
        return []
    return quest.objectives


def _all_collect_objectives(quest) -> list:
    objs = list(quest.objectives or [])
    for s in (getattr(quest, "stages", None) or []):
        objs.extend(s.objectives)
    return objs


def completion_message(quest) -> str:
    if quest.quest_id.startswith("arc__"):
        return f"Story task complete: {quest.name}. Continue with `choose`."
    if quest.quest_id.startswith("deed__"):
        # A campaign deed settles itself into the shared world; no turn-in.
        return f"Deed done: {quest.name}."
    return f"Quest completed: {quest.name}! Return to the quest giver to turn it in."


def stage_message(quest) -> str:
    stage = quest.stages[quest.current_stage]
    return f"Stage complete! Next: {stage.description}"


def consume_quest_items(player: Player, quest) -> list[str]:
    """Remove items the quest's collect objectives required, on turn-in."""
    messages: list[str] = []
    for o in _all_collect_objectives(quest):
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
    Recompute collect/visit progress for active quests' current stage, advancing
    stages and completing quests as objectives are met. Kill objectives are
    handled at the moment of the kill (in attack). Returns player-facing messages.
    """
    messages: list[str] = []
    newly_completed: list[str] = []
    visited = set(player.visited_locations) | {player.location}

    for quest_id, quest in list(player.active_quests.items()):
        if quest.status != "accepted":
            continue

        while True:
            objs = current_objectives(quest)
            for obj in objs:
                if obj.type == "collect":
                    obj.progress = min(obj.required, player.inventory.get(obj.target, 0))
                elif obj.type == "visit":
                    if obj.target in visited:
                        obj.progress = obj.required

            if objs and all(o.progress >= o.required for o in objs):
                if quest.stages and quest.current_stage < len(quest.stages) - 1:
                    quest.current_stage += 1
                    messages.append(stage_message(quest))
                    continue  # re-evaluate the new stage (may already be satisfied)
                quest.status = "completed"
                quest.completed_at = int(time.time() * 1000)
                newly_completed.append(quest_id)
                messages.append(completion_message(quest))
            break

    for quest_id in newly_completed:
        player.completed_quests[quest_id] = player.active_quests.pop(quest_id)

    return messages
