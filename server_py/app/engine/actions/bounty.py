"""
Bounties: players fund contracts on monsters; whoever lands the kill collects.
Cooperation across time — the bounty board is async multiplayer's job queue.
"""

from __future__ import annotations

import uuid

from ...types import Player, ActionResponse
from ...db import create_bounty, get_open_bounties, upsert_player
from ...bestiary import all_monster_names
from ...presence import ago
from ..state_view import build_action_state

MIN_BOUNTY = 2


def _canonical_monster_name(name: str) -> str | None:
    needle = name.strip().lower()
    for known in all_monster_names():
        if known.lower() == needle:
            return known
    return None


def post_bounty(player: Player, target: str, coins: int) -> ActionResponse:
    if coins < MIN_BOUNTY:
        return ActionResponse(ok=False, error=f"A bounty needs at least {MIN_BOUNTY} coins behind it.")
    if player.inventory.get("coin", 0) < coins:
        return ActionResponse(ok=False, error="You don't have that many coins.")

    canonical = _canonical_monster_name(target)
    if not canonical:
        return ActionResponse(ok=False, error=f"No one has ever heard of a “{target}”.")

    # Escrow the reward up front so the payout is always good.
    player.inventory["coin"] -= coins
    upsert_player(player)

    bounty_id = f"b_{uuid.uuid4().hex[:10]}"
    create_bounty(
        bounty_id=bounty_id,
        poster_id=player.player_id,
        poster_name=player.name,
        target_name=canonical,
        reward_coins=coins,
    )
    return ActionResponse(
        ok=True,
        messages=[
            f"You post a bounty: {coins} coins for the head of a {canonical}.",
            "Any other adventurer who slays one collects the reward.",
        ],
        state=build_action_state(player, scene_dirty=False),
    )


def list_bounties(player: Player) -> ActionResponse:
    bounties = get_open_bounties()
    if not bounties:
        messages = ["The bounty board is empty. Post one: bounty <coins> <monster>."]
    else:
        messages = ["Open bounties:"]
        for b in bounties:
            mine = " (yours)" if b["poster_id"] == player.player_id else ""
            messages.append(
                f"  - {b['reward_coins']} coins for a {b['target_name']}, "
                f"posted by {b['poster_name']} {ago(b['created_at'])}{mine}"
            )
    state = build_action_state(player, scene_dirty=False)
    return ActionResponse(ok=True, messages=messages, state=state)
