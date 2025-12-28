from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional, Any, Dict

from .types import Player


DB_PATH = "game.sqlite"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
              player_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              location TEXT NOT NULL,
              level INTEGER NOT NULL,
              xp INTEGER NOT NULL,
              hp INTEGER NOT NULL,
              max_hp INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS action_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL,
              player_id TEXT NOT NULL,
              action TEXT NOT NULL,
              args_json TEXT NOT NULL,
              result_json TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_player(player_id: str) -> Optional[Player]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()
        if not row:
            return None
        return Player(**dict(row))
    finally:
        conn.close()


def upsert_player(p: Player) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO players (player_id, name, location, level, xp, hp, max_hp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
              name=excluded.name,
              location=excluded.location,
              level=excluded.level,
              xp=excluded.xp,
              hp=excluded.hp,
              max_hp=excluded.max_hp
            """,
            (p.player_id, p.name, p.location, p.level, p.xp, p.hp, p.max_hp),
        )
        conn.commit()
    finally:
        conn.close()


def log_action(*, player_id: str, action: str, args: Any, result: Any) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO action_log (ts, player_id, action, args_json, result_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(time.time() * 1000), player_id, action, json.dumps(args or {}), json.dumps(result or {})),
        )
        conn.commit()
    finally:
        conn.close()

