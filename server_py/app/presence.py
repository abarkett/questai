"""
Player presence helpers. A player is "online" if they've acted recently;
party members who have been gone far longer are pruned so stale groups (e.g.
an alt you haven't logged into in months) don't linger forever.
"""

from __future__ import annotations

import time

ONLINE_WINDOW_MS = 5 * 60 * 1000          # active within 5 min => online
STALE_PARTY_MS = 14 * 24 * 3600 * 1000    # gone >14 days => dropped from party


def now_ms() -> int:
    return int(time.time() * 1000)


def is_online(last_seen: int, now: int | None = None) -> bool:
    if not last_seen:
        return False
    return (now or now_ms()) - last_seen <= ONLINE_WINDOW_MS


def is_stale(last_seen: int, now: int | None = None) -> bool:
    """True if a member has been gone long enough to drop from a party."""
    if not last_seen:
        return False  # never-seen / brand-new: don't prune
    return (now or now_ms()) - last_seen > STALE_PARTY_MS


def ago(last_seen: int, now: int | None = None) -> str:
    if not last_seen:
        return "unknown"
    secs = max(0, ((now or now_ms()) - last_seen) // 1000)
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"
