"""
Miriel-voiced companion banter.

Unlike location prose (which is required and fails loud), a companion's spoken
lines are *flavour*: nice when the AI is up, but never a hard dependency. So
this helper is strictly best-effort — it tries Miriel and, on anything at all
going wrong (unconfigured, network, empty answer), returns the written
fallback instead of raising. That keeps recruiting an ally working offline and
under test while still letting the AI give each companion a voice.
"""

from __future__ import annotations

from typing import Optional

from .types import Player, Companion


_OCCASION_INSTRUCTION = {
    "join": "They have just agreed to travel with the player. Give their first words as a companion.",
    "farewell": "They are parting ways with the player here. Give their goodbye.",
    "level_up": "They have just grown more loyal after winning a fight together. Give a short, warmer line.",
}


def _build_prompt(player: Player, companion: Companion, occasion: str) -> str:
    instruction = _OCCASION_INSTRUCTION.get(occasion, "Give a short line of companion banter.")
    return f"""Write one short line of spoken dialogue for a companion in a medieval fantasy game.

COMPANION:
- Name: {companion.name}
- Manner: {companion.archetype} (vanguard = bold front-line fighter, mender = caring healer, outrider = wary scout)

ADVENTURER THEY FOLLOW:
- Name: {player.name} (Level {player.level})
- Location: {player.location}

SITUATION:
{instruction}

REQUIREMENTS:
1. First person, in character, 1 sentence (no more than ~20 words).
2. Medieval fantasy tone, no modern words.
3. Return ONLY the spoken words — no quotation marks, no narration, no name prefix."""


def companion_line(
    player: Player,
    companion: Companion,
    occasion: str,
    *,
    fallback: str,
) -> str:
    """Best-effort AI line for a companion moment. Never raises; returns the
    fallback if Miriel is unavailable or gives nothing usable."""
    try:
        from .services.miriel_client import get_miriel_client, extract_answer

        client = get_miriel_client()
        if not client.enabled:
            return fallback

        resp = client.query(
            query=_build_prompt(player, companion, occasion),
            project="questai",
            force_exhaustive=False,
        )
        if not resp:
            return fallback
        text = (extract_answer(resp) or "").strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()
        return text or fallback
    except Exception as e:  # flavour must never break the action
        print(f"[MIRIEL] companion line failed: {e}")
        return fallback
