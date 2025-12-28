from __future__ import annotations

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware

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

