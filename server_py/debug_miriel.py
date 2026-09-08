"""
Print the raw Miriel query response, so response-shape issues are diagnosable
at a glance instead of guessed at.

Run from server_py/ (with MIRIEL_API_KEY in .env):  python3 debug_miriel.py
Paste the output when reporting prose problems.
"""

from __future__ import annotations

import json

from dotenv import load_dotenv

load_dotenv()

from app.services.miriel_client import (  # noqa: E402
    get_miriel_client,
    is_miriel_enabled,
    extract_answer,
    describe_shape,
)


def _truncate(node, max_str=160):
    if isinstance(node, dict):
        return {k: _truncate(v, max_str) for k, v in node.items()}
    if isinstance(node, list):
        out = [_truncate(v, max_str) for v in node[:5]]
        if len(node) > 5:
            out.append(f"... (+{len(node) - 5} more)")
        return out
    if isinstance(node, str) and len(node) > max_str:
        return node[:max_str] + f"... (+{len(node) - max_str} chars)"
    return node


def main() -> None:
    print(f"Miriel enabled: {is_miriel_enabled()}")
    if not is_miriel_enabled():
        print("Set MIRIEL_API_KEY in .env first.")
        return

    client = get_miriel_client()
    query = (
        "In 1-2 vivid sentences, describe this fantasy RPG location as the "
        "player sees it right now. Location: Town Square. A cobblestone "
        "plaza with a fountain. Time of day: dusk. No creatures are present."
    )
    print(f"\nQuery: {query[:80]}...")
    resp = client.query(query=query, project="questai")

    print("\n--- response shape ---")
    print(describe_shape(resp, depth=5))

    print("\n--- full response (long strings truncated) ---")
    print(json.dumps(_truncate(resp), indent=2, default=str)[:4000])

    answer = extract_answer(resp)
    print("\n--- extract_answer result ---")
    print(repr(answer[:300]) if answer else "(nothing extracted — paste all of the above)")


if __name__ == "__main__":
    main()
