from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import hashlib

from fastapi import FastAPI, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .engine.parse_command import parse_command, ParseError

from .db import init_db, create_faction, get_cached_scene_image
from .engine.apply_action import apply_action
from .factions import FACTIONS
from .services.image_gen import image_gen_enabled

app = FastAPI(title="RPG World Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # Seed the persistent monster table from the static catalog (once).
    from .engine.entities import seed_world_monsters
    seed_world_monsters()
    # The shared world always has a running community goal.
    from .world_goals import ensure_active_goal
    ensure_active_goal()
    # Built-in data-driven world rules.
    from .world_rules import seed_default_db_rules
    seed_default_db_rules()
    # A fresh universe already reaches past the hand-authored core: starter
    # regions are pre-minted so day one is bigger than the static 22 rooms.
    from .regiongen import pre_mint_regions
    pre_mint_regions()
    # The Restoration's opening act is written from this world (by Miriel,
    # from the places, creatures and people that actually exist — the minted
    # starter regions included) before the first player arrives.
    try:
        from .restoration import ensure_campaign
        act = ensure_campaign()
        print(f"[CAMPAIGN] current act: {act.index + 1} — {act.name} ({act.source})")
    except Exception as e:  # the campaign must never block startup
        print(f"[CAMPAIGN] opening act not written at startup: {e}")
    # Initialize factions
    for faction_id, faction in FACTIONS.items():
        create_faction(
            faction_id=faction_id,
            name=faction.name,
            alignment=faction.alignment,
            data={
                "influence_locations": faction.influence_locations,
                "npc_members": faction.npc_members,
                "description": faction.description,
            }
        )


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/action")
def action(req: dict, x_player_id: str | None = Header(default=None)):
    result = apply_action(player_id=x_player_id, req_json=req)
    # FastAPI will serialize pydantic model
    return result

@app.post("/command")
def command(
    text: str = Body(embed=True),
    x_player_id: str | None = Header(default=None),
):
    """
    Accepts raw text commands (SMS / CLI / web input).
    """
    try:
        action_req = parse_command(text)
    except ParseError as e:
        return {"ok": False, "messages": [], "error": str(e)}

    return apply_action(player_id=x_player_id, req_json=action_req)


@app.post("/sms")
def sms(
    text: str = Body(embed=True),
    sender: str = Body(embed=True, alias="from"),
):
    """
    SMS-shaped gateway: a sender handle (phone number) and a text command in,
    one compact plain-text message out. New senders are walked through
    creating a character; after that the full command grammar applies.
    """
    from fastapi.responses import PlainTextResponse
    from .db import get_sms_player_id, bind_sms_identity
    from .render_text import render_plain
    from .engine.parse_command import parse_command as _parse, ParseError as _ParseError

    try:
        action_req = _parse(text)
    except _ParseError as e:
        return PlainTextResponse(str(e))

    player_id = get_sms_player_id(sender)

    if action_req.get("action") == "create_player":
        if player_id:
            return PlainTextResponse("You already have a hero. Text 'look' to play.")
        result = apply_action(player_id=None, req_json=action_req)
        if result.ok and result.state and "player" in result.state:
            new_id = result.state["player"]["player_id"]
            bind_sms_identity(sender, new_id)
            name = result.state["player"]["name"]
            return PlainTextResponse(
                f"Welcome, {name}! You stand in the Town Square. "
                "Try: look, go north, fight rat, quests, help anytime."
            )
        return PlainTextResponse(result.error or "Could not create your hero.")

    if not player_id:
        return PlainTextResponse(
            "Welcome to QuestAI. Text 'create <name>' to forge your hero."
        )

    result = apply_action(player_id=player_id, req_json=action_req)
    from .db import get_player as _get_player
    return PlainTextResponse(render_plain(result, player=_get_player(player_id)))


@app.get("/intro")
def intro():
    """
    What a newcomer sees before they have a hero: the realm as it stands
    right now (the current act, how much of it is put right, who has been
    doing the righting), the paths they can walk, and a prompt for the
    title art — all drawn from the live, generated campaign so the welcome
    screen is never the same twice and never a lie.
    """
    from .archetypes import ARCHETYPES
    out = {
        "paths": [
            {"id": a.id, "name": a.name, "description": a.description, "passive": a.passive}
            for a in ARCHETYPES.values()
        ],
        "act": None,
        "heroes": [],
        "righted": 0,
        "total": 0,
        "art_prompt": None,
        "images": image_gen_enabled(),
    }
    try:
        from .restoration import current_act, righted_map, max_acts
        from .db import get_restorations
        act = current_act()
        done = righted_map()
        if act:
            out["act"] = {"index": act.index, "total": max_acts(), "name": act.name, "blurb": act.blurb,
                          "climax": act.climax_boss}
            out["total"] = len(act.wrongs)
            out["righted"] = sum(1 for w in act.wrongs if w.id in done)
            wrongs_text = "; ".join(w.blurb for w in act.wrongs if w.deed_type != "climax")[:600]
            out["art_prompt"] = (
                "Fantasy RPG title illustration. Wide horizontal composition (16:9), cinematic, "
                "detailed hand-painted fantasy art, the frame filled edge to edge, no text, no UI, no borders. "
                f"A realm that has fallen and waits to be restored — the act called '{act.name}': {act.blurb} "
                f"Signs of it in the land: {wrongs_text} "
                f"Looming far off: {act.climax_boss}. Dawn light on the horizon: hope, not despair."
            )
        else:
            out["act"] = {"index": None, "total": None, "name": "The Realm Restored",
                          "blurb": "Every wrong is put right. The Chronicle is complete.", "climax": None}
            out["art_prompt"] = (
                "Fantasy RPG title illustration. Wide horizontal composition (16:9), cinematic, detailed "
                "hand-painted fantasy art, no text, no UI. A restored realm at golden hour: a town at peace, "
                "banners, fields full, roads open to the mountains."
            )
        seen = []
        for r in reversed(get_restorations()):
            if r["righted_by_name"] not in seen:
                seen.append(r["righted_by_name"])
            if len(seen) >= 5:
                break
        out["heroes"] = seen
    except Exception as e:
        print(f"[INTRO] campaign summary skipped: {e}")
    return out


@app.post("/prefetch")
def prefetch(x_player_id: str | None = Header(default=None)):
    """
    Queue look-ahead warming (neighbor scenes, post-combat scenes, Miriel
    prose, NPC dialogue) for the player's current situation. The dispatcher
    already does this after every action; this lets a client ask again (e.g.
    on resume). Returns at once — the work runs on the server's warmer.
    """
    if not x_player_id:
        return {"ok": False}
    from .engine.prefetch import schedule_player_warm
    return schedule_player_warm(x_player_id, force=True)


@app.post("/api/ai/image")
def ai_image(prompt: str = Body(..., embed=True), wait: bool = Body(default=True, embed=True)):
    """
    Render (and persistently cache) a scene image for a prompt.

    Single shared world: the cache is keyed by a hash of the prompt and shared
    by every player, so returning to the same place reuses the same image
    across sessions and restarts. A miss with no API key (or a render failure)
    returns a non-200 the frontend treats as "no scene", never breaking play.

    ``wait=false`` is the prefetch mode: a miss queues the render on the
    server's background warmer and answers 202 immediately, so a browser
    warming several scenes at once never ties up its connections (and never
    delays the player's next command) waiting on image models.
    """
    key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    cached = get_cached_scene_image(key)
    if cached is not None:
        return {"image": cached, "cached": True}

    if not image_gen_enabled():
        return JSONResponse(
            status_code=503,
            content={"error": "image generation not configured (set GEMINI_API_KEY)"},
        )

    from .pregen import render_scene_to_cache, schedule_scene_render
    if not wait:
        schedule_scene_render(prompt, priority=1)
        return JSONResponse(status_code=202, content={"status": "rendering"})

    # Miss: render via the shared path (Miriel enrichment when available,
    # cached under the *base* prompt key). Single-flighted: if the warmer is
    # already rendering this scene, this request waits for it instead of
    # rendering twice.
    if not render_scene_to_cache(prompt):
        return JSONResponse(status_code=502, content={"error": "image generation failed"})

    return {"image": get_cached_scene_image(key), "cached": False}
