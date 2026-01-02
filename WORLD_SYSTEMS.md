# QuestAI - Evolving World Systems

This document describes the new world evolution, faction reputation, and party systems implemented in Phases 8-10.

## Phase 8: World Systems That Evolve Over Time

### World Clock

The world operates on a turn-based system where each significant player action advances time:

- **World Turn Counter**: Stored in the `world_clock` table
- **Turn Increment**: Happens on successful actions (except passive ones like `look`, `stats`, `inventory`)
- **Usage**: Can be used to trigger time-based events and world evolution

```python
from app.db import get_world_turn, increment_world_turn

current_turn = get_world_turn()  # Get current world turn
new_turn = increment_world_turn()  # Advance time by one turn
```

### World State Flags

Global world state is tracked using key-value pairs:

- **Storage**: `world_state` table
- **Examples**: `forest_infested`, `town_security_level`, `market_open`
- **Dynamic Descriptions**: Location descriptions update based on world state

```python
from app.db import get_world_state, set_world_state

# Get a state value
is_infested = get_world_state("forest_infested") == "true"

# Set a state value
set_world_state("forest_infested", "true")
```

### World Evolution Rules

The `world_rules.py` module contains deterministic rules that mutate world state:

- **Rule Structure**: Condition + Action
- **Examples**:
  - Forest becomes infested if rats survive too long
  - Forest clears when rats are eliminated
  - Town guards appear if too much PvP occurs

```python
from app.world_rules import evaluate_world_rules

triggered_rules = evaluate_world_rules()
```

### World Events (Miriel Integration)

World evolution events are logged for memory/learning systems:

```python
from app.db import log_world_event

log_world_event(
    event_type="world_evolution",
    location_id="forest",
    data={
        "change": "forest_infested",
        "description": "The forest became more dangerous as rats multiplied."
    }
)
```

## Phase 9: Factions, Reputation, and Social Meaning

### Factions

Four core factions are defined:

1. **Town Guard** (Lawful) - Protectors of the town
2. **Merchants Guild** (Neutral) - Traders and shopkeepers
3. **The Outlaws** (Chaotic) - Bandits and rogues
4. **Forest Druids** (Neutral) - Guardians of nature

Each faction has:
- Influence locations
- NPC members
- Alignment

### Reputation System

Reputation is **event-based**, not a single number:

- **Storage**: `reputation_events` table logs all reputation-affecting actions
- **Calculation**: Reputation is derived by summing event values
- **Tiers**: Hostile (-100), Unfriendly (-50), Neutral (0), Friendly (50), Honored (100)

```python
from app.db import log_reputation_event, calculate_reputation

# Log a reputation event
log_reputation_event(
    player_id="player123",
    faction_id="town_guard",
    event_type="quest_completed",
    value=10,
    description="Completed town quest",
    location_id="town_square"
)

# Calculate total reputation
reputation = calculate_reputation("player123", "town_guard")
```

### Reputation Effects

Reputation influences:
- **Price Modifiers**: Better prices with higher reputation (framework ready)
- **NPC Behavior**: Hostility, dialogue tone (framework ready)
- **Quest Availability**: Some quests require certain reputation

### Commands

- `reputation` or `rep` or `factions` - View your reputation with all factions

### Automatic Reputation Changes

- **PvP in Faction Territory**: Attacking players in faction-controlled areas damages reputation
- **Quest Completion**: Completing quests improves reputation
- **Helping NPCs**: Positive interactions boost reputation

## Phase 10: Player-to-Player Social Systems

### Parties/Alliances

Players can form parties for cooperation:

- **Party Creation**: Automatically created when inviting first member
- **Leadership**: Party creator is the leader
- **Membership**: Players can be in one party at a time

### Commands

- `party status` - View your current party
- `party invite <player>` - Invite a nearby player to your party (leader only)
- `accept_party_invite <invite_id>` - Accept a party invitation
- `party leave` - Leave your current party (disbands if you're the leader)

### Party Features

- **Shared Visibility**: Framework ready for party members to share location info
- **Shared Quests**: Framework ready for party-wide quest progress

## Database Schema

### Phase 8 Tables

```sql
-- World clock
CREATE TABLE world_clock (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  current_turn INTEGER NOT NULL DEFAULT 0
);

-- World state flags
CREATE TABLE world_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  updated_turn INTEGER NOT NULL
);

-- World events log
CREATE TABLE world_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turn INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  location_id TEXT,
  data_json TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
```

### Phase 9 Tables

```sql
-- Factions
CREATE TABLE factions (
  faction_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  alignment TEXT,
  data_json TEXT NOT NULL
);

-- Reputation events
CREATE TABLE reputation_events (
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
```

### Phase 10 Tables

```sql
-- Parties
CREATE TABLE parties (
  party_id TEXT PRIMARY KEY,
  leader_id TEXT NOT NULL,
  name TEXT,
  created_at INTEGER NOT NULL,
  created_turn INTEGER NOT NULL
);

-- Party members
CREATE TABLE party_members (
  party_id TEXT NOT NULL,
  player_id TEXT NOT NULL,
  joined_at INTEGER NOT NULL,
  joined_turn INTEGER NOT NULL,
  PRIMARY KEY (party_id, player_id)
);

-- Party invitations
CREATE TABLE party_invites (
  invite_id TEXT PRIMARY KEY,
  party_id TEXT NOT NULL,
  from_player_id TEXT NOT NULL,
  to_player_id TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
```

## Future Enhancements

### Phase 8
- Periodic world rule evaluation
- More complex evolution rules
- Time-based NPC spawning/despawning

### Phase 9
- Price modifiers in shops based on reputation
- NPC dialogue changes based on reputation
- Faction-specific quests
- Reputation requirements for quests/items

### Phase 10
- Shared party visibility (see party members' locations)
- Party-wide quest progress
- Party chat/communication
- Party loot distribution
- Alliance system (multiple parties working together)
