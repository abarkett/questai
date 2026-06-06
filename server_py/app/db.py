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
              equipment_json TEXT DEFAULT '{}',
              abilities_json TEXT DEFAULT '[]',
              ability_cooldowns_json TEXT DEFAULT '{}',
              status_effects_json TEXT DEFAULT '{}',
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

            -- Miriel Integration: Story arcs for narrative continuity
            CREATE TABLE IF NOT EXISTS story_arcs (
              arc_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              description TEXT NOT NULL,
              arc_type TEXT NOT NULL,           -- 'personal', 'faction', 'world'
              current_chapter INTEGER DEFAULT 1,
              total_chapters INTEGER,
              status TEXT NOT NULL,              -- 'active', 'paused', 'completed'
              faction_alignment TEXT,
              created_at INTEGER NOT NULL,
              created_turn INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              metadata_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS player_story_arcs (
              player_id TEXT NOT NULL,
              arc_id TEXT NOT NULL,
              joined_at INTEGER NOT NULL,
              joined_turn INTEGER NOT NULL,
              choices_json TEXT DEFAULT '[]',   -- Track player decisions
              current_chapter INTEGER DEFAULT 1,
              status TEXT DEFAULT 'active',      -- per-player: 'active' | 'completed'
              PRIMARY KEY (player_id, arc_id)
            );

            -- Miriel Integration: Cache AI responses to reduce API calls
            CREATE TABLE IF NOT EXISTS miriel_content_cache (
              cache_key TEXT PRIMARY KEY,
              content_type TEXT NOT NULL,       -- 'quest', 'dialogue', 'story_arc'
              content_json TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL
            );

            -- Persistent, shared scene-image cache (single shared world).
            -- Keyed by a hash of the render prompt so the same place yields the
            -- same image for every player and across sessions/restarts.
            CREATE TABLE IF NOT EXISTS scene_images (
              cache_key TEXT PRIMARY KEY,
              prompt TEXT NOT NULL,
              image_data TEXT NOT NULL,         -- data:image/...;base64,... URI
              model TEXT,
              created_at INTEGER NOT NULL
            );

            -- Live monster instances. Persisting these (instead of mutating an
            -- in-memory global) survives restarts and makes combat atomic and
            -- consistent across concurrent players. Monsters are deleted on death.
            CREATE TABLE IF NOT EXISTS monsters (
              instance_id TEXT PRIMARY KEY,
              location_id TEXT NOT NULL,
              name TEXT NOT NULL,
              hp INTEGER NOT NULL,
              max_hp INTEGER NOT NULL,
              attack INTEGER NOT NULL DEFAULT 1,
              xp_reward INTEGER NOT NULL DEFAULT 0,
              loot_json TEXT NOT NULL DEFAULT '{}',
              spawned_turn INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_story_arcs_status ON story_arcs(status);
            CREATE INDEX IF NOT EXISTS idx_monsters_location ON monsters(location_id);
            CREATE INDEX IF NOT EXISTS idx_player_story_arcs_player ON player_story_arcs(player_id);

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
    
    # Collect all player IDs to delete
    ids_to_delete = []
    
    for row in duplicates:
        lower_name = row[0]
        # Get all players with this name, ordered by player_id (oldest first)
        cursor.execute("""
            SELECT player_id FROM players 
            WHERE LOWER(name) = ? 
            ORDER BY player_id ASC
        """, (lower_name,))
        
        player_ids = [r[0] for r in cursor.fetchall()]
        
        # Keep the first one, mark the rest for deletion
        if len(player_ids) > 1:
            ids_to_delete.extend(player_ids[1:])
    
    # Delete all duplicates in a single statement for efficiency
    if ids_to_delete:
        placeholders = ','.join('?' * len(ids_to_delete))
        conn.execute(f"DELETE FROM players WHERE player_id IN ({placeholders})", ids_to_delete)



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
        "equipment_json": "TEXT DEFAULT '{}'",
        "abilities_json": "TEXT DEFAULT '[]'",
        "ability_cooldowns_json": "TEXT DEFAULT '{}'",
        "status_effects_json": "TEXT DEFAULT '{}'",
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

    # Per-player story-arc progress columns (added after the table shipped).
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='player_story_arcs'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(player_story_arcs)")
        arc_cols = {row[1] for row in cursor.fetchall()}
        for col, coltype in {
            "current_chapter": "INTEGER DEFAULT 1",
            "status": "TEXT DEFAULT 'active'",
        }.items():
            if col not in arc_cols:
                conn.execute(f"ALTER TABLE player_story_arcs ADD COLUMN {col} {coltype}")

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
    data["equipment"] = json.loads(data.get("equipment_json") or "{}")
    data["abilities"] = json.loads(data.get("abilities_json") or "[]")
    data["ability_cooldowns"] = json.loads(data.get("ability_cooldowns_json") or "{}")
    data["status_effects"] = json.loads(data.get("status_effects_json") or "{}")

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
              equipment_json,
              abilities_json,
              ability_cooldowns_json,
              status_effects_json,
              active_quests_json,
              completed_quests_json,
              archived_quests_json,
              last_defeated_at,
              last_attacked_target,
              last_attacked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
              name=excluded.name,
              location=excluded.location,
              level=excluded.level,
              xp=excluded.xp,
              hp=excluded.hp,
              max_hp=excluded.max_hp,
              inventory_json=excluded.inventory_json,
              equipment_json=excluded.equipment_json,
              abilities_json=excluded.abilities_json,
              ability_cooldowns_json=excluded.ability_cooldowns_json,
              status_effects_json=excluded.status_effects_json,
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
                json.dumps(p.equipment),
                json.dumps(p.abilities),
                json.dumps(p.ability_cooldowns),
                json.dumps(p.status_effects),
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


def get_pending_trades_by_player(player_id: str) -> List[Dict[str, Any]]:
    """Get all pending trades where player is the sender/offerer"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM pending_trades WHERE from_player_id = ?", (player_id,)
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

    # Learn in Miriel (Phase 2: Learning System)
    from .miriel_learning import learn_world_event
    try:
        learn_world_event(event_type, location_id, data)
    except Exception:
        pass  # Don't crash on learning errors


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

    # Learn in Miriel (Phase 2: Learning System)
    from .miriel_learning import learn_reputation_change
    try:
        learn_reputation_change(player_id, faction_id, event_type, value, description)
    except Exception:
        pass  # Don't crash on learning errors


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


# ===== Miriel Integration: Story Arcs and AI Content =====

def get_player_story_arcs(player_id: str) -> List[Dict[str, Any]]:
    """Get all active story arcs for a player."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT sa.* FROM story_arcs sa
            JOIN player_story_arcs psa ON sa.arc_id = psa.arc_id
            WHERE psa.player_id = ? AND sa.status = 'active'
            """,
            (player_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_story_arc(
    arc_id: str,
    title: str,
    description: str,
    arc_type: str,
    total_chapters: int,
    faction_alignment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Create a new story arc."""
    conn = get_conn()
    try:
        turn = get_world_turn()
        now = int(time.time() * 1000)
        conn.execute(
            """
            INSERT INTO story_arcs (
              arc_id, title, description, arc_type, total_chapters,
              status, faction_alignment, created_at, created_turn, updated_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                arc_id,
                title,
                description,
                arc_type,
                total_chapters,
                faction_alignment,
                now,
                turn,
                now,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_player_arc(player_id: str, arc_id: str) -> Optional[Dict[str, Any]]:
    """Per-player progress on a single story arc, or None if not started."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM player_story_arcs WHERE player_id = ? AND arc_id = ?",
            (player_id, arc_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_player_arcs(player_id: str) -> List[Dict[str, Any]]:
    """All story arcs this player has started (any status)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM player_story_arcs WHERE player_id = ?",
            (player_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def start_player_arc(player_id: str, arc_id: str) -> None:
    """Begin an arc for a player at chapter 1 (no-op if already started)."""
    conn = get_conn()
    try:
        now = int(time.time() * 1000)
        turn = get_world_turn()
        conn.execute(
            """
            INSERT OR IGNORE INTO player_story_arcs
              (player_id, arc_id, joined_at, joined_turn, choices_json, current_chapter, status)
            VALUES (?, ?, ?, ?, '[]', 1, 'active')
            """,
            (player_id, arc_id, now, turn),
        )
        conn.commit()
    finally:
        conn.close()


def update_player_arc(
    player_id: str,
    arc_id: str,
    *,
    current_chapter: int,
    status: str,
    choices: List[Dict[str, Any]],
) -> None:
    """Persist a player's arc progress (chapter, status, recorded choices)."""
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE player_story_arcs
            SET current_chapter = ?, status = ?, choices_json = ?
            WHERE player_id = ? AND arc_id = ?
            """,
            (current_chapter, status, json.dumps(choices), player_id, arc_id),
        )
        conn.commit()
    finally:
        conn.close()


def join_story_arc(player_id: str, arc_id: str) -> None:
    """Add a player to a story arc."""
    conn = get_conn()
    try:
        turn = get_world_turn()
        conn.execute(
            """
            INSERT OR IGNORE INTO player_story_arcs (player_id, arc_id, joined_at, joined_turn)
            VALUES (?, ?, ?, ?)
            """,
            (player_id, arc_id, int(time.time() * 1000), turn),
        )
        conn.commit()
    finally:
        conn.close()


def update_story_arc_chapter(arc_id: str, new_chapter: int) -> None:
    """Advance a story arc to a new chapter."""
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE story_arcs
            SET current_chapter = ?, updated_at = ?
            WHERE arc_id = ?
            """,
            (new_chapter, int(time.time() * 1000), arc_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_player_actions(player_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent player actions from the action log."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT action, args_json, ts
            FROM action_log
            WHERE player_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (player_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
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


def cache_miriel_content(cache_key: str, content_type: str, content_json: str, ttl_seconds: int = 3600) -> None:
    """Cache Miriel-generated content."""
    conn = get_conn()
    try:
        now = int(time.time() * 1000)
        expires_at = now + (ttl_seconds * 1000)
        conn.execute(
            """
            INSERT OR REPLACE INTO miriel_content_cache (cache_key, content_type, content_json, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cache_key, content_type, content_json, now, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_cached_miriel_content(cache_key: str) -> Optional[str]:
    """Retrieve cached Miriel content if not expired."""
    conn = get_conn()
    try:
        now = int(time.time() * 1000)
        row = conn.execute(
            """
            SELECT content_json FROM miriel_content_cache
            WHERE cache_key = ? AND expires_at > ?
            """,
            (cache_key, now),
        ).fetchone()
        return row["content_json"] if row else None
    finally:
        conn.close()


# ===== Scene image cache (persistent, shared across players) =====

def get_cached_scene_image(cache_key: str) -> Optional[str]:
    """Return a cached scene image (data URI) for a prompt hash, or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT image_data FROM scene_images WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        return row["image_data"] if row else None
    finally:
        conn.close()


def cache_scene_image(cache_key: str, prompt: str, image_data: str, model: Optional[str]) -> None:
    """Persist a rendered scene image so the same place reuses it everywhere."""
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO scene_images (cache_key, prompt, image_data, model, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cache_key, prompt, image_data, model, int(time.time() * 1000)),
        )
        conn.commit()
    finally:
        conn.close()


# ===== Monsters (persistent, shared world entities) =====

def spawn_monster(
    instance_id: str,
    location_id: str,
    name: str,
    hp: int,
    max_hp: int,
    attack: int = 1,
    xp_reward: int = 0,
    loot: Optional[Dict[str, int]] = None,
    spawned_turn: Optional[int] = None,
) -> None:
    """Create (or replace) a monster instance in the world."""
    conn = get_conn()
    try:
        if spawned_turn is None:
            spawned_turn = get_world_turn()
        conn.execute(
            """
            INSERT OR REPLACE INTO monsters
              (instance_id, location_id, name, hp, max_hp, attack, xp_reward, loot_json, spawned_turn)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (instance_id, location_id, name, hp, max_hp, attack, xp_reward,
             json.dumps(loot or {}), spawned_turn),
        )
        conn.commit()
    finally:
        conn.close()


def get_monsters_at(location_id: str) -> List[Dict[str, Any]]:
    """All live monsters at a location (loot decoded)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM monsters WHERE location_id = ? ORDER BY instance_id", (location_id,)
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["loot"] = json.loads(data.get("loot_json") or "{}")
            result.append(data)
        return result
    finally:
        conn.close()


def count_monsters_at(location_id: str) -> int:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM monsters WHERE location_id = ?", (location_id,)
        ).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


def damage_monster(instance_id: str, damage: int) -> Optional[Dict[str, Any]]:
    """
    Atomically apply damage to a monster. Returns:
      - None if the monster no longer exists (e.g. another player just killed it)
      - {'killed': True, 'name', 'hp': 0, 'location_id', 'xp_reward', 'loot'} on kill
      - {'killed': False, 'name', 'hp', 'location_id'} otherwise

    Uses BEGIN IMMEDIATE so concurrent attackers can't double-kill or lose
    damage to a read-modify-write race.
    """
    conn = get_conn()
    try:
        conn.isolation_level = None  # manual transaction control
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        row = cur.execute(
            "SELECT hp, name, attack, xp_reward, loot_json, location_id FROM monsters WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()
        if row is None:
            cur.execute("COMMIT")
            return None

        new_hp = row["hp"] - damage
        if new_hp <= 0:
            cur.execute("DELETE FROM monsters WHERE instance_id = ?", (instance_id,))
            cur.execute("COMMIT")
            return {
                "killed": True,
                "name": row["name"],
                "hp": 0,
                "attack": row["attack"],
                "location_id": row["location_id"],
                "xp_reward": row["xp_reward"],
                "loot": json.loads(row["loot_json"] or "{}"),
            }

        cur.execute("UPDATE monsters SET hp = ? WHERE instance_id = ?", (new_hp, instance_id))
        cur.execute("COMMIT")
        return {
            "killed": False,
            "name": row["name"],
            "hp": new_hp,
            "attack": row["attack"],
            "location_id": row["location_id"],
        }
    finally:
        conn.close()


def remove_monster(instance_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM monsters WHERE instance_id = ?", (instance_id,))
        conn.commit()
    finally:
        conn.close()

