from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..types import Player
from ..world import get_location
from .entities import get_entities_at, filter_current_player


def build_location_view_for_player(player: Player) -> Dict[str, Any]:
    """
    Canonical snapshot of the world from *this player's* perspective.
    This is the ONE place we:
      - build the location dict
      - attach entities
      - filter the current player out (so UI never shows yourself in People Here)
    """
    loc = get_location(player.location)

    entities = filter_current_player(
        get_entities_at(player.location),
        player.player_id,
    )

    return {
        "location": {
            "id": loc.id,
            "name": loc.name,
            "description": loc.description,
            "exits": [{"to": e.to, "label": e.label} for e in loc.exits],
        },
        "entities": entities,
        "adjacent_scenes": get_adjacent_scenes_for_prefetch(loc.id),
    }


def get_adjacent_scenes_for_prefetch(location_id: str) -> List[Dict[str, Any]]:
    """
    Adjacent scenes for image prefetch.
    Note: This is NOT player-specific and doesn't need to filter "self".
    """
    loc = get_location(location_id)
    scenes: List[Dict[str, Any]] = []

    for ex in loc.exits:
        next_loc = get_location(ex.to)
        scenes.append(
            {
                "location": {
                    "id": next_loc.id,
                    "name": next_loc.name,
                    "description": next_loc.description,
                    "exits": [{"to": e.to, "label": e.label} for e in next_loc.exits],
                },
                "entities": get_entities_at(next_loc.id),
            }
        )

    return scenes


def build_action_state(
    player: Player,
    *,
    scene_dirty: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Full ActionResponse.state builder used by all actions.
    Centralizes: player dump + location view + optional flags like scene_dirty.
    """
    state: Dict[str, Any] = {
        "player": player.model_dump(),
        **build_location_view_for_player(player),
    }
    if scene_dirty is not None:
        state["scene_dirty"] = scene_dirty
    return state