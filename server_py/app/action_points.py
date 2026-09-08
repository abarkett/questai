"""
Action-point (AP) economy: the casual-play keystone.

Every world-changing action costs AP; AP regenerates in real time up to a cap.
Short sessions are the intended play pattern: nobody can no-life their way to
dominance in the shared universe, every player gets the same action budget,
and AI generation costs are naturally bounded per player.

AP regenerates lazily — it is recomputed from `ap_updated_at` whenever the
player acts, so no background process is needed and the model works the same
over web, CLI, or SMS.

Tunables come from the environment so ops (and tests) can adjust them:
  QUESTAI_AP_MAX            cap (default 30)
  QUESTAI_AP_REGEN_SECONDS  seconds per point (default 180; <= 0 disables AP)
"""

from __future__ import annotations

import os
import time

from .types import Player


def ap_max() -> int:
    try:
        return max(1, int(os.getenv("QUESTAI_AP_MAX", "30")))
    except ValueError:
        return 30


def ap_regen_seconds() -> int:
    try:
        return int(os.getenv("QUESTAI_AP_REGEN_SECONDS", "180"))
    except ValueError:
        return 180


def ap_enabled() -> bool:
    return ap_regen_seconds() > 0


def now_ms() -> int:
    return int(time.time() * 1000)


def refill(player: Player, now: int | None = None) -> None:
    """Accrue any AP earned since the player last acted (lazy regen)."""
    if not ap_enabled():
        return
    now = now or now_ms()
    cap = ap_max()
    if player.ap_updated_at is None:
        # First contact with the AP system (new player or migrated save):
        # start with a full bar.
        player.action_points = cap
        player.ap_updated_at = now
        return
    if player.action_points >= cap:
        player.ap_updated_at = now
        return
    regen_ms = ap_regen_seconds() * 1000
    earned = (now - player.ap_updated_at) // regen_ms
    if earned > 0:
        player.action_points = min(cap, player.action_points + int(earned))
        # Keep the remainder so partial progress toward the next point isn't lost.
        player.ap_updated_at += int(earned) * regen_ms
        if player.action_points >= cap:
            player.ap_updated_at = now


def spend(player: Player, cost: int = 1) -> bool:
    """Spend AP if available. Returns False (and charges nothing) if short."""
    if not ap_enabled() or cost <= 0:
        return True
    if player.action_points < cost:
        return False
    if player.action_points >= ap_max():
        # Start the regen clock the moment the bar dips below full.
        player.ap_updated_at = now_ms()
    player.action_points -= cost
    return True


def seconds_to_next_ap(player: Player, now: int | None = None) -> int:
    """Seconds until the next point lands (0 when full or AP disabled)."""
    if not ap_enabled() or player.action_points >= ap_max():
        return 0
    now = now or now_ms()
    regen_ms = ap_regen_seconds() * 1000
    elapsed = now - (player.ap_updated_at or now)
    return max(0, (regen_ms - elapsed % regen_ms) // 1000)


def status_line(player: Player) -> str:
    return f"AP: {player.action_points}/{ap_max()}"
