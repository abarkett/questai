from __future__ import annotations

import time
from ...types import Player, ActionResponse
from ..entities import find_entity, get_entities_at, serialize_entity
from ...world import get_location
from ...world_quests import QUEST_TEMPLATES, is_quest_available
from ..state_view import build_action_state
from ...db import upsert_player
from copy import deepcopy


def _dynamic_quest_id(player: Player, npc_id: str) -> str:
    """
    Id for this NPC's current dynamic quest. Stable within an offer→accept
    cycle, and rotates as the player finishes quests so they never get the
    same generated quest twice.
    """
    seed = len(player.completed_quests) + len(player.archived_quests)
    short = player.player_id.replace("-", "")[:8]
    return f"dyn_{npc_id}_{short}_{seed}"


def _offer_dynamic_quest(player: Player, npc: dict, messages: list) -> bool:
    """Generate and offer a fresh AI quest from this NPC. Returns True if offered."""
    qid = _dynamic_quest_id(player, npc["id"])
    # Never re-offer something already in the player's logs.
    if (qid in player.active_quests or qid in player.completed_quests
            or qid in player.archived_quests):
        return False

    from ...miriel_quests import get_or_generate_quest
    quest, _is_generated = get_or_generate_quest(qid, player, npc["id"])
    if not quest:
        return False

    from ...miriel_dialogue import generate_quest_offer_dialogue
    ai_dialogue = generate_quest_offer_dialogue(
        player=player,
        quest_name=quest.name,
        quest_description=quest.description,
        npc_id=npc["id"],
    )
    messages.append(f'"{ai_dialogue}"' if ai_dialogue else f'"{quest.description}"')
    messages.append(f"You may `accept {qid}`.")
    return True


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
            # Turn in if this NPC gave the quest (templates via static list,
            # dynamic quests via giver_npc_id) and it's completed.
            if ((quest.giver_npc_id == npc["id"] or qid in npc.get("quests", []))
                    and quest.status == "completed"):
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
        # Active quests with this NPC: templates via static list, dynamic via giver.
        active_with_npc = [
            q for q in player.active_quests.values()
            if q.giver_npc_id == npc["id"] or q.quest_id in npc.get("quests", [])
        ]

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
                # Offer the first available template quest
                qid = available[0]
                quest = QUEST_TEMPLATES.get(qid)

                if quest:
                    # Try to generate AI dialogue for quest offer
                    from ...miriel_dialogue import generate_quest_offer_dialogue
                    ai_dialogue = generate_quest_offer_dialogue(
                        player=player,
                        quest_name=quest.name,
                        quest_description=quest.description,
                        npc_id=npc["id"]
                    )

                    if ai_dialogue:
                        messages.append(f'"{ai_dialogue}"')
                    else:
                        # Fallback to template description
                        messages.append(f'"{quest.description}"')

                    messages.append(f"You may `accept {qid}`.")
            else:
                # No template available -> offer a fresh, dynamically generated quest
                # so the quest giver always has new work once templates run out.
                offered = _offer_dynamic_quest(player, npc, messages)
                if not offered:
                    if unavailable_reasons:
                        from ...miriel_dialogue import generate_npc_dialogue
                        ai_dialogue = generate_npc_dialogue(
                            player=player,
                            npc_id=npc["id"],
                            npc_role="quest_giver",
                            dialogue_type="quest_unavailable"
                        )
                        messages.append(
                            f'"{ai_dialogue}"' if ai_dialogue else f'"{unavailable_reasons[0]}"'
                        )
                    else:
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

    # Recurring story-arc giver: narrate the player's arc state.
    if npc.get("role") == "arc_giver":
        from .story import arc_talk_lines
        messages.extend(arc_talk_lines(player))

    # Temple healer: offer restoration.
    if npc.get("role") == "healer":
        from .heal import HEAL_COST
        messages.append(
            f'"Rest a moment, traveler. For an offering of {HEAL_COST} coins I will mend '
            f'your wounds and lift any affliction. Just say `heal`."'
        )

    # Generic NPC dialogue (not quest_giver, shop, arc_giver, or healer)
    if npc.get("role") not in ["quest_giver", "shop", "arc_giver", "healer"]:
        # Try to generate AI dialogue for generic greeting
        from ...miriel_dialogue import generate_npc_dialogue
        ai_dialogue = generate_npc_dialogue(
            player=player,
            npc_id=npc["id"],
            npc_role=npc.get("role", "generic"),
            dialogue_type="greeting"
        )

        if ai_dialogue:
            messages.append(f'"{ai_dialogue}"')
        else:
            # Fallback to static dialogue
            messages.append('"Hello there."')

    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )