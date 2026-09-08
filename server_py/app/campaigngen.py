"""
The generated campaign: Miriel authors each act of the Restoration from the
living world.

Nothing about the campaign is hand-written in play. When an act begins, the
code assembles a *dossier* of the world as it actually is right now — every
place (hand-authored or minted), every creature and where it prowls, every NPC,
what can be gathered, the Chronicle so far (who put what right), the regions
players discovered and who discovered them, the last great threat and who
felled it, the recent world events — and asks Miriel to author the next act
from it: its wrongs, the deed that rights each one, the place that changes and
how it reads once restored, the patron who cares, the title earned, and the
great threat that is the act's climax.

Code is the referee. Miriel may only name targets that exist (validated
against the dossier), gets its structural mistakes fed back once for repair,
and never chooses a number: stats, budgets, ids and flags are assigned here.
If Miriel is unavailable, or its answer cannot be made sound, the hand-authored
act for that index (or, past those, a procedural skeleton) stands in — so the
campaign always exists, but with Miriel it is *written from what the players
did*.

Acts are authored once and persisted (campaign_acts); they never change after
that, so every player is playing the same story.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import db
from . import single_flight

# Prompt markers. Tests install a responder that keys off these to answer the
# right kind of query with the right kind of content.
ACT_MARKER = "[[CAMPAIGN_ACT]]"
CHRONICLE_MARKER = "[[CHRONICLE_ENTRY]]"
PATRON_MARKER = "[[PATRON_LINE]]"

DEFAULT_MAX_ACTS = 3


def max_acts() -> int:
    """How many acts the Restoration runs before the realm is restored."""
    try:
        return max(1, int(os.getenv("QUESTAI_CAMPAIGN_ACTS", str(DEFAULT_MAX_ACTS))))
    except ValueError:
        return DEFAULT_MAX_ACTS


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40]


# ---------------------------------------------------------------------------
# The dossier: the world as it is, for the loremaster to write from
# ---------------------------------------------------------------------------

def world_dossier(act_index: int, previous_acts: list) -> Dict[str, Any]:
    from .content import all_location_ids, get_location_or_none, monster_catalog, generated_npcs_at, resource_at
    from .world_entities import WORLD_ENTITIES
    from .items import ITEMS, get_item
    from .engine.entities import world_level

    regions = {r["region_id"]: r for r in db.list_regions()}

    # Places.
    locations: List[Dict[str, Any]] = []
    for lid in all_location_ids():
        loc = get_location_or_none(lid)
        if not loc:
            continue
        row = db.get_gen_location(lid)
        region = regions.get(row["region_id"]) if row and row.get("region_id") else None
        entry: Dict[str, Any] = {"id": lid, "name": loc.name, "description": (loc.description or "")[:160]}
        if region:
            entry["region"] = region["name"]
            if region.get("discovered_by"):
                entry["discovered_by"] = region["discovered_by"]
        locations.append(entry)

    # Creatures: catalog (static + minted), one line per name.
    monsters: Dict[str, Dict[str, Any]] = {}
    for lid, e in monster_catalog():
        m = monsters.setdefault(e.name, {"name": e.name, "locations": [], "hp": e.hp, "attack": e.attack, "count": 0})
        if lid not in m["locations"]:
            m["locations"].append(lid)
        m["count"] += 1

    # People.
    npcs: List[Dict[str, Any]] = []
    seen_npc = set()
    for lid, ents in WORLD_ENTITIES.items():
        for e in ents:
            if e.type == "npc" and e.name not in seen_npc:
                seen_npc.add(e.name)
                npcs.append({"name": e.name, "location": lid, "role": getattr(e, "role", None)})
    for lid in all_location_ids():
        for e in generated_npcs_at(lid):
            if e.name not in seen_npc:
                seen_npc.add(e.name)
                npcs.append({"name": e.name, "location": lid, "role": getattr(e, "role", None)})

    # Things that can actually be gathered or won.
    from .world_quests import get_valid_quest_targets
    item_ids = set(get_valid_quest_targets()["items"])
    for lid in all_location_ids():
        r = resource_at(lid)
        if r:
            item_ids.add(r)
    for row in db.get_all_gen_items():
        if (row["data"] or {}).get("type") == "material":
            item_ids.add(row["item_id"])
    items = []
    for iid in sorted(item_ids):
        it = get_item(iid) or ITEMS.get(iid)
        if it:
            items.append({"id": iid, "name": it.name})

    # The story so far.
    chronicle = []
    prev_wrongs = {w.id: (a, w) for a in previous_acts for w in a.wrongs}
    for r in db.get_restorations():
        found = prev_wrongs.get(r["wrong_id"])
        chronicle.append({
            "wrong": found[1].title if found else r["wrong_id"],
            "act": r["act"],
            "righted_by": r["righted_by_name"],
            "entry": r.get("entry"),
        })
    acts_so_far = [{
        "index": a.index, "name": a.name, "blurb": a.blurb, "climax_boss": a.climax_boss,
        "act_title": a.act_title, "completion_text": a.completion_text,
    } for a in previous_acts]
    used_targets = sorted({w.target for a in previous_acts for w in a.wrongs})

    events = []
    for ev in db.get_world_events(40):
        if ev["event_type"] in ("deed", "action"):
            continue
        d = ev.get("data") or {}
        if d.get("description"):
            events.append(d["description"])
        if len(events) >= 20:
            break

    heroes = sorted({c["righted_by"] for c in chronicle} | {l["discovered_by"] for l in locations if l.get("discovered_by")})

    # Incidents (see app/incidents.py): what befell the realm between deeds,
    # and who answered — or didn't.
    incidents = []
    try:
        for inc in db.get_recent_incidents(12):
            if inc["status"] == "active":
                continue
            incidents.append({
                "kind": inc["kind"], "title": inc["title"], "location": inc.get("location_id"),
                "status": inc["status"], "resolved_by": inc.get("resolved_by_name"),
            })
            heroes = sorted(set(heroes) | ({inc["resolved_by_name"]} if inc.get("resolved_by_name") else set()))
    except Exception as e:
        print(f"[CAMPAIGN] incidents in dossier skipped: {e}")

    return {
        "act_index": act_index,
        "acts_total": max_acts(),
        "world_level": world_level(),
        "locations": locations,
        "monsters": sorted(monsters.values(), key=lambda m: m["hp"]),
        "npcs": npcs,
        "items": items,
        "acts_so_far": acts_so_far,
        "chronicle": chronicle,
        "heroes": heroes,
        "recent_events": events,
        "incidents": incidents,
        "used_targets": used_targets,
    }


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

_SCHEMA = {
    "name": "Act name (3-5 words)",
    "blurb": "One sentence: what is wrong with the realm in this act, and why it matters.",
    "act_title": "A title granted to everyone who rights a wrong in this act",
    "completion_text": "2 sentences narrating the realm once this act is complete.",
    "wrongs": [
        {
            "title": "The wrong, as a chapter heading (e.g. 'Rats in the Granary')",
            "blurb": "One sentence: the fallen state, as the Chronicle names it.",
            "deed_type": "kill | collect | visit",
            "target": "EXACT monster name (kill), item id (collect), or location id (visit) from the dossier",
            "required": "1-3 for kill, 2-5 for collect, 1 for visit",
            "patron": "EXACT NPC name from the dossier who cares about this wrong",
            "location": "location id from the dossier whose description changes when righted (or null)",
            "restored": "2 sentences: how that place reads once the wrong is righted",
            "title_earned": "A short Legend title for whoever rights it (e.g. 'Keeper of the Mill')",
            "righted_text": "1-2 sentences narrating the moment it is put right",
        }
    ],
    "climax": {
        "name": "The act's great threat: a NEW named boss not in the monster list (e.g. 'The Ashen Dragon')",
        "title": "Its epithet (e.g. 'Cinderwing, the Sky's Ruin')",
        "blurb": "One sentence: the threat it poses, as the Chronicle names it.",
        "description": "2 sentences describing it; make clear no one can fell it alone.",
        "lair_desc": "2 sentences: the Warfront muster-ground with this threat looming over it.",
        "minion_name": "The lesser creature it summons when wounded (e.g. 'Cinder Whelp')",
        "phase_messages": ["1 sentence: it enrages and summons its minion", "1 sentence: it heals itself and summons another"],
        "trophy_name": "The trophy taken from its corpse (e.g. 'Dragon Heart')",
        "relic_name": "The weapon forged from the trophy (e.g. 'Cinderwing Blade')",
        "relic_material": "item id from the dossier that the relic is forged with",
        "title_earned": "Legend title for whoever lands the killing blow (e.g. 'Dragonsbane')",
        "completion_text": "1-2 sentences narrating its fall.",
    },
}


def build_act_prompt(dossier: Dict[str, Any], problems: Optional[List[str]] = None) -> str:
    n = dossier["act_index"] + 1
    total = dossier["acts_total"]
    stage = ("the opening act: begin close to home, with the town's own doorstep" if n == 1 else
             "the final act: the deepest, oldest wrong; make it feel like an ending" if n >= total else
             f"act {n} of {total}: push outward and deeper than the acts before it")
    parts = [
        ACT_MARKER,
        "You are the loremaster of a shared fantasy world. The realm lies fallen and its players are "
        "restoring it act by act. Author the next act of the Restoration from the world AS IT IS, "
        f"described in the dossier below. This is {stage}.",
        "",
        "Rules (the game engine enforces them; anything that breaks one is rejected):",
        "- Write 4 or 5 wrongs plus 1 climax. Each wrong is righted by ONE simple deed.",
        "- Every kill target must be an EXACT name from `monsters`; prefer creatures not in `used_targets`. "
        "Choose creatures whose `locations` fit the story, and keep `required` at or below its `count`.",
        "- Every collect target must be an EXACT `id` from `items`; every visit target and every `location` "
        "an EXACT `id` from `locations`; every patron an EXACT `name` from `npcs`.",
        "- Escalate: later acts use stronger creatures (higher hp) and farther places than earlier acts.",
        "- The story must grow from `chronicle`, `heroes`, `acts_so_far` and `recent_events`: name the heroes "
        "who came before, let earlier restorations matter, and let discovered regions become the stage.",
        "- The climax boss must be NEW (not a `monsters` name and not a previous `climax_boss`).",
        "- Prose only in text fields; no markdown, no lists inside strings.",
        "",
        "Reply with ONLY a JSON object of exactly this shape:",
        json.dumps(_SCHEMA, indent=1),
        "",
        "DOSSIER:",
        json.dumps(dossier, indent=0),
    ]
    if problems:
        parts += ["", "Your previous answer was rejected for these reasons; fix every one of them:",
                  *[f"- {p}" for p in problems]]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Validation: the referee
# ---------------------------------------------------------------------------

class ActValidationError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _text(d: dict, key: str, lo: int, hi: int, problems: List[str], where: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not (lo <= len(v.strip()) <= hi):
        problems.append(f"{where}.{key} must be text of {lo}-{hi} characters")
        return ""
    return " ".join(v.split())


def _climax_stats(index: int) -> Dict[str, int]:
    """Numbers for a climax are the engine's, never the model's. Act 1 matches
    the hand-authored dragon; each act after it is a heavier beast."""
    return {
        "base_hp": 800 + 250 * index,
        "base_attack": 14 + 2 * index,
        "base_reward": 600 + 150 * index,
        "minion_hp": 18 + 5 * index,
        "minion_attack": 6 + index,
        "minion_xp": 14 + 2 * index,
        "minion_coin": 6 + index,
        "relic_damage": 18 + 3 * index,
        "relic_value": 500 + 150 * index,
        "trophy_value": 300 + 50 * index,
    }


def validate_act(raw: Any, index: int, dossier: Dict[str, Any], previous_acts: list) -> Dict[str, Any]:
    """Turn Miriel's answer into a sound Act dict (as stored), or raise
    ActValidationError listing every problem so the model can repair them."""
    problems: List[str] = []
    if not isinstance(raw, dict):
        raise ActValidationError(["the answer must be a JSON object"])

    monsters = {m["name"]: m for m in dossier["monsters"]}
    items = {i["id"] for i in dossier["items"]}
    locations = {l["id"] for l in dossier["locations"]}
    npcs = {n["name"] for n in dossier["npcs"]}
    used_ids = {w.id for a in previous_acts for w in a.wrongs}
    prev_bosses = {a.climax_boss for a in previous_acts}

    name = _text(raw, "name", 3, 60, problems, "act")
    blurb = _text(raw, "blurb", 20, 300, problems, "act")
    act_title = _text(raw, "act_title", 3, 60, problems, "act")
    completion = _text(raw, "completion_text", 20, 600, problems, "act")

    wrongs_raw = raw.get("wrongs")
    if not isinstance(wrongs_raw, list) or not (3 <= len(wrongs_raw) <= 6):
        problems.append("wrongs must be a list of 4 or 5 entries")
        wrongs_raw = []

    wrongs: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for i, w in enumerate(wrongs_raw):
        where = f"wrongs[{i}]"
        if not isinstance(w, dict):
            problems.append(f"{where} must be an object")
            continue
        title = _text(w, "title", 3, 80, problems, where)
        wid = f"a{index}_{_slug(title)}" or f"a{index}_wrong_{i}"
        if wid in seen_ids or wid in used_ids:
            problems.append(f"{where}.title duplicates another wrong ({title})")
        seen_ids.add(wid)
        deed_type = w.get("deed_type")
        target = w.get("target") if isinstance(w.get("target"), str) else ""
        try:
            required = int(w.get("required", 1))
        except (TypeError, ValueError):
            required = 0
        if deed_type == "kill":
            if target not in monsters:
                problems.append(f"{where}.target '{target}' is not a monster name from the dossier")
            elif not (1 <= required <= max(1, min(3, monsters[target]["count"]))):
                problems.append(f"{where}.required must be 1-{max(1, min(3, monsters[target]['count']))} for {target}")
        elif deed_type == "collect":
            if target not in items:
                problems.append(f"{where}.target '{target}' is not an item id from the dossier")
            if not (1 <= required <= 5):
                problems.append(f"{where}.required must be 1-5 for a collect deed")
        elif deed_type == "visit":
            if target not in locations:
                problems.append(f"{where}.target '{target}' is not a location id from the dossier")
            required = 1
        else:
            problems.append(f"{where}.deed_type must be kill, collect or visit")
        patron = w.get("patron")
        if patron not in npcs:
            problems.append(f"{where}.patron '{patron}' is not an NPC name from the dossier")
        location = w.get("location")
        if location is not None and location not in locations:
            problems.append(f"{where}.location '{location}' is not a location id from the dossier")
        restored = w.get("restored")
        if location is not None:
            restored = _text(w, "restored", 20, 500, problems, where)
        wblurb = _text(w, "blurb", 10, 300, problems, where)
        title_earned = _text(w, "title_earned", 3, 40, problems, where)
        righted_text = _text(w, "righted_text", 10, 400, problems, where)

        # The player-facing deed line is the engine's: it must be exact.
        if deed_type == "kill" and target in monsters:
            from .content import get_location_or_none
            wheres = [get_location_or_none(l).name for l in monsters[target]["locations"][:2] if get_location_or_none(l)]
            deed = f"Slay {required} {target}{'s' if required > 1 else ''}" + (f" ({' / '.join(wheres)})" if wheres else "") + "."
        elif deed_type == "collect":
            from .items import get_item
            it = get_item(target)
            deed = f"Gather {required} {it.name if it else target}{'s' if required > 1 and it else ''} for {patron}."
        elif deed_type == "visit":
            from .content import get_location_or_none
            loc = get_location_or_none(target)
            deed = f"Reach {loc.name if loc else target} and return word of it."
        else:
            deed = ""

        wrongs.append({
            "id": wid, "title": title, "blurb": wblurb, "deed": deed,
            "deed_type": deed_type, "target": target, "required": required,
            "patron": patron, "location": location, "restored": restored if location else None,
            "flag": f"{wid}_righted", "title_earned": title_earned, "righted_text": righted_text,
        })

    # The climax.
    c = raw.get("climax")
    climax: Dict[str, Any] = {}
    if not isinstance(c, dict):
        problems.append("climax must be an object")
    else:
        cname = _text(c, "name", 3, 60, problems, "climax")
        if cname in monsters or cname in prev_bosses:
            problems.append(f"climax.name '{cname}' must be new (not an existing creature or a previous boss)")
        ctitle = _text(c, "title", 3, 80, problems, "climax")
        cblurb = _text(c, "blurb", 10, 300, problems, "climax")
        cdesc = _text(c, "description", 20, 500, problems, "climax")
        lair = _text(c, "lair_desc", 20, 500, problems, "climax")
        minion = _text(c, "minion_name", 3, 40, problems, "climax")
        if minion in monsters:
            problems.append("climax.minion_name must be a new creature")
        pm = c.get("phase_messages")
        if not (isinstance(pm, list) and len(pm) == 2 and all(isinstance(s, str) and 10 <= len(s) <= 300 for s in pm)):
            problems.append("climax.phase_messages must be a list of exactly 2 sentences")
            pm = ["", ""]
        trophy = _text(c, "trophy_name", 3, 40, problems, "climax")
        relic = _text(c, "relic_name", 3, 40, problems, "climax")
        material = c.get("relic_material")
        if material not in items:
            problems.append(f"climax.relic_material '{material}' is not an item id from the dossier")
        ctitle_earned = _text(c, "title_earned", 3, 40, problems, "climax")
        ccompletion = _text(c, "completion_text", 10, 400, problems, "climax")
        key = f"a{index}_{_slug(cname)}"
        stats = _climax_stats(index)
        climax = {
            "key": key,
            "name": cname, "title": ctitle, "blurb": cblurb, "description": cdesc,
            "lair_name": f"The Warfront — {ctitle}" if ctitle else f"The Warfront — {cname}",
            "lair_desc": lair,
            "base_hp": stats["base_hp"], "base_attack": stats["base_attack"], "base_reward": stats["base_reward"],
            "trophy": f"trophy_{key}", "trophy_name": trophy,
            "relic": f"relic_{key}", "relic_name": relic, "relic_material": material,
            "effect": {f"{key}_felled": "true"},
            "completion_text": ccompletion,
            "title_earned": ctitle_earned,
            "phases": [
                {"at": 0.66, "enrage_add": 4 + index, "message": pm[0],
                 "summon": {"name": minion, "hp": stats["minion_hp"], "attack": stats["minion_attack"],
                            "xp_reward": stats["minion_xp"], "loot": {"coin": stats["minion_coin"]}}},
                {"at": 0.33, "enrage_add": 6 + index, "heal_frac": 0.10, "message": pm[1],
                 "summon": {"name": minion, "hp": stats["minion_hp"], "attack": stats["minion_attack"],
                            "xp_reward": stats["minion_xp"], "loot": {"coin": stats["minion_coin"]}}},
            ],
        }

    if problems:
        raise ActValidationError(problems)

    # The climax is a wrong too — the act's last, righted by the raid.
    wrongs.append({
        "id": climax["key"], "title": f"{climax['name']} Holds the Warfront", "blurb": climax["blurb"],
        "deed": f"Fell {climax['name']} at the Warfront (`raid strike` — the whole realm may join).",
        "deed_type": "climax", "target": climax["name"], "required": 1,
        "patron": _warfront_patron(dossier), "location": None, "restored": None,
        "flag": climax["effect"] and next(iter(climax["effect"])),
        "title_earned": climax["title_earned"], "righted_text": climax["completion_text"],
    })

    return {
        "index": index, "name": name, "blurb": blurb, "wrongs": wrongs,
        "climax_boss": climax["name"], "act_title": act_title, "completion_text": completion,
        "climax": climax, "source": "miriel",
    }


def _warfront_patron(dossier: Dict[str, Any]) -> str:
    names = [n["name"] for n in dossier["npcs"]]
    return "Town Warden" if "Town Warden" in names else (names[0] if names else "Town Warden")


# ---------------------------------------------------------------------------
# Fallbacks: the campaign always exists
# ---------------------------------------------------------------------------

def skeleton_act(index: int, dossier: Dict[str, Any], previous_acts: list) -> Dict[str, Any]:
    """A procedural act from the catalog, in template prose. Used only when
    there is no hand-authored act for this index and Miriel could not write one."""
    from .content import get_location_or_none
    used = set(dossier["used_targets"])
    pool = [m for m in dossier["monsters"] if m["name"] not in used] or list(dossier["monsters"])
    # Escalate: later acts pull from the stronger end of the catalog.
    pool.sort(key=lambda m: m["hp"])
    start = min(len(pool) - 1, (index * 4) % max(1, len(pool)))
    picks = (pool[start:] + pool[:start])[:4]
    npcs = [n["name"] for n in dossier["npcs"]] or ["Town Warden"]
    wrongs = []
    for i, m in enumerate(picks):
        loc_id = m["locations"][0]
        loc = get_location_or_none(loc_id)
        lname = loc.name if loc else loc_id
        wid = f"a{index}_{_slug(m['name'])}"
        wrongs.append({
            "id": wid, "title": f"The {m['name']}s of {lname}",
            "blurb": f"{m['name']}s hold {lname}; no one passes there safely.",
            "deed": f"Slay 1 {m['name']} ({lname}).", "deed_type": "kill", "target": m["name"], "required": 1,
            "patron": npcs[i % len(npcs)], "location": loc_id,
            "restored": f"{lname} is quiet again. The {m['name']}s that held it are gone, and the way through is walked once more.",
            "flag": f"{wid}_righted", "title_earned": f"Scourge of {lname}",
            "righted_text": f"The last {m['name']} falls. {lname} is free.",
        })
    from .raids import RAID_BOSSES
    base = RAID_BOSSES[index % len(RAID_BOSSES)]
    reborn = index >= len(RAID_BOSSES)
    cname = f"{base['name']} Reborn" if reborn else base["name"]
    key = f"a{index}_{_slug(cname)}"
    climax = dict(base)
    climax.update({
        "key": key, "name": cname, "blurb": base["description"].split(". ")[0] + ".",
        "effect": {f"{key}_felled": "true"} if reborn else base["effect"],
        "trophy": base["trophy"], "title_earned": f"{cname.split()[-1]}sbane",
        "relic": None, "relic_name": None, "relic_material": None,
    })
    wrongs.append({
        "id": key, "title": f"{cname} Holds the Warfront", "blurb": climax["blurb"],
        "deed": f"Fell {cname} at the Warfront (`raid strike`).", "deed_type": "climax", "target": cname,
        "required": 1, "patron": _warfront_patron(dossier), "location": None, "restored": None,
        "flag": next(iter(climax["effect"])), "title_earned": climax["title_earned"],
        "righted_text": base["completion_text"],
    })
    return {
        "index": index, "name": f"The {index + 1}{_ordinal(index + 1)} Reckoning",
        "blurb": "What still stalks the realm must be driven out, place by place.",
        "wrongs": wrongs, "climax_boss": cname, "act_title": f"Reckoner of the {index + 1}{_ordinal(index + 1)} Act",
        "completion_text": "Another act of the realm's restoration is written; the Chronicle names every hand.",
        "climax": climax, "source": "skeleton",
    }


def _ordinal(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------

def _ask_miriel_for_act(index: int, dossier: Dict[str, Any], previous_acts: list) -> Optional[Dict[str, Any]]:
    """Two tries: the second feeds the first answer's problems back for repair."""
    from .services.miriel_client import is_miriel_enabled, get_miriel_client, extract_answer

    if not is_miriel_enabled():
        return None
    problems: Optional[List[str]] = None
    for attempt in (1, 2):
        try:
            resp = get_miriel_client().query(query=build_act_prompt(dossier, problems), project="questai")
            answer = extract_answer(resp) or ""
            match = re.search(r"\{.*\}", answer, re.DOTALL)
            if not match:
                problems = ["the reply contained no JSON object"]
                print(f"[CAMPAIGN] act {index} attempt {attempt}: no JSON in answer")
                continue
            raw = json.loads(match.group(0))
            return validate_act(raw, index, dossier, previous_acts)
        except ActValidationError as e:
            problems = e.problems
            print(f"[CAMPAIGN] act {index} attempt {attempt} rejected: {e}")
        except json.JSONDecodeError as e:
            problems = [f"the JSON did not parse: {e}"]
            print(f"[CAMPAIGN] act {index} attempt {attempt}: bad JSON ({e})")
        except Exception as e:
            print(f"[CAMPAIGN] act {index} attempt {attempt} failed: {e}")
            return None
    return None


def _install_climax_items(climax: Dict[str, Any]) -> None:
    """The trophy and the relic forged from it exist as real (generated) items."""
    from .content import invalidate_cache
    if not climax.get("trophy_name"):
        return  # skeleton/authored climaxes use hand-authored items
    stats = _climax_stats(int(climax["key"].split("_")[0][1:]))
    db.upsert_gen_item(item_id=climax["trophy"], data={
        "item_id": climax["trophy"], "name": climax["trophy_name"], "type": "material",
        "value": stats["trophy_value"],
    })
    db.upsert_gen_item(item_id=climax["relic"], data={
        "item_id": climax["relic"], "name": climax["relic_name"], "type": "weapon", "slot": "weapon",
        "damage": stats["relic_damage"], "value": stats["relic_value"],
    }, recipe={"inputs": {climax["trophy"]: 1, climax["relic_material"]: 3}, "qty": 1})
    invalidate_cache()


def author_act(index: int, previous_acts: list, authored_fallback=None) -> Dict[str, Any]:
    """
    Write act `index` into the world, once. Returns the stored act row's data.
    Miriel authors it from the dossier; failing that, the hand-authored act for
    this index (if any), failing that a skeleton. Single-flighted and
    first-writer-wins, so concurrent callers share one act.
    """
    def _do() -> Dict[str, Any]:
        existing = db.get_campaign_act(index)
        if existing:
            return existing["data"]

        dossier = world_dossier(index, previous_acts)
        data = _ask_miriel_for_act(index, dossier, previous_acts)
        if data is None:
            if authored_fallback is not None:
                data = dict(authored_fallback)
                data["source"] = "authored"
            else:
                data = skeleton_act(index, dossier, previous_acts)

        if data.get("climax"):
            _install_climax_items(data["climax"])

        if db.create_campaign_act(index, data["source"], data):
            db.log_world_event(
                event_type="act_authored",
                location_id=None,
                data={"act": index, "name": data["name"], "source": data["source"],
                      "description": f"A new chapter of the Chronicle opens: {data['name']}. {data['blurb']}"},
            )
            print(f"[CAMPAIGN] act {index} authored ({data['source']}): {data['name']}")
            _learn_act(data, dossier)
            return data
        stored = db.get_campaign_act(index)
        return stored["data"] if stored else data

    return single_flight.run(f"author_act_{index}", _do)


