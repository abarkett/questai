# Miriel AI Integration for QuestAI

## Overview

QuestAI now integrates with Miriel, an AI context engine that enables dynamic storyline generation. Templates are now **optional** - if they don't exist, Miriel generates content dynamically based on comprehensive game context.

## Features

### ✅ Comprehensive Learning System
- **ALL player actions** are learned for maximum context
- World events (forest infestation, etc.) automatically logged
- Reputation changes tracked across all factions
- Party activities and quest sharing learned
- Full game state captured with every action

### ✅ AI-Powered Quest Generation
- **Hybrid system**: Templates checked first, AI generation as fallback
- Contextual quests based on:
  - Player level and quest history
  - Faction reputation
  - Recent 20 actions
  - Active story arcs
  - Current world state
- Auto-learning enabled: Generated quests feed back into context

### ✅ Dynamic NPC Dialogue
- Context-aware responses based on:
  - Player's faction reputation
  - Active/completed quests
  - World state (forest infestation, etc.)
  - NPC role and faction alignment
- Multiple dialogue types:
  - Greetings
  - Quest offers
  - Quest progress checks
  - Quest unavailable explanations
- Graceful fallback to static dialogue if AI unavailable

### ✅ Multi-Quest Story Arcs
- Generate branching narrative storylines
- 3 arc types: personal, faction, world
- Chapter-based progression
- Player choices tracked
- Auto-advance when chapter quests completed

## Setup

### 1. Install Dependencies

```bash
cd server_py
pip install -e .
```

This installs:
- `requests` - For Miriel API calls
- `python-dotenv` - For environment variables

### 2. Configure Miriel API Key

Create a `.env` file in `/server_py`:

```bash
cp .env.example .env
```

Edit `.env` and add your Miriel API key:

```
MIRIEL_API_KEY=your_actual_api_key_here
MIRIEL_API_URL=https://api.prod.miriel.ai
MIRIEL_AUTO_LEARNING=true
```

Get your API key at: https://miriel.ai

### 3. Run the Server

```bash
# From server_py directory
uvicorn app.main:app --reload --port 8787
```

The server will:
- Initialize Miriel client on startup
- Create new database tables (story_arcs, miriel_content_cache, etc.)
- Begin learning from all player actions

## How It Works

### Architecture

```
Player Action → apply_action.py
              ↓
         Learn in Miriel (all context)
              ↓
         Database + Miriel Project "questai"
              ↓
    Quest Generation / Dialogue Generation
              ↓
         Context-aware AI content
```

### Learning Flow

Every successful action triggers:

1. **Action Logging** (existing system)
2. **Miriel Learning** (new):
   - Player state (level, location, inventory)
   - Quest history (active, completed, archived)
   - Party membership and members
   - Faction reputations
   - World state snapshot
   - Action result and messages

### Quest Generation Flow

When a player tries to accept a quest:

1. Check `QUEST_TEMPLATES` first (templates take priority)
2. If not found, generate via Miriel with context:
   - Player history (last 20 actions)
   - Faction reputation
   - Active quests
   - World state
   - Story arcs
3. Parse AI response into Quest object
4. Cache for 1 hour
5. Auto-learn the generated quest

### Dialogue Generation Flow

When a player talks to an NPC:

1. Check if Miriel is enabled
2. Build context (reputation, quests, world state)
3. Generate contextual dialogue
4. Cache for 30 minutes
5. Auto-learn the dialogue
6. Fallback to static dialogue if AI fails

## Graceful Degradation

**The game works perfectly without Miriel configured!**

If `MIRIEL_API_KEY` is not set:
- Miriel client initializes but `enabled = False`
- All learning calls return `False` silently
- Quest generation falls back to templates
- Dialogue generation falls back to static responses
- No errors, no crashes - seamless operation

## Database Schema

### New Tables

**story_arcs**: Multi-quest narrative storylines
```sql
CREATE TABLE story_arcs (
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
```

**player_story_arcs**: Join table for player participation
```sql
CREATE TABLE player_story_arcs (
  player_id TEXT NOT NULL,
  arc_id TEXT NOT NULL,
  joined_at INTEGER NOT NULL,
  joined_turn INTEGER NOT NULL,
  choices_json TEXT DEFAULT '[]',
  PRIMARY KEY (player_id, arc_id)
);
```

**miriel_content_cache**: Cache AI responses
```sql
CREATE TABLE miriel_content_cache (
  cache_key TEXT PRIMARY KEY,
  content_type TEXT NOT NULL,       -- 'quest', 'dialogue', 'story_arc'
  content_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
```

## File Structure

```
server_py/app/
├── services/
│   ├── miriel_client.py          # Miriel API client (singleton)
│   └── miriel_prompts.py         # Prompt templates for AI queries
├── miriel_learning.py            # Event learning system
├── miriel_quests.py              # AI quest generation + story arcs
├── miriel_dialogue.py            # AI NPC dialogue generation
├── types_story_arcs.py           # Story arc data models
├── db.py                         # Database (includes new tables + functions)
├── world_quests.py               # Quest templates (modified for AI support)
├── engine/
│   ├── apply_action.py           # Main dispatcher (learning hook added)
│   └── actions/
│       ├── accept_quest.py       # Quest acceptance (AI support added)
│       └── talk.py               # NPC dialogue (AI integration added)
```

## API Examples

### Generate a Quest

```python
from app.miriel_quests import generate_quest_for_player
from app.types import Player

# Generate quest for player
quest = generate_quest_for_player(
    player=player,
    quest_id_hint="merchant_trouble",
    npc_id="merchant"
)

if quest:
    print(f"Generated: {quest.name}")
    print(f"Description: {quest.description}")
```

### Generate NPC Dialogue

```python
from app.miriel_dialogue import generate_npc_dialogue

dialogue = generate_npc_dialogue(
    player=player,
    npc_id="guard",
    npc_role="guard",
    dialogue_type="greeting"
)

if dialogue:
    print(f'Guard says: "{dialogue}"')
```

### Create Story Arc

```python
from app.miriel_quests import create_and_start_story_arc

arc_id = create_and_start_story_arc(
    player=player,
    arc_type="faction",
    chapters=3
)

if arc_id:
    print(f"Started story arc: {arc_id}")
```

## Monitoring

### Check Miriel Status

```python
from app.services.miriel_client import get_miriel_client

client = get_miriel_client()
print(f"Miriel enabled: {client.enabled}")
print(f"Auto-learning: {client.auto_learning_enabled}")
```

### View Learned Data

All data is stored in Miriel's "questai" project namespace. Access via Miriel dashboard or API.

### Cache Performance

Check cache hit rates:

```sql
SELECT content_type, COUNT(*) as cached_items
FROM miriel_content_cache
WHERE expires_at > strftime('%s', 'now') * 1000
GROUP BY content_type;
```

## Customization

### Adjust Cache TTL

Edit cache durations in:
- `miriel_quests.py`: Quest cache (default 1 hour)
- `miriel_dialogue.py`: Dialogue cache (default 30 min)

### Modify Prompts

Edit prompt templates in:
- `services/miriel_prompts.py`

Example:
```python
def build_quest_generation_prompt(...):
    prompt = f"""Generate a quest...

    CUSTOM REQUIREMENTS:
    - Must involve dragons
    - Reward should include rare items
    ...
    """
```

### Add New Dialogue Types

1. Add type to `miriel_dialogue.py`:
```python
type_instructions = {
    'greeting': "...",
    'farewell': "Generate a warm goodbye",  # New type
}
```

2. Use in talk.py:
```python
dialogue = generate_npc_dialogue(
    player, npc_id, npc_role, dialogue_type="farewell"
)
```

## Troubleshooting

### "AI features disabled" message

**Cause**: `MIRIEL_API_KEY` not set or invalid

**Fix**:
1. Check `.env` file exists in `server_py/`
2. Verify API key is correct
3. Restart server

### Quest generation returns None

**Causes**:
- Miriel API error
- Invalid JSON response
- Network issue

**Debug**:
```bash
# Check logs for [MIRIEL] messages
tail -f server.log | grep MIRIEL
```

**Fallback**: Template quests still work!

### Dialogue not generating

**Fallback behavior**: Static dialogue like "Hello there." is used

**Check**:
- Miriel API key valid
- Network connectivity
- Cache not causing stale responses

**Clear cache**:
```sql
DELETE FROM miriel_content_cache;
```

## Performance Considerations

### API Call Optimization

- **Caching**: 1 hour for quests, 30 min for dialogue
- **Auto-learning**: Async (doesn't block gameplay)
- **Graceful fallback**: Zero impact if Miriel unavailable

### Database Impact

- New tables are indexed for fast lookups
- Cache cleanup happens automatically (expires_at check)
- Learning doesn't slow down actions (exception handling)

## Future Enhancements

Potential additions:

1. **Dynamic World Events**
   - Generate world-changing events based on player actions
   - Adaptive difficulty based on player skill

2. **Personalized Item Descriptions**
   - Items remember their history
   - "This sword was wielded by..."

3. **NPC Memory System**
   - NPCs remember past interactions
   - Long-term relationships evolve

4. **Quest Chains**
   - Auto-generate follow-up quests
   - Branching storylines based on choices

## Support

For Miriel API support: https://miriel.ai/docs
For QuestAI integration issues: Check implementation plan in `/Users/andy/.claude/plans/pure-conjuring-swan.md`

---

**Implementation Complete!** 🎉

All 5 phases implemented:
- ✅ Phase 1: Foundation
- ✅ Phase 2: Learning System
- ✅ Phase 3: Quest Generation
- ✅ Phase 4: NPC Dialogue
- ✅ Phase 5: Story Arcs

The game now features fully dynamic AI-generated storylines while maintaining backward compatibility with template-based content.
