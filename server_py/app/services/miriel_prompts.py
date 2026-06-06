"""
Prompt templates for Miriel AI queries.
Centralized prompt engineering for consistency and quality.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from ..types import Player


def build_quest_generation_prompt(
    player: Player,
    context: Dict[str, Any],
    quest_id_hint: Optional[str] = None,
    npc_id: Optional[str] = None
) -> str:
    """
    Generate prompt for quest creation.

    Args:
        player: The player for whom to generate the quest
        context: Rich context including quests, reputation, world state
        quest_id_hint: Optional quest ID hint
        npc_id: NPC offering the quest

    Returns:
        Formatted prompt string for Miriel
    """

    active_quests_str = ', '.join(context.get('active_quests', [])) or 'None'
    completed_quests_str = ', '.join(context.get('completed_quests', [])[:5]) or 'None'  # Last 5
    reputations_str = ', '.join([f"{k}: {v}" for k, v in context.get('reputations', {}).items()]) or 'Neutral with all'

    world_state_items = []
    for key, value in context.get('world_state', {}).items():
        world_state_items.append(f"- {key}: {value}")
    world_state_str = '\n'.join(world_state_items) if world_state_items else "- No special conditions"

    recent_actions_str = "No recent actions"
    if context.get('recent_actions'):
        recent = context['recent_actions'][:5]  # Last 5 actions
        recent_actions_str = ', '.join([a.get('action', 'unknown') for a in recent])

    # Only reference monsters that actually exist, so the quest is completable.
    valid_targets = context.get('valid_targets', {}) or {}
    valid_monsters = valid_targets.get('monsters') or ['Rat']
    monsters_str = ', '.join(valid_monsters)
    example_target = valid_monsters[0]

    # Anti-repeat: discourage reusing quests the player has already seen.
    seen_names = context.get('seen_quest_names', []) or []
    avoid_str = '; '.join(seen_names[-12:]) if seen_names else 'None yet'

    novelty_seed = context.get('novelty_seed', 0)

    prompt = f"""Generate a UNIQUE medieval fantasy quest for player '{player.name}' (Level {player.level}).

PLAYER CONTEXT:
- Current Location: {context.get('location', 'unknown')}
- Active Quests: {active_quests_str}
- Recently Completed: {completed_quests_str}
- Faction Standings: {reputations_str}
- Recent Actions: {recent_actions_str}

WORLD STATE:
{world_state_str}

AVOID REPETITION — do NOT reuse the names, themes, targets, or framing of these
quests the player has already seen:
- {avoid_str}

VARIETY:
- Variation token: {novelty_seed} (use as a seed — make this quest clearly distinct from earlier ones)
- Vary the name, framing, stakes, monster count, and rewards every time
- Give it a memorable hook (a rumor, a character, or a twist) in the description

QUEST REQUIREMENTS:
1. Appropriate for a Level {player.level} player
2. Connect to the player's recent activity, location, or faction standing
3. Medieval fantasy tone (no modern references), personal and contextual — not generic
4. Must be COMPLETABLE in the current world: only "kill" objectives are supported
5. The "kill" target MUST be exactly one of these in-world monsters: {monsters_str}.
   Do NOT invent monsters outside that list, or the quest becomes impossible.
6. Rewards should match difficulty/level (coin, optionally healing_herb)

Return ONLY valid JSON matching this exact schema (no additional text):
{{
  "quest_id": "{quest_id_hint or 'generated_quest_' + str(player.level)}",
  "name": "Distinct Quest Name",
  "description": "Quest hook from the NPC's perspective (1-2 sentences)",
  "objectives": [
    {{
      "type": "kill",
      "target": "{example_target}",
      "required": 3
    }}
  ],
  "rewards": {{"coin": 10, "healing_herb": 1}},
  "repeatable": false,
  "giver_npc_id": "{npc_id or 'unknown'}"
}}"""

    return prompt


def build_story_arc_prompt(player: Player, context: Dict[str, Any]) -> str:
    """
    Generate prompt for multi-chapter story arc creation.

    Args:
        player: The player for whom to generate the arc
        context: Rich context including arc type and player history

    Returns:
        Formatted prompt string for Miriel
    """

    arc_type = context.get('arc_type', 'personal')
    chapters = context.get('requested_chapters', 3)
    reputations_str = ', '.join([f"{k}: {v}" for k, v in context.get('reputations', {}).items()]) or 'Neutral'

    prompt = f"""Create a {chapters}-chapter story arc for '{player.name}' (Level {player.level}).

PLAYER CONTEXT:
- Level: {player.level}
- Location: {context.get('location', 'unknown')}
- Faction Standings: {reputations_str}
- Quests Completed: {len(context.get('completed_quests', []))}

