"""
The Restoration campaign: the spine of the game.

The realm starts *fallen*. A finite ledger of **wrongs** — a granary overrun, a
mill held by bandits, a temple with empty shelves, a dragon on the Warfront —
and the game is about putting them right. Each wrong is righted by a **deed**:
a simple kill / collect / visit quest using the ordinary quest machinery. What
makes it more than an errand is what righting it *does*, which no plain quest
ever did:

  1. the world **changes, permanently** — the location reads differently (in
     the web state *and* in the base Miriel narrates from), a world-state flag
     flips (which NPC dialogue sees), and sometimes a rule changes (a restocked
     temple heals for free);
  2. the **Chronicle records who did it**, by name, for everyone, forever;
  3. the righter earns a **title** — a chapter in their personal Legend.

Wrongs are grouped into **acts**, each with a raid boss as its climax. A felled
climax *stays* felled: the campaign is won act by act and ends in the realm's
restoration. Restoration is shared (one world; whoever rights a wrong rights
it for all), the Legend is personal (what *you* put right). Code is the
referee; Miriel narrates the change.

The acts themselves are **written by Miriel from the living world** as the
campaign reaches them (see app/campaigngen.py): what is wrong, what deed
rights it, how the place reads afterwards, who cares, what title it earns, and
what great threat closes the act — all authored from the actual places,
creatures, people, discoveries and Chronicle of *this* world, validated by
code, and persisted so every player shares one story. The hand-authored acts
below are the fallback when Miriel cannot write one.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from .types import Player, ActionResponse
from .types_quests import Quest, QuestObjective
from .db import (
    get_world_state,
    set_world_state,
    log_world_event,
    get_restorations,
    get_restoration,
    set_restoration_entry,
    mark_wrong_righted,
    get_player,
    upsert_player,
    get_campaign_acts,
)


class Wrong(BaseModel):
    id: str
    title: str                     # "Rats in the Granary"
    blurb: str                     # the fallen state, as the Chronicle names it
    deed: str                      # what must be done (player-facing)
    deed_type: str                 # kill | collect | visit | climax
    target: str
    required: int = 1
    patron: str                    # NPC name who cares about this wrong
    location: Optional[str] = None # location whose description changes when righted
    restored: Optional[str] = None # that location's description once righted
    flag: str                      # world_state key flipped to "true"
    title_earned: str              # Legend title for the righter
    righted_text: str              # narration when it is righted


class Act(BaseModel):
    index: int
    name: str
    blurb: str
    wrongs: List[Wrong]
    climax_boss: str               # raid boss name (see app/raids.py)
    act_title: str                 # title for everyone who righted a wrong in it
    completion_text: str
    climax: Optional[dict] = None  # generated raid spec (None: hand-authored boss in raids.py)
    source: str = "authored"       # authored | miriel | skeleton


# The hand-authored acts: the fallback story when Miriel can't write one for
# an index. (Still exported as ACTS for older imports.)
AUTHORED_ACTS: List[Act] = [
    Act(
        index=0,
        name="The Town Besieged",
        blurb="The town's own doorstep is overrun. Before the realm can be reclaimed, home must be made safe.",
        climax_boss="The Ashen Dragon",
        act_title="Defender of the Town",
        completion_text=(
            "The town breathes. The granary is full, the mill turns, the temple is stocked, "
            "the roads are walked without fear — and the sky over the Warfront is clear. "
            "The first act of the realm's restoration is written."
        ),
        wrongs=[
            Wrong(
                id="granary_rats",
                title="Rats in the Granary",
                blurb="Rats pour from the Forest into the town granary; the stores are being eaten hollow.",
                deed="Cull the rats in the Forest (slay 2 Rats).",
                deed_type="kill", target="Rat", required=2,
                patron="Town Warden",
                location="town_square",
                restored=(
                    "A cobblestone plaza with a fountain. The granary doors stand open again and "
                    "the rat-plague is broken; people bustle about with easy faces."
                ),
                flag="granary_safe",
                title_earned="Granary's Guard",
                righted_text="The last of the swarm is cut down. The granary is safe, and the town will eat this winter.",
            ),
            Wrong(
                id="mill_bandits",
                title="Bandits at the Old Mill",
                blurb="Bandits squat in the Abandoned Mill; no grain has been ground in a season.",
                deed="Drive the bandit from the Abandoned Mill (slay 1 Bandit).",
                deed_type="kill", target="Bandit", required=1,
                patron="Old Merchant",
                location="old_mill",
                restored=(
                    "The old mill turns again. Flour dust hangs in the sunlit air, the squatters' "
                    "rope and sacks are gone, and the wheel groans steadily over the water."
                ),
                flag="mill_reclaimed",
                title_earned="Keeper of the Mill",
                righted_text="The bandit flees the mill. By morning the wheel is turning, and flour reaches the market.",
            ),
            Wrong(
                id="temple_stores",
                title="The Temple's Empty Shelves",
                blurb="The temple's stores of healing herbs are gone; the priest turns the wounded away.",
                deed="Gather 3 Herb Bundles for the temple.",
                deed_type="collect", target="herb_bundle", required=3,
                patron="Temple Priest",
                location="temple",
                restored=(
                    "A quiet sanctuary of white stone and candlelight. Shelves along the wall are "
                    "lined with dried herbs, and the priest tends the wounded freely beneath the altar."
                ),
                flag="temple_stocked",
                title_earned="Temple's Provider",
                righted_text="The priest takes the herbs with both hands. 'The temple asks nothing of the wounded now,' she says.",
            ),
            Wrong(
                id="deep_road_wolves",
                title="Wolves on the Deep Road",
                blurb="A wolf-pack haunts the Deep Forest; the game trail to the wilds is closed.",
                deed="Scatter the pack in the Deep Forest (slay 2 Wolves).",
                deed_type="kill", target="Wolf", required=2,
                patron="Huntmaster",
                location="deep_forest",
                restored=(
                    "Tall trees and a trodden, quiet game trail. The wolf-pack that haunted this "
                    "road is scattered; hunters pass through again."
                ),
                flag="deep_road_safe",
                title_earned="Roadwarden",
                righted_text="The pack breaks and runs. The deep road is open, and the wilds beyond it are within reach.",
            ),
            Wrong(
                id="hollow_spider",
                title="The Silk-Choked Hollow",
                blurb="A venomous spider has webbed Spider Hollow shut; nothing goes in or out.",
                deed="Clear Spider Hollow (slay 1 Venomous Spider).",
                deed_type="kill", target="Venomous Spider", required=1,
                patron="Huntmaster",
                location="spider_hollow",
                restored=(
                    "A cleft in the rock, its webs cut away and burned. Daylight reaches the "
                    "hollow floor for the first time in years."
                ),
                flag="hollow_cleared",
                title_earned="Hollowbane",
                righted_text="The spider falls and its webs are torn down. The hollow is open to the sky.",
            ),
            Wrong(
                id="ashen_dragon",
                title="The Ashen Dragon Holds the Warfront",
                blurb="A dragon of cinder wheels over the muster-ground, raining fire on every road.",
                deed="Fell The Ashen Dragon at the Warfront (`raid strike` — the whole realm may join).",
                deed_type="climax", target="The Ashen Dragon", required=1,
                patron="Town Warden",
                flag="ashen_dragon_felled",
                title_earned="Dragonsbane",
                righted_text="The Ashen Dragon falls from the sky. The roads are clear of fire.",
            ),
        ],
    ),
    Act(
        index=1,
        name="The Wilds Reclaimed",
        blurb="With the town secure, the wilds beyond it must be won back from what took them.",
        climax_boss="The Drowned King",
        act_title="Reclaimer of the Wilds",
        completion_text=(
            "The wilds are reclaimed. Goblins routed, the pass and the glacier freed, the deep "
            "quiet — and the Drowned King sunk beneath still water. The second act is written."
        ),
        wrongs=[
            Wrong(
                id="goblin_warband",
                title="The Goblin Warband",
                blurb="Goblins raid from the Deep Forest; the hunters' camps are burned.",
                deed="Break the warband (slay 2 Goblins).",
                deed_type="kill", target="Goblin", required=2,
                patron="Huntmaster", location=None,
                flag="goblins_routed", title_earned="Goblin-Router",
                righted_text="The warband scatters into the trees. The hunters return to their camps.",
            ),
            Wrong(
                id="harpy_roost",
                title="Harpies Over the Pass",
                blurb="Harpies roost above the Mountain Pass; no caravan dares the crossing.",
                deed="Clear the roost (slay 1 Harpy).",
                deed_type="kill", target="Harpy", required=1,
                patron="Mountain Ranger",
                location="mountain_pass",
                restored="A high, wind-scoured pass. The harpy roost is empty, and the first caravan in a year winds through below.",
                flag="pass_cleared", title_earned="Sky-Clearer",
                righted_text="The harpy plummets from the crag. The pass is open.",
            ),
            Wrong(
                id="frozen_troll",
                title="The Troll in the Glacier",
                blurb="An Ice Troll holds the Frozen Cave; the crystal-cutters have fled.",
                deed="Slay the Ice Troll in the Frozen Cave.",
                deed_type="kill", target="Ice Troll", required=1,
                patron="Mountain Ranger",
                location="frozen_cave",
                restored="A cavern of blue ice, silent now. Crystal-cutters' picks ring out from the far wall.",
                flag="glacier_freed", title_earned="Frost-Breaker",
                righted_text="The troll shatters. The glacier is free, and the cutters go back to work.",
            ),
            Wrong(
                id="cavern_troll",
                title="The Thing in the Cavern",
                blurb="A Cave Troll has made the Echoing Cavern its lair; the road below is lost.",
                deed="Slay the Cave Troll in the Echoing Cavern.",
                deed_type="kill", target="Cave Troll", required=1,
                patron="The Wanderer",
                location="cavern",
                restored="The cavern echoes only with dripping water now. The stair to the deep lies open.",
                flag="cavern_quiet", title_earned="Deep-Delver",
                righted_text="The troll is slain. The cavern is quiet, and the way down is open.",
            ),
            Wrong(
                id="drowned_king",
                title="The Drowned King Rises",
                blurb="A crowned horror walks out of the floodwaters with the drowned at its heel.",
                deed="Fell The Drowned King at the Warfront (`raid strike`).",
                deed_type="climax", target="The Drowned King", required=1,
                patron="Town Warden",
                flag="drowned_king_felled", title_earned="Kingsbane",
                righted_text="The Drowned King sinks. The floods recede.",
            ),
        ],
    ),
    Act(
        index=2,
        name="The Deep Restored",
        blurb="What stirs beneath the realm must be stilled, or nothing above it is truly safe.",
        climax_boss="The Colossus of Dust",
        act_title="Restorer of the Realm",
        completion_text=(
            "The deep is stilled and the Colossus is dust. From the granary to the great forge, "
            "the realm is restored — and the Chronicle names every hand that restored it."
        ),
        wrongs=[
            Wrong(
                id="obsidian_golem",
                title="The Golem in the Gallery",
                blurb="An Obsidian Golem paces the Obsidian Gallery; the mythril veins are unworkable.",
                deed="Break the Obsidian Golem.",
                deed_type="kill", target="Obsidian Golem", required=1,
                patron="The Wanderer", location=None,
                flag="gallery_stilled", title_earned="Stone-Breaker",
                righted_text="The golem cracks and crumbles. The gallery is still.",
            ),
            Wrong(
                id="sulfur_drake",
                title="The Drake of the Vents",
                blurb="A Sulfur Drake nests in the Sulfur Vents; the deep road is choked with fumes.",
                deed="Slay the Sulfur Drake.",
                deed_type="kill", target="Sulfur Drake", required=1,
                patron="The Wanderer", location=None,
                flag="vents_quelled", title_earned="Drake-Slayer",
                righted_text="The drake is slain. The vents cool.",
            ),
            Wrong(
                id="forge_guardian",
                title="The Silent Forge",
                blurb="The Forge Guardian bars the Great Forge; no relic has been struck in an age.",
                deed="Defeat the Forge Guardian.",
                deed_type="kill", target="Forge Guardian", required=1,
                patron="The Wanderer", location=None,
                flag="forge_rekindled", title_earned="Forge-Master",
                righted_text="The guardian falls silent. The great forge is rekindled.",
            ),
            Wrong(
                id="dust_colossus",
                title="The Walking Mountain",
                blurb="A mountain stands up and begins to walk.",
                deed="Fell The Colossus of Dust at the Warfront (`raid strike`).",
                deed_type="climax", target="The Colossus of Dust", required=1,
                patron="Town Warden",
                flag="dust_colossus_felled", title_earned="Colossus-Feller",
                righted_text="The Colossus crumbles into a hill of sand. The ground stops shaking.",
            ),
        ],
    ),
]

ACTS = AUTHORED_ACTS  # legacy alias; live code uses get_acts()

CAMPAIGN_FLAG = "realm_restored"


def now_ms() -> int:
    return int(time.time() * 1000)


# -------------------------------------------------
# The acts of this world
# -------------------------------------------------

# Acts are immutable once written, so they are cached by count: a new row is
# the only thing that can change the list.
_acts_cache: Dict[int, Act] = {}


def _load_acts() -> List[Act]:
    rows = get_campaign_acts()
    if len(rows) != len(_acts_cache) or any(r["act_index"] not in _acts_cache for r in rows):
        _acts_cache.clear()
        for r in rows:
            _acts_cache[r["act_index"]] = Act(**r["data"])
    return [_acts_cache[i] for i in sorted(_acts_cache)]


def _author(index: int, previous: List[Act]) -> Act:
    from .campaigngen import author_act
    fallback = AUTHORED_ACTS[index].model_dump() if index < len(AUTHORED_ACTS) else None
    data = author_act(index, previous, authored_fallback=fallback)
    _acts_cache.clear()
    return Act(**data)


def max_acts() -> int:
    from .campaigngen import max_acts as _max
    return _max()


def get_acts() -> List[Act]:
    """Every act written so far. Writing happens here, lazily: the opening act
    the first time anyone asks, and each next act once the one before it is
    complete — so the story is always authored from the world as it stands."""
    acts = _load_acts()
    if not acts:
        acts = [_author(0, [])]
    while len(acts) < max_acts() and is_act_complete(acts[-1].index):
        acts = acts + [_author(len(acts), acts)]
    return acts


def ensure_campaign() -> Act:
    """Startup hook: make sure the opening act exists. Returns the current or
    last act."""
    acts = get_acts()
    return current_act() or acts[-1]


def climax_spec(index: int) -> Optional[dict]:
    """The generated raid spec for act `index`'s climax, if it has one."""
    for act in _load_acts():
        if act.index == index:
            return act.climax
    return None


