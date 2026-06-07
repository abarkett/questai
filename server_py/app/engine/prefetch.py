"""
Background cache warming. The scene images are already prefetched on the
client; this warms the *Miriel text* layer (location descriptions) for the
current room and its neighbors, so a `look` (or arriving and looking) is
instant instead of waiting on a Miriel round-trip.

Best-effort by design: warming never raises (even if Miriel is down) — it just
populates caches that the real, crash-hard code paths read later.
"""

from __future__ import annotations

from typing import Any, Dict

from ..db import get_player, get_world_turn
from ..world import get_location
from .entities import get_entities_at
from .state_view import effective_description


def warm_location_caches(player_id: str) -> Dict[str, Any]:
    player = get_player(player_id)
    if not player:
        return {"ok": False, "warmed": 0}

    from ..descriptions import describe  # local import: Miriel-backed

    loc = get_location(player.location)
    # Current room + each adjacent room (so a look here, or after moving, is warm).
    target_ids = [loc.id] + [ex.to for ex in loc.exits]
    turn = get_world_turn()

    warmed = 0
    for loc_id in target_ids:
        try:
            target = get_location(loc_id)
            entities = get_entities_at(loc_id)
            describe(player, target, entities, effective_description(target), turn)
            warmed += 1
        except Exception:
            # Warmer is best-effort: a Miriel outage here must not fail the
            # request (the user-facing look() still crashes hard on its own).
            pass

    return {"ok": True, "warmed": warmed}
