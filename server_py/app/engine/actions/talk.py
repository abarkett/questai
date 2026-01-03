from __future__ import annotations

import time
from ...types import Player, ActionResponse
from ..entities import find_entity, get_entities_at, serialize_entity
from ...world import get_location
from ...world_quests import QUEST_TEMPLATES, is_quest_available
from ..state_view import build_action_state
from ...db import upsert_player
from copy import deepcopy


def talk(player: Player, target: str) -> ActionResponse:
    npc = find_entity(player.location, target)

    if not npc or npc["type"] != "npc":
        return ActionResponse(
            ok=False,
            error="There is no one like that to talk to."
        )

    messages = [f"{npc['name']} says:"]

    # First, check if player has any completed quests to turn in to this NPC
    if npc.get("role") == "quest_giver":
        turned_in_quests = []
        for qid in list(player.completed_quests.keys()):
            quest = player.completed_quests[qid]
            # Check if this quest is offered by this NPC and is completed
            if qid in npc.get("quests", []) and quest.status == "completed":
                # Turn in the quest
                for item, quantity in quest.rewards.items():
                    player.inventory[item] = player.inventory.get(item, 0) + quantity

                quest.status = "turned_in"
                quest.turned_in_at = int(time.time() * 1000)

                # Move to archived quests
                player.archived_quests[qid] = quest
                del player.completed_quests[qid]
                turned_in_quests.append(quest)

        if turned_in_quests:
            for quest in turned_in_quests:
                messages.append(f'"Excellent work on {quest.name}!"')
                for item, quantity in quest.rewards.items():
                    messages.append(f"Received: {quantity}x {item}")
            upsert_player(player)

    if npc.get("role") == "quest_giver":
        # Check for active quests with this NPC
        active_with_npc = []
        for qid in npc.get("quests", []):
            if qid in player.active_quests:
                active_with_npc.append(player.active_quests[qid])

        if active_with_npc:
            # Player has active quest(s) with this NPC
            for quest in active_with_npc:
                progress_strs = []
                for obj in quest.objectives:
                    progress_strs.append(f"{obj.target}: {obj.progress}/{obj.required}")
                progress = ", ".join(progress_strs)
                messages.append(f'"How goes {quest.name}? ({progress})"')
        else:
            # No active quests, check for new ones to offer
            available = []
            unavailable_reasons = []

            for qid in npc.get("quests", []):
                print(f"[QUEST OFFER] Checking quest: {qid}")
                quest_template = QUEST_TEMPLATES.get(qid)
                print(f"[QUEST OFFER] Template found: {quest_template is not None}")
                if quest_template:
                    print(f"[QUEST OFFER] Template repeatable: {quest_template.repeatable}")

                # Skip if player already has this quest active or completed (but not turned in)
                if qid in player.active_quests or qid in player.completed_quests:
                    print(f"[QUEST OFFER] Quest {qid} is active or completed, skipping")
                    continue

                print(f"[QUEST OFFER] Quest in archived: {qid in player.archived_quests}")
                # For non-repeatable quests, skip if already archived
                if qid in player.archived_quests and not (quest_template and quest_template.repeatable):
                    print(f"[QUEST OFFER] Quest {qid} is archived and not repeatable, skipping")
                    continue

                # Check if quest is available based on world state
                print(f"[QUEST OFFER] Checking if quest {qid} is available...")
                is_available, reason = is_quest_available(qid)
                print(f"[QUEST OFFER] Quest {qid} available: {is_available}, reason: {reason}")
                if is_available:
                    available.append(qid)
                elif reason:
                    unavailable_reasons.append(reason)

            print(f"[QUEST OFFER] Available quests: {available}")
            print(f"[QUEST OFFER] Unavailable reasons: {unavailable_reasons}")

            if available:
                # Offer the first available quest
                qid = available[0]
                quest = QUEST_TEMPLATES[qid]
                messages.append(f'"{quest.description}"')
                messages.append(f"You may `accept {qid}`.")
            elif unavailable_reasons:
                # Give context-aware dialogue
                messages.append(f'"{unavailable_reasons[0]}"')
            else:
                # Player has completed all quests
                messages.append('"You have done all I asked. Thank you."')

    if npc.get("role") == "shop":
        if not npc.get("inventory"):
            messages.append('"Sorry, I have nothing for sale right now."')
        else:
            items = ", ".join(
                f"{item} ({data['price']} coins)"
                for item, data in npc["inventory"].items()
            )
            messages.append(f'"Take a look at my wares: {items}."')
            messages.append("You can `buy <item>`.")

    else:
        messages.append('"Hello there."')

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )