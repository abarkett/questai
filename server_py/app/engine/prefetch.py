"""
Look-ahead warming: the places a player might go next arrive ready.

The moment a player is somewhere, everything they are likely to need next is
generated in the background, on the server, shared by every player:

  * the scene image of every adjacent room (as it is right now);
  * the scene images this room will show once its monsters fall (the fully
    cleared room, and each single monster removed), so a kill doesn't pause;
  * Miriel prose for this room and its neighbors, so arriving (or `look`) is a
    cache hit instead of a Miriel round-trip;
  * NPC greetings and the next quest offer for the people here.

Everything is best-effort: warming never raises (even if Miriel or the image
model is down) — it only populates caches the real, crash-hard code paths read
later. `warm_location_caches` does it all inline (the shape the tests use);
`schedule_player_warm` is what the action dispatcher calls after every action,
queueing the same work on the background warmer (see app/warmer.py).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from ..db import get_player, get_world_turn
from ..world import get_location
from .entities import get_entities_at, filter_current_player
from .state_view import effective_description

# Queue priorities (lower runs first): next door first, then what this room
# turns into after a fight, then the rooms next door after *their* fights.
PRIO_NEIGHBOR_SCENE = 0
PRIO_HERE_TEXT = 1
PRIO_HERE_VARIANT = 2
PRIO_NEIGHBOR_TEXT = 3
PRIO_HERE_NPC = 4
PRIO_NEIGHBOR_VARIANT = 6


# ---------------------------------------------------------------------------
# Unit warmers: each fills one cache entry, raising on failure.
# ---------------------------------------------------------------------------

def _warm_description(player, loc_id: str) -> None:
    from ..descriptions import describe

    target = get_location(loc_id)
    entities = get_entities_at(loc_id)
    if player is not None:
        entities = filter_current_player(entities, player.player_id)
    describe(player, target, entities, effective_description(target), get_world_turn())


def _warm_cleared_description(player, loc_id: str) -> bool:
    """The 'room after its monsters fall' prose. Returns False if no monsters."""
    from ..descriptions import describe

    target = get_location(loc_id)
    entities = get_entities_at(loc_id)
    if not any(e.get("type") == "monster" for e in entities):
        return False
    cleared = [e for e in entities if e.get("type") != "monster"]
    describe(player, target, cleared, target.cleared_description or target.description, get_world_turn())
    return True


def _warm_npc(player, npc: Dict[str, Any]) -> bool:
    role = npc.get("role")
    if role == "quest_giver":
        from .npc_offers import next_offer
        from ..miriel_dialogue import generate_quest_offer_dialogue
        offer = next_offer(player, npc)  # also generates+caches a dynamic quest
        if not offer:
            return False
        quest, _ = offer
        generate_quest_offer_dialogue(player, quest.name, quest.description, npc["id"])
        return True
    if role in ("shop", "arc_giver", "healer"):
        return False
    from ..miriel_dialogue import generate_npc_dialogue
    generate_npc_dialogue(player, npc["id"], role or "generic", "greeting")
    return True


def scene_prompts_for_player(player) -> List[Dict[str, Any]]:
    """
    Every scene prompt the web client could ask for next, most likely first:
    each neighbor as-is, this room's post-combat variants, each neighbor's
    post-combat variants. Built with the same prompt builder as the client, so
    the cache keys match byte-for-byte.
    """
    from ..scene_prompts import scene_prompt_for_entities, combat_variant_entity_sets

    loc = get_location(player.location)
    here = filter_current_player(get_entities_at(loc.id), player.player_id)
    out: List[Dict[str, Any]] = []

    neighbors = []
    for ex in loc.exits:
        try:
            nloc = get_location(ex.to)
        except Exception:
            continue
        nents = get_entities_at(nloc.id)
        neighbors.append((nloc, nents))
        out.append({"prompt": scene_prompt_for_entities(nloc, nents), "priority": PRIO_NEIGHBOR_SCENE,
                    "what": f"{nloc.id} (next door)"})

    for ents in combat_variant_entity_sets(here):
        out.append({"prompt": scene_prompt_for_entities(loc, ents), "priority": PRIO_HERE_VARIANT,
                    "what": f"{loc.id} (after combat)"})

    for nloc, nents in neighbors:
        for ents in combat_variant_entity_sets(nents):
            out.append({"prompt": scene_prompt_for_entities(nloc, ents), "priority": PRIO_NEIGHBOR_VARIANT,
                        "what": f"{nloc.id} (next door, after combat)"})
    return out


# ---------------------------------------------------------------------------
# Inline warming (synchronous; used by tests and by the background jobs).
# ---------------------------------------------------------------------------

def warm_location_caches(player_id: str, *, scenes: bool = True) -> Dict[str, Any]:
    """
    Warm every cache for the player's current room and its neighbors, inline.
    Returns counts; never raises.
    """
    player = get_player(player_id)
    if not player:
        return {"ok": False, "warmed": 0, "scenes": 0}

    from ..services.miriel_client import is_miriel_enabled

    warmed = 0
    if is_miriel_enabled():
        loc = get_location(player.location)
        for loc_id in [loc.id] + [ex.to for ex in loc.exits]:
            try:
                _warm_description(player, loc_id)
                warmed += 1
            except Exception:
                pass
        try:
            if _warm_cleared_description(player, loc.id):
                warmed += 1
        except Exception:
            pass
        for npc in [e for e in get_entities_at(loc.id) if e.get("type") == "npc"]:
            try:
                if _warm_npc(player, npc):
                    warmed += 1
            except Exception:
                pass

    rendered = 0
    if scenes:
        from ..pregen import render_scene_to_cache
        for job in scene_prompts_for_player(player):
            try:
                if render_scene_to_cache(job["prompt"]):
                    rendered += 1
            except Exception:
                pass

    return {"ok": True, "warmed": warmed, "scenes": rendered}


# ---------------------------------------------------------------------------
# Background scheduling (what the dispatcher calls after every action).
# ---------------------------------------------------------------------------

_last_signature: Dict[str, str] = {}


def _situation_signature(player) -> str:
    """Cheap fingerprint of 'where the player is and what is there'."""
    loc = get_location(player.location)
    parts = [loc.id, effective_description(loc), str(get_world_turn() // 12)]
    # What is here *and* next door: a kill or respawn in either changes the
    # scenes worth having ready.
    for lid in [loc.id] + [ex.to for ex in loc.exits]:
        names = ",".join(sorted(f"{e.get('type')}:{e.get('name')}" for e in get_entities_at(lid)))
        parts.append(f"{lid}={names}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def schedule_player_warm(player_id: str, *, force: bool = False) -> Dict[str, Any]:
    """
    Queue look-ahead warming for a player's current situation. Deduplicated:
    a second action in an unchanged room queues nothing. Never raises.
    """
    try:
        player = get_player(player_id)
        if not player:
            return {"ok": False, "queued": 0}

        sig = _situation_signature(player)
        if not force and _last_signature.get(player_id) == sig:
            return {"ok": True, "queued": 0, "skipped": True}
        _last_signature[player_id] = sig

        from .. import warmer
        from ..pregen import schedule_scene_render
        from ..services.miriel_client import is_miriel_enabled

        queued = 0
        loc = get_location(player.location)
        turn_bucket = get_world_turn() // 12

        # Scenes next door go first: they are what the next `move` shows.
        for job in scene_prompts_for_player(player):
            if schedule_scene_render(job["prompt"], priority=job["priority"]):
                queued += 1

        if is_miriel_enabled():
            def desc_job(lid: str, prio: int):
                key = f"desc:{lid}:{turn_bucket}"
                return warmer.submit(key, lambda: _warm_description(None, lid), priority=prio)

            if desc_job(loc.id, PRIO_HERE_TEXT):
                queued += 1
            for ex in loc.exits:
                if desc_job(ex.to, PRIO_NEIGHBOR_TEXT):
                    queued += 1
            if warmer.submit(f"cleared:{loc.id}:{turn_bucket}",
                             lambda: _warm_cleared_description(None, loc.id), priority=PRIO_HERE_VARIANT):
                queued += 1
            for npc in [e for e in get_entities_at(loc.id) if e.get("type") == "npc"]:
                nid = npc["id"]
                if warmer.submit(f"npc:{player_id}:{nid}:{turn_bucket}",
                                 lambda n=npc: _warm_npc(player, n), priority=PRIO_HERE_NPC):
                    queued += 1

        if queued:
            print(f"[WARM] {player.name} @ {loc.id}: queued {queued} look-ahead jobs")
        return {"ok": True, "queued": queued}
    except Exception as e:  # noqa: BLE001 - never let warming touch a request
        print(f"[WARM] scheduling failed for {player_id}: {e}")
        return {"ok": False, "queued": 0}


def reset_warm_signatures() -> None:
    """Forget dedup state (tests)."""
    _last_signature.clear()
