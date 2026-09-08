# QuestAI — 15-Minute Playtest Guide

A guided route that touches every new system, with the specific question to
ask yourself at each stop, and where the tuning knob lives if the answer is
"meh". Run the server with `QUESTAI_AP_REGEN_SECONDS=15` so AP never stalls
the test.

## The route

1. **Create / log in (Town Square).**
   *Should feel:* a world already in motion — the season callout, and
   "Word going around:" gossip on `look`.
   *If it doesn't:* rumor selection lives in `app/echoes.py::rumor_lines`.

2. **Walk: square → tavern → cellar door (Briar Gate or similar).**
   *Should feel:* "wait, the tavern has a *door*?" — and a whole region
   behind it with its own look, monsters, and an NPC offering a quest chain.
   *Knobs:* starter regions `QUESTAI_PREMINT`; themes in
   `app/regiongen.py::THEMES`.

3. **Keep moving, 8–10 rooms.** Watch for caches, shrines, travelers, omens,
   ambushes.
   *Should feel:* the road has dice in it — roughly 1 move in 5 should
   produce *something*.
   *Knob:* `ENCOUNTER_CHANCE` (and the weights) in `app/encounters.py`.

4. **Fight. A lot.** Use `fight bold <x>` on trash, `attack` or
   `fight cautious` on scary things.
   *Should feel:* one action = one meaningful encounter; stances should
   feel like real choices. Watch for trinkets ("Tucked in the leavings...")
   and the Blight counter ticking.
   *Knobs:* `STANCES`/`MAX_ROUNDS` in `app/engine/actions/fight.py`; drop
   bands atop `app/loot.py`.

5. **Get hurt and go broke on purpose.** Then `rest` somewhere safe.
   *Should feel:* scrappy, not punishing — time always works as a recovery
   currency.
   *Knob:* `REST_HP` in `app/engine/actions/rest.py`.

6. **If a torn map dropped:** follow it and `dig`.
   *Should feel:* anticipation during the walk, a little jackpot at the end.
   *Knobs:* `MAP_CHANCE`, `dig_payout` in `app/loot.py`.

7. **`explore` at a sealed frontier** (deep forest, foothills, spider
   hollow...).
   *Should feel:* the headline moment — your name written into a region no
   one has seen.

8. **Second character (other browser/incognito), walk where you've been.**
   *Should feel:* a inhabited world — your first character's echoes, notes,
   and discovery credit everywhere.

9. **Post a bounty (`bounty 10 Rat`), claim it with the other character.**
   *Should feel:* async multiplayer working — money moves between players
   who were never online together.

10. **Walk away for 35+ minutes, come back, act.**
    *Should feel:* the world moved without you — a one-line pulse (6h+ gets
    the full narrated recap).
    *Knobs:* `PULSE_GAP_MS` / `RECAP_GAP_MS` in `app/recap.py`.

## The campaign route (the spine)

Ask one question at every stop: *did I want to keep going?*

1. **Open the page with no saved hero.**
   *Should feel:* a title screen that already tells a story — the realm's
   current act and blurb, how much of it is put right and by whom, the
   threat looming, three paths to choose, one field for a name. With
   `GEMINI_API_KEY` set, title art is rendered for the act (one image shared
   by all; it changes when the act does). Forge a hero, then type `campaign`.
   *Should feel:* a story already written for *this* world — Act I named,
   four or five wrongs, an empty Legend. With Miriel up the act is authored
   from the live world at server start (check the log line
   `[CAMPAIGN] current act: … (miriel)`; `(authored)` means it fell back).
   *Knobs:* `GET /intro` in `app/main.py`; `web/src/app/welcome.tsx`; the
   prompt and the referee in `app/campaigngen.py`.
2. **`talk` to the patron a wrong names.**
   *Should feel:* a person who wants something put right, handing you the
   `undertake` line.
3. **`undertake <wrong>`, go do the deed.**
   *Should feel:* on the last kill / delivery, no turn-in — the Chronicle
   speaks (one narrated sentence about *you*), the title lands, the place
   reads restored on the next `look`.
4. **Second character (incognito), `campaign`.**
   *Should feel:* "✓ righted by <your first hero>" — a shared world.
5. **Right the rest, then `raid strike` at the Warfront until the climax falls.**
   *Should feel:* it stays dead; Act II opens and its text names the heroes
   of Act I and the beast they felled.
   *Knobs:* `_climax_stats` in `app/campaigngen.py`; `QUESTAI_CAMPAIGN_ACTS`.
6. **Keep acting for a dozen turns, then `news`.**
   *Should feel:* something *happened* while you were busy — wolves at a gate
   you can't pass, or a festival that makes rest cheap — and it reads like a
   reaction to what you did. Ignore an incursion and come back: it dug in.
   *Knobs:* `QUESTAI_INCIDENT_EVERY_TURNS` (set it to 3 for a playtest);
   `MAX_ACTIVE`, `_creature_stats` in `app/incidents.py`.
7. **`explore` at a frontier (the tavern cellar, the riverside towpath).**
   *Should feel:* a region written *for that door* — its name, creatures and
   keeper fit where you came from. The log line
   `[REGIONGEN] region N minted: … (theme: miriel)` confirms Miriel wrote it.

## The three questions that matter

- **Surprise:** did anything happen this session that you didn't see coming?
- **Pull:** when you stopped, was there something specific you wanted to do
  next session (a map to dig, a frontier to open, a bounty out)?
- **Presence:** did the world feel like other people exist in it?

If any answer is "no", that's the report to send — name the moment where the
feeling failed and the fix is usually one constant away.
