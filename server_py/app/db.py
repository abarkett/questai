from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional, Any, Dict, List

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
              max_hp INTEGER NOT NULL,
              inventory_json TEXT NOT NULL,
              active_quests_json TEXT DEFAULT '{}',
              completed_quests_json TEXT DEFAULT '{}',
              archived_quests_json TEXT DEFAULT '{}',
              last_defeated_at INTEGER,
              last_attacked_target TEXT,
              last_attacked_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS action_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL,
              player_id TEXT NOT NULL,
              action TEXT NOT NULL,
              args_json TEXT NOT NULL,
              result_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pending_trades (
              trade_id TEXT PRIMARY KEY,
              from_player_id TEXT NOT NULL,
              to_player_id TEXT NOT NULL,
              offered_items_json TEXT NOT NULL,
              requested_items_json TEXT NOT NULL,
              created_at INTEGER NOT NULL
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
        data = dict(row)
        data["inventory"] = json.loads(data["inventory_json"])
        
        # Handle quest fields for backwards compatibility
        data["active_quests"] = json.loads(data.get("active_quests_json", "{}"))
        data["completed_quests"] = json.loads(data.get("completed_quests_json", "{}"))
        data["archived_quests"] = json.loads(data.get("archived_quests_json", "{}"))
        
        # Deprecated: keep empty for backwards compatibility
        data["quests"] = {}
        
        # Handle new optional fields for backwards compatibility
        data.setdefault("last_defeated_at", None)
        data.setdefault("last_attacked_target", None)
        data.setdefault("last_attacked_at", None)
        return Player(**data)
    finally:
        conn.close()

def get_players_at_location(location_id: str) -> List[Player]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM players WHERE location = ?",
            (location_id,),
        ).fetchall()

        players = []
        for row in rows:
            data = dict(row)
            data["inventory"] = json.loads(data["inventory_json"])
            
            # Handle quest fields for backwards compatibility
            data["active_quests"] = json.loads(data.get("active_quests_json", "{}"))
            data["completed_quests"] = json.loads(data.get("completed_quests_json", "{}"))
            data["archived_quests"] = json.loads(data.get("archived_quests_json", "{}"))
            
            # Deprecated: keep empty for backwards compatibility
            data["quests"] = {}
            
            # Handle new optional fields for backwards compatibility
            data.setdefault("last_defeated_at", None)
            data.setdefault("last_attacked_target", None)
            data.setdefault("last_attacked_at", None)
            players.append(Player(**data))

        return players
    finally:
        conn.close()

def upsert_player(p: Player) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO players (
              player_id,
              name,
              location,
              level,
              xp,
              hp,
              max_hp,
              inventory_json,
              active_quests_json,
              completed_quests_json,
              archived_quests_json,
              last_defeated_at,
              last_attacked_target,
              last_attacked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
              name=excluded.name,
              location=excluded.location,
              level=excluded.level,
              xp=excluded.xp,
              hp=excluded.hp,
              max_hp=excluded.max_hp,
              inventory_json=excluded.inventory_json,
              active_quests_json=excluded.active_quests_json,
              completed_quests_json=excluded.completed_quests_json,
              archived_quests_json=excluded.archived_quests_json,
              last_defeated_at=excluded.last_defeated_at,
              last_attacked_target=excluded.last_attacked_target,
              last_attacked_at=excluded.last_attacked_at
            """,
            (
                p.player_id,
                p.name,
                p.location,
                p.level,
                p.xp,
                p.hp,
                p.max_hp,
                json.dumps(p.inventory),
                json.dumps({k: v.model_dump() for k, v in p.active_quests.items()}),
                json.dumps({k: v.model_dump() for k, v in p.completed_quests.items()}),
                json.dumps({k: v.model_dump() for k, v in p.archived_quests.items()}),
                p.last_defeated_at,
                p.last_attacked_target,
                p.last_attacked_at,
            ),
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


def create_pending_trade(
    trade_id: str,
    from_player_id: str,
    to_player_id: str,
    offered_items: dict[str, int],
    requested_items: dict[str, int],
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO pending_trades (
              trade_id, from_player_id, to_player_id, 
              offered_items_json, requested_items_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                from_player_id,
                to_player_id,
                json.dumps(offered_items),
                json.dumps(requested_items),
                int(time.time() * 1000),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_trade(trade_id: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM pending_trades WHERE trade_id = ?", (trade_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["offered_items"] = json.loads(data["offered_items_json"])
        data["requested_items"] = json.loads(data["requested_items_json"])
        return data
    finally:
        conn.close()


def delete_pending_trade(trade_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM pending_trades WHERE trade_id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()


def get_pending_trades_for_player(player_id: str) -> List[Dict[str, Any]]:
    """Get all pending trades where player is the recipient"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM pending_trades WHERE to_player_id = ?", (player_id,)
        ).fetchall()
        trades = []
        for row in rows:
            data = dict(row)
            data["offered_items"] = json.loads(data["offered_items_json"])
            data["requested_items"] = json.loads(data["requested_items_json"])
            trades.append(data)
        return trades
    finally:
        conn.close()

