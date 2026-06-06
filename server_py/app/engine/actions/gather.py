from __future__ import annotations

from ...types import Player, ActionResponse
from ...items import LOCATION_RESOURCES, get_item
from ...db import upsert_player
from ..state_view import build_action_state


def gather(player: Player) -> ActionResponse:
    resource = LOCATION_RESOURCES.get(player.location)
    if not resource:
        return ActionResponse(ok=False, error="There's nothing to gather here.")

    player.inventory[resource] = player.inventory.get(resource, 0) + 1
    item = get_item(resource)
    name = item.name if item else resource

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"You gather {name}."],
        state=build_action_state(player, scene_dirty=False),
    )
