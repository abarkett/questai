from __future__ import annotations

from ...types import Player, ActionResponse, Companion
from ...db import upsert_player
from ...companions import (
    RECRUIT_COST,
    ARCHETYPE_BLURB,
    is_recruitable,
    pick_archetype,
    now_ms,
)
from ...miriel_companion import companion_line
from ..entities import find_entity
from ..state_view import build_action_state


def recruit(player: Player, target: str) -> ActionResponse:
    if player.companion:
        return ActionResponse(
            ok=False,
            error=(
                f"{player.companion.name} already travels with you. "
                "`dismiss` them before recruiting another."
            ),
        )

    npc = find_entity(player.location, target)
    if not npc or npc.get("type") != "npc":
        return ActionResponse(ok=False, error="There is no one like that here to recruit.")

    if not is_recruitable(npc):
        return ActionResponse(
            ok=False,
            error=f"{npc['name']} has work to do here and won't be joining you.",
        )

    if player.inventory.get("coin", 0) < RECRUIT_COST:
        return ActionResponse(
            ok=False,
            error=(
                f"Recruiting {npc['name']} takes a {RECRUIT_COST}-coin signing bonus — "
                "you can't cover it."
            ),
        )

    player.inventory["coin"] = player.inventory.get("coin", 0) - RECRUIT_COST
    archetype = pick_archetype(npc)
    companion = Companion(
        npc_id=npc["id"],
        name=npc["name"],
        archetype=archetype,
        recruited_at=now_ms(),
    )
    player.companion = companion

    line = companion_line(
        player, companion, "join",
        fallback=f"Lead on, {player.name}. I'll watch your back.",
    )

    messages = [
        f"{npc['name']} pockets your coin and falls into step beside you.",
        f'{companion.name}: "{line}"',
        ARCHETYPE_BLURB[archetype],
    ]
    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
