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

## 9. Companions (`app/companions.py`, `recruit`/`dismiss`/`companion`)

You can recruit an NPC you meet in the world to travel and fight at your side.
A companion is a *personal* ally inspired by that NPC — the original stays put
for everyone else — and you keep one at a time. Recruiting costs a coin signing
bonus, giving wealth one more place to go and the choice some weight.

The split mirrors the rest of the overhaul: **code is the referee, Miriel is the
personality.**

- **Deterministic combat (the referee).** Three archetypes, assigned stably
  from the source NPC (a healer joins as a **mender**; everyone else is split by
  id into **vanguard** / **outrider**):
  - *vanguard* — lands a flat blow on the monster every round you press an
    attack, and can take the finishing kill;
  - *mender* — heals you each round instead of swinging (and idles at full HP);
  - *outrider* — turns aside a fraction of every blow you take, and harries the
    enemy for a little damage.
  Loyalty grows one point per won encounter (0–100 → levels 1–5), scaling their
  contribution. All of it is roll-free and unit-tested.
- **AI personality (best-effort).** Joining, parting, and growing-closer lines
  are Miriel-voiced — but unlike location prose they *never* fail hard: if
  Miriel is unconfigured or returns nothing, a written fallback is used, so
  recruiting an ally works offline and under test. An ally's banter is flavour,
  not a hard dependency.

The companion is integrated into `fight` (the collapsed-encounter verb), persists
on the player (`companion_json`), and surfaces in `stats` and the web client.

**Your own path colours what your ally can do** (§14): one signature synergy
per archetype, applied in the same deterministic combat functions —
- a **Warden**'s steadiness bolsters their support: the ally's healing is +50%
  and its guard is firmer;
- a **Trickster**'s aggression drives them: the ally's strikes hit +50% harder;
- a **Channeler**'s attunement quickens the bond: loyalty grows twice as fast.

Percentage bonuses round half-up, so a "+50%" never rounds down to nothing.
The active synergy is shown in `companion` status.

## 10. Co-op raid bosses (`app/raids.py`, `raid` / `raid strike`)

The async social layer made loud. Where a community goal (§6) is chipped down by
everyone's *ordinary* play, a raid boss is chipped down by everyone's *deliberate*
blows: one great threat with a huge, world-level-scaled HP pool that no single
player can fell in a session. You `raid strike` to land a blow; the boss strikes
back (a single counter-blow is capped at a quarter of your health, so a raid is a
fight you withdraw from to heal — never one that two-shots you). Your companion
adds its damage to each strike.

The boss **manifests at the Warfront** — a static location one step from the
Town Square (`go warfront`). You must be there to strike it: a beat of travel
and gathering, not a button mashed from a tavern. The Warfront's name and
description re-skin to whichever threat currently holds it.

As the boss is worn down it fights through **phases** (the same idea as the
regular boss mechanics in `bosses.py`, each firing once at an HP threshold): it
**enrages** (hits harder), **self-heals** a slice of its health (a DPS check the
community must out-damage), and **summons adds** — ordinary monsters that spawn
at the Warfront for players to cut down with the normal `fight` verb.

When the boss finally falls:

- **every player who landed a blow is paid** a share of the spoils pool,
  proportional to the damage they did (with a floor, so even a single hit pays);
- **the finisher is crowned** — a coin bonus, the boss's trophy item, and their
  name written into the world's history (a `raid_defeated` world event and a
  `raid` echo at their location);
- **the boss's leftover adds disperse** from the Warfront;
- **the world visibly changes** (a world-state effect flips), and **the next
  threat immediately rises**, so the realm always has a great beast on the horizon.

The trophies (`dragon_heart`, `coral_crown`, `colossus_core`) aren't just curios:
each forges, with deep-tier materials, into a **best-in-slot relic** — the
Cinderwing Blade (+18 dmg), Tidewarden Plate (+12 def), and Colossus Maul
(+22 dmg) — via ordinary `craft` recipes, so raid spoils feed straight back into
the gear ladder.

It reuses the proven pieces: the community goal's atomic contribute-and-reward,
the bounty board's pay-out-to-many, and the echo/world-event history. The boss
lives in its own tables (`raid_bosses`, `raid_contributions`) with a
`damage_raid_boss` that — like monster combat — uses `BEGIN IMMEDIATE` so
concurrent strikers can't double-kill or lose damage. The active boss is surfaced
in every action's state for the web client (an HP bar + strike button).

## 11. Stakes on defeat (`app/defeat.py`)

Being beaten finally costs something — gently, as befits a casual shared world.
Every defeat in the game (monster combat, a lingering poison, a travel ambush,
the raid Warfront) now routes through one `apply_defeat`, so when you fall you:

- **scatter a fifth of the coin** you were carrying where you fell;
- **carry a `wounded` debuff** out of it that dulls your blows for a few combat
  actions — the one effect that follows you home (all others are cleared);
- **shake your companion's loyalty**, and they can **lose heart and desert** if
  you keep falling with little loyalty left;
- **leave a "fallen here" echo** at the spot for whoever passes through next.

Then you wake, recovered, back in town. Centralizing the five old copy-pasted
respawn blocks into one function is what makes the stakes consistent — and it's
the payoff for the two `# stake for a later system` hooks left in the companion
and raid code. The wound is shaken off by `rest` (the free recovery path also
binds it, even at full HP) or the temple `heal`; otherwise it simply ticks down
over a few combat actions.

