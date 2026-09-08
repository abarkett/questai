from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import upsert_player
from ...status_effects import clear_negative
from ..entities import get_entities_at
from ..state_view import build_action_state


# A deliberately tiny offering: the temple is a safety net, not an economy sink.
HEAL_COST = 2


def heal_cost() -> int:
    """What the temple asks. Once the campaign restocks its shelves (the
    'temple_stores' wrong is righted), the priest asks nothing — a restoration
    you can feel, not just read about."""
    try:
        from ...restoration import is_righted
        if is_righted("temple_stores"):
            return 0
    except Exception:
        pass
    # A passing boon (a festival, a blessing — see app/incidents.py) can do
    # the same for a while.
    try:
        from ...incidents import boon_active
        if boon_active("free_heal"):
            return 0
    except Exception:
        pass
    return HEAL_COST


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

    cost = heal_cost()
    if cost and player.inventory.get("coin", 0) < cost:
        return ActionResponse(
            ok=False,
            error=f"The temple asks a small offering of {cost} coins, which you cannot spare.",
        )

    if cost:
        player.inventory["coin"] -= cost
        if player.inventory["coin"] <= 0:
            del player.inventory["coin"]

    player.hp = player.max_hp
    cured = clear_negative(player)

    if cost:
        messages = [f"The priest tends you for an offering of {cost} coins. You are fully restored."]
    else:
        messages = ["The priest tends you and asks nothing — the temple's shelves are full again. You are fully restored."]
    messages.extend(cured)

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )
