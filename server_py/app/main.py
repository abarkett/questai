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

