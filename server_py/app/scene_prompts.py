"""
Scene prompt construction — the Python twin of web/src/app/lib/scene.ts.

The shared image cache is keyed by sha256(prompt), so server-side
pre-generation only pays off if this builder produces *byte-identical* output
to the client's buildScenePrompt. If you change one, change the other (the
parity is locked by a fixture test in test_pregen.py).
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_scene_prompt(location_name: str, description: str, entity_names: List[str]) -> str:
    creatures = (
        f"Depict exactly these living things and no others: {', '.join(entity_names)}."
        if entity_names
        else "No creatures or people are present; depict the empty location."
    )

    return f"""
  Fantasy RPG scene illustration.
  Wide horizontal composition (16:9).
  Cinematic landscape framing.

  IMPORTANT:
  - The scene must fill the entire frame edge-to-edge.
  - No borders, no margins, no white space.
  - No blank background areas.
  - The image should extend fully to all edges.

  Style: detailed hand-painted fantasy art.
  Location: {location_name}.
  Description: {description}
  {creatures}
  Do not add extra characters, companions, adventurers, or a party.

  No text, no UI, no labels.
  """.strip()


def scene_entity_names(entities: List[Dict[str, Any]]) -> List[str]:
    """Creature/NPC names exactly as the client filters them (never players)."""
    return [
        e["name"] if isinstance(e, dict) else str(e)
        for e in entities
        if e and (isinstance(e, str) or e.get("type") in ("monster", "npc"))
    ]


def scene_prompt_for_location(location_id: str) -> str:
    """The prompt the web client would build for this location right now."""
    from .world import get_location
    from .engine.entities import get_entities_at
    from .engine.state_view import effective_description

    loc = get_location(location_id)
    names = scene_entity_names(get_entities_at(location_id))
    return build_scene_prompt(loc.name, effective_description(loc), names)
