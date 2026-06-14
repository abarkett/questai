from __future__ import annotations

from ...types import Player, ActionResponse
from ...items import get_recipe, get_item
from ...db import upsert_player
from ..state_view import build_action_state


def normalize_item_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _display(item_id: str) -> str:
    item = get_item(item_id)
    return item.name if item else item_id


def craft(player: Player, item_name: str) -> ActionResponse:
    key = normalize_item_key(item_name)
    recipe = get_recipe(key)
    if not recipe:
        return ActionResponse(ok=False, error="You don't know how to craft that.")

    inputs = recipe.get("inputs", {})
    out_qty = recipe.get("qty", 1)

    missing = [
        f"{need}x {_display(mat)}"
        for mat, need in inputs.items()
        if player.inventory.get(mat, 0) < need
    ]
    if missing:
        error = "You lack materials: " + ", ".join(missing)
        # A common trip-up: the material is safe in the stronghold stash.
        in_stash = [
            _display(mat) for mat, need in inputs.items()
            if player.inventory.get(mat, 0) < need and (player.stash or {}).get(mat, 0) > 0
        ]
        if in_stash:
            error += f". Some sit in your stronghold stash ({', '.join(in_stash)}) — `unstash` them first."
        return ActionResponse(ok=False, error=error)

    for mat, need in inputs.items():
        player.inventory[mat] -= need
        if player.inventory[mat] <= 0:
            del player.inventory[mat]

    player.inventory[key] = player.inventory.get(key, 0) + out_qty

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"You craft {out_qty}x {_display(key)}."],
        state=build_action_state(player, scene_dirty=False),
    )
