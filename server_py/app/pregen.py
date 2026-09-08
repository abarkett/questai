"""
Mint-time pre-generation: a new region arrives warm.

When a region is minted, its expensive AI assets are generated up front in a
background thread instead of on each player's first visit: Miriel location
prose (current and cleared variants) and scene images keyed exactly the way
the web client will ask for them (see scene_prompts.py). Everything here is
best-effort — a missing API key or a failed render just means that asset is
generated lazily later, exactly as before.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any, Dict

from . import db


def _warm_location_text(location_id: str) -> int:
    """Cache Miriel prose for a room as-is and as-cleared. Returns count warmed."""
    from .services.miriel_client import is_miriel_enabled
    if not is_miriel_enabled():
        return 0

    from .world import get_location
    from .engine.entities import get_entities_at
    from .engine.state_view import effective_description
    from .descriptions import describe

    loc = get_location(location_id)
    entities = get_entities_at(location_id)
    turn = db.get_world_turn()
    warmed = 0

    # describe() raises on anything short of real Miriel prose, so a success
    # here genuinely means an authored description landed in the cache.
    try:
        describe(None, loc, entities, effective_description(loc), turn)
        warmed += 1
    except Exception as e:
        print(f"[PREGEN] description warm failed for {location_id}: {e}")

    monsters = [e for e in entities if e.get("type") == "monster"]
    if monsters:
        try:
            cleared = [e for e in entities if e.get("type") != "monster"]
            describe(None, loc, cleared, loc.cleared_description or loc.description, turn)
            warmed += 1
        except Exception as e:
            print(f"[PREGEN] cleared-description warm failed for {location_id}: {e}")
    return warmed


def render_scene_to_cache(prompt: str) -> bool:
    """
    Render a scene image for `prompt` into the shared cache (keyed by the hash
    of the *base* prompt, matching /api/ai/image). Returns True if the cache
    holds an image afterwards. Raises if Miriel enrichment is unavailable.
    """
    from .services import image_gen

    key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if db.get_cached_scene_image(key) is not None:
        return True
    if not image_gen.image_gen_enabled():
        return False

    # Enrichment requires Miriel and propagates its failures (no fallback):
    # a scene rendered without world context would silently cache forever.
    render_prompt = image_gen.enrich_scene_prompt(prompt)

    image = image_gen.generate_scene_image(render_prompt)
    if not image:
        return False
    db.cache_scene_image(key, prompt, image, image_gen.get_image_model())
    return True


def _warm_location_image(location_id: str) -> bool:
    from .scene_prompts import scene_prompt_for_location

    try:
        return render_scene_to_cache(scene_prompt_for_location(location_id))
    except Exception as e:
        print(f"[PREGEN] scene warm failed for {location_id}: {e}")
        return False


def pregenerate_region_assets(spec: Dict[str, Any], *, background: bool = True) -> None:
    """Warm text and image caches for every location in a freshly minted region."""
    location_ids = [l["location_id"] for l in spec["locations"]]

    def _run() -> None:
        text = images = 0
        for lid in location_ids:
            try:
                text += _warm_location_text(lid)
                images += 1 if _warm_location_image(lid) else 0
            except Exception as e:  # never let warming hurt anything
                print(f"[PREGEN] {lid}: {e}")
        print(f"[PREGEN] {spec['region_id']}: warmed {text} descriptions, {images} scenes")

    if background:
        threading.Thread(target=_run, name=f"pregen-{spec['region_id']}", daemon=True).start()
    else:
        _run()
