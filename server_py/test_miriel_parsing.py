"""
Tests for the tolerant Miriel answer extractor: live API versions have moved
the answer text around inside the response; extract_answer must find it
wherever it reasonably lives, and describe_shape must make failures legible.

Run from server_py/:  python3 test_miriel_parsing.py
"""

from app.services.miriel_client import extract_answer, describe_shape


def main() -> None:
    # Canonical shape (and what the test responder emits).
    assert extract_answer({"results": {"answer": "Prose."}}) == "Prose."
    print("PASS  canonical {results: {answer}} shape")

    # Live-API variants: the answer nested deeper inside results.
    assert extract_answer(
        {"results": {"query_response": {"answer": "Deep prose."}}, "results_diff": {}}
    ) == "Deep prose."
    assert extract_answer(
        {"results": [{"meta": 1}, {"answer": "Listed prose."}], "results_diff": []}
    ) == "Listed prose."
    print("PASS  nested and list-shaped results")

    # Key priority: 'answer' anywhere beats generic 'text'/'response' keys.
    assert extract_answer(
        {"results": {"text": "wrong", "inner": {"answer": "right"}}}
    ) == "right"
    # ...but generic keys are used when no 'answer' exists at all — gated on
    # length so status strings can't masquerade as prose.
    assert extract_answer(
        {"results": {"response": "A long line of genuine fallback prose."}}
    ) == "A long line of genuine fallback prose."
    assert extract_answer({"results": {"message": "success", "status": "ok"}}) == ""
    print("PASS  'answer' outranks generic keys; generic keys still rescue")

    # Whitespace-only and missing text yield "" (callers fail hard on it).
    assert extract_answer({"results": {"answer": "   "}}) == ""
    assert extract_answer({"results": {"chunks": [1, 2]}, "results_diff": {}}) == ""
    assert extract_answer(None) == ""
    assert extract_answer("just a string") == ""
    print("PASS  unusable responses yield empty (loud failure upstream)")

    # Shape descriptions are compact and reveal nesting for error logs.
    shape = describe_shape({"results": {"chunks": [{"id": 1}]}, "results_diff": {}})
    assert "results" in shape and "chunks" in shape, shape
    print(f"PASS  describe_shape is legible: {shape}")

    print("\nALL MIRIEL PARSING TESTS PASSED")


if __name__ == "__main__":
    main()
