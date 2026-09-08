"""
Plain-text rendering: the canonical low-bandwidth view of the game.

Every action result must be playable as short plain text — the web client is
a rich view over the same content, and the SMS skin is just this renderer
behind a phone number. Keeping this path first-class is what keeps the game
honest about being playable anywhere.
"""

from __future__ import annotations

from .types import ActionResponse, Player

# Comfortable for a long SMS (3 concatenated segments) while staying cheap.
MAX_SMS_CHARS = 440


def status_suffix(player: Player | None) -> str:
    if not player:
        return ""
    from .action_points import ap_enabled, ap_max

    parts = [f"HP {player.hp}/{player.max_hp}"]
    if ap_enabled():
        parts.append(f"AP {player.action_points}/{ap_max()}")
    return " [" + " ".join(parts) + "]"


def render_plain(result: ActionResponse, *, player: Player | None = None,
                 max_chars: int = MAX_SMS_CHARS) -> str:
    """One compact plain-text message for an action result."""
    if not result.ok:
        text = result.error or "That didn't work."
    else:
        # Collapse the message list into flowing text; drop blank lines.
        lines = [m.strip() for m in result.messages if m and m.strip()]
        text = " ".join(lines) if lines else "Done."

    suffix = status_suffix(player) if result.ok else ""
    budget = max_chars - len(suffix)
    if len(text) > budget:
        text = text[: budget - 1].rstrip() + "…"
    return text + suffix
