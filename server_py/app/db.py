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

            -- Phase 8: World clock and state
            CREATE TABLE IF NOT EXISTS world_clock (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              current_turn INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS world_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at INTEGER NOT NULL,
              updated_turn INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS world_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              turn INTEGER NOT NULL,
              event_type TEXT NOT NULL,
              location_id TEXT,
              data_json TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );

            -- Phase 9: Factions and reputation
            CREATE TABLE IF NOT EXISTS factions (
              faction_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              alignment TEXT,
              data_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reputation_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              player_id TEXT NOT NULL,
              faction_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              value INTEGER NOT NULL,
              description TEXT NOT NULL,
              location_id TEXT,
              turn INTEGER NOT NULL,
              created_at INTEGER NOT NULL
            );

            -- Phase 10: Parties and alliances
            CREATE TABLE IF NOT EXISTS parties (
              party_id TEXT PRIMARY KEY,
              leader_id TEXT NOT NULL,
              name TEXT,
              created_at INTEGER NOT NULL,
              created_turn INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS party_members (
              party_id TEXT NOT NULL,
              player_id TEXT NOT NULL,
              joined_at INTEGER NOT NULL,
              joined_turn INTEGER NOT NULL,
              PRIMARY KEY (party_id, player_id)
            );

            CREATE TABLE IF NOT EXISTS party_invites (
              invite_id TEXT PRIMARY KEY,
              party_id TEXT NOT NULL,
              from_player_id TEXT NOT NULL,
              to_player_id TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );

            -- Initialize world clock if not exists
            INSERT OR IGNORE INTO world_clock (id, current_turn) VALUES (1, 0);
            """
        )
        conn.commit()
        
        # Migrate existing tables to add missing columns
        _migrate_schema(conn)
    finally:
        conn.close()


def _remove_duplicate_players(conn: sqlite3.Connection) -> None:
    """Remove duplicate player records, keeping the first created player by player_id."""
    cursor = conn.cursor()
    
    # Find players with duplicate names (case-insensitive)
    cursor.execute("""
        SELECT LOWER(name) as lower_name, COUNT(*) as cnt 
        FROM players 
        GROUP BY LOWER(name) 
        HAVING cnt > 1
    """)
    duplicates = cursor.fetchall()
    
    for row in duplicates:
        lower_name = row[0]
        # Get all players with this name, ordered by player_id (oldest first)
        cursor.execute("""
            SELECT player_id FROM players 
            WHERE LOWER(name) = ? 
            ORDER BY player_id ASC
        """, (lower_name,))
        
        player_ids = [r[0] for r in cursor.fetchall()]
        
        # Keep the first one, delete the rest
        if len(player_ids) > 1:
            for player_id in player_ids[1:]:
                conn.execute("DELETE FROM players WHERE player_id = ?", (player_id,))


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add any missing columns to existing tables for backwards compatibility."""
    cursor = conn.cursor()
    
    # Check if players table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='players'"
    )
    if not cursor.fetchone():
        return  # Players table doesn't exist yet, nothing to migrate
    
    # Get current columns in players table
    cursor.execute("PRAGMA table_info(players)")
    columns = {row[1] for row in cursor.fetchall()}
    
    # Define expected columns and their types for migration
    expected_columns = {
        "active_quests_json": "TEXT DEFAULT '{}'",
        "completed_quests_json": "TEXT DEFAULT '{}'",
        "archived_quests_json": "TEXT DEFAULT '{}'",
        "last_defeated_at": "INTEGER",
        "last_attacked_target": "TEXT",
        "last_attacked_at": "INTEGER",
    }
    
    # Add missing columns
    for column_name, column_type in expected_columns.items():
        if column_name not in columns:
            conn.execute(f"ALTER TABLE players ADD COLUMN {column_name} {column_type}")
    
    # Clean up duplicate players (keep oldest by player_id)
    _remove_duplicate_players(conn)
    
    # Create unique index on lowercase name to prevent future duplicates
    # Using IF NOT EXISTS to avoid errors if index already exists
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_players_name_lower 
        ON players (LOWER(name))
    """)
    
    conn.commit()


def _build_player_from_row(row: sqlite3.Row) -> Player:
    """Helper function to build a Player object from a database row."""
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


def get_player(player_id: str) -> Optional[Player]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()
        if not row:
            return None
        return _build_player_from_row(row)
    finally:
        conn.close()

def get_player_by_name(name: str) -> Optional[Player]:
    """Get a player by their name (case-insensitive)."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM players WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        if not row:
            return None
        return _build_player_from_row(row)
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
            players.append(_build_player_from_row(row))

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


