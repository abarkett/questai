"""
Community goals: the shared-spectacle spine of the living world.

A server-wide objective ("cull 100 monsters before the Blight spreads") that
every player's ordinary play chips away at. On completion the world visibly
changes (world-state effects), every contributor is paid, and the event enters
the world's history — echoes, recaps, and Miriel context all see it.

Goals rotate: when one ends, the next seasonal goal seeds itself, so the
shared world always has a heartbeat. Low individual commitment, high
collective drama — built for a universe of casual, mostly-offline players.
"""

from __future__ import annotations

import time
from typing import List, Optional

from .db import (
    create_world_goal,
    get_active_world_goals,
    increment_world_goal,
    complete_world_goal,
    expire_world_goal,
    get_goal_contributions,
    get_goal_contribution,
    count_world_goals,
    get_player,
    upsert_player,
    set_world_state,
    log_world_event,
)
from .types import Player

GOAL_DURATION_MS = 7 * 24 * 60 * 60 * 1000  # one week per season

# Rotation of seasonal goals. `target_name=None` means any monster counts.
SEASONAL_GOALS = [
    {
        "name": "The Blight",
        "description": (
            "A creeping blight drives the wilds mad. Cull the monsters "
            "before it takes root."
        ),
        "kind": "kill_count",
        "target_name": None,
        "required": 100,
        "reward_coins": 20,
        "effect": {"blight_cleansed": "true"},
        "completion_text": "The Blight recedes! The wilds breathe easy again.",
    },
    {
        "name": "Vermin Tide",
        "description": "Rats pour from every cellar and hollow. Turn the tide.",
        "kind": "kill_count",
        "target_name": "Rat",
        "required": 25,
        "reward_coins": 15,
        "effect": {"vermin_tide_broken": "true"},
        "completion_text": "The Vermin Tide breaks! The town sleeps soundly tonight.",
    },
    {
        "name": "Embers Below",
        "description": (
            "The deep places stir and burn. Beat the fire back, blade by blade."
        ),
        "kind": "kill_count",
        "target_name": None,
        "required": 150,
        "reward_coins": 30,
        "effect": {"embers_quelled": "true"},
        "completion_text": "The Embers Below are quelled. The deep grows quiet.",
    },
]


def now_ms() -> int:
    return int(time.time() * 1000)


def _seed_goal(index: int) -> None:
    spec = SEASONAL_GOALS[index % len(SEASONAL_GOALS)]
    goal_id = f"goal_{index}"
    create_world_goal(
        goal_id=goal_id,
        name=spec["name"],
        description=spec["description"],
        kind=spec["kind"],
        target_name=spec["target_name"],
        required=spec["required"],
        reward_coins=spec["reward_coins"],
        expires_at=now_ms() + GOAL_DURATION_MS,
        effect=spec["effect"],
    )
    log_world_event(
        event_type="goal_started",
        location_id=None,
        data={"goal_id": goal_id, "description": f"A new season begins: {spec['name']} — {spec['description']}"},
    )


def ensure_active_goal() -> None:
    """Seed the next seasonal goal whenever none is running."""
    if not get_active_world_goals():
        _seed_goal(count_world_goals())


def _completion_text(goal: dict) -> str:
    for spec in SEASONAL_GOALS:
        if spec["name"] == goal["name"]:
            return spec["completion_text"]
    return f"{goal['name']} is complete!"


def _payout(goal: dict, killer: Player) -> List[str]:
    """Pay every contributor; the killer is mutated in-memory (caller persists)."""
    messages: List[str] = []
    reward = int(goal.get("reward_coins") or 0)
    if reward <= 0:
        return messages
    for contrib in get_goal_contributions(goal["goal_id"]):
        if contrib["player_id"] == killer.player_id:
            killer.inventory["coin"] = killer.inventory.get("coin", 0) + reward
            messages.append(f"Your part in {goal['name']} earns you {reward} coins.")
            continue
        p = get_player(contrib["player_id"])
        if p:
            p.inventory["coin"] = p.inventory.get("coin", 0) + reward
            upsert_player(p)
    return messages


def record_kill_progress(player: Player, monster_name: str) -> List[str]:
    """Advance any matching community goals by one kill."""
    messages: List[str] = []
    for goal in get_active_world_goals():
        if goal["kind"] != "kill_count":
            continue
        if goal["target_name"] and goal["target_name"].lower() != monster_name.lower():
            continue

        if goal.get("expires_at") and now_ms() > goal["expires_at"]:
            if expire_world_goal(goal["goal_id"]):
                log_world_event(
                    event_type="goal_expired",
                    location_id=None,
                    data={
                        "goal_id": goal["goal_id"],
                        "description": f"{goal['name']} passed unanswered. The world remembers.",
                    },
                )
            continue

        updated = increment_world_goal(goal["goal_id"], player.player_id, player.name)
        if not updated:
            continue
        messages.append(f"({updated['name']}: {min(updated['progress'], updated['required'])}/{updated['required']})")

        if updated["progress"] >= updated["required"] and complete_world_goal(goal["goal_id"]):
            for key, value in (updated.get("effect") or {}).items():
                set_world_state(key, value)
            text = _completion_text(updated)
            log_world_event(
                event_type="goal_completed",
                location_id=None,
                data={
                    "goal_id": updated["goal_id"],
                    "description": f"{text} (Final blow: {player.name}.)",
                },
            )
            messages.append(text)
            messages.append(f"You struck the final blow of {updated['name']}!")
            messages.extend(_payout(updated, player))

    # Keep the world's heartbeat going.
    ensure_active_goal()
    return messages


def goals_overview(player: Player) -> List[str]:
    """Player-facing summary of the running goals."""
    ensure_active_goal()
    goals = get_active_world_goals()
    if not goals:
        return ["The world is quiet. A new season will begin soon."]
    lines: List[str] = []
    for goal in goals:
        pct = min(100, 100 * goal["progress"] // max(1, goal["required"]))
        days_left = ""
        if goal.get("expires_at"):
            remaining = max(0, goal["expires_at"] - now_ms())
            days_left = f", {remaining // (24*3600*1000)}d left"
        lines.append(f"{goal['name']} — {goal['description']}")
        lines.append(
            f"  Progress: {goal['progress']}/{goal['required']} ({pct}%){days_left}. "
            f"Your part: {get_goal_contribution(goal['goal_id'], player.player_id)}. "
            f"Reward: {goal['reward_coins']} coins per contributor."
        )
    return lines
