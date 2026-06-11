# QuestAI Overhaul: The Growing World

This document describes the systems added in the gameplay overhaul. The four
founding constraints are unchanged — multiplayer in one universe, casual to
jump in and out of, playable in a web client (and over SMS), AI-generated and
responsive story/plot/images — but the design now treats **AI as the content
factory and deterministic code as the referee**, and treats **short sessions
as the intended way to play**.

## 1. Action points (`app/action_points.py`)

Every world-changing action costs 1 AP; passive reads (look, stats, map,
journal, bounties, goals...) are free. AP regenerates in real time up to a cap
and accrues lazily — no background process.

- Defaults: 30 cap, 1 point per 3 minutes. Tune with `QUESTAI_AP_MAX` and
  `QUESTAI_AP_REGEN_SECONDS` (set regen `<= 0` to disable AP entirely).
- Why: levels the field between hardcore and casual players in one shared
  universe, makes 5-minute sessions first-class, bounds AI API spend per
  player, and maps directly onto SMS play.

## 2. Collapsed-encounter combat (`fight`)

`fight [bold|cautious] <target>` resolves a whole encounter in one action.
Stances trade damage dealt, damage taken, and the HP threshold where you
disengage (bold presses to 15% HP, cautious withdraws at 50%). The classic
blow-by-blow `attack` remains for duels and fine control.

## 3. Content registry (`app/content.py`)

World content now has two sources merged behind one lookup layer:

- the hand-authored Python catalogs (`world.py`, `world_entities.py`,
  `items.py`, `world_quests.py`) — the seed of the universe;
- the `gen_*` tables (`gen_locations`, `gen_exits`, `gen_entities`,
  `gen_items`, `gen_quests`, `regions`) — content minted at runtime.

Locations, items, recipes, NPCs, monsters, gather resources, bestiary
entries, and quest templates all resolve through the registry, so the engine
never cares whether content was authored or generated.

## 4. Region minting (`app/regiongen.py`, `explore`)

The world grows at its frontiers. Frontier locations (Riverside,
Spider Hollow, Frozen Cave, Magma Core — and every minted region's boss lair)
hint `Something here remains uncharted...`; the `explore` action mints the
region behind them:

- 4–6 connected locations, themed monster roster, a boss, a new crafting
  material, craftable weapon and armor, and a 3-quest chain from a local NPC;
- stats are budgeted by tier and enforced by `validate_region` — no region
  reaches the shared world unless its graph is connected and its numbers are
  inside budget;
- generation is deterministic (seeded) and works offline; Miriel, when
  configured, re-voices location prose but can never touch the numbers;
- regions are minted once and shared by everyone — one universe, one canon.
  The discoverer's name is written into the region's entry text forever;
- each boss lair is the next frontier, so the map grows without bound.

## 5. Async multiplayer: cooperation across time

Casual players are rarely online together, so the social layer works on
traces rather than presence:

- **Echoes** (`app/echoes.py`): kills, discoveries, and bounty claims log
  `deed` events; `look` (and the web sidebar) show what other players did at
  your location recently.
- **Notes** (`note <text>`): leave a short message at any location (last 20
  kept per spot, 3 shown).
- **Bounties** (`bounty <coins> <monster>`, `bounties`): coins are escrowed
  when posted; whoever lands a kill on that monster collects, atomically.
  You cannot claim your own bounty.
- **Login recap** (`app/recap.py`): returning after 6+ hours prepends a
  "while you were away" summary built from the world event log —
  Miriel-narrated when configured, plain bullets otherwise.

## 5b. Travel encounters (`app/encounters.py`)

Movement is the most-repeated action in the game, so it carries surprise:
roughly one move in five produces a moment — a hidden cache (coins or the
local gatherable), a wayside shrine (healing or a strength blessing), a
passing traveler who repeats *real* world news from the rumor pool, an omen
that points at unopened frontiers, or (in dangerous country) an ambush. The
table is danger-weighted, deterministic, and RNG-injectable like combat.

## 6. Community goals (`app/world_goals.py`, `goals`)

Rotating server-wide seasonal objectives (The Blight, Vermin Tide, Embers
Below) that every kill advances. On completion: world state flips, every
contributor is paid, the finisher is named in world history, and the next
season seeds itself. The shared world always has a heartbeat.

## 7. Data-driven world rules (`world_rules` table)

World evolution rules can now be content instead of code: JSON condition /
effect lists interpreted by `app/world_rules.py` (world-state checks, monster
counts, turn deltas → set state, spawn monsters, log events; per-rule
cooldowns). The original Python rules still run. A seeded "wandering beast"
rule provides a recurring ambient event.

## 8. Text-first rendering and SMS (`app/render_text.py`, `POST /sms`)

Every action result renders as one compact plain-text message with an HP/AP
status suffix. `POST /sms {"from": <handle>, "text": <command>}` gives full
play from a bare phone number: new senders are onboarded with
`create <name>`, then the entire command grammar applies.

**Miriel is required, and its failures are loud by design.** Location prose
has no fallback: if Miriel is unconfigured — or reachable but returning no
usable prose — `describe()` raises and the request fails hard, on every
surface (web, CLI, SMS). Silent degradation to authored text hides a broken
AI integration behind a working-looking game. (Quests and NPC dialogue keep
their original template fallbacks; descriptions and scene-prompt enrichment
do not.)

## New commands

| Command | Effect |
| --- | --- |
| `fight [bold\|cautious] <target>` | Resolve a whole encounter in one action |
| `explore` | Open a frontier into a brand-new region |
| `note <text>` | Leave a note at your location |
| `bounty <coins> <monster>` / `bounties` | Post / list monster bounties |
| `goals` | Show the running community goal and your contribution |
| `ap` | Show stats including action points |

## Testing

All systems have offline script tests in `server_py/` (run each with
`python3 test_<name>.py`): `test_content_registry.py`,
`test_action_points.py`, `test_living_world.py`, `test_regiongen.py`,
`test_world_rules_engine.py`, `test_sms.py`, plus the pre-existing suite.
