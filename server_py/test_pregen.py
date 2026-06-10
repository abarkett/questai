"""
Tests for mint-time pre-generation (Miriel prose + scene images) and the
per-region world rules installed by region minting.

Run from server_py/:  python3 test_pregen.py
"""

import hashlib
import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_monsters_at, remove_monster, get_world_state  # noqa: E402
from app.scene_prompts import build_scene_prompt, scene_prompt_for_location  # noqa: E402
from app.pregen import pregenerate_region_assets  # noqa: E402
from app.engine.actions.explore import explore  # noqa: E402
from app.services.miriel_client import install_test_responder, get_miriel_client  # noqa: E402
from app.services import image_gen  # noqa: E402
from app.world_rules import evaluate_db_rules  # noqa: E402


def main() -> None:
    # --- Prompt parity fixture ---
    # Byte-identical output of web/src/app/lib/scene.ts buildScenePrompt for the
    # same inputs (verified against the real TS via node). If this assertion
    # breaks, scene.ts and scene_prompts.py have drifted apart.
    prompt = build_scene_prompt("Empty Hall", "Quiet.", [])
    assert prompt.startswith("Fantasy RPG scene illustration.")
    assert "No creatures or people are present; depict the empty location." in prompt
    assert hashlib.sha256(prompt.encode()).hexdigest() == (
        "35a14013a7156efd74672ae97eafccdd2a533486e64ad41d9e3cb0a43b8640a5"
    ), "scene_prompts.py no longer matches web/src/app/lib/scene.ts"
    print("PASS  python prompt builder matches the TS client byte-for-byte")

    # --- Stub the AI services so warming is observable offline ---
    get_miriel_client().enabled = True
    install_test_responder(lambda q: "Stubbed prose for a freshly minted place.")

    rendered = []

    def fake_render(p):
        rendered.append(p)
        return "data:image/png;base64,FAKE"

    real_enabled, real_render = image_gen.image_gen_enabled, image_gen.generate_scene_image
    image_gen.image_gen_enabled = lambda: True
    image_gen.generate_scene_image = fake_render

    try:
        # Minting a region (explore) warms its assets. Run the warmer
        # synchronously afterwards too, so the test never races the thread.
        scout = Player(player_id="scout", name="Scout", location="riverside",
                       level=3, xp=0, hp=30, max_hp=30)
        upsert_player(scout)
        r = explore(scout)
        assert r.ok, r.error
        region = db.get_region_by_origin("riverside")
        spec_locs = [l for l in db.get_all_gen_locations()
                     if l["region_id"] == region["region_id"]]
        assert spec_locs

        pregenerate_region_assets(
            {"region_id": region["region_id"],
             "locations": [{"location_id": l["location_id"]} for l in spec_locs]},
            background=False,
        )

        # Every region location has a cached scene image under the exact key
        # the web client will compute.
        for l in spec_locs:
            client_prompt = scene_prompt_for_location(l["location_id"])
            key = hashlib.sha256(client_prompt.encode("utf-8")).hexdigest()
            assert db.get_cached_scene_image(key), f"no warmed scene for {l['location_id']}"
        print(f"PASS  {len(spec_locs)} scene images pre-rendered under client cache keys")

        # Warming is idempotent: a second pass renders nothing new.
        before = len(rendered)
        pregenerate_region_assets(
            {"region_id": region["region_id"],
             "locations": [{"location_id": l["location_id"]} for l in spec_locs]},
            background=False,
        )
        assert len(rendered) == before, "cached scenes must not re-render"
        print("PASS  warming is idempotent (cache hits skip rendering)")

        # Miriel prose was cached for the entry room (look will hit the cache).
        from app.descriptions import describe
        from app.world import get_location
        install_test_responder(lambda q: (_ for _ in ()).throw(RuntimeError("must not be called")))
        loc = get_location(region["entry_location"])
        from app.engine.entities import get_entities_at
        from app.engine.state_view import effective_description
        text = describe(None, loc, get_entities_at(loc.id),
                        effective_description(loc), db.get_world_turn())
        assert "Stubbed prose" in text, text
        print("PASS  location prose pre-cached (look is a cache hit)")
    finally:
        image_gen.image_gen_enabled = real_enabled
        image_gen.generate_scene_image = real_render
        install_test_responder(None)
        get_miriel_client().enabled = False

    # --- Per-region world rules ---
    rules = {r["rule_id"]: r for r in db.get_enabled_world_rules()}
    rid = region["region_id"]
    assert f"{rid}_cleared" in rules and f"{rid}_resurgence" in rules, rules.keys()
    print("PASS  minting installs cleared + resurgence rules for the region")

    # Clear every room -> the 'falls quiet' rule fires once.
    for l in spec_locs:
        for m in get_monsters_at(l["location_id"]):
            remove_monster(m["instance_id"])
    triggered = evaluate_db_rules()
    assert any("Falls Quiet" in t for t in triggered), triggered
    assert get_world_state(f"{rid}_cleared") == "true"
    assert not any("Falls Quiet" in t for t in evaluate_db_rules()), "fires once"
    print("PASS  clearing the region fires its falls-quiet rule once")

    # After enough turns, the region stirs: a monster respawns mid-region.
    for _ in range(10):
        db.increment_world_turn()
    triggered = evaluate_db_rules()
    assert any("Stirs" in t for t in triggered), triggered
    assert get_world_state(f"{rid}_cleared") == "false"
    resurgent = [m for ll in spec_locs for m in get_monsters_at(ll["location_id"])
                 if m["instance_id"].endswith("_resurgent")]
    assert resurgent, "resurgent monster spawned"
    print("PASS  a quiet region stirs again on its own")

    print("\nALL PREGEN + REGION RULE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
