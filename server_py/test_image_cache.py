"""
Offline tests for the scene image endpoint + persistent cache.

Exercises everything except the live Gemini render (which needs an API key):
  - no API key configured -> graceful 503, nothing cached
  - a seeded cache entry -> served from DB as cached=True (no Gemini call)
  - a distinct prompt -> distinct key -> miss again

Run from server_py/:  python3 test_image_cache.py
"""

import hashlib
import os
import tempfile

import app.db as db

# Isolate the DB so we never touch the real game.sqlite.
_tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp.close()
db.DB_PATH = _tmp.name

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

# Ensure the no-key branches are what we test first.
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("MIRIEL_API_KEY", None)

from app.services.image_gen import enrich_scene_prompt  # noqa: E402

PROMPT = "Fantasy RPG scene illustration of a quiet town square at dusk."
KEY = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()


def main() -> None:
    with TestClient(app) as client:  # triggers startup -> init_db()
        # 1) Miss with no key -> 503, and nothing persisted.
        r = client.post("/api/ai/image", json={"prompt": PROMPT})
        assert r.status_code == 503, (r.status_code, r.text)
        assert db.get_cached_scene_image(KEY) is None
        print("PASS  no-key miss -> 503, no cache write")

        # 2) Seed the persistent cache; same prompt now served from DB.
        db.cache_scene_image(KEY, PROMPT, "data:image/png;base64,SEEDED", "test-model")
        r = client.post("/api/ai/image", json={"prompt": PROMPT})
        assert r.status_code == 200, (r.status_code, r.text)
        body = r.json()
        assert body["cached"] is True, body
        assert body["image"].endswith("SEEDED"), body
        print("PASS  cache hit -> 200 cached=True, no Gemini call")

        # 3) Distinct prompt -> distinct key -> miss again (still no key).
        r = client.post("/api/ai/image", json={"prompt": PROMPT + " with a dragon overhead"})
        assert r.status_code == 503, (r.status_code, r.text)
        print("PASS  distinct prompt -> distinct key -> 503")

    # 4) Miriel enrichment degrades to the base prompt unchanged when disabled.
    assert enrich_scene_prompt(PROMPT) == PROMPT
    print("PASS  prompt enrichment no-ops gracefully when Miriel is off")

    print("\nALL IMAGE CACHE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_tmp.name)
