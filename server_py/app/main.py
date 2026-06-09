from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import hashlib

from fastapi import FastAPI, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .engine.parse_command import parse_command, ParseError

from .db import init_db, create_faction, get_cached_scene_image, cache_scene_image
from .engine.apply_action import apply_action
from .factions import FACTIONS
from .services.image_gen import (
    generate_scene_image,
    get_image_model,
    image_gen_enabled,
    enrich_scene_prompt,
)

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


@app.post("/prefetch")
def prefetch(x_player_id: str | None = Header(default=None)):
    """
    Warm Miriel text caches (location descriptions) for the player's current
    room and its neighbors. Best-effort and never fails; called by the client in
    the background to make subsequent `look`s instant.
    """
    if not x_player_id:
        return {"ok": False}
    from .engine.prefetch import warm_location_caches
    return warm_location_caches(x_player_id)


@app.post("/api/ai/image")
def ai_image(prompt: str = Body(..., embed=True)):
    """
    Render (and persistently cache) a scene image for a prompt.

    Single shared world: the cache is keyed by a hash of the prompt and shared
    by every player, so returning to the same place reuses the same image
    across sessions and restarts. A miss with no API key (or a render failure)
    returns a non-200 the frontend treats as "no scene", never breaking play.
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

    # Miss: enrich the prompt with Miriel's world context, then render. We cache
    # under the *base* prompt key so the scene renders once and stays consistent.
    image = generate_scene_image(enrich_scene_prompt(prompt))
    if not image:
        return JSONResponse(status_code=502, content={"error": "image generation failed"})

    cache_scene_image(key, prompt, image, get_image_model())
    return {"image": image, "cached": False}

