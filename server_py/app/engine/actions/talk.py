from __future__ import annotations

from ...types import Player, ActionResponse
from ..entities import find_entity, get_entities_at, serialize_entity
from ...world import get_location
from ...world_quests import QUEST_TEMPLATES
from copy import deepcopy


def talk(player: Player, target: str) -> ActionResponse:
    npc = find_entity(player.location, target)

    if not npc or npc.type != "npc":
        return ActionResponse(
            ok=False,
            error="There is no one like that to talk to."
        )

    messages = [f"{npc.name} says:"]

    if npc.role == "quest_giver":
        available = []
        for qid in npc.quests or []:
            if qid not in player.quests:
                available.append(qid)

        if not available:
            messages.append("“You have done all I asked. Thank you.”")
        else:
            qid = available[0]
            quest = QUEST_TEMPLATES[qid]
            messages.append(f"“{quest.description}”")
            messages.append(f"You may `accept {qid}`.")

    if npc.role == "shop":
        if not npc.inventory:
            messages.append("“Sorry, I have nothing for sale right now.”")
        else:
            items = ", ".join(
                f"{item} ({data['price']} coins)"
                for item, data in npc.inventory.items()
            )
            messages.append(f"“Take a look at my wares: {items}.”")
            messages.append("You can `buy <item>`.")

    else:
        messages.append("“Hello there.”")

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
        },
    )