"""
The personal stronghold: a place of your own that grows with your wealth.

Where the rest of the world is shared, your stronghold is yours alone. It gives
a long-horizon home for the coin and loot a casual player piles up:

  * **Tiers** — pour coin into it to raise it from a Campsite to a Citadel; each
    tier is a visible step forward that's *yours*, and a reason to come back.
  * **A stash** — store items out of your pack; higher tiers hold more. The one
    place to keep raid trophies, spare gear, and overflow safe.
  * **Tribute** — a built stronghold earns a trickle of coin while you're away,
    capped so it rewards returning, not idling. Claimed when you check in.

All of it is personal bookkeeping — no AI, no shared-world effect — so none of
it costs action points. Code is the referee; there's nothing here to voice.
"""

from __future__ import annotations

import time
from typing import List, Optional

from .types import Player, ActionResponse
from .db import upsert_player

MAX_LEVEL = 5

TIER_NAMES = {
    0: "open ground",
    1: "Campsite",
    2: "Cabin",
    3: "Cottage",
    4: "Keep",
    5: "Citadel",
}

# Coin to reach each level from the one below. Escalates hard — this is meant to
# be a sink that outlasts the early game.
UPGRADE_COST = {1: 50, 2: 150, 3: 400, 4: 1000, 5: 2500}

# Distinct item types the stash can hold at each tier (stacks are unlimited).
STASH_SLOTS = {0: 0, 1: 6, 2: 10, 3: 16, 4: 24, 5: 40}

# Coin earned per real-time hour, by tier, and the cap (in hours) it accrues to.
TRIBUTE_PER_HOUR = {0: 0, 1: 2, 2: 5, 3: 10, 4: 20, 5: 40}
TRIBUTE_CAP_HOURS = 24


def now_ms() -> int:
    return int(time.time() * 1000)


def tier_name(level: int) -> str:
    return TIER_NAMES.get(level, "Stronghold")


def stash_capacity(level: int) -> int:
    return STASH_SLOTS.get(level, 0)


def next_cost(level: int) -> Optional[int]:
    return UPGRADE_COST.get(level + 1)


def accrued_tribute(player: Player, now: Optional[int] = None) -> int:
    """Coin waiting to be collected, from tier and time since the last claim."""
    if player.stronghold_level <= 0 or not player.stronghold_collected_at:
        return 0
    now = now or now_ms()
    per_hour = TRIBUTE_PER_HOUR.get(player.stronghold_level, 0)
    if per_hour <= 0:
        return 0
    hours = (now - player.stronghold_collected_at) / (3600 * 1000)
    hours = min(hours, TRIBUTE_CAP_HOURS)
    return int(per_hour * hours)


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _display(item_id: str) -> str:
    from .items import get_item
    it = get_item(item_id)
    return it.name if it else item_id


def _state(player: Player) -> ActionResponse:
    from .engine.state_view import build_action_state
    return build_action_state(player, scene_dirty=False)


# -------------------------------------------------
# Actions
# -------------------------------------------------

def build(player: Player) -> ActionResponse:
    """Found or upgrade the stronghold by one tier."""
    from .engine.state_view import build_action_state

    if player.stronghold_level >= MAX_LEVEL:
        return ActionResponse(
            ok=False,
            error=f"Your {tier_name(MAX_LEVEL)} is as grand as it gets. There is nothing left to raise.",
        )

    cost = next_cost(player.stronghold_level)
    coins = player.inventory.get("coin", 0)
    if coins < cost:
        return ActionResponse(
            ok=False,
            error=(
                f"Raising your holding to a {tier_name(player.stronghold_level + 1)} "
                f"costs {cost} coins — you have {coins}."
            ),
        )

    player.inventory["coin"] = coins - cost
    was = player.stronghold_level
    player.stronghold_level += 1
    # Tribute starts accruing the moment the stronghold first exists.
    if was == 0:
        player.stronghold_collected_at = now_ms()

    upsert_player(player)
    name = tier_name(player.stronghold_level)
    msg = (
        f"You found a Campsite — a place of your own at last."
        if was == 0 else
        f"Your holding rises into a {name}."
    )
    extra = f" It can stash {stash_capacity(player.stronghold_level)} kinds of goods."
    return ActionResponse(
        ok=True,
        messages=[msg + extra],
        state=build_action_state(player, scene_dirty=False),
    )


