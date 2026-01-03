from copy import deepcopy
import time
from ...types import Player, ActionResponse
from ...world_quests import QUEST_TEMPLATES
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity
from ...world import get_location
from ..state_view import build_action_state


def accept_quest(player: Player, quest_id: str) -> ActionResponse:
    from ...db import get_player_party, get_player, upsert_player as db_upsert_player

    template = QUEST_TEMPLATES.get(quest_id)
    if not template:
        return ActionResponse(ok=False, error="Unknown quest.")

    # Check if quest is already in any quest list
    if quest_id in player.active_quests:
        return ActionResponse(ok=False, error="You already have that quest active.")
    if quest_id in player.completed_quests:
        return ActionResponse(ok=False, error="You already completed that quest.")

    # If quest is archived, only allow if it's repeatable
    if quest_id in player.archived_quests:
        if not template.repeatable:
            return ActionResponse(ok=False, error="That quest is archived.")
        # Remove from archived quests to start fresh
        del player.archived_quests[quest_id]

    quest = deepcopy(template)
    quest.status = "accepted"
    quest.accepted_at = int(time.time() * 1000)
    player.active_quests[quest_id] = quest

    messages = [f"Quest accepted: {quest.name}"]

    # Share quest with party members
    party = get_player_party(player.player_id)
    if party:
        for member_id in party["members"]:
            if member_id == player.player_id:
                continue  # Skip self
            member = get_player(member_id)
            if member:
                # Only add if they don't already have it
                if (quest_id not in member.active_quests and
                    quest_id not in member.completed_quests):
                    # Remove from archived if repeatable
                    if quest_id in member.archived_quests and template.repeatable:
                        del member.archived_quests[quest_id]

                    # Give them a fresh copy of the quest
                    member_quest = deepcopy(template)
                    member_quest.status = "accepted"
                    member_quest.accepted_at = int(time.time() * 1000)
                    member.active_quests[quest_id] = member_quest
                    db_upsert_player(member)
                    messages.append(f"[Party] {member.name} also accepted the quest")

    upsert_player(player)

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )