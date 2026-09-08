"""
World events with teeth: incidents Miriel authors between the campaign's deeds.

A world event used to be a line of text. An **incident** is a line of text
that *does something*: it is authored by Miriel from the world as it is (the
same dossier the campaign is written from), validated by code, installed as a
real mechanic, and then either **resolved by play** or **expired with a
consequence**. Either way it enters world history — and the next act's
dossier — so the story reacts to what happened, not only to what was slain.

Two kinds, each with a mechanic the engine actually enforces:

  incursion  A named new creature (Miriel's) appears at a place in numbers,
             and may close a road out of it while it lasts. Resolved when the
             last of them dies (the killer is named and paid). If no one
             comes, they dig in: a stronger leader rises, the closure holds,
             and the world records that the realm let it happen.

  boon       A festival, a blessing, a market glut: for a while a rule
             changes — the temple heals free, rest heals double, or the shops
             sell cheap. Nothing to resolve; it simply passes.

Cadence and numbers are the engine's. Miriel supplies only what happens and
how it reads.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from . import db
from . import single_flight
from .db import get_world_turn, get_world_state, set_world_state, log_world_event

INCIDENT_MARKER = "[[INCIDENT]]"

BOON_EFFECTS = ("free_heal", "rest_double", "shop_discount")
SHOP_DISCOUNT = 0.75

# Cadence (world turns between incidents) and lifetime bounds.
DEFAULT_EVERY_TURNS = 12
MIN_DURATION, MAX_DURATION = 8, 40
MAX_ACTIVE = 2            # at most this many at once, and at most one incursion


def every_turns() -> int:
    try:
        return max(1, int(os.getenv("QUESTAI_INCIDENT_EVERY_TURNS", str(DEFAULT_EVERY_TURNS))))
    except ValueError:
        return DEFAULT_EVERY_TURNS


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:40]


# ---------------------------------------------------------------------------
# What is in force right now
# ---------------------------------------------------------------------------

def active_incidents() -> List[Dict[str, Any]]:
    return db.get_active_incidents()


def incidents_at(location_id: str) -> List[Dict[str, Any]]:
    return [i for i in active_incidents() if i.get("location_id") == location_id]


def boon_active(effect: str) -> bool:
    """Whether a boon with this effect is in force anywhere."""
    return any(i["kind"] == "boon" and i["data"].get("effect") == effect for i in active_incidents())


def exit_blocked(from_loc: str, to_loc: str) -> Optional[Dict[str, Any]]:
    """The incursion closing this road, if any."""
    for i in active_incidents():
        if (i["kind"] == "incursion" and i.get("location_id") == from_loc
                and i["data"].get("blocks_exit_to") == to_loc):
            return i
    return None


def _instance_prefix(incident_id: str) -> str:
    return f"inc_{incident_id}_"


def creatures_left(incident: Dict[str, Any]) -> int:
    prefix = _instance_prefix(incident["incident_id"])
    return sum(1 for m in db.get_monsters_at(incident["location_id"])
               if str(m["instance_id"]).startswith(prefix))


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------

_SCHEMA = {
    "kind": "incursion | boon",
    "title": "A headline (3-6 words, e.g. 'Ash-Wolves at the Mill')",
    "blurb": "One sentence: what is happening, as gossip would tell it.",
    "location": "EXACT location id from the dossier where it happens",
    "announce_text": "1-2 sentences narrating its arrival, for the world's history.",
    "incursion": {
        "creature_name": "A NEW creature name for the intruders (not in monsters)",
        "count": "2 or 3",
        "blocks_exit_to": "an EXACT exit id of that location that they close, or null",
        "resolution_text": "1 sentence for history when the last of them is slain (use {hero} for the slayer)",
        "consequence_text": "1 sentence for history if no one answers and they dig in",
        "leader_name": "The stronger one that rises if they dig in (new name)",
    },
    "boon": {
        "effect": "free_heal | rest_double | shop_discount",
        "passing_text": "1 sentence for history when it ends",
    },
    "duration_turns": "a number from 8 to 40",
}


def _dossier() -> Dict[str, Any]:
    from .campaigngen import world_dossier
    from .restoration import _load_acts, current_act
    acts = _load_acts()
    d = world_dossier(len(acts), acts)
    act = current_act()
    from .content import get_location_or_none
    exits = {}
    for loc in d["locations"]:
        l = get_location_or_none(loc["id"])
        if l:
            exits[loc["id"]] = [e.to for e in l.exits]
    return {
        "world_level": d["world_level"],
        "current_act": {"name": act.name, "blurb": act.blurb} if act else None,
        "locations": [{"id": l["id"], "name": l["name"], "exits": exits.get(l["id"], []),
                       **({"region": l["region"]} if l.get("region") else {})} for l in d["locations"]],
        "monsters": [m["name"] for m in d["monsters"]],
        "npcs": [{"name": n["name"], "location": n["location"]} for n in d["npcs"]],
        "chronicle": d["chronicle"][-8:],
        "heroes": d["heroes"],
        "recent_events": d["recent_events"][:12],
        "active_incidents": [{"kind": i["kind"], "title": i["title"], "location": i["location_id"]}
                             for i in active_incidents()],
        "past_incidents": [{"kind": i["kind"], "title": i["title"], "status": i["status"],
                            "resolved_by": i.get("resolved_by_name")}
                           for i in db.get_recent_incidents(6) if i["status"] != "active"],
    }


def build_incident_prompt(dossier: Dict[str, Any], problems: Optional[List[str]] = None) -> str:
    want = "boon" if any(i["kind"] == "incursion" for i in dossier["active_incidents"]) else "incursion or boon"
    parts = [
        INCIDENT_MARKER,
        "You are the loremaster of a shared, living fantasy world. Between the great deeds of its "
        "restoration, smaller things happen: raiders, plagues, festivals, blessings, a glut at market. "
        f"Author ONE such incident now ({want}) from the world AS IT IS in the dossier — a reaction to "
        "what its heroes have done and where they have been, not a random event.",
        "",
        "Rules (the engine enforces them):",
        "- `location` must be an EXACT location id from `locations`; `blocks_exit_to` an EXACT id in that location's `exits`, or null.",
        "- An incursion's creature_name and leader_name must be NEW (not in `monsters`, not a previous incident's).",
        "- Do not repeat an `active_incidents` or `past_incidents` title or premise.",
        "- Prose only in text fields; no markdown; no game syntax.",
        "",
        "Reply with ONLY a JSON object of exactly this shape (fill only the branch matching `kind`):",
        json.dumps(_SCHEMA, indent=1),
        "",
        "DOSSIER:",
        json.dumps(dossier, indent=0),
    ]
    if problems:
        parts += ["", "Your previous answer was rejected for these reasons; fix every one of them:",
                  *[f"- {p}" for p in problems]]
    return "\n".join(parts)


class IncidentValidationError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _creature_stats(level: int) -> Dict[str, int]:
    """Intruders are a real fight for the world's level but never a wall."""
    from .engine.entities import scale_stats
    hp, atk, xp = scale_stats(14, 4, 12, level)
    return {"hp": hp, "attack": atk, "xp_reward": xp, "coin": 5 + level}