def deposit(player: Player, item_name: str, qty: Optional[int]) -> ActionResponse:
    from .engine.state_view import build_action_state

    if player.stronghold_level <= 0:
        return ActionResponse(ok=False, error="You have nowhere to store that. `build` a stronghold first.")

    key = _norm(item_name)
    if key == "coin":
        return ActionResponse(ok=False, error="Coin doesn't go in the stash — it funds the `build` and earns you tribute.")
    have = player.inventory.get(key, 0)
    if have <= 0:
        return ActionResponse(ok=False, error=f"You aren't carrying any {_display(key)}.")

    move = have if qty is None else min(qty, have)
    if move <= 0:
        return ActionResponse(ok=False, error="Store how many?")

    # A new kind of item needs a free slot; topping up an existing stack is free.
    if key not in player.stash and len(player.stash) >= stash_capacity(player.stronghold_level):
        return ActionResponse(
            ok=False,
            error=(
                f"Your {tier_name(player.stronghold_level)} stash is full "
                f"({stash_capacity(player.stronghold_level)} kinds). Upgrade it, or withdraw something first."
            ),
        )

    player.inventory[key] = have - move
    if player.inventory[key] <= 0:
        del player.inventory[key]
    player.stash[key] = player.stash.get(key, 0) + move

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"Stored {move}x {_display(key)}. ({len(player.stash)}/{stash_capacity(player.stronghold_level)} kinds in the stash.)"],
        state=build_action_state(player, scene_dirty=False),
    )


def withdraw(player: Player, item_name: str, qty: Optional[int]) -> ActionResponse:
    from .engine.state_view import build_action_state

    if player.stronghold_level <= 0:
        return ActionResponse(ok=False, error="You have no stash to draw from.")

    key = _norm(item_name)
    have = player.stash.get(key, 0)
    if have <= 0:
        return ActionResponse(ok=False, error=f"There's no {_display(key)} in your stash.")

    move = have if qty is None else min(qty, have)
    if move <= 0:
        return ActionResponse(ok=False, error="Withdraw how many?")

    player.stash[key] = have - move
    if player.stash[key] <= 0:
        del player.stash[key]
    player.inventory[key] = player.inventory.get(key, 0) + move

    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"Withdrew {move}x {_display(key)}."],
        state=build_action_state(player, scene_dirty=False),
    )


def collect(player: Player) -> ActionResponse:
    from .engine.state_view import build_action_state

    if player.stronghold_level <= 0:
        return ActionResponse(ok=False, error="You have no stronghold to draw tribute from.")

    amount = accrued_tribute(player)
    player.stronghold_collected_at = now_ms()
    if amount <= 0:
        upsert_player(player)
        return ActionResponse(
            ok=True,
            messages=["No tribute has gathered yet. Come back later."],
            state=build_action_state(player, scene_dirty=False),
        )

    player.inventory["coin"] = player.inventory.get("coin", 0) + amount
    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[f"Your {tier_name(player.stronghold_level)} yields {amount} coins in tribute."],
        state=build_action_state(player, scene_dirty=False),
    )


def status(player: Player) -> ActionResponse:
    from .engine.state_view import build_action_state

    if player.stronghold_level <= 0:
        messages = [
            "You hold no ground of your own yet.",
            f"`build` a Campsite for {UPGRADE_COST[1]} coins — a stash, a tribute, and a place to grow.",
        ]
        return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=False))

    lvl = player.stronghold_level
    messages = [f"Your stronghold: a {tier_name(lvl)} (tier {lvl}/{MAX_LEVEL})."]

    cost = next_cost(lvl)
    if cost is not None:
        messages.append(f"`build` to raise it to a {tier_name(lvl + 1)} for {cost} coins.")
    else:
        messages.append("It stands as grand as it gets.")

    tribute = accrued_tribute(player)
    rate = TRIBUTE_PER_HOUR.get(lvl, 0)
    messages.append(f"Tribute waiting: {tribute} coins ({rate}/hr, caps at {TRIBUTE_CAP_HOURS}h). `collect` it.")

    cap = stash_capacity(lvl)
    if player.stash:
        items = ", ".join(f"{qty}x {_display(k)}" for k, qty in player.stash.items())
        messages.append(f"Stash ({len(player.stash)}/{cap} kinds): {items}")
    else:
        messages.append(f"Stash is empty ({cap} kinds of room). `stash <item>` to store something.")

    return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=False))


def summary(player: Player) -> Optional[dict]:
    """Compact stronghold state for the web client (None if not yet founded)."""
    if player.stronghold_level <= 0:
        return {
            "level": 0,
            "tier": tier_name(0),
            "next_cost": UPGRADE_COST[1],
        }
    lvl = player.stronghold_level
    return {
        "level": lvl,
        "tier": tier_name(lvl),
        "next_cost": next_cost(lvl),
        "next_tier": tier_name(lvl + 1) if next_cost(lvl) else None,
        "tribute": accrued_tribute(player),
        "stash": dict(player.stash),
        "stash_cap": stash_capacity(lvl),
    }
