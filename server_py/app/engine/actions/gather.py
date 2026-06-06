from __future__ import annotations

import time

from ...types import Player, ActionResponse
from ...items import LOCATION_RESOURCES, get_item
from ...db import upsert_player, get_world_state, set_world_state
from ...ambush import has_aggressive, maybe_ambush
from ..state_view import build_action_state

# When it's safe (no hostiles), gathering has a short cooldown so it can't be
# spammed for infinite resources.
GATHER_COOLDOWN_MS = 12 * 1000


def gather(player: Player) -> ActionResponse:
    resource = LOCATION_RESOURCES.get(player.location)
    if not resource:
        return ActionResponse(ok=False, error="There's nothing to gather here.")

    messages: list[str] = []
    item = get_item(resource)
    name = item.name if item else resource

    if has_aggressive(player.location):
        # Risky: gathering in the open may provoke a hostile monster.
        ambush_msgs = maybe_ambush(player)
        messages.extend(ambush_msgs)
        if player.hp <= 0:
            # Driven off before you could collect anything.
            upsert_player(player)
            return ActionResponse(ok=True, messages=messages,
                                  state=build_action_state(player, scene_dirty=True))
    else:
        # Safe: enforce a cooldown so it can't be farmed instantly.
        now = int(time.time() * 1000)
        key = f"gather_cd_{player.player_id}"
        try:
            last = int(get_world_state(key) or 0)
        except ValueError:
            last = 0
        if now - last < GATHER_COOLDOWN_MS:
            wait = (GATHER_COOLDOWN_MS - (now - last)) // 1000 + 1
            return ActionResponse(ok=False, error=f"The land needs a moment to recover ({wait}s).")
        set_world_state(key, str(now))

    player.inventory[resource] = player.inventory.get(resource, 0) + 1
    messages.append(f"You gather {name}.")

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
