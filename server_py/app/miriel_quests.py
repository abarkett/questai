"""
AI-powered quest generation using Miriel.
Hybrid system: checks templates first, generates via AI if missing.
Includes story arc progression system for multi-quest narratives.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Dict, Any, Optional, Tuple, List

from .services.miriel_client import get_miriel_client
from .services.miriel_prompts import build_quest_generation_prompt, build_story_arc_prompt
from .types import Player
from .types_quests import Quest, QuestObjective
from .types_story_arcs import StoryArc, StoryArcChapter
from .world_quests import QUEST_TEMPLATES
from .db import (
    get_all_world_state,
    calculate_reputation,
    get_all_factions,
    get_recent_player_actions,
    get_player_story_arcs,
    cache_miriel_content,
    get_cached_miriel_content,
    create_story_arc,
    join_story_arc,
    update_story_arc_chapter,
    get_world_turn,
)


def get_or_generate_quest(
    quest_id: str,
    player: Player,
    npc_id: Optional[str] = None
) -> Tuple[Optional[Quest], bool]:
    """
    Returns (quest, is_generated).
    First checks templates, then generates via Miriel if not found.

    Args:
        quest_id: Quest identifier
        player: Player requesting the quest
        npc_id: NPC offering the quest

    Returns:
        Tuple of (Quest object or None, whether it was AI-generated)
    """
    # Check template first (templates take priority)
    if quest_id in QUEST_TEMPLATES:
        template_quest = QUEST_TEMPLATES[quest_id]
        # Set the giver NPC if provided
        if npc_id and template_quest.giver_npc_id is None:
            template_quest.giver_npc_id = npc_id
        return (template_quest, False)

    # Generate via Miriel if template not found
    quest = generate_quest_for_player(player, quest_id_hint=quest_id, npc_id=npc_id)
    if quest:
        return (quest, True)

    return (None, False)


def generate_quest_for_player(
    player: Player,
    quest_id_hint: Optional[str] = None,
    npc_id: Optional[str] = None
) -> Optional[Quest]:
    """
    Generate a contextual quest using Miriel based on:
    - Player's quest history
    - Current faction reputation
    - Recent actions (last 20)
    - Active story arcs
    - World state

    Args:
        player: Player for whom to generate the quest
        quest_id_hint: Optional quest ID to use
        npc_id: NPC offering the quest

    Returns:
        Generated Quest object or None if generation failed
    """
    client = get_miriel_client()
    if not client.enabled:
        print("[MIRIEL] Quest generation skipped - Miriel not enabled")
        return None

    try:
        # Build rich context
        context = _build_quest_context(player)

        # Check cache first
        cache_key = _generate_cache_key("quest", context, quest_id_hint or "", npc_id or "")
        cached = get_cached_miriel_content(cache_key)
        if cached:
            print(f"[MIRIEL] Using cached quest for {player.name}")
            try:
                quest_data = json.loads(cached)
                return Quest(**quest_data)
            except Exception as e:
                print(f"[MIRIEL] Failed to parse cached quest: {e}")

        # Build prompt
        prompt = build_quest_generation_prompt(
            player=player,
            context=context,
            quest_id_hint=quest_id_hint,
            npc_id=npc_id
        )

        # Query Miriel
        print(f"[MIRIEL] Generating quest for {player.name} (level {player.level})")
        response = client.query(
            query=prompt,
            project="questai",
            force_exhaustive=False
        )

        if not response:
            print("[MIRIEL] Quest generation returned no response")
            return None

        # Extract text from response
        response_text = response.get("results", {}).get("answer", "")
        if not response_text:
            print("[MIRIEL] Quest generation returned empty answer")
            return None

        # Parse response into Quest object
        try:
            # Try to extract JSON from the response
            # Sometimes the AI includes extra text, so we need to find the JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                quest_data = json.loads(json_str)
            else:
                quest_data = json.loads(response_text)

            # Validate required fields
            if not all(key in quest_data for key in ['quest_id', 'name', 'description', 'objectives', 'rewards']):
                print(f"[MIRIEL] Quest missing required fields: {quest_data.keys()}")
                return None

            # Create Quest object
            quest = Quest(**quest_data)

            # Cache the generated quest
            cache_miriel_content(cache_key, "quest", json.dumps(quest_data), ttl_seconds=3600)

            # Learn the generated quest (auto-learning)
            if client.auto_learning_enabled:
                try:
                    client.learn(
                        input_data={
                            "type": "generated_quest",
                            "quest": quest_data,
                            "player_context": context
                        },
                        metadata={
                            "content_type": "quest",
                            "player_id": player.player_id,
                            "quest_id": quest.quest_id
                        }
                    )
                except Exception as e:
                    print(f"[MIRIEL] Failed to learn generated quest: {e}")

            print(f"[MIRIEL] Successfully generated quest: {quest.name}")
            return quest

        except json.JSONDecodeError as e:
            print(f"[MIRIEL] Failed to parse quest JSON: {e}")
            print(f"[MIRIEL] Response: {response_text[:500]}")
            return None
        except Exception as e:
            print(f"[MIRIEL] Failed to create quest object: {e}")
            return None

    except Exception as e:
        print(f"[MIRIEL] Quest generation error: {e}")
        return None


def generate_story_arc(
    player: Player,
    arc_type: str = "personal",
    chapters: int = 3
) -> Optional[Dict[str, Any]]:
    """
    Generate a multi-quest story arc.

    Args:
        player: Player for whom to generate the arc
        arc_type: Type of arc ('personal', 'faction', 'world')
        chapters: Number of chapters

    Returns:
        Story arc data dict or None if generation failed
    """
    client = get_miriel_client()
    if not client.enabled:
        return None

    try:
        context = _build_quest_context(player)
        context["arc_type"] = arc_type
        context["requested_chapters"] = chapters

        prompt = build_story_arc_prompt(player, context)

        print(f"[MIRIEL] Generating {chapters}-chapter {arc_type} story arc for {player.name}")
        response = client.query(
            query=prompt,
            project="questai",
            force_exhaustive=False
        )

        if not response:
            return None

        response_text = response.get("results", {}).get("answer", "")
        if not response_text:
            return None

        try:
            # Extract JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                arc_data = json.loads(json_str)
            else:
                arc_data = json.loads(response_text)

            # Learn the generated arc
            if client.auto_learning_enabled:
                try:
                    client.learn(
                        input_data={
                            "type": "generated_story_arc",
                            "arc": arc_data,
                            "player_context": context
                        },
                        metadata={
                            "content_type": "story_arc",
                            "player_id": player.player_id,
                            "arc_id": arc_data.get("arc_id")
                        }
                    )
                except Exception:
                    pass

            print(f"[MIRIEL] Successfully generated story arc: {arc_data.get('title')}")
            return arc_data

        except json.JSONDecodeError as e:
            print(f"[MIRIEL] Failed to parse story arc JSON: {e}")
            return None

    except Exception as e:
        print(f"[MIRIEL] Story arc generation error: {e}")
        return None


def _build_quest_context(player: Player) -> Dict[str, Any]:
    """
    Build comprehensive context for quest generation.

    Args:
        player: Player for context

    Returns:
        Context dictionary with all relevant game state
    """
    context = {
        "player_id": player.player_id,
        "player_name": player.name,
        "player_level": player.level,
        "location": player.location,
        "active_quests": [],
        "completed_quests": [],
        "archived_quests": []
    }

    # Add quest context
    if player.active_quests:
        context["active_quests"] = [q.quest_id for q in player.active_quests.values()]
    if player.completed_quests:
        context["completed_quests"] = list(player.completed_quests.keys())
    if player.archived_quests:
        context["archived_quests"] = list(player.archived_quests.keys())

    # Add reputation context
    try:
        reputations = {}
        for faction in get_all_factions():
            rep = calculate_reputation(player.player_id, faction["faction_id"])
            reputations[faction["faction_id"]] = rep
        context["reputations"] = reputations
    except Exception:
        context["reputations"] = {}

    # Add recent action history
    try:
        recent_actions = get_recent_player_actions(player.player_id, limit=20)
        context["recent_actions"] = recent_actions
    except Exception:
        context["recent_actions"] = []

    # Add world state
    try:
        context["world_state"] = get_all_world_state()
    except Exception:
        context["world_state"] = {}

    # Add active story arcs
    try:
        arcs = get_player_story_arcs(player.player_id)
        if arcs:
            context["active_story_arcs"] = [
                {"arc_id": a["arc_id"], "chapter": a.get("current_chapter", 1)}
                for a in arcs
            ]
    except Exception:
        pass

    return context


def _generate_cache_key(content_type: str, context: Dict[str, Any], *args) -> str:
    """
    Generate deterministic cache key from content type, context, and additional args.

    Args:
        content_type: Type of content ('quest', 'dialogue', etc.)
        context: Context dictionary
        *args: Additional arguments to include in key

    Returns:
        SHA256 hash as cache key
    """
    # Create a simplified context for caching (ignore timestamps and very specific data)
    cache_context = {
        "type": content_type,
        "player_level": context.get("player_level"),
        "location": context.get("location"),
        "active_quests": context.get("active_quests", []),
        "completed_count": len(context.get("completed_quests", [])),
        "reputations": context.get("reputations", {}),
        "world_state": context.get("world_state", {}),
        "args": args
    }

    combined = json.dumps(cache_context, sort_keys=True)
    return hashlib.sha256(combined.encode()).hexdigest()


# ===== Story Arc Progression System =====

def check_story_arc_progression(player: Player) -> List[str]:
    """
    Check if player has completed all quests in current chapter of any story arc.
    Returns list of arc_ids that should advance to next chapter.

    Args:
        player: Player to check

    Returns:
        List of arc IDs ready to progress
    """
    ready_to_advance = []

    try:
        # Get all active story arcs for this player
        arcs_data = get_player_story_arcs(player.player_id)

        for arc_data in arcs_data:
            arc_id = arc_data["arc_id"]
            current_chapter = arc_data.get("current_chapter", 1)

            # Parse metadata to get chapter quest IDs
            try:
                metadata = json.loads(arc_data.get("metadata_json", "{}"))
                chapters = metadata.get("chapters", [])

                if current_chapter <= len(chapters):
                    chapter = chapters[current_chapter - 1]  # 0-indexed list
                    chapter_quest_ids = chapter.get("quest_ids", [])

                    # Check if all chapter quests are completed or archived
                    all_completed = True
                    for quest_id in chapter_quest_ids:
                        if quest_id not in player.archived_quests:
                            all_completed = False
                            break

                    if all_completed and chapter_quest_ids:  # Don't advance if no quests
                        ready_to_advance.append(arc_id)

            except Exception as e:
                print(f"[STORY ARC] Failed to check arc {arc_id}: {e}")
                continue

    except Exception as e:
        print(f"[STORY ARC] Failed to check progression: {e}")

    return ready_to_advance


def advance_story_arc(player_id: str, arc_id: str) -> Optional[int]:
    """
    Advance a story arc to the next chapter.

    Args:
        player_id: Player advancing the arc
        arc_id: Story arc to advance

    Returns:
        New chapter number or None if arc is complete
    """
    try:
        arcs_data = get_player_story_arcs(player_id)
        arc_data = None

        for arc in arcs_data:
            if arc["arc_id"] == arc_id:
                arc_data = arc
                break

        if not arc_data:
            print(f"[STORY ARC] Arc {arc_id} not found for player {player_id}")
            return None

        current_chapter = arc_data.get("current_chapter", 1)
        total_chapters = arc_data.get("total_chapters", 1)

        if current_chapter >= total_chapters:
            print(f"[STORY ARC] Arc {arc_id} already at final chapter")
            return None

        # Advance to next chapter
        new_chapter = current_chapter + 1
        update_story_arc_chapter(arc_id, new_chapter)

        print(f"[STORY ARC] Advanced {arc_id} to chapter {new_chapter}/{total_chapters}")
        return new_chapter

    except Exception as e:
        print(f"[STORY ARC] Failed to advance arc: {e}")
        return None


def create_and_start_story_arc(
    player: Player,
    arc_type: str = "personal",
    chapters: int = 3
) -> Optional[str]:
    """
    Generate a story arc and start it for the player.

    Args:
        player: Player to create arc for
        arc_type: Type of arc
        chapters: Number of chapters

    Returns:
        Arc ID if successful, None otherwise
    """
    try:
        # Generate the story arc
        arc_data = generate_story_arc(player, arc_type, chapters)
        if not arc_data:
            return None

        # Create in database
        create_story_arc(
            arc_id=arc_data["arc_id"],
            title=arc_data["title"],
            description=arc_data["description"],
            arc_type=arc_data["arc_type"],
            total_chapters=arc_data["total_chapters"],
            faction_alignment=arc_data.get("faction_alignment"),
            metadata=arc_data
        )

        # Join player to arc
        join_story_arc(player.player_id, arc_data["arc_id"])

        print(f"[STORY ARC] Created and started arc: {arc_data['title']}")
        return arc_data["arc_id"]

    except Exception as e:
        print(f"[STORY ARC] Failed to create arc: {e}")
        return None