def validate_incident(raw: Any, dossier: Dict[str, Any]) -> Dict[str, Any]:
    problems: List[str] = []
    if not isinstance(raw, dict):
        raise IncidentValidationError(["the answer must be a JSON object"])

    def text(d: dict, key: str, lo: int, hi: int, where: str) -> str:
        v = d.get(key)
        if not isinstance(v, str) or not (lo <= len(v.strip()) <= hi):
            problems.append(f"{where}{key} must be text of {lo}-{hi} characters")
            return ""
        return " ".join(v.split())

    locations = {l["id"]: l for l in dossier["locations"]}
    monsters = set(dossier["monsters"])
    past_titles = {i["title"].lower() for i in dossier["active_incidents"] + dossier["past_incidents"]}
    for i in db.get_recent_incidents(30):
        d = i.get("data") or {}
        for k in ("creature_name", "leader_name"):
            if d.get(k):
                monsters.add(d[k])

    kind = raw.get("kind")
    if kind not in ("incursion", "boon"):
        problems.append("kind must be incursion or boon")
    if kind == "incursion" and any(i["kind"] == "incursion" for i in dossier["active_incidents"]):
        problems.append("an incursion is already underway; author a boon")
    title = text(raw, "title", 3, 60, "")
    if title.lower() in past_titles:
        problems.append(f"title '{title}' repeats an existing incident")
    blurb = text(raw, "blurb", 10, 300, "")
    location = raw.get("location")
    if location not in locations:
        problems.append(f"location '{location}' is not a location id from the dossier")
    announce = text(raw, "announce_text", 10, 400, "")
    try:
        duration = int(raw.get("duration_turns", 0))
    except (TypeError, ValueError):
        duration = 0
    if not (MIN_DURATION <= duration <= MAX_DURATION):
        problems.append(f"duration_turns must be {MIN_DURATION}-{MAX_DURATION}")

    data: Dict[str, Any] = {"blurb": blurb, "announce_text": announce}
    if kind == "incursion":
        inc = raw.get("incursion") if isinstance(raw.get("incursion"), dict) else {}
        creature = text(inc, "creature_name", 3, 40, "incursion.")
        if creature in monsters:
            problems.append(f"incursion.creature_name '{creature}' already exists")
        leader = text(inc, "leader_name", 3, 40, "incursion.")
        if leader in monsters or leader == creature:
            problems.append(f"incursion.leader_name '{leader}' must be new")
        try:
            count = int(inc.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        if not (2 <= count <= 3):
            problems.append("incursion.count must be 2 or 3")
        blocks = inc.get("blocks_exit_to")
        if blocks is not None and (location not in locations or blocks not in locations[location]["exits"]):
            problems.append(f"incursion.blocks_exit_to '{blocks}' is not an exit of {location}")
        resolution = text(inc, "resolution_text", 10, 300, "incursion.")
        consequence = text(inc, "consequence_text", 10, 300, "incursion.")
        data.update({"creature_name": creature, "leader_name": leader, "count": count,
                     "blocks_exit_to": blocks, "resolution_text": resolution,
                     "consequence_text": consequence})
    elif kind == "boon":
        boon = raw.get("boon") if isinstance(raw.get("boon"), dict) else {}
        effect = boon.get("effect")
        if effect not in BOON_EFFECTS:
            problems.append(f"boon.effect must be one of {', '.join(BOON_EFFECTS)}")
        passing = text(boon, "passing_text", 10, 300, "boon.")
        data.update({"effect": effect, "passing_text": passing})

    if problems:
        raise IncidentValidationError(problems)
    return {"kind": kind, "title": title, "location_id": location, "duration": duration, "data": data}


def _ask_miriel(dossier: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from .services.miriel_client import is_miriel_enabled, get_miriel_client, extract_answer
    if not is_miriel_enabled():
        return None
    problems: Optional[List[str]] = None
    for attempt in (1, 2):
        try:
            resp = get_miriel_client().query(query=build_incident_prompt(dossier, problems), project="questai")
            answer = extract_answer(resp) or ""
            match = re.search(r"\{.*\}", answer, re.DOTALL)
            if not match:
                problems = ["the reply contained no JSON object"]
                print(f"[INCIDENTS] attempt {attempt}: no JSON in answer")
                continue
            return validate_incident(json.loads(match.group(0)), dossier)
        except IncidentValidationError as e:
            problems = e.problems
            print(f"[INCIDENTS] attempt {attempt} rejected: {e}")
        except json.JSONDecodeError as e:
            problems = [f"the JSON did not parse: {e}"]
            print(f"[INCIDENTS] attempt {attempt}: bad JSON ({e})")
        except Exception as e:
            print(f"[INCIDENTS] attempt {attempt} failed: {e}")
            return None
    return None


def _install(spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Write the incident into the world: the row, its creatures, its history."""
    turn = get_world_turn()
    incident_id = f"{turn}_{_slug(spec['title'])}"
    if not db.create_incident(
        incident_id=incident_id, kind=spec["kind"], title=spec["title"],
        location_id=spec["location_id"], data=spec["data"],
        created_turn=turn, expires_turn=turn + spec["duration"],
    ):
        return None
    if spec["kind"] == "incursion":
        from .engine.entities import world_level
        stats = _creature_stats(world_level())
        for i in range(spec["data"]["count"]):
            db.spawn_monster(
                instance_id=f"{_instance_prefix(incident_id)}{i}",
                location_id=spec["location_id"],
                name=spec["data"]["creature_name"],
                hp=stats["hp"], max_hp=stats["hp"], attack=stats["attack"],
                xp_reward=stats["xp_reward"], loot={"coin": stats["coin"]},
                spawned_turn=turn,
            )
    log_world_event(
        event_type="incident_started",
        location_id=spec["location_id"],
        data={"incident_id": incident_id, "kind": spec["kind"], "title": spec["title"],
              "description": spec["data"]["announce_text"]},
    )
    set_world_state("last_incident_turn", str(turn))
    print(f"[INCIDENTS] {spec['kind']} begins: {spec['title']} at {spec['location_id']}")
    return db.get_incident(incident_id)


def maybe_author_incident() -> Optional[Dict[str, Any]]:
    """Turn hook: when the cadence allows and there is room, author one.
    Single-flighted; never raises."""
    try:
        turn = get_world_turn()
        last = int(get_world_state("last_incident_turn") or 0)
        if turn - last < every_turns():
            return None
        if len(active_incidents()) >= MAX_ACTIVE:
            return None
        from .services.miriel_client import is_miriel_enabled
        if not is_miriel_enabled():
            return None

        def _do():
            if int(get_world_state("last_incident_turn") or 0) != last:
                return None  # someone else just did
            spec = _ask_miriel(_dossier())
            if spec is None:
                # Don't hammer Miriel every turn on failure: back off a cadence.
                set_world_state("last_incident_turn", str(turn))
                return None
            return _install(spec)

        return single_flight.run("author_incident", _do)
    except Exception as e:
        print(f"[INCIDENTS] authoring failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Resolution and expiry
# ---------------------------------------------------------------------------

def on_monster_killed(player, instance_id: str) -> List[str]:
    """Kill hook: the last intruder slain resolves its incursion."""
    if not str(instance_id).startswith("inc_"):
        return []
    for inc in active_incidents():
        if inc["kind"] != "incursion" or not str(instance_id).startswith(_instance_prefix(inc["incident_id"])):
            continue
        if creatures_left(inc) > 0:
            left = creatures_left(inc)
            return [f"{left} of the {inc['data']['creature_name']}s remain — {inc['title']} is not over."]
        turn = get_world_turn()
        if not db.close_incident(inc["incident_id"], "resolved", turn, player.player_id, player.name):
            return []
        from .engine.entities import world_level
        reward = 20 + 8 * world_level()
        player.inventory["coin"] = player.inventory.get("coin", 0) + reward
        text = inc["data"]["resolution_text"].replace("{hero}", player.name)
        if player.name not in text:
            text = f"{text} ({player.name} ended it.)"
        log_world_event(
            event_type="incident_resolved",
            location_id=inc["location_id"],
            data={"incident_id": inc["incident_id"], "title": inc["title"],
                  "player_id": player.player_id, "player_name": player.name, "description": text},
        )
        from .echoes import record_deed
        try:
            record_deed(player, inc["location_id"], f"{player.name} ended {inc['title']}", kind="incident")
        except Exception:
            pass
        msgs = [f"— {inc['title']} is ended. —", text, f"The realm's thanks: {reward} coins."]
        if inc["data"].get("blocks_exit_to"):
            from .content import get_location_or_none
            to = get_location_or_none(inc["data"]["blocks_exit_to"])
            msgs.append(f"The way to {to.name if to else inc['data']['blocks_exit_to']} is open again.")
        return msgs
    return []


def tick_incidents() -> List[str]:
    """Turn hook: expire what has run out. An unanswered incursion digs in."""
    turn = get_world_turn()
    notes: List[str] = []
    for inc in active_incidents():
        if turn < inc["expires_turn"]:
            continue
        if inc["kind"] == "incursion" and creatures_left(inc) > 0:
            if not db.close_incident(inc["incident_id"], "expired", turn):
                continue
            # They dig in: a leader rises among them, and the road they closed
            # stays closed until the leader falls (see exit_blocked_by_leader).
            from .engine.entities import world_level
            stats = _creature_stats(world_level())
            db.spawn_monster(
                instance_id=f"{_instance_prefix(inc['incident_id'])}leader",
                location_id=inc["location_id"],
                name=inc["data"]["leader_name"],
                hp=stats["hp"] * 2, max_hp=stats["hp"] * 2, attack=stats["attack"] + 2,
                xp_reward=stats["xp_reward"] * 2, loot={"coin": stats["coin"] * 3},
                spawned_turn=turn,
            )
            set_world_state(f"incident_{inc['incident_id']}_dug_in", "true")
            text = inc["data"]["consequence_text"]
            log_world_event(
                event_type="incident_expired",
                location_id=inc["location_id"],
                data={"incident_id": inc["incident_id"], "title": inc["title"], "description": text},
            )
            notes.append(text)
        else:
            if not db.close_incident(inc["incident_id"], "expired" if inc["kind"] == "boon" else "resolved", turn):
                continue
            text = inc["data"].get("passing_text") or f"{inc['title']} has passed."
            log_world_event(
                event_type="incident_expired",
                location_id=inc["location_id"],
                data={"incident_id": inc["incident_id"], "title": inc["title"], "description": text},
            )
            notes.append(text)
    return notes


def exit_blocked_any(from_loc: str, to_loc: str) -> Optional[Dict[str, Any]]:
    """A road closed by a live incursion, or by a dug-in one whose leader still
    stands. The road reopens the moment the last intruder or the leader dies."""
    live = exit_blocked(from_loc, to_loc)
    if live:
        return live
    for inc in db.get_recent_incidents(20):
        if (inc["kind"] == "incursion" and inc["status"] == "expired"
                and inc.get("location_id") == from_loc
                and inc["data"].get("blocks_exit_to") == to_loc
                and creatures_left(inc) > 0):
            return inc
    return None


# ---------------------------------------------------------------------------
# Surfacing
# ---------------------------------------------------------------------------

def location_lines(location_id: str) -> List[str]:
    """What a player sees here because of an incident."""
    from .content import get_location_or_none
    lines: List[str] = []
    for inc in incidents_at(location_id):
        d = inc["data"]
        if inc["kind"] == "incursion":
            left = creatures_left(inc)
            line = f"{inc['title']}: {d['blurb']}"
            if left:
                line += f" {left} {d['creature_name']}{'s' if left > 1 else ''} here — slay them all to end it."
            if d.get("blocks_exit_to"):
                to = get_location_or_none(d["blocks_exit_to"])
                line += f" They hold the way to {to.name if to else d['blocks_exit_to']}."
            lines.append(line)
        else:
            lines.append(f"{inc['title']}: {d['blurb']} ({_boon_words(d.get('effect'))})")
    return lines


def _boon_words(effect: Optional[str]) -> str:
    return {
        "free_heal": "the temple heals for nothing while it lasts",
        "rest_double": "rest heals double while it lasts",
        "shop_discount": "the shops sell cheap while it lasts",
    }.get(effect or "", "")


def incident_summary(player) -> List[Dict[str, Any]]:
    """Compact active incidents for the web client and guidance."""
    from .content import get_location_or_none
    out = []
    for inc in active_incidents():
        loc = get_location_or_none(inc["location_id"])
        d = inc["data"]
        out.append({
            "id": inc["incident_id"], "kind": inc["kind"], "title": inc["title"],
            "blurb": d["blurb"], "location": inc["location_id"],
            "location_name": loc.name if loc else inc["location_id"],
            "here": inc["location_id"] == player.location,
            "turns_left": max(0, inc["expires_turn"] - get_world_turn()),
            "creatures_left": creatures_left(inc) if inc["kind"] == "incursion" else None,
            "creature_name": d.get("creature_name"),
            "effect": d.get("effect"),
            "effect_words": _boon_words(d.get("effect")) if inc["kind"] == "boon" else None,
        })
    return out


def incidents_status(player):
    """`news` / `incidents`: what is happening in the realm right now."""
    from .types import ActionResponse
    from .engine.state_view import build_action_state
    from .content import get_location_or_none
    msgs: List[str] = []
    live = active_incidents()
    if not live:
        msgs.append("The realm is quiet, for now. Word travels where people gather — `look` in town.")
    for inc in live:
        loc = get_location_or_none(inc["location_id"])
        d = inc["data"]
        where = loc.name if loc else inc["location_id"]
        left = inc["expires_turn"] - get_world_turn()
        if inc["kind"] == "incursion":
            n = creatures_left(inc)
            msgs.append(f"! {inc['title']} — {where}. {d['blurb']} {n} {d['creature_name']}{'s' if n != 1 else ''} "
                        f"remain; if none answer within {left} turns, they dig in.")
        else:
            msgs.append(f"+ {inc['title']} — {where}. {d['blurb']} {_boon_words(d.get('effect')).capitalize()}, "
                        f"{left} more turns.")
    past = [i for i in db.get_recent_incidents(6) if i["status"] != "active"]
    for inc in past[:3]:
        who = f" — ended by {inc['resolved_by_name']}" if inc.get("resolved_by_name") else ""
        msgs.append(f"  ({inc['status']}) {inc['title']}{who}")
    return ActionResponse(ok=True, messages=msgs, state=build_action_state(player, scene_dirty=False))
