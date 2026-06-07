"""
AI-powered NPC dialogue generation using Miriel.
Generates context-aware responses based on player history and world events.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional, Dict, Any

from .services.miriel_client import get_miriel_client, MirielUnavailable
from .services.miriel_prompts import build_dialogue_prompt, build_quest_offer_dialogue_prompt
from .types import Player
from .db import (
    calculate_reputation,
    get_all_world_state,
    cache_miriel_content,
    get_cached_miriel_content,
)
from .factions import FACTIONS


def generate_npc_dialogue(
    player: Player,
    npc_id: str,
    npc_role: str,
    dialogue_type: str = "greeting"
) -> Optional[str]:
    """
    Generate contextual NPC dialogue.

    dialogue_type can be:
    - 'greeting': General hello
    - 'quest_offer': Offering a quest
    - 'quest_progress': Checking quest progress
    - 'quest_complete': Congratulating completion
    - 'quest_unavailable': Explaining why no quests available
    - 'shop': Merchant dialogue

    Args:
        player: The player interacting with the NPC
        npc_id: NPC identifier
        npc_role: NPC role (quest_giver, shop, generic, etc.)
        dialogue_type: Type of dialogue to generate

    Returns:
        Generated dialogue string or None if generation failed
    """
    client = get_miriel_client()
    if not client.enabled:
        raise MirielUnavailable("Miriel is not configured (set MIRIEL_API_KEY).")

    try:
        # Build context
        context = {
            "player_id": player.player_id,
            "player_name": player.name,
            "player_level": player.level,
            "location": player.location,
            "npc_id": npc_id,
            "npc_role": npc_role,
            "dialogue_type": dialogue_type
        }

        # Add faction and reputation context if NPC belongs to a faction
        faction_info = _get_npc_faction(npc_id)
        if faction_info:
            reputation = calculate_reputation(player.player_id, faction_info["faction_id"])
            context["faction"] = faction_info["faction_id"]
            context["reputation"] = reputation
            context["reputation_tier"] = _get_reputation_tier(reputation)

        # Add quest context
        context["active_quests"] = [q.quest_id for q in player.active_quests.values()]
        context["completed_quests"] = list(player.completed_quests.keys())

        # Add world state for contextual awareness
        context["world_state"] = get_all_world_state()

        # Check cache first
        cache_key = _generate_dialogue_cache_key(context)
        cached = get_cached_miriel_content(cache_key)
        if cached:
            try:
                # Cached dialogue is stored as JSON string containing just the text
                return json.loads(cached)
            except Exception:
                pass  # Cache miss, continue to generation

        # Build prompt
        prompt = build_dialogue_prompt(context)

        # Query Miriel
        print(f"[MIRIEL] Generating {dialogue_type} dialogue for NPC {npc_id}")
        response = client.query(
            query=prompt,
            project="questai",
            force_exhaustive=False
        )

        if not response:
            return None

        # Extract dialogue from response
        dialogue_text = response.get("results", {}).get("answer", "").strip()
        if not dialogue_text:
            return None

        # Clean up the response (remove quotes if AI added them)
        if dialogue_text.startswith('"') and dialogue_text.endswith('"'):
            dialogue_text = dialogue_text[1:-1]

        # Cache the generated dialogue (shorter TTL for dialogue - 30 minutes)
        cache_miriel_content(cache_key, "dialogue", json.dumps(dialogue_text), ttl_seconds=1800)

        # Learn the generated dialogue (auto-learning)
        if client.auto_learning_enabled:
            try:
                client.learn(
                    input_data={
                        "type": "generated_dialogue",
                        "dialogue": dialogue_text,
                        "context": context
                    },
                    metadata={
                        "content_type": "dialogue",
                        "npc_id": npc_id,
                        "dialogue_type": dialogue_type,
                        "player_id": player.player_id
                    }
                )
            except Exception as e:
                print(f"[MIRIEL] Failed to learn dialogue: {e}")

        return dialogue_text

    except Exception as e:
        # Crash hard when Miriel isn't working (no silent fallback). An empty
        # answer is handled above by returning None (Miriel up, just no content).
        print(f"[MIRIEL] Dialogue generation error: {e}")
        raise


def generate_quest_offer_dialogue(
    player: Player,
    quest_name: str,
    quest_description: str,
    npc_id: str
) -> Optional[str]:
    """
    Generate dialogue for offering a specific quest.

    This is a specialized version that incorporates the actual quest details.

    Args:
        player: The player being offered the quest
        quest_name: Name of the quest
        quest_description: Quest description
        npc_id: NPC offering the quest

    Returns:
        Generated dialogue or None
    """
    client = get_miriel_client()
    if not client.enabled:
        raise MirielUnavailable("Miriel is not configured (set MIRIEL_API_KEY).")

    try:
        context = {}

        # Add faction/reputation context
        faction_info = _get_npc_faction(npc_id)
        if faction_info:
            reputation = calculate_reputation(player.player_id, faction_info["faction_id"])
            context["reputation_tier"] = _get_reputation_tier(reputation)
        else:
            context["reputation_tier"] = "Neutral"

        # Build specialized prompt
        prompt = build_quest_offer_dialogue_prompt(
            player, quest_name, quest_description, npc_id, context
        )

        response = client.query(
            query=prompt,
            project="questai",
            force_exhaustive=False
        )

        if not response:
            return None

        dialogue_text = response.get("results", {}).get("answer", "").strip()
        if dialogue_text.startswith('"') and dialogue_text.endswith('"'):
            dialogue_text = dialogue_text[1:-1]

        return dialogue_text

    except Exception as e:
        print(f"[MIRIEL] Quest offer dialogue error: {e}")
        raise


def _get_npc_faction(npc_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the faction that an NPC belongs to.

    Args:
        npc_id: NPC identifier

    Returns:
        Faction info dict or None
    """
    for faction_id, faction in FACTIONS.items():
        if npc_id in faction.npc_members:
            return {
                "faction_id": faction_id,
                "name": faction.name,
                "alignment": faction.alignment
            }
    return None


def _get_reputation_tier(reputation: int) -> str:
    """
    Convert numeric reputation to tier name.

    Args:
        reputation: Numeric reputation value

    Returns:
        Tier name (Hostile, Unfriendly, Neutral, Friendly, Honored)
    """
    if reputation <= -100:
        return "Hostile"
    elif reputation <= -50:
        return "Unfriendly"
    elif reputation < 50:
        return "Neutral"
    elif reputation < 100:
        return "Friendly"
    else:
        return "Honored"


def _generate_dialogue_cache_key(context: Dict[str, Any]) -> str:
    """
    Generate cache key for dialogue.

    Note: Dialogue cache is context-sensitive but time-insensitive
    (we don't include exact timestamp, just general game state).

    Args:
        context: Dialogue context

    Returns:
        SHA256 hash as cache key
    """
    cache_context = {
        "npc_id": context.get("npc_id"),
        "dialogue_type": context.get("dialogue_type"),
        "player_level": context.get("player_level"),
        "location": context.get("location"),
        "reputation_tier": context.get("reputation_tier", "Neutral"),
        "has_active_quests": len(context.get("active_quests", [])) > 0,
        "world_state_keys": sorted(context.get("world_state", {}).keys())
    }

    combined = json.dumps(cache_context, sort_keys=True)
    return hashlib.sha256(combined.encode()).hexdigest()