STORY ARC REQUIREMENTS:
1. Arc Type: {arc_type}
   - "personal": Character-driven narrative about player's journey
   - "faction": Storyline tied to a specific faction
   - "world": Large-scale events affecting the game world

2. Structure:
   - {chapters} chapters total
   - Each chapter has 1-2 quests
   - Difficulty should escalate with each chapter
   - Player choices should create branching paths

3. Tone: Medieval fantasy, epic and engaging

Return ONLY valid JSON matching this schema:
{{
  "arc_id": "arc_{arc_type}_{player.level}",
  "title": "Arc Title",
  "description": "Epic arc description (2-3 sentences)",
  "arc_type": "{arc_type}",
  "total_chapters": {chapters},
  "chapters": [
    {{
      "chapter_num": 1,
      "title": "Chapter 1 Title",
      "quest_ids": ["quest_ch1_part1", "quest_ch1_part2"],
      "branching_choices": ["Help the village", "Side with the faction"]
    }}
  ],
  "faction_alignment": "faction_id or null"
}}"""

    return prompt


def build_dialogue_prompt(context: Dict[str, Any]) -> str:
    """
    Generate prompt for NPC dialogue.

    Args:
        context: Rich context including NPC role, player reputation, world state

    Returns:
        Formatted prompt string for Miriel
    """

    dialogue_type = context.get('dialogue_type', 'greeting')
    reputation_tier = context.get('reputation_tier', 'Neutral')
    npc_role = context.get('npc_role', 'generic')

    world_state_items = []
    for key, value in context.get('world_state', {}).items():
        if value != 'false':  # Only mention active states
            world_state_items.append(f"- {key}: {value}")
    world_state_str = '\n'.join(world_state_items) if world_state_items else "- Normal conditions"

    active_quests = ', '.join(context.get('active_quests', [])) or 'None'

    # Dialogue type specific instructions
    type_instructions = {
        'greeting': "Generate a friendly greeting appropriate to NPC role and reputation",
        'quest_offer': "Generate dialogue offering the quest, building intrigue",
        'quest_progress': "Generate dialogue checking on quest progress, showing interest",
        'quest_complete': "Generate dialogue congratulating the player warmly",
        'quest_unavailable': "Generate dialogue explaining why no quests are available right now",
        'shop': "Generate merchant dialogue showcasing wares"
    }

    instruction = type_instructions.get(dialogue_type, "Generate appropriate NPC dialogue")

    prompt = f"""Generate NPC dialogue for a medieval fantasy game.

NPC DETAILS:
- NPC ID: {context.get('npc_id', 'unknown')}
- Role: {npc_role}
- Dialogue Type: {dialogue_type}

PLAYER CONTEXT:
- Player Name: {context.get('player_name', 'Adventurer')}
- Player Level: {context.get('player_level', 1)}
- Location: {context.get('location', 'unknown')}
- Active Quests: {active_quests}

RELATIONSHIP:
- Faction: {context.get('faction', 'None')}
- Reputation: {reputation_tier} ({context.get('reputation', 0)})

WORLD STATE:
{world_state_str}

INSTRUCTIONS:
{instruction}

REQUIREMENTS:
1. Stay in character for NPC role
2. Reflect reputation level (Hostile/Unfriendly/Neutral/Friendly/Honored)
3. Reference relevant world events if applicable
4. Keep dialogue concise (1-2 sentences)
5. Use medieval fantasy tone
6. Be specific and contextual, not generic
7. DO NOT include quest mechanics (accept/turn in) - just the dialogue

Return ONLY the dialogue text (no JSON, no quotes around the entire response, just the NPC's words):"""

    return prompt


def build_quest_offer_dialogue_prompt(
    player: Player,
    quest_name: str,
    quest_description: str,
    npc_id: str,
    context: Dict[str, Any]
) -> str:
    """
    Generate dialogue for offering a specific quest.

    This is a more specialized version of dialogue generation
    that incorporates the actual quest details.
    """

    reputation_tier = context.get('reputation_tier', 'Neutral')

    prompt = f"""Generate NPC dialogue for offering a quest.

NPC: {npc_id}
Player: {player.name} (Level {player.level})
Reputation: {reputation_tier}

QUEST TO OFFER:
Name: {quest_name}
Description: {quest_description}

INSTRUCTIONS:
1. Create engaging dialogue that introduces the quest
2. Build intrigue and urgency
3. Reflect the NPC's personality and your relationship
4. Keep it 2-3 sentences
5. Medieval fantasy tone

Return ONLY the dialogue (no JSON, no extra formatting):"""

    return prompt
