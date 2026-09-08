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

    # Nothing to warm when Miriel is off: describe() falls back to authored
    # text and the dialogue/quest generators no-op.
    from ..services.miriel_client import is_miriel_enabled
    if not is_miriel_enabled():
        return {"ok": True, "warmed": 0}

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

    here_entities = get_entities_at(loc.id)

    # (3) The "cleared room" description, so looking/arriving after a kill is warm.
    monsters = [e for e in here_entities if e.get("type") == "monster"]
    if monsters:
        try:
            cleared = [e for e in here_entities if e.get("type") != "monster"]
            describe(player, loc, cleared, loc.cleared_description or loc.description, turn)
            warmed += 1
        except Exception:
            pass

    # (1)/(2) NPC dialogue + the next (possibly dynamically generated) quest.
    for npc in [e for e in here_entities if e.get("type") == "npc"]:
        role = npc.get("role")
        try:
            if role == "quest_giver":
                from .npc_offers import next_offer
                from ..miriel_dialogue import generate_quest_offer_dialogue
                offer = next_offer(player, npc)  # also generates+caches a dynamic quest
                if offer:
                    quest, _ = offer
                    generate_quest_offer_dialogue(player, quest.name, quest.description, npc["id"])
                    warmed += 1
            elif role not in ("shop", "arc_giver", "healer"):
                from ..miriel_dialogue import generate_npc_dialogue
                generate_npc_dialogue(player, npc["id"], role or "generic", "greeting")
                warmed += 1
        except Exception:
            pass

    return {"ok": True, "warmed": warmed}
