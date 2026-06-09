"""
Process-wide single-flight: collapse concurrent calls that share a key so the
expensive work (a Miriel round-trip) runs once and every caller gets the same
result. Used so a still-running background warm is awaited by a concurrent
look/move instead of firing a duplicate request.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from typing import Callable, Dict, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_inflight: Dict[str, Future] = {}


def run(key: str, fn: Callable[[], T]) -> T:
    """
    Run fn() once per key across concurrent callers. The first caller (leader)
    executes fn; others wait and receive the same result (or exception).
    """
    with _lock:
        fut = _inflight.get(key)
        leader = fut is None
        if leader:
            fut = Future()
            _inflight[key] = fut

    if not leader:
        return fut.result()  # waits for the leader; re-raises its exception

    try:
        result = fn()
        fut.set_result(result)
        return result
    except BaseException as exc:  # noqa: BLE001 - propagate to followers too
        fut.set_exception(exc)
        raise
    finally:
        with _lock:
            _inflight.pop(key, None)
