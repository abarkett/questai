from copy import deepcopy
from ...types import Player, ActionResponse
from ...world_quests import QUEST_TEMPLATES
from ...db import upsert_player
from ..entities import get_entities_at, serialize_entity, get_adjacent_scenes
from ...world import get_location


def accept_quest(player: Player, quest_id: str) -> ActionResponse:
    if quest_id in player.quests:
        return ActionResponse(ok=False, error="You already have that quest.")

    template = QUEST_TEMPLATES.get(quest_id)
    if not template:
        return ActionResponse(ok=False, error="Unknown quest.")

    quest = deepcopy(template)
    quest.status = "active"
    player.quests[quest_id] = quest

    upsert_player(player)
    loc = get_location(player.location)
    entities = get_entities_at(player.location)

    return ActionResponse(
        ok=True,
        messages=[f"Quest accepted: {quest.name}"],
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