"""
Tests for world events with teeth: Miriel-authored incidents with real
mechanics — an incursion that closes a road until its intruders die, an
unanswered one that digs in, and boons that change a rule for a while.

Run from server_py/:  python3 test_incidents.py
"""

import json
import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")
os.environ["QUESTAI_INCIDENT_EVERY_TURNS"] = "3"
os.environ["QUESTAI_CAMPAIGN_ACTS"] = "2"
os.environ.pop("MIRIEL_API_KEY", None)

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.services.miriel_client import install_test_responder  # noqa: E402
from app.campaigngen import ACT_MARKER  # noqa: E402
from app.incidents import (  # noqa: E402
    INCIDENT_MARKER, validate_incident, IncidentValidationError, active_incidents, creatures_left,
    tick_incidents, maybe_author_incident, boon_active, exit_blocked_any, incident_summary,
)
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player, get_world_events, get_world_turn, get_monsters_at  # noqa: E402
from app.engine.parse_command import parse_command  # noqa: E402
from app.engine.apply_action import apply_action  # noqa: E402


def incursion_json(*, creature="Ash-Wolf", block="north_road", bad_location=False,
                   leader="The Grey Matriarch") -> str:
    return json.dumps({
        "kind": "incursion", "title": "Ash-Wolves on the North Road",
        "blurb": "A pack of ash-grey wolves has come down off the hills and holds the square's north gate.",
        "location": "nowhere" if bad_location else "town_square",
        "announce_text": "Ash-grey wolves slink into the square at dusk and take the north gate for their own.",
        "incursion": {
            "creature_name": creature, "count": 2, "blocks_exit_to": block,
            "resolution_text": "{hero} drove the ash-wolves from the north gate, and the road was walked again.",
            "consequence_text": "No one came for the wolves. They dug in at the gate, and a grey matriarch rose among them.",
            "leader_name": leader,
        },
        "duration_turns": 10,
    })


def boon_json(effect="rest_double") -> str:
    return json.dumps({
        "kind": "boon", "title": "The Festival of Lanterns",
        "blurb": "Lanterns hang in every street and the whole town sleeps easy.",
        "location": "town_square",
        "announce_text": "Lanterns go up across the town: the Festival of Lanterns begins.",
        "boon": {"effect": effect, "passing_text": "The last lanterns gutter out; the festival is over."},
        "duration_turns": 8,
    })


class Loremaster:
    def __init__(self):
        self.prompts, self.answers = [], []

    def __call__(self, q: str) -> str:
        self.prompts.append(q)
        if q.startswith(INCIDENT_MARKER):
            return self.answers.pop(0) if self.answers else "I have nothing to add."
        if q.startswith(ACT_MARKER):
            return "no act from me"        # the authored act stands in
        return "Test prose."


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=5, xp=0, hp=60, max_hp=60, inventory={"coin": 50})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def do(pid, cmd):
    return apply_action(player_id=pid, req_json=parse_command(cmd))


def spend_turns(pid, n):
    """Advance the world clock with harmless actions."""
    for _ in range(n):
        p = get_player(pid); p.hp = 1; upsert_player(p)
        r = do(pid, "rest")
        assert r.ok, r.error


