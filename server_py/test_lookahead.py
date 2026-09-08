"""
Look-ahead warming: the places a player might go next are generated on the
server, in the background, the moment they arrive somewhere — and revisiting
a place that hasn't changed never waits on an AI round-trip.

Covers:
  - after any action, every adjacent scene and this room's post-combat
    scenes are rendered under the exact keys the web client will ask for;
  - the same situation is not re-queued on the next action (dedup), but a
    change next door is;
  - /api/ai/image with wait=false answers 202 and warms in the background;
    a later request finds the image;
  - a foreground render and a background warm of the same scene share one
    render (single-flight);
  - location prose is served stale-while-revalidate: a due-for-refresh
    description answers instantly from the cache while Miriel rewrites it in
    the background; a never-described place still waits (and still fails
    hard with Miriel down — no fallback).

Run from server_py/:  python3 test_lookahead.py
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

from app import warmer  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_world_turn, remove_monster, get_monsters_at  # noqa: E402
from app.world import get_location  # noqa: E402
from app.engine.entities import get_entities_at, filter_current_player  # noqa: E402
from app.engine.state_view import effective_description  # noqa: E402
from app.engine.prefetch import schedule_player_warm, scene_prompts_for_player, reset_warm_signatures  # noqa: E402
from app.engine.apply_action import apply_action  # noqa: E402
from app.scene_prompts import build_scene_prompt, scene_entity_names  # noqa: E402
from app.services.miriel_client import install_test_responder, get_miriel_client, MirielUnavailable  # noqa: E402
from app.services import image_gen  # noqa: E402
from app.pregen import render_scene_to_cache, scene_cache_key  # noqa: E402
from app.descriptions import describe, cache_key_for  # noqa: E402


def client_prompt(loc_id: str, entities) -> str:
    """What web/src/app/lib/scene.ts would build for this location+entities."""
    loc = get_location(loc_id)
    return build_scene_prompt(loc.name, effective_description(loc), scene_entity_names(entities))


def main() -> None:
    warmer.SYNC = True  # run queued jobs inline: deterministic, observable

    rendered = []

    def fake_render(p):
        rendered.append(p)
        return "data:image/png;base64,FAKE"

    real_enabled, real_render = image_gen.image_gen_enabled, image_gen.generate_scene_image
    image_gen.image_gen_enabled = lambda: True
    image_gen.generate_scene_image = fake_render
    get_miriel_client().enabled = True
    install_test_responder(lambda q: "Stubbed Miriel prose.")

    try:
        # ---- 1. An action warms next door + this room's post-combat scenes ----
        p = Player(player_id="p", name="P", location="forest", level=3, xp=0, hp=30, max_hp=30)
        upsert_player(p)
        r = apply_action(player_id="p", req_json={"action": "look", "args": {}})
        assert r.ok, r.error

        forest = get_location("forest")
        assert forest.exits, "test needs a room with exits"
        for ex in forest.exits:
            prompt = client_prompt(ex.to, get_entities_at(ex.to))
            assert db.get_cached_scene_image(scene_cache_key(prompt)), f"neighbor {ex.to} not warmed"
        print(f"PASS  {len(forest.exits)} adjacent scenes rendered under the client's keys")

        here = filter_current_player(get_entities_at("forest"), "p")
        monsters = [e for e in here if e.get("type") == "monster"]
        assert monsters, "forest should start with monsters"
        cleared_prompt = client_prompt("forest", [e for e in here if e.get("type") != "monster"])
        assert db.get_cached_scene_image(scene_cache_key(cleared_prompt)), "cleared-room scene not warmed"
        if len(monsters) > 1:
            minus_one = client_prompt("forest", [e for e in here if e.get("id") != monsters[0]["id"]])
            assert db.get_cached_scene_image(scene_cache_key(minus_one)), "minus-one scene not warmed"
        print("PASS  this room's post-combat scenes rendered ahead of the fight")

        # The prose next door is warm too: moving there is a cache hit.
        nbr = forest.exits[0].to
        nloc = get_location(nbr)
        key = cache_key_for(nloc, get_entities_at(nbr), get_world_turn(), effective_description(nloc))
        assert db.get_cached_miriel_content(key), "neighbor prose not warmed"
        print("PASS  neighbor prose warmed")

        # ---- 2. Dedup: an unchanged situation queues nothing more ----
        before = len(rendered)
        res = schedule_player_warm("p")
        assert res.get("skipped") and res["queued"] == 0, res
        assert len(rendered) == before
        # ...but a change next door (a monster slain there) re-warms.
        changed = next((ex.to for ex in forest.exits if get_monsters_at(ex.to)), None)
        if changed:
            remove_monster(get_monsters_at(changed)[0]["instance_id"])
            res = schedule_player_warm("p")
            assert not res.get("skipped"), res
            prompt = client_prompt(changed, get_entities_at(changed))
            assert db.get_cached_scene_image(scene_cache_key(prompt)), "changed neighbor not re-warmed"
        print("PASS  warming is deduplicated per situation and re-runs when next door changes")

        # ---- 3. wait=false: 202 now, warmed in the background ----
        from fastapi.testclient import TestClient
        from app.main import app as fastapi_app
        os.environ["GEMINI_API_KEY"] = "test"  # endpoint gate (render itself is stubbed)
        with TestClient(fastapi_app) as client:
            prompt = "Fantasy RPG scene illustration. A lone tower at dusk."
            n = len(rendered)
            r = client.post("/api/ai/image", json={"prompt": prompt, "wait": False})
            assert r.status_code == 202, (r.status_code, r.text)
            assert len(rendered) == n + 1, "prefetch should have queued (and, in SYNC, run) a render"
            r = client.post("/api/ai/image", json={"prompt": prompt})
            assert r.status_code == 200 and r.json()["cached"] is True, r.text
            assert len(rendered) == n + 1, "no second render for a warmed scene"
            print("PASS  /api/ai/image wait=false -> 202, then served from cache")

            # /prefetch returns at once with a count (not the warmed work itself).
            r = client.post("/prefetch", headers={"x-player-id": "p"})
            assert r.status_code == 200 and r.json()["ok"], r.text
            print("PASS  /prefetch schedules and returns immediately")
        os.environ.pop("GEMINI_API_KEY", None)

        # ---- 4. Single-flight: concurrent renders of one scene -> one render ----
        import threading
        gate = threading.Event()
        slow_renders = []

        def slow_render(pr):
            gate.wait(5)
            slow_renders.append(pr)
            return "data:image/png;base64,SLOW"

        image_gen.generate_scene_image = slow_render
        prompt = "Fantasy RPG scene illustration. Two travellers, one render."
        results = []
        ts = [threading.Thread(target=lambda: results.append(render_scene_to_cache(prompt))) for _ in range(3)]
        for t in ts:
            t.start()
        gate.set()
        for t in ts:
            t.join(10)
        assert results == [True, True, True], results
        assert len(slow_renders) == 1, f"expected one render, got {len(slow_renders)}"
        image_gen.generate_scene_image = fake_render
        print("PASS  concurrent requests for one scene share a single render")

        # ---- 5. Prose: stale-while-revalidate ----
        loc = get_location("town_square")
        ents = get_entities_at("town_square")
        base = effective_description(loc)
        calls = []

        def counting(q):
            calls.append(q)
            return f"Prose #{len(calls)}"

        install_test_responder(counting)
        first = describe(p, loc, ents, base, 0)
        assert first == "Prose #1" and len(calls) == 1
        # Same situation, refresh bucket turned over: answered from the stale
        # copy at once; the refresh ran in the background (inline under SYNC).
        second = describe(p, loc, ents, base, 12)
        assert second == "Prose #1", second
        assert len(calls) == 2, "refresh should have been queued"
        third = describe(p, loc, ents, base, 12)
        assert third == "Prose #2", third
        print("PASS  a known place answers instantly (stale) while the refresh runs in the background")

        # A never-described situation (different creatures) still waits on Miriel...
        fresh = describe(p, loc, [{"type": "monster", "name": "Basilisk"}], base, 12)
        assert fresh == "Prose #3", fresh
        # ...and still fails hard with Miriel down (no fallback, ever).
        get_miriel_client().enabled = False
        raised = False
        try:
            describe(p, loc, [{"type": "monster", "name": "Wyvern"}], base, 12)
        except MirielUnavailable:
            raised = True
        assert raised
        get_miriel_client().enabled = True
        print("PASS  a new situation waits on Miriel; Miriel down still fails hard")

        # Even an *expired* entry counts as stale: returning after a long
        # absence is still instant.
        db.cache_miriel_content(cache_key_for(loc, ents, 24, base), "dialogue", "Old prose", ttl_seconds=-1)
        n = len(calls)
        got = describe(p, loc, ents, base, 24)
        assert got in ("Old prose", "Prose #2", "Prose #3") and got != f"Prose #{n + 1}", got
        print("PASS  an expired description is served stale, not regenerated in the foreground")
    finally:
        image_gen.image_gen_enabled = real_enabled
        image_gen.generate_scene_image = real_render
        install_test_responder(None)
        get_miriel_client().enabled = False
        warmer.SYNC = False
        reset_warm_signatures()

    print("\nALL LOOK-AHEAD TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
