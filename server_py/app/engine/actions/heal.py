from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import upsert_player
from ...status_effects import clear_negative
from ..entities import get_entities_at
from ..state_view import build_action_state


# A deliberately tiny offering: the temple is a safety net, not an economy sink.
HEAL_COST = 2


def _healer_at(location_id: str):
    for e in get_entities_at(location_id):
        if e["type"] == "npc" and e.get("role") == "healer":
            return e
    return None


def heal(player: Player) -> ActionResponse:
    healer = _healer_at(player.location)
    if healer is None:
        return ActionResponse(ok=False, error="There is no healer here.")

    has_wounds = player.hp < player.max_hp
    has_ailments = bool(player.status_effects)
    if not has_wounds and not has_ailments:
        return ActionResponse(
            ok=True,
            messages=['The priest smiles. "You are already hale and whole, friend."'],
            state=build_action_state(player, scene_dirty=False),
        )

    if player.inventory.get("coin", 0) < HEAL_COST:
        return ActionResponse(
            ok=False,
            error=f"The temple asks a small offering of {HEAL_COST} coins, which you cannot spare.",
        )

    player.inventory["coin"] -= HEAL_COST
    if player.inventory["coin"] <= 0:
        del player.inventory["coin"]

    player.hp = player.max_hp
    cured = clear_negative(player)

    messages = [f"The priest tends you for an offering of {HEAL_COST} coins. You are fully restored."]
    messages.extend(cured)

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
