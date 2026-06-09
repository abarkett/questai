"""
Noticeboard: leave a short note at your current location for other players
to find — directions, warnings, boasts. Async multiplayer in one line.
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import add_location_note
from ...world import get_location
from ..state_view import build_action_state

MAX_NOTE_LEN = 200


def post_note(player: Player, text: str) -> ActionResponse:
    text = " ".join(text.split())
    if len(text) < 3:
        return ActionResponse(ok=False, error="Write something worth reading (3+ characters).")
    if len(text) > MAX_NOTE_LEN:
        return ActionResponse(ok=False, error=f"Notes are capped at {MAX_NOTE_LEN} characters.")

    add_location_note(
        location_id=player.location,
        player_id=player.player_id,
        player_name=player.name,
        text=text,
    )
    loc = get_location(player.location)
    return ActionResponse(
        ok=True,
        messages=[f"You leave a note at {loc.name}: “{text}”"],
        state=build_action_state(player, scene_dirty=False),
    )