# ===== Phase 8: World Clock =====

def get_world_turn() -> int:
    """Get the current world turn counter."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT current_turn FROM world_clock WHERE id = 1").fetchone()
        return row["current_turn"] if row else 0
    finally:
        conn.close()


def increment_world_turn() -> int:
    """Increment and return the new world turn."""
    conn = get_conn()
    try:
        conn.execute("UPDATE world_clock SET current_turn = current_turn + 1 WHERE id = 1")
        conn.commit()
        row = conn.execute("SELECT current_turn FROM world_clock WHERE id = 1").fetchone()
        return row["current_turn"] if row else 0
    finally:
        conn.close()


# ===== Phase 8: World State =====

def get_world_state(key: str) -> Optional[str]:
    """Get a world state value by key."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM world_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_world_state(key: str, value: str) -> None:
    """Set a world state value."""
    conn = get_conn()
    try:
        turn = get_world_turn()
        conn.execute(
            """
            INSERT INTO world_state (key, value, updated_at, updated_turn)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value=excluded.value,
              updated_at=excluded.updated_at,
              updated_turn=excluded.updated_turn
            """,
            (key, value, int(time.time() * 1000), turn),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_world_state() -> Dict[str, str]:
    """Get all world state key-value pairs."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM world_state").fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        conn.close()


# ===== Phase 8: World Events =====

def log_world_event(event_type: str, location_id: Optional[str], data: Dict[str, Any]) -> None:
    """Log a world evolution event (for Miriel integration)."""
    conn = get_conn()
    try:
        turn = get_world_turn()
        conn.execute(
            """
            INSERT INTO world_events (turn, event_type, location_id, data_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (turn, event_type, location_id, json.dumps(data), int(time.time() * 1000)),
        )
        conn.commit()
    finally:
        conn.close()


def get_world_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent world events."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM world_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        events = []
        for row in rows:
            data = dict(row)
            data["data"] = json.loads(data["data_json"])
            events.append(data)
        return events
    finally:
        conn.close()


# ===== Phase 9: Factions =====

def create_faction(faction_id: str, name: str, alignment: str, data: Dict[str, Any]) -> None:
    """Create a new faction."""
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO factions (faction_id, name, alignment, data_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(faction_id) DO UPDATE SET
              name=excluded.name,
              alignment=excluded.alignment,
              data_json=excluded.data_json
            """,
            (faction_id, name, alignment, json.dumps(data)),
        )
        conn.commit()
    finally:
        conn.close()


def get_faction(faction_id: str) -> Optional[Dict[str, Any]]:
    """Get faction data."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM factions WHERE faction_id = ?", (faction_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["data"] = json.loads(data["data_json"])
        return data
    finally:
        conn.close()


def get_all_factions() -> List[Dict[str, Any]]:
    """Get all factions."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM factions").fetchall()
        factions = []
        for row in rows:
            data = dict(row)
            data["data"] = json.loads(data["data_json"])
            factions.append(data)
        return factions
    finally:
        conn.close()


# ===== Phase 9: Reputation Events =====

def log_reputation_event(
    player_id: str,
    faction_id: str,
    event_type: str,
    value: int,
    description: str,
    location_id: Optional[str] = None,
) -> None:
    """Log a reputation-affecting event."""
    conn = get_conn()
    try:
        turn = get_world_turn()
        conn.execute(
            """
            INSERT INTO reputation_events (
              player_id, faction_id, event_type, value, description, location_id, turn, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (player_id, faction_id, event_type, value, description, location_id, turn, int(time.time() * 1000)),
        )
        conn.commit()
    finally:
        conn.close()


def get_reputation_events(
    player_id: str,
    faction_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get reputation events for a player, optionally filtered by faction."""
    conn = get_conn()
    try:
        if faction_id:
            rows = conn.execute(
                """
                SELECT * FROM reputation_events 
                WHERE player_id = ? AND faction_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (player_id, faction_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM reputation_events 
                WHERE player_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (player_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def calculate_reputation(player_id: str, faction_id: str) -> int:
    """Calculate total reputation for a player with a faction."""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(value), 0) as total
            FROM reputation_events
            WHERE player_id = ? AND faction_id = ?
            """,
            (player_id, faction_id),
        ).fetchone()
        return row["total"] if row else 0
    finally:
        conn.close()


# ===== Phase 10: Parties =====

def create_party(party_id: str, leader_id: str, name: Optional[str] = None) -> None:
    """Create a new party."""
    conn = get_conn()
    try:
        turn = get_world_turn()
        conn.execute(
            """
            INSERT INTO parties (party_id, leader_id, name, created_at, created_turn)
            VALUES (?, ?, ?, ?, ?)
            """,
            (party_id, leader_id, name, int(time.time() * 1000), turn),
        )
        # Add leader as first member
        conn.execute(
            """
            INSERT INTO party_members (party_id, player_id, joined_at, joined_turn)
            VALUES (?, ?, ?, ?)
            """,
            (party_id, leader_id, int(time.time() * 1000), turn),
        )
        conn.commit()
    finally:
        conn.close()


def get_party(party_id: str) -> Optional[Dict[str, Any]]:
    """Get party data."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM parties WHERE party_id = ?", (party_id,)).fetchone()
        if not row:
            return None
        party = dict(row)
        
        # Get members
        member_rows = conn.execute(
            "SELECT player_id FROM party_members WHERE party_id = ?", (party_id,)
        ).fetchall()
        party["members"] = [row["player_id"] for row in member_rows]
        
        return party
    finally:
        conn.close()


def get_player_party(player_id: str) -> Optional[Dict[str, Any]]:
    """Get the party that a player belongs to."""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT p.* FROM parties p
            JOIN party_members pm ON p.party_id = pm.party_id
            WHERE pm.player_id = ?
            """,
            (player_id,),
        ).fetchone()
        if not row:
            return None
        party = dict(row)
        
        # Get members
        member_rows = conn.execute(
            "SELECT player_id FROM party_members WHERE party_id = ?", (party["party_id"],)
        ).fetchall()
        party["members"] = [row["player_id"] for row in member_rows]
        
        return party
    finally:
        conn.close()


def add_party_member(party_id: str, player_id: str) -> None:
    """Add a player to a party."""
    conn = get_conn()
    try:
        turn = get_world_turn()
        conn.execute(
            """
            INSERT INTO party_members (party_id, player_id, joined_at, joined_turn)
            VALUES (?, ?, ?, ?)
            """,
            (party_id, player_id, int(time.time() * 1000), turn),
        )
        conn.commit()
    finally:
        conn.close()


def remove_party_member(party_id: str, player_id: str) -> None:
    """Remove a player from a party."""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM party_members WHERE party_id = ? AND player_id = ?",
            (party_id, player_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_party(party_id: str) -> None:
    """Delete a party and all its members."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM party_members WHERE party_id = ?", (party_id,))
        conn.execute("DELETE FROM parties WHERE party_id = ?", (party_id,))
        conn.execute("DELETE FROM party_invites WHERE party_id = ?", (party_id,))
        conn.commit()
    finally:
        conn.close()


def create_party_invite(invite_id: str, party_id: str, from_player_id: str, to_player_id: str) -> None:
    """Create a party invitation."""
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO party_invites (invite_id, party_id, from_player_id, to_player_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (invite_id, party_id, from_player_id, to_player_id, int(time.time() * 1000)),
        )
        conn.commit()
    finally:
        conn.close()


def get_party_invite(invite_id: str) -> Optional[Dict[str, Any]]:
    """Get a party invitation."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM party_invites WHERE invite_id = ?", (invite_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_player_party_invites(player_id: str) -> List[Dict[str, Any]]:
    """Get all party invites for a player."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM party_invites WHERE to_player_id = ?", (player_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_party_invite(invite_id: str) -> None:
    """Delete a party invitation."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM party_invites WHERE invite_id = ?", (invite_id,))
        conn.commit()
    finally:
        conn.close()