def _learn_act(data: Dict[str, Any], dossier: Dict[str, Any]) -> None:
    """Best-effort: the authored act enters Miriel's memory of this world, so
    dialogue and later acts can refer back to it."""
    try:
        from .services import miriel_client as mc
        client = mc.get_miriel_client()
        if not mc.is_miriel_enabled() or not client.auto_learning_enabled or mc._TEST_RESPONDER is not None:
            return
        client.learn(
            input_data={"type": "campaign_act", "act": data, "heroes": dossier.get("heroes", [])},
            metadata={"content_type": "campaign_act", "act_index": data["index"]},
        )
    except Exception as e:
        print(f"[CAMPAIGN] learn skipped: {e}")


# ---------------------------------------------------------------------------
# The Chronicle's voice
# ---------------------------------------------------------------------------

def voice_patron_line(npc_name: str, wrong: Any, state: str, player: Any,
                      record: Optional[Dict[str, Any]], progress: str = "") -> Optional[str]:
    """
    What a patron says about their wrong, in Miriel's voice, with the
    Chronicle in view: an open wrong is a plea, one underway is a check-in,
    a righted one is gratitude that names who did it (and what the Chronicle
    wrote). Cached per (npc, wrong, state, righter, progress) so a
    conversation is stable but moves when the world does. Best-effort: None
    means the deterministic line stands.
    """
    from .services.miriel_client import is_miriel_enabled, get_miriel_client, extract_answer

    if not is_miriel_enabled():
        return None
    import hashlib
    righter = (record or {}).get("righted_by_name") or ""
    entry = (record or {}).get("entry") or ""
    key = "patron_" + hashlib.sha256(
        f"{npc_name}|{wrong.id}|{state}|{righter}|{progress}|{player.player_id if state == 'righted' else ''}".encode()
    ).hexdigest()[:16]
    cached = db.get_cached_miriel_content(key)
    if cached:
        return cached
    try:
        legend = ", ".join(getattr(player, "titles", None) or []) or "no titles yet"
        if state == "righted":
            you = "the very adventurer you are speaking to" if (record or {}).get("righted_by_id") == player.player_id else righter
            situation = (f"The wrong has been PUT RIGHT by {you}. Chronicle entry: '{entry or wrong.righted_text}'. "
                         f"Speak of it with gratitude and name who did it; the world is changed: {wrong.restored or wrong.righted_text}")
        elif state == "active":
            situation = f"{player.name} has taken up the deed and is partway through ({progress}). Urge them on."
        elif wrong.deed_type == "climax":
            situation = "This is the act's great threat, felled only by the whole realm together at the Warfront. Ask them to join the muster."
        else:
            situation = f"The wrong is OPEN. Plead with {player.name} to take it up. The deed: {wrong.deed}"
        query = (
            f"{PATRON_MARKER}\nYou are {npc_name}, an NPC in a fantasy world, speaking to the adventurer {player.name} "
            f"(Legend: {legend}). You care about this wrong: '{wrong.title}' — {wrong.blurb}\n{situation}\n"
            "Reply with ONLY what you say aloud: 1-2 sentences, in character, vivid, no quotes, no stage directions, "
            "no commands or game syntax."
        )
        text = " ".join((extract_answer(get_miriel_client().query(query=query, project="questai")) or "").split())
        text = text.strip().strip('"').strip("“”")
        if 10 <= len(text) <= 400 and "{" not in text and "`" not in text:
            db.cache_miriel_content(key, "dialogue", text, ttl_seconds=1800)
            return text
    except Exception as e:
        print(f"[CAMPAIGN] patron voice skipped: {e}")
    return None


def narrate_chronicle_entry(wrong: Any, player: Any) -> Optional[str]:
    """One sentence for the Chronicle about *this* righting — who, how, with
    whom. Best-effort; None means the wrong's authored righted_text stands."""
    from .services.miriel_client import is_miriel_enabled, get_miriel_client, extract_answer

    if not is_miriel_enabled():
        return None
    try:
        who = player.name
        if getattr(player, "archetype", None):
            who += f", a {player.archetype}"
        comp = getattr(player, "companion", None)
        companion = f" with {comp.name} the {comp.archetype} at their side" if comp else ""
        titles = ", ".join(getattr(player, "titles", None) or []) or "none yet"
        query = (
            f"{CHRONICLE_MARKER}\nWrite ONE sentence (max 40 words) for a realm's Chronicle recording that "
            f"{who}{companion} put right the wrong '{wrong.title}' ({wrong.blurb}) by this deed: {wrong.deed} "
            f"Their titles so far: {titles}. Third person, past tense, no quotes, no preamble."
        )
        text = " ".join((extract_answer(get_miriel_client().query(query=query, project="questai")) or "").split())
        if 15 <= len(text) <= 400 and "{" not in text:
            return text.strip('"')
    except Exception as e:
        print(f"[CAMPAIGN] chronicle entry skipped: {e}")
    return None