def climax_specs() -> List[dict]:
    return [a.climax for a in _load_acts() if a.climax]


# -------------------------------------------------
# Lookups
# -------------------------------------------------

def find_wrong(wrong_id: str) -> Optional[Tuple[Act, Wrong]]:
    for act in get_acts():
        for w in act.wrongs:
            if w.id == wrong_id:
                return act, w
    return None


def wrong_for_boss(boss_name: str) -> Optional[Tuple[Act, Wrong]]:
    for act in get_acts():
        for w in act.wrongs:
            if w.deed_type == "climax" and w.target == boss_name:
                return act, w
    return None


def righted_map() -> Dict[str, dict]:
    return {r["wrong_id"]: r for r in get_restorations()}


def is_righted(wrong_id: str) -> bool:
    return get_restoration(wrong_id) is not None


def _act_flag(index: int) -> str:
    return f"act_{index}_complete"


def is_act_complete(index: int) -> bool:
    return (get_world_state(_act_flag(index)) or "") == "true"


def current_act() -> Optional[Act]:
    """The act the realm is fighting through now; None once all are won."""
    for act in get_acts():
        if not is_act_complete(act.index):
            return act
    return None


def current_act_index() -> Optional[int]:
    act = current_act()
    return act.index if act else None


def campaign_complete() -> bool:
    return current_act() is None


