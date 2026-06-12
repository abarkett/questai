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

## The three questions that matter

- **Surprise:** did anything happen this session that you didn't see coming?
- **Pull:** when you stopped, was there something specific you wanted to do
  next session (a map to dig, a frontier to open, a bounty out)?
- **Presence:** did the world feel like other people exist in it?

If any answer is "no", that's the report to send — name the moment where the
feeling failed and the fix is usually one constant away.
