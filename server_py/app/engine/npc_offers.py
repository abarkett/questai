"""
What a quest-giver NPC would offer the player next — shared by the talk action
and the background cache warmer so they agree on what to (pre)generate.
"""

from __future__ import annotations

from typing import Optional, Tuple

from ..world_quests import QUEST_TEMPLATES, is_quest_available


def has_active_quest_with_npc(player, npc: dict) -> bool:
    return any(
        q.giver_npc_id == npc["id"] or q.quest_id in (npc.get("quests") or [])
        for q in player.active_quests.values()
    )


def next_offer(player, npc: dict) -> Optional[Tuple]:
    """
    Return (quest, is_dynamic) the NPC would offer next, or None if it has an
    active quest with the player or nothing to offer. For the dynamic case this
    generates (and caches) the AI quest, so calling it warms that cache too.
    """
    if npc.get("type") != "npc" or npc.get("role") != "quest_giver":
        return None
    if has_active_quest_with_npc(player, npc):
        return None

    # First available template quest.
    for qid in npc.get("quests") or []:
        template = QUEST_TEMPLATES.get(qid)
        if qid in player.active_quests or qid in player.completed_quests:
            continue
        if qid in player.archived_quests and not (template and template.repeatable):
            continue
        available, _ = is_quest_available(qid)
        if available and template:
            return (template, False)

    # Otherwise a fresh, dynamically generated quest (raises if Miriel is down).
    from .actions.talk import _dynamic_quest_id
    from ..miriel_quests import get_or_generate_quest

    qid = _dynamic_quest_id(player, npc["id"])
    if (qid in player.active_quests or qid in player.completed_quests
            or qid in player.archived_quests):
        return None
    quest, _ = get_or_generate_quest(qid, player, npc["id"])
    return (quest, True) if quest else None