def restored_description(location_id: str) -> Optional[str]:
    """If a righted wrong re-describes this location, that description. The
    latest act's restoration wins if several touched the same place."""
    done = righted_map()
    found = None
    for act in _load_acts():
        for w in act.wrongs:
            if w.location == location_id and w.restored and w.id in done:
                found = w.restored
    return found


def deed_quest_id(wrong_id: str) -> str:
    return f"deed__{wrong_id}"


def grant_title(player: Player, title: str) -> bool:
    if title in (player.titles or []):
        return False
    player.titles = list(player.titles or []) + [title]
    return True


# -------------------------------------------------
# Player-facing state
# -------------------------------------------------

def wrong_state(player: Player, w: Wrong, done: Dict[str, dict]) -> str:
    """'righted' | 'active' (you hold its deed) | 'open'."""
    if w.id in done:
        return "righted"
    if deed_quest_id(w.id) in (player.active_quests or {}):
        return "active"
    if deed_quest_id(w.id) in (player.completed_quests or {}):
        return "active"
    return "open"


def _deed_progress(player: Player, w: Wrong) -> str:
    q = (player.active_quests or {}).get(deed_quest_id(w.id))
    if not q:
        return ""
    from .engine.quest_progress import current_objectives
    parts = [f"{o.progress}/{o.required}" for o in current_objectives(q)]
    return ", ".join(parts)


def next_wrong_for(player: Player) -> Optional[Tuple[Wrong, str]]:
    """The wrong to point the player at: a deed they already hold, else the
    first open one in the current act. Climaxes are pointed at last."""
    act = current_act()
    if not act:
        return None
    done = righted_map()
    ordered = [w for w in act.wrongs if w.deed_type != "climax"] + \
              [w for w in act.wrongs if w.deed_type == "climax"]
    for w in ordered:
        if wrong_state(player, w, done) == "active":
            return w, "active"
    for w in ordered:
        if wrong_state(player, w, done) == "open":
            return w, "open"
    return None


# -------------------------------------------------
# Actions
# -------------------------------------------------

def undertake(player: Player, wrong_id: str) -> ActionResponse:
    """Take up a wrong's deed as a quest."""
    from .engine.state_view import build_action_state

    key = (wrong_id or "").strip().lower().replace(" ", "_")
    found = find_wrong(key)
    if not found:
        return ActionResponse(ok=False, error="No such wrong is written in the Chronicle. See `campaign`.")
    act, w = found

    cur = current_act()
    if cur is None:
        return ActionResponse(ok=False, error="The realm is restored. There is nothing left to put right.")
    if act.index != cur.index:
        if act.index < cur.index:
            return ActionResponse(ok=False, error=f"{w.title} was righted in an earlier act.")
        return ActionResponse(ok=False, error=f"{w.title} belongs to a later act — finish {cur.name} first.")
    if is_righted(w.id):
        r = get_restoration(w.id)
        return ActionResponse(ok=False, error=f"{w.title} has already been put right by {r['righted_by_name']}.")
    if w.deed_type == "climax":
        return ActionResponse(
            ok=False,
            error=f"{w.title} is the act's great threat — it is felled at the Warfront (`raid strike`), not undertaken alone.",
        )

    qid = deed_quest_id(w.id)
    if qid in player.active_quests or qid in player.completed_quests:
        return ActionResponse(ok=False, error=f"You have already taken up {w.title}. See `journal`.")

    player.active_quests[qid] = Quest(
        quest_id=qid,
        name=w.title,
        description=w.deed,
        objectives=[QuestObjective(type=w.deed_type, target=w.target, required=w.required)],
        rewards={},
        status="accepted",
        accepted_at=now_ms(),
    )
    upsert_player(player)
    return ActionResponse(
        ok=True,
        messages=[
            f"You take up the deed: {w.title}.",
            w.blurb,
            f"Deed: {w.deed}",
            "Put it right, and the Chronicle will carry your name.",
        ],
        state=build_action_state(player, scene_dirty=False),
    )


def right_wrong(wrong_id: str, player: Player) -> List[str]:
    """Right a wrong in the shared world, crediting this player if they're first.
    Flips the flag, writes the Chronicle, grants the title, and checks the act."""
    found = find_wrong(wrong_id)
    if not found:
        return []
    act, w = found
    messages: List[str] = []

    first = mark_wrong_righted(w.id, act.index, player.player_id, player.name)
    if first:
        set_world_state(w.flag, "true")
        # The Chronicle's own words for this righting — who, how, with whom —
        # narrated from the deed as it was actually done (best-effort).
        entry = None
        try:
            from .campaigngen import narrate_chronicle_entry
            entry = narrate_chronicle_entry(w, player)
            if entry:
                set_restoration_entry(w.id, entry)
        except Exception as e:
            print(f"[RESTORATION] chronicle entry failed: {e}")
        log_world_event(
            event_type="wrong_righted",
            location_id=w.location,
            data={
                "wrong_id": w.id,
                "act": act.index,
                "player_id": player.player_id,
                "player_name": player.name,
                "description": entry or f"{w.title} — put right by {player.name}. {w.righted_text}",
            },
        )
        from .echoes import record_deed
        try:
            record_deed(player, w.location or player.location, f"{player.name} put right: {w.title}", kind="restoration")
        except Exception:
            pass
        messages.append(w.righted_text)
        messages.append(f"The Chronicle records it: {w.title} — righted by {player.name}.")
        if entry:
            messages.append(f"“{entry}”")
        if grant_title(player, w.title_earned):
            messages.append(f"Your Legend grows: you are named {w.title_earned}.")
        messages.extend(_check_act(act, player))
    else:
        r = get_restoration(w.id)
        who = r["righted_by_name"] if r else "another"
        messages.append(f"{w.title} was put right by {who} while you worked. The realm thanks you all the same.")
    return messages


def settle_deeds(player: Player) -> List[str]:
    """Post-action hook: any deed quest that just completed rights its wrong.
    Consumes collect items (they're delivered), then archives the quest."""
    messages: List[str] = []
    for qid in list((player.completed_quests or {}).keys()):
        if not qid.startswith("deed__"):
            continue
        quest = player.completed_quests[qid]
        if quest.status != "completed":
            continue
        wrong_id = qid[len("deed__"):]
        from .engine.quest_progress import consume_quest_items
        messages.extend(consume_quest_items(player, quest))
        messages.extend(right_wrong(wrong_id, player))
        quest.status = "turned_in"
        quest.turned_in_at = now_ms()
        player.archived_quests[qid] = player.completed_quests.pop(qid)
    return messages


def climax_felled(boss_name: str, finisher: Player) -> List[str]:
    """Raid hook: felling an act's great threat rights its climax wrong."""
    found = wrong_for_boss(boss_name)
    if not found:
        return []
    _act, w = found
    return right_wrong(w.id, finisher)


def _check_act(act: Act, player: Player) -> List[str]:
    """If every wrong in the act is righted, complete it: flag, history, and
    the act's title for everyone who righted something in it."""
    if is_act_complete(act.index):
        return []
    done = righted_map()
    if not all(w.id in done for w in act.wrongs):
        return []

    set_world_state(_act_flag(act.index), "true")
    messages = [f"— {act.name} is complete. —", act.completion_text]
    log_world_event(
        event_type="act_complete",
        location_id=None,
        data={"act": act.index, "name": act.name, "description": act.completion_text},
    )

    # Everyone who righted a wrong in this act shares its title.
    righters = {done[w.id]["righted_by_id"] for w in act.wrongs if w.id in done}
    for pid in righters:
        target = player if pid == player.player_id else get_player(pid)
        if not target:
            continue
        if grant_title(target, act.act_title):
            if target is player:
                messages.append(f"Your Legend grows: you are named {act.act_title}.")
            else:
                upsert_player(target)

    if act.index + 1 >= max_acts():
        set_world_state(CAMPAIGN_FLAG, "true")
        log_world_event(
            event_type="realm_restored",
            location_id=None,
            data={"description": "The realm is restored. The Chronicle is complete."},
        )
        messages.append("The realm is restored. Every hand that restored it is written in the Chronicle.")
    else:
        # The next act is written NOW, from the world these players made —
        # the Chronicle they filled, the regions they opened, the beast they
        # felled all become its raw material.
        try:
            nxt = get_acts()[act.index + 1]
            messages.append(f"A new act begins: {nxt.name}. {nxt.blurb}")
        except Exception as e:
            print(f"[RESTORATION] next act not yet written: {e}")
            messages.append("A new act of the Restoration is being written. See `campaign` soon.")
    return messages


# -------------------------------------------------
# Status, guidance, and the web
# -------------------------------------------------

