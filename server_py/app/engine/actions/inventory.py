from ...types import Player, ActionResponse
from ...items import ITEMS


def inventory(player: Player) -> ActionResponse:
    if not player.inventory:
        return ActionResponse(ok=True, messages=["Your inventory is empty."])

    lines = ["You are carrying:"]
    for item_id, qty in player.inventory.items():
        item = ITEMS.get(item_id)
        name = item.name if item else item_id
        lines.append(f"- {name} x{qty}")

    return ActionResponse(ok=True, messages=lines)