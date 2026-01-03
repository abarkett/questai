from copy import deepcopy
import time
from ...types import Player, ActionResponse
from ...world_quests import QUEST_TEMPLATES
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity
from ...world import get_location
from ..state_view import build_action_state


def accept_quest(player: Player, quest_id: str) -> ActionResponse:
    # Check if quest is already in any quest list
    if quest_id in player.active_quests:
        return ActionResponse(ok=False, error="You already have that quest active.")
    if quest_id in player.completed_quests:
        return ActionResponse(ok=False, error="You already completed that quest.")
    if quest_id in player.archived_quests:
        return ActionResponse(ok=False, error="That quest is archived.")

    template = QUEST_TEMPLATES.get(quest_id)
    if not template:
        return ActionResponse(ok=False, error="Unknown quest.")

    quest = deepcopy(template)
    quest.status = "accepted"
    quest.accepted_at = int(time.time() * 1000)
    player.active_quests[quest_id] = quest

    upsert_player(player)
    loc = get_location(player.location)
    entities = get_entities_at(player.location)

    return ActionResponse(
        ok=True,
        messages=[f"Quest accepted: {quest.name}"],
        state=build_action_state(player, scene_dirty=False),
    )