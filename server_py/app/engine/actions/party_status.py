"""
View party status — with presence (online/offline) and auto-pruning of
members who have been gone too long.
"""

from __future__ import annotations

from ...types import Player, ActionResponse
from ...db import (
    get_player_party, get_player, get_last_seen_map,
    remove_party_member, delete_party,
)
from ...presence import is_online, is_stale, ago, now_ms
from ..state_view import build_action_state


def _prune_stale(party: dict, now: int) -> list[str]:
    """Drop members gone past the stale threshold. Returns removed names."""
    seen = get_last_seen_map(party["members"])
    removed = []
    for member_id in list(party["members"]):
        if is_stale(seen.get(member_id, 0), now):
            member = get_player(member_id)
            removed.append(member.name if member else member_id)
            remove_party_member(party["party_id"], member_id)
            party["members"].remove(member_id)
    return removed


def party_status(player: Player) -> ActionResponse:
    party = get_player_party(player.player_id)
    if not party:
        return ActionResponse(
            ok=True,
            messages=["You are not in a party."],
            state=build_action_state(player),
        )

    now = now_ms()
    removed = _prune_stale(party, now)

    # If the party has collapsed to one (or zero) members, disband it.
    if len(party["members"]) <= 1:
        delete_party(party["party_id"])
        messages = ["Your party has disbanded — everyone else has been gone too long."]
        if removed:
            messages.append(f"Dropped: {', '.join(removed)}")
        return ActionResponse(ok=True, messages=messages, state=build_action_state(player))

    seen = get_last_seen_map(party["members"])
    lines = [f"Party: {party.get('name', 'Unnamed Party')}"]
    for member_id in party["members"]:
        member = get_player(member_id)
        if not member:
            continue
        ls = seen.get(member_id, 0)
        tag = "online" if is_online(ls, now) else f"offline, {ago(ls, now)}"
        leader = " (Leader)" if member_id == party["leader_id"] else ""
        lines.append(f"  {member.name}{leader} — {tag}")

    if removed:
        lines.append(f"(Dropped for inactivity: {', '.join(removed)})")

    return ActionResponse(ok=True, messages=lines, state=build_action_state(player))