## 12. The personal stronghold (`app/stronghold.py`)

The first thing in the game that is *yours alone*, and a long-horizon home for
the coin and loot a casual player piles up:

- **Tiers** — pour coin into it to raise it from a Campsite → Cabin → Cottage →
  Keep → Citadel (costs escalate 50 → 2500), a visible step forward that's yours;
- **A stash** — store items out of your pack; each tier holds more *kinds* of
  goods (6 → 40). The place to keep raid trophies, spare gear, and overflow safe;
- **Tribute** — a built stronghold earns a trickle of coin per real-time hour
  (2/hr → 40/hr), capped at 24 hours, so it rewards *returning* rather than
  idling. Lazily accrued like action points; claimed with `collect`.

It's all personal bookkeeping — no AI, no shared-world effect — so none of it
costs action points, and it persists on the player (`stronghold_level`,
`stash_json`, `stronghold_collected_at`). Surfaced in the web client as a panel
(build / collect / upgrade / per-item withdraw) with a `stash` shortcut on every
inventory row.

## 13. Onboarding & discovery (`app/guidance.py`, `next`)

The game grew a lot of systems; a new player shouldn't have to already know they
exist. `next` (also `guide`/`hint`) reads the player's current state and the
world around them and offers a few pointed nudges toward what they can do *now*:
equip the weapon in your pack, talk to the quest giver in the room, recruit the
ally standing here, found a stronghold once you can afford it, collect your
tribute, join the threat at the Warfront, explore the frontier underfoot, forge
that raid trophy, craft what your materials allow.

Every suggestion is **stateless and self-resolving**: it's derived purely from
present state, so it appears only while relevant and vanishes once you've done
the thing — a guide that *reads* the world rather than scripting a tutorial
sequence, with survival nudges (a wound, low HP) sorted to the top. New
characters are told to type `next`; the web client shows the suggestions as a
"What now?" panel of clickable commands, and they ride along in every action's
state so they stay live.

## 14. Build identity (`app/archetypes.py`, `path` / `learn`)

The one early choice that makes two characters play differently. At creation
(`create <name> <path>`, or `path <id>` later) you take one of three archetypes:

- **Warden** — *Stalwart:* +3 defense to every blow taken; a bruiser's kit
  (power_strike → second_wind → rend → bulwark → rallying_cry → crushing_blow).
- **Trickster** — *Deadly:* +3 damage to every blow landed; fast and bloody
  (quick_strike → rupture → power_strike → rend → lacerate → eviscerate).
- **Channeler** — *Attuned:* abilities recharge 30% faster; a caster's kit
  (firebolt → second_wind → cleave → rupture → chain_lightning → inferno).

Each path offers six abilities reaching level 12. The mid-tier picks (L10)
introduce a **buff** ability kind (Rallying Cry applies a self `strength`
effect) alongside deeper bleeds and wider area damage. The L12 **capstones
cost 2 skill points** — so with one point earned per level, high-level builds
can't simply collect everything and must choose which capstone to reach for.

The passives fold into the existing combat maths in one place each
(`total_attack_damage`, `defense_bonus`, and a single `cooldown_ms` helper
threaded through every cooldown site), so an archetype's effect is exact.

Abilities are no longer auto-granted by level. Levelling now grants **skill
points**, which you spend with `learn <ability>` on your path's pool (each
ability gated by a level). Two characters of different paths therefore field
different kits *and* different passives. Players from before archetypes
(`archetype = None`) fall back to a generalist pool of the original abilities,
so nothing they had breaks. The path is a one-time choice — once walked, it
can't be unwalked. The guidance engine nudges choosing a path and spending
skill points; the web client shows a path-picker and `learn` buttons.

## New commands

| Command | Effect |
| --- | --- |
| `fight [bold\|cautious] <target>` | Resolve a whole encounter in one action |
| `explore` | Open a frontier into a brand-new region |
| `note <text>` | Leave a note at your location |
| `bounty <coins> <monster>` / `bounties` | Post / list monster bounties |
| `goals` | Show the running community goal and your contribution |
| `raid` | Show the looming co-op raid boss and your share of the fight |
| `raid strike` | Land a blow on the realm's raid boss (it strikes back) |
| `recruit <npc>` | Hire an NPC as a companion (costs a coin signing bonus) |
| `companion` | Show your current ally, their archetype and loyalty |
| `dismiss` | Part ways with your companion |
| `stronghold` / `home` | Show your stronghold: tier, tribute, and stash |
| `build` | Found or upgrade your stronghold by one tier |
| `stash <item> [n]` / `unstash <item> [n]` | Store / withdraw goods from the stash |
| `collect` | Claim the coin tribute your stronghold has earned |
| `next` / `guide` | Contextual "what now?" — your best next steps right now |
| `create <name> <path>` / `path <id>` | Choose your archetype (warden/trickster/channeler) |
| `learn <ability>` | Spend a skill point on an ability of your path |
| `ap` | Show stats including action points |

## Testing

All systems have offline script tests in `server_py/` (run each with
`python3 test_<name>.py`): `test_content_registry.py`,
`test_action_points.py`, `test_living_world.py`, `test_regiongen.py`,
`test_world_rules_engine.py`, `test_sms.py`, `test_companions.py`,
`test_raids.py`, `test_defeat.py`, `test_stronghold.py`, `test_guidance.py`,
`test_cohesion.py` (an integration walk that exercises the Miriel-gated
move/look path), `test_archetypes.py`, plus the pre-existing suite.
