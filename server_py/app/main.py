from __future__ import annotations

from fastapi import FastAPI, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from .engine.parse_command import parse_command, ParseError

from .db import init_db
from .engine.apply_action import apply_action

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