def main() -> None:
    lore = Loremaster()
    install_test_responder(lore)
    from app.incidents import _dossier

    # ---- the referee ----
    d = _dossier()
    assert any(l["id"] == "town_square" and "north_road" in l["exits"] for l in d["locations"])
    try:
        validate_incident(json.loads(incursion_json(bad_location=True)), d)
        assert False
    except IncidentValidationError as e:
        assert any("nowhere" in p for p in e.problems), e.problems
    try:
        validate_incident(json.loads(incursion_json(creature="Rat")), d)
        assert False
    except IncidentValidationError as e:
        assert any("Rat" in p for p in e.problems), e.problems
    try:
        validate_incident(json.loads(incursion_json(block="forest")), d)   # not an exit of the square
        assert False
    except IncidentValidationError as e:
        assert any("forest" in p for p in e.problems), e.problems
    ok = validate_incident(json.loads(incursion_json()), d)
    assert ok["kind"] == "incursion" and ok["data"]["count"] == 2 and ok["duration"] == 10
    print("PASS  the referee rejects unknown places, existing creatures, and roads that aren't there")

    # ---- an incursion arrives on the cadence, with teeth ----
    a = mk("a")
    lore.answers = [incursion_json()]
    spend_turns("a", 3)
    live = active_incidents()
    assert len(live) == 1 and live[0]["kind"] == "incursion", live
    inc = live[0]
    assert creatures_left(inc) == 2
    assert any(m["name"] == "Ash-Wolf" for m in get_monsters_at("town_square"))
    started = [e for e in get_world_events(10) if e["event_type"] == "incident_started"]
    assert started and "north gate" in started[0]["data"]["description"]
    print("PASS  an incursion is authored from the world and its creatures are real")

    # The road it holds is closed; look and news say so; guidance points at it.
    r = do("a", "go north road")
    assert not r.ok and "Ash-Wolf" in r.error and "North Road" in r.error, r.error
    r = do("a", "look")
    assert any("Ash-Wolves on the North Road" in m and "hold the way" in m for m in r.messages), r.messages
    r = do("a", "news")
    assert any("Ash-Wolves" in m and "remain" in m for m in r.messages), r.messages
    assert any(g["command"] == "fight Ash-Wolf" for g in r.state["guidance"]), r.state["guidance"]
    assert r.state["incidents"][0]["here"] and r.state["incidents"][0]["creatures_left"] == 2
    print("PASS  the held road is closed, and look, news, guidance and the web state all say so")

    # ---- slaying the last intruder ends it, names the slayer, opens the road ----
    coins = get_player("a").inventory.get("coin", 0)
    kills = 0
    for _ in range(12):
        r = do("a", "fight bold Ash-Wolf")
        if not r.ok:
            break
        if any("is defeated" in m for m in r.messages):
            kills += 1
        if any("is ended" in m for m in r.messages):
            break
        p = get_player("a"); p.hp = 60; upsert_player(p)
    assert kills == 2, (kills, r.messages)
    assert any("Hero_a drove the ash-wolves" in m for m in r.messages), r.messages
    assert any("North Road is open again" in m for m in r.messages), r.messages
    assert db.get_incident(inc["incident_id"])["status"] == "resolved"
    assert db.get_incident(inc["incident_id"])["resolved_by_name"] == "Hero_a"
    assert get_player("a").inventory.get("coin", 0) > coins
    assert do("a", "go north road").ok
    resolved = [e for e in get_world_events(10) if e["event_type"] == "incident_resolved"]
    assert resolved and resolved[0]["data"]["player_name"] == "Hero_a"
    print("PASS  the last kill ends the incursion, pays and names the slayer, and reopens the road")

    # ---- an unanswered incursion digs in ----
    do("a", "go town square")
    lore.answers = [incursion_json(creature="Cinder Jackal", block="north_road", leader="The Jackal Sire").replace(
        "Ash-Wolves on the North Road", "Jackals at the Gate")]
    spend_turns("a", 3)
    inc2 = next(i for i in active_incidents() if i["kind"] == "incursion")
    assert inc2["data"]["creature_name"] == "Cinder Jackal"
    spend_turns("a", 10)                      # nobody answers
    assert db.get_incident(inc2["incident_id"])["status"] == "expired"
    assert any(m["name"] == "The Jackal Sire" for m in get_monsters_at("town_square"))
    expired = [e for e in get_world_events(15) if e["event_type"] == "incident_expired"]
    assert expired and "dug in" in expired[0]["data"]["description"]
    r = do("a", "go north road")
    assert not r.ok and "Jackals at the Gate" in r.error, r.error          # the road stays held
    print("PASS  an unanswered incursion digs in: a leader rises and the road stays closed")

    # Killing them all — leader included — still opens it.
    for _ in range(30):
        if not exit_blocked_any("town_square", "north_road"):
            break
        target = "The Jackal Sire" if not any(m["name"] == "Cinder Jackal" for m in get_monsters_at("town_square")) else "Cinder Jackal"
        do("a", f"fight bold {target}")
        p = get_player("a"); p.hp = 60; upsert_player(p)
    assert exit_blocked_any("town_square", "north_road") is None
    assert do("a", "go north road").ok
    print("PASS  cutting down the dug-in pack and its leader reopens the road")

    # ---- a boon changes a rule while it lasts ----
    do("a", "go town square")
    lore.answers = [boon_json("rest_double")]
    spend_turns("a", 3)
    assert boon_active("rest_double")
    p = get_player("a"); p.hp = 1; upsert_player(p)
    r = do("a", "rest")
    assert any("+8 HP" in m for m in r.messages), r.messages       # REST_HP 4, doubled
    r = do("a", "look")
    assert any("Festival of Lanterns" in m and "double" in m for m in r.messages), r.messages
    summ = incident_summary(get_player("a"))
    assert summ and summ[0]["kind"] == "boon" and summ[0]["effect"] == "rest_double"
    print("PASS  a boon doubles rest while it lasts, and the square says why")

    # A second boon while one is active: at most MAX_ACTIVE, and the incursion
    # slot is respected by the prompt.
    lore.answers = [boon_json("free_heal").replace("The Festival of Lanterns", "Blessing of the Dawn")]
    spend_turns("a", 3)
    assert boon_active("free_heal")
    from app.engine.actions.heal import heal_cost
    assert heal_cost() == 0
    assert len(active_incidents()) == 2
    lore.answers = [incursion_json(creature="Bog Hound", leader="The Bog Alpha")]
    spend_turns("a", 3)                                       # no room: nothing authored
    assert len(active_incidents()) == 2
    print("PASS  boons stack to the cap; the temple heals free under a blessing")

    # ...and they pass.
    spend_turns("a", 9)
    assert not boon_active("rest_double") and not boon_active("free_heal")
    passed = [e for e in get_world_events(20) if e["event_type"] == "incident_expired" and "lanterns" in e["data"]["description"]]
    assert passed
    print("PASS  boons pass, and history says so")

    # ---- what happened feeds the next act ----
    from app.campaigngen import world_dossier
    from app.restoration import get_acts
    dd = world_dossier(1, get_acts())
    kinds = {(i["title"], i["status"], i["resolved_by"]) for i in dd["incidents"]}
    assert ("Ash-Wolves on the North Road", "resolved", "Hero_a") in kinds, kinds
    assert ("Jackals at the Gate", "expired", None) in kinds, kinds
    assert "Hero_a" in dd["heroes"]
    print("PASS  incidents — answered and unanswered — enter the dossier the next act is written from")

    install_test_responder(None)
    print("\nAll incident tests passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