def campaign_status(player: Player) -> ActionResponse:
    """`campaign` / `chronicle`: the ledger of wrongs and your Legend."""
    from .engine.state_view import build_action_state

    done = righted_map()
    messages: List[str] = []
    act = current_act()
    if act is None:
        messages.append("THE REALM IS RESTORED. The Chronicle is complete.")
    else:
        messages.append(f"Act {act.index + 1}: {act.name} — {act.blurb}")

    acts = get_acts()
    for a in acts:
        if act is not None and a.index > act.index:
            messages.append(f"Act {a.index + 1}: {a.name} — (not yet)")
            continue
        if act is not None and a.index == act.index:
            pass
        elif a.index != (act.index if act else -1):
            messages.append(f"Act {a.index + 1}: {a.name} — complete.")
        for w in a.wrongs:
            state = wrong_state(player, w, done)
            if state == "righted":
                messages.append(f"  ✓ {w.title} — righted by {done[w.id]['righted_by_name']}")
                if done[w.id].get("entry"):
                    messages.append(f"      “{done[w.id]['entry']}”")
            elif act is not None and a.index == act.index:
                if state == "active":
                    messages.append(f"  … {w.title} — underway ({_deed_progress(player, w)}). {w.deed}")
                elif w.deed_type == "climax":
                    messages.append(f"  ! {w.title} — {w.deed}")
                else:
                    messages.append(f"  • {w.title} — `undertake {w.id}`. {w.deed}")

    if player.titles:
        messages.append("Your Legend: " + ", ".join(player.titles))
    else:
        messages.append("Your Legend is unwritten. Put a wrong right and it begins.")

    return ActionResponse(ok=True, messages=messages, state=build_action_state(player, scene_dirty=False))


def campaign_summary(player: Player) -> dict:
    """Compact campaign state for the web client."""
    done = righted_map()
    act = current_act()
    wrongs = []
    if act is not None:
        for w in act.wrongs:
            state = wrong_state(player, w, done)
            wrongs.append({
                "id": w.id,
                "title": w.title,
                "blurb": w.blurb,
                "deed": w.deed,
                "status": state,
                "righted_by": done[w.id]["righted_by_name"] if w.id in done else None,
                "entry": done[w.id].get("entry") if w.id in done else None,
                "command": (f"undertake {w.id}" if state == "open" and w.deed_type != "climax" else None),
                "progress": _deed_progress(player, w) if state == "active" else "",
                "climax": w.deed_type == "climax",
            })
    return {
        "complete": act is None,
        "act_index": act.index if act else max_acts(),
        "acts_total": max_acts(),
        "act_name": act.name if act else "The Realm Restored",
        "act_blurb": act.blurb if act else "Every wrong is put right. The Chronicle is complete.",
        "act_source": act.source if act else None,
        "wrongs": wrongs,
        "titles": list(player.titles or []),
    }


def patron_lines(npc_name: str, player: Player) -> List[str]:
    """What an NPC says about the wrongs they care about — the narrative
    doorway into the campaign. Miriel voices the line with the Chronicle in
    view (who righted it, what was written); the engine always follows it
    with the exact ledger line, so the *task* is never lost in the prose. A
    deterministic line stands in when Miriel does not answer."""
    act = current_act()
    if act is None:
        return []
    done = righted_map()
    lines: List[str] = []
    for w in act.wrongs:
        if w.patron != npc_name:
            continue
        state = wrong_state(player, w, done)
        progress = _deed_progress(player, w) if state == "active" else ""
        voiced = None
        try:
            from .campaigngen import voice_patron_line
            voiced = voice_patron_line(npc_name, w, state, player, done.get(w.id), progress)
        except Exception as e:
            print(f"[CAMPAIGN] patron voice failed: {e}")

        if state == "righted":
            who = done[w.id]["righted_by_name"]
            you = "You" if done[w.id]["righted_by_id"] == player.player_id else who
            lines.append(f'"{voiced}"' if voiced else f'"{w.title} is put right — {you} saw to that. The realm remembers."')
        elif state == "active":
            lines.append((f'"{voiced}"' if voiced else '"How goes it? Do not fail us."')
                         + f" — {w.title}: {progress}. {w.deed}")
        elif w.deed_type == "climax":
            lines.append((f'"{voiced}"' if voiced else f'"{w.blurb} Only the whole realm together can fell it."')
                         + f" — {w.title}: {w.deed}")
        else:
            lines.append((f'"{voiced}"' if voiced else f'"{w.blurb} Will you put it right?"')
                         + f" — {w.title}: {w.deed} (`undertake {w.id}`)")
    return lines
