"""
Process-wide background warmer.

A tiny prioritised job queue served by a few daemon threads. Everything that
pre-generates AI assets ahead of need (neighbor scenes, combat-variant scenes,
location prose, NPC dialogue) is submitted here so that:

  * it runs *on the server*, shared by every player, instead of in one
    browser tab that caps concurrent connections and forgets on reload;
  * identical work is never queued twice (jobs are keyed);
  * the most likely next need (the rooms next door) is served first;
  * a slow or failing job can never hurt a player's request — jobs are
    best-effort and every exception is swallowed and logged.

Tests set ``SYNC = True`` to run submitted jobs inline on the calling thread,
which makes warming deterministic and observable without sleeping.
"""

from __future__ import annotations

import itertools
import os
import queue
import threading
import traceback
from typing import Callable, Optional, Set

# Run jobs inline instead of on worker threads (tests / debugging).
SYNC = False

DEFAULT_WORKERS = 3

_lock = threading.Lock()
_queue: "queue.PriorityQueue[tuple[int, int, str, Callable[[], object]]]" = queue.PriorityQueue()
_pending: Set[str] = set()      # job keys queued or running
_workers: list[threading.Thread] = []
_seq = itertools.count()


def worker_count() -> int:
    try:
        return max(1, int(os.getenv("QUESTAI_WARM_WORKERS", str(DEFAULT_WORKERS))))
    except ValueError:
        return DEFAULT_WORKERS


def _run_job(key: str, fn: Callable[[], object]) -> None:
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - warming is best-effort by design
        print(f"[WARM] {key} failed: {e}")
        if os.getenv("QUESTAI_WARM_DEBUG"):
            traceback.print_exc()
    finally:
        with _lock:
            _pending.discard(key)


def _worker_loop() -> None:
    while True:
        _prio, _n, key, fn = _queue.get()
        try:
            _run_job(key, fn)
        finally:
            _queue.task_done()


def _ensure_workers() -> None:
    # Called with _lock held.
    want = worker_count()
    while len(_workers) < want:
        t = threading.Thread(
            target=_worker_loop, name=f"warmer-{len(_workers)}", daemon=True
        )
        t.start()
        _workers.append(t)


def submit(key: str, fn: Callable[[], object], *, priority: int = 5) -> bool:
    """
    Queue ``fn`` under ``key`` unless an identical job is already queued or
    running. Lower ``priority`` runs first. Returns True if the job was
    accepted. Never raises.
    """
    with _lock:
        if key in _pending:
            return False
        _pending.add(key)
        if SYNC:
            inline = True
        else:
            inline = False
            _queue.put((priority, next(_seq), key, fn))
            _ensure_workers()
    if inline:
        _run_job(key, fn)
    return True


def is_pending(key: str) -> bool:
    with _lock:
        return key in _pending


def pending_count() -> int:
    with _lock:
        return len(_pending)


def wait_idle(timeout: Optional[float] = None) -> bool:
    """Block until every queued job has finished (tests). True if it did."""
    if SYNC:
        return True
    done = threading.Event()

    def _poll() -> None:
        _queue.join()
        done.set()

    threading.Thread(target=_poll, daemon=True).start()
    return done.wait(timeout)
