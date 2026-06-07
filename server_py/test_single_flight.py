"""
Tests for single-flight dedup: concurrent identical work runs once and all
callers share the result; and the Miriel client single-flights identical
concurrent queries (so a background warm + a real look share one round-trip).

Run from server_py/:  python3 test_single_flight.py
"""

import os
import tempfile
import threading
import time

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.single_flight import run as single_flight  # noqa: E402
from app.services.miriel_client import install_test_responder, get_miriel_client  # noqa: E402


def main() -> None:
    # 1) Concurrent calls with the same key run fn once; all get the same result.
    calls = []
    lock = threading.Lock()

    def fn():
        with lock:
            calls.append(1)
        time.sleep(0.15)  # hold the flight open so others pile on
        return "RESULT"

    results: list = []

    def worker():
        results.append(single_flight("k", fn))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["RESULT"] * 6, results
    assert len(calls) == 1, ("fn must run once for concurrent same-key calls", len(calls))

    # A different key runs separately; and after completion the key is fresh again.
    single_flight("other", fn)
    assert len(calls) == 2
    single_flight("k", fn)
    assert len(calls) == 3
    print("PASS  single_flight: one execution per concurrent key; fresh after done")

    # Exceptions propagate to every waiting caller.
    def boom():
        time.sleep(0.05)
        raise ValueError("nope")

    errs: list = []

    def eworker():
        try:
            single_flight("err", boom)
        except ValueError:
            errs.append(1)

    ts = [threading.Thread(target=eworker) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(errs) == 4, errs
    print("PASS  single_flight: exception reaches all waiters")

    # 2) Miriel client single-flights identical concurrent queries.
    query_calls = []

    def slow_responder(q):
        with lock:
            query_calls.append(q)
        time.sleep(0.15)
        return "AI text for: " + q

    install_test_responder(slow_responder)
    get_miriel_client().enabled = True
    client = get_miriel_client()

    answers: list = []

    def qworker():
        answers.append(client.query(query="describe the forest", project="questai"))

    qts = [threading.Thread(target=qworker) for _ in range(5)]
    for t in qts:
        t.start()
    for t in qts:
        t.join()
    assert all(a["results"]["answer"] == "AI text for: describe the forest" for a in answers), answers
    assert len(query_calls) == 1, ("identical concurrent queries must collapse to one", len(query_calls))

    # A different query is a separate flight.
    client.query(query="describe the cavern", project="questai")
    assert len(query_calls) == 2
    install_test_responder(None)
    print("PASS  client single-flights identical concurrent queries")

    print("\nALL SINGLE-FLIGHT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
