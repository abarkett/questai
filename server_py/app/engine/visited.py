from __future__ import annotations

from ..types import Player


def mark_visited(player: Player) -> bool:
    """
    Record the player's current location as discovered.
    Returns True if it was newly added (so the caller can persist).
    """
    if player.location not in player.visited_locations:
        player.visited_locations.append(player.location)
        return True
    return False
