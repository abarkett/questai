from __future__ import annotations

from ...types import Player, ActionResponse
from ...items import get_item
from ...db import upsert_player
from ..state_view import build_action_state


def normalize_item_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _display_name(item_id: str) -> str:
    item = get_item(item_id)
    return item.name if item else item_id


def equip(player: Player, item_name: str) -> ActionResponse:
    key = normalize_item_key(item_name)

    if player.inventory.get(key, 0) <= 0:
        return ActionResponse(ok=False, error="You don't have that item.")

    item = get_item(key)
    if not item or item.type not in ("weapon", "armor") or not item.slot:
        return ActionResponse(ok=False, error="You can't equip that.")

    slot = item.slot
    messages = []

    # Return whatever is currently in the slot to the inventory.
    current = player.equipment.get(slot)
    if current:
        player.inventory[current] = player.inventory.get(current, 0) + 1
        messages.append(f"You unequip {_display_name(current)}.")

    # Move the new item from inventory into the slot.
    player.inventory[key] -= 1
    if player.inventory[key] <= 0:
        del player.inventory[key]
    player.equipment[slot] = key

    bonus = (
        f"+{item.damage} damage" if item.type == "weapon" else f"+{item.defense} defense"
    )
    messages.append(f"You equip {item.name} ({bonus}).")

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=messages,
        state=build_action_state(player, scene_dirty=False),
    )


def unequip(player: Player, slot: str) -> ActionResponse:
    slot = slot.strip().lower()
    if slot not in ("weapon", "armor"):
        return ActionResponse(ok=False, error="Equip slots are: weapon, armor.")

    current = player.equipment.get(slot)
    if not current:
        return ActionResponse(ok=False, error=f"You have nothing equipped in your {slot} slot.")

    player.inventory[current] = player.inventory.get(current, 0) + 1
    del player.equipment[slot]

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"You unequip {_display_name(current)}."],
        state=build_action_state(player, scene_dirty=False),
    )
