from __future__ import annotations

from ...types import Player, ActionResponse
from ..state_view import build_action_state


def _quest_view(quest) -> dict:
    from ..quest_progress import current_objectives
    objs = current_objectives(quest)
    view = {
        "quest_id": quest.quest_id,
        "name": quest.name,
        "description": quest.description,
        "status": quest.status,
        "objectives": [
            {
                "type": o.type,
                "target": o.target,
                "progress": o.progress,
                "required": o.required,
            }
            for o in objs
        ],
        "rewards": dict(quest.rewards),
    }
    if getattr(quest, "stages", None):
        view["stage"] = quest.current_stage + 1
        view["total_stages"] = len(quest.stages)
        view["stage_description"] = quest.stages[quest.current_stage].description
    return view


def journal(player: Player) -> ActionResponse:
    active = [_quest_view(q) for q in player.active_quests.values()]
    completed = [_quest_view(q) for q in player.completed_quests.values()]
    archived = [_quest_view(q) for q in player.archived_quests.values()]

    messages = ["Quest Journal:"]

    if active:
        messages.append("Active:")
        for q in active:
            messages.append(f"  {q['name']}")
            for o in q["objectives"]:
                messages.append(f"      {o['type']} {o['target']}: {o['progress']}/{o['required']}")
    if completed:
        messages.append("Ready to turn in:")
        for q in completed:
            messages.append(f"  {q['name']} (return to the quest giver)")
    if archived:
        messages.append(f"Finished: {len(archived)}")
    if not active and not completed and not archived:
        messages.append("  (no quests yet — talk to a quest giver)")

    state = build_action_state(player, scene_dirty=False)
    state["journal"] = {"active": active, "completed": completed, "archived": archived}

    return ActionResponse(ok=True, messages=messages, state=state)
