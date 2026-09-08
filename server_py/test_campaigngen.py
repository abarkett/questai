"""
Tests for the generated campaign: Miriel authors each act of the Restoration
from the living world; code validates, repairs, falls back, and persists.

Run from server_py/:  python3 test_campaigngen.py
"""

import json
import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")
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
from app.campaigngen import (  # noqa: E402
    ACT_MARKER, CHRONICLE_MARKER, PATRON_MARKER, validate_act, world_dossier, ActValidationError,
)
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player, get_world_events  # noqa: E402
from app.world import get_location  # noqa: E402
from app.engine.state_view import effective_description  # noqa: E402
import app.restoration as R  # noqa: E402


# ---- the stub loremaster -----------------------------------------------

def act_json(index: int, *, bad_target: bool = False, boss: str = "The Hollow Sovereign") -> str:
    """A well-formed act in the model's voice, built on creatures that exist."""
    wrongs = [
        {"title": "The Rat-Kings of the Forest", "blurb": "Rats swarm the forest verges and the town's stores.",
         "deed_type": "kill", "target": "Ratt" if bad_target else "Rat", "required": 2, "patron": "Town Warden",
         "location": "forest", "restored": "The forest floor is clear of the swarm. Foragers walk the verges again without fear.",
         "title_earned": "Verge-Warden", "righted_text": "The last rat-king dies squealing. The forest breathes."},
        {"title": "The Mill Held Hostage", "blurb": "A bandit squats in the abandoned mill.",
         "deed_type": "kill", "target": "Bandit", "required": 1, "patron": "Old Merchant",
         "location": "old_mill", "restored": "The mill-wheel groans back into motion. Flour dust hangs gold in the light.",
         "title_earned": "Mill-Freer", "righted_text": "The bandit flees across the river. The wheel turns."},
        {"title": "Herbs for the Dawn", "blurb": "The temple's shelves are bare of herbs.",
         "deed_type": "collect", "target": "herb_bundle", "required": 2, "patron": "Temple Priest",
         "location": "temple", "restored": "Bundled herbs line the temple walls again, and the priest tends the hurt freely.",
         "title_earned": "Herb-Bearer", "righted_text": "The priest takes the bundles with both hands."},
        {"title": "Wolves on the Deep Road", "blurb": "Wolves haunt the deep forest road.",
         "deed_type": "kill", "target": "Wolf", "required": 1, "patron": "Huntmaster",
         "location": None, "restored": None,
         "title_earned": "Road-Opener", "righted_text": "The pack scatters into the dark."},
    ]
    if index == 1:
        wrongs = [
            {"title": "The Harpy's Crag", "blurb": "Harpies nest above the pass.",
             "deed_type": "kill", "target": "Harpy", "required": 1, "patron": "Mountain Ranger",
             "location": "mountain_pass", "restored": "The crag is silent; a caravan winds through the pass below.",
             "title_earned": "Crag-Clearer", "righted_text": "The harpy falls from the crag."},
            {"title": "The Glacier's Tenant", "blurb": "An ice troll holds the frozen cave.",
             "deed_type": "kill", "target": "Ice Troll", "required": 1, "patron": "Mountain Ranger",
             "location": "frozen_cave", "restored": "The cave rings with cutters' picks once more.",
             "title_earned": "Frost-Ender", "righted_text": "The troll shatters into blue shards."},
            {"title": "Word from the Depths", "blurb": "No one has returned from the sunless depths.",
             "deed_type": "visit", "target": "underdeep", "required": 1, "patron": "The Wanderer",
             "location": None, "restored": None,
             "title_earned": "Depth-Walker", "righted_text": "You return with word of the depths."},
            {"title": "The Cavern Troll", "blurb": "A cave troll blocks the stair down.",
             "deed_type": "kill", "target": "Cave Troll", "required": 1, "patron": "The Wanderer",
             "location": "cavern", "restored": "The cavern drips in silence. The stair lies open.",
             "title_earned": "Stair-Opener", "righted_text": "The troll topples. The way down is clear."},
        ]
    return json.dumps({
        "name": f"The Reckoning of Act {index + 1}",
        "blurb": "The realm's nearest wounds must close before its deeper ones can be reached.",
        "act_title": f"Reckoner {index + 1}",
        "completion_text": "The town's wounds close. The Chronicle turns a page and the realm looks outward.",
        "wrongs": wrongs,
        "climax": {
            "name": boss, "title": "Crowned in Hollow Bone",
            "blurb": "A crowned thing of hollow bone walks the Warfront and no blade alone can stop it.",
            "description": "It stands taller than the muster-tents, crowned in hollow bone. No one hero can bring it down; the realm together might.",
            "lair_desc": "The Warfront lies under its shadow, banners snapping. Spears bristle toward the crowned thing.",
            "minion_name": "Bone Whelp",
            "phase_messages": ["The Sovereign howls and a Bone Whelp claws up from the mud!",
                               "The Sovereign knits its bones and calls another Bone Whelp!"],
            "trophy_name": "Hollow Crown", "relic_name": "Sovereign's Edge", "relic_material": "iron_ore",
            "title_earned": "Sovereign-Ender",
            "completion_text": "The Hollow Sovereign collapses into a heap of bone. The Warfront is quiet.",
        },
    })


def dossier_of(prompt: str) -> dict:
    """The dossier JSON embedded in an act prompt (repair notes may follow it)."""
    tail = prompt.split("DOSSIER:\n", 1)[1]
    return json.JSONDecoder().raw_decode(tail)[0]


class Loremaster:
    """Answers act prompts with JSON, chronicle prompts with a sentence, and
    everything else with prose. Records every prompt it saw."""
    def __init__(self):
        self.prompts = []
        self.plan = {}  # act_index -> list of answers, consumed in order

    def __call__(self, q: str) -> str:
        self.prompts.append(q)
        if q.startswith(ACT_MARKER):
            idx = int(dossier_of(q)["act_index"])
            answers = self.plan.get(idx)
            if answers:
                return answers.pop(0)
            return act_json(idx, boss="The Hollow Sovereign" if idx == 0 else "The Pale Matriarch")
        if q.startswith(CHRONICLE_MARKER):
            return "Hero_a, with steel and stubbornness, cleared the rat-kings from the forest verges."
        if q.startswith(PATRON_MARKER):
            if "PUT RIGHT" in q:
                return "Bless Hero_a — the verges are clear, and I sleep again."
            return "The rats are in the grain and the children go hungry. Will you go where I cannot?"
        return "Test prose."


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="town_square",
                level=5, xp=0, hp=40, max_hp=40, inventory={"coin": 50})
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    lore = Loremaster()
    install_test_responder(lore)

    # ---- the referee: validation catches what the model gets wrong ----
    dossier = world_dossier(0, [])
    assert any(m["name"] == "Rat" for m in dossier["monsters"]) and any(n["name"] == "Town Warden" for n in dossier["npcs"])
    assert any(i["id"] == "herb_bundle" for i in dossier["items"])
    try:
        validate_act(json.loads(act_json(0, bad_target=True)), 0, dossier, [])
        assert False, "a bogus monster must be rejected"
    except ActValidationError as e:
        assert any("Ratt" in p for p in e.problems), e.problems
    ok = validate_act(json.loads(act_json(0)), 0, dossier, [])
    assert ok["source"] == "miriel" and len(ok["wrongs"]) == 5 and ok["wrongs"][-1]["deed_type"] == "climax"
    assert ok["wrongs"][0]["id"] == "a0_the_rat_kings_of_the_forest"
    assert ok["wrongs"][0]["deed"].startswith("Slay 2 Rats"), ok["wrongs"][0]["deed"]   # the engine writes the deed line
    assert ok["climax"]["base_hp"] == 800 and ok["climax"]["phases"][0]["summon"]["name"] == "Bone Whelp"
    print("PASS  the referee rejects unknown targets and assigns ids, deeds and numbers itself")

    # ---- repair: a rejected answer is fed back with its problems, once ----
    lore.plan[0] = [act_json(0, bad_target=True), act_json(0)]
    acts = R.get_acts()
    assert len(acts) == 1 and acts[0].source == "miriel" and acts[0].name == "The Reckoning of Act 1", acts
    act_prompts = [p for p in lore.prompts if p.startswith(ACT_MARKER)]
    assert len(act_prompts) == 2 and "rejected" in act_prompts[1] and "Ratt" in act_prompts[1]
    ev = [e for e in get_world_events(10) if e["event_type"] == "act_authored"]
    assert ev and ev[0]["data"]["source"] == "miriel"
    print("PASS  the opening act is authored by Miriel, repaired once, and persisted")

    # Written once: a second load is the same act, with no new prompt.
    n = len(lore.prompts)
    assert R.get_acts()[0].name == "The Reckoning of Act 1" and len(lore.prompts) == n
    assert db.get_campaign_act(0)["source"] == "miriel"
    print("PASS  an act is written once and shared")

    # ---- the generated climax is a real raid boss with real loot ----
    from app.raids import ensure_active_raid, _spec_for
    from app.db import get_active_raid_boss
    from app.items import get_item, get_recipe
    ensure_active_raid()
    boss = get_active_raid_boss()
    assert boss and boss["name"] == "The Hollow Sovereign" and boss["trophy"] == "trophy_a0_the_hollow_sovereign", boss
    assert _spec_for(boss)["phases"][0]["summon"]["name"] == "Bone Whelp"
    assert get_item(boss["trophy"]).name == "Hollow Crown"
    relic = get_recipe("relic_a0_the_hollow_sovereign")
    assert relic and relic["inputs"] == {boss["trophy"]: 1, "iron_ore": 3}, relic
    assert get_item("relic_a0_the_hollow_sovereign").damage == 18
    print("PASS  the generated climax rises at the Warfront with a trophy and a relic recipe")

    # ---- patrons speak in Miriel's voice, and the ledger line always follows ----
    p = mk("a")
    lines = R.patron_lines("Town Warden", p)
    assert any("children go hungry" in l and "`undertake a0_the_rat_kings_of_the_forest`" in l for l in lines), lines
    print("PASS  a patron pleads in Miriel's voice and the exact deed line follows")

    # ---- a generated wrong plays like any other, and the Chronicle speaks ----
    r = R.undertake(p, "a0_the_rat_kings_of_the_forest")
    assert r.ok, r
    msgs = R.right_wrong("a0_the_rat_kings_of_the_forest", p)
    upsert_player(p)
    assert R.is_righted("a0_the_rat_kings_of_the_forest") and "Verge-Warden" in p.titles
    assert any("steel and stubbornness" in m for m in msgs), msgs
    assert db.get_restoration("a0_the_rat_kings_of_the_forest")["entry"].startswith("Hero_a, with steel")
    assert "clear of the swarm" in effective_description(get_location("forest"))
    st = R.campaign_status(get_player("a"))
    assert any("steel and stubbornness" in m for m in st.messages)
    print("PASS  righting a generated wrong changes the world and the Chronicle narrates it")

    # ...and the patron now speaks of it with the Chronicle in view.
    thanks = R.patron_lines("Town Warden", mk("z"))
    assert any("Bless Hero_a" in l for l in thanks), thanks
    voiced_prompt = [q for q in lore.prompts if q.startswith(PATRON_MARKER) and "PUT RIGHT" in q][-1]
    assert "steel and stubbornness" in voiced_prompt      # the Chronicle entry reached the patron
    print("PASS  a patron's gratitude names the righter and quotes the Chronicle")

    # ---- the next act is written from what these players did ----
    fin = mk("fin")
    # The Warfront's threat is felled the real way (it dies), then the rest.
    db.damage_raid_boss(boss["raid_id"], boss["hp"], "fin", "Hero_fin")
    assert get_active_raid_boss() is None
    for w in R.get_acts()[0].wrongs:
        if not R.is_righted(w.id):
            R.right_wrong(w.id, fin)
    upsert_player(fin)
    assert R.is_act_complete(0)
    acts = R.get_acts()
    assert len(acts) == 2 and acts[1].index == 1 and acts[1].name == "The Reckoning of Act 2", [a.name for a in acts]
    assert R.current_act().index == 1
    last_prompt = [p for p in lore.prompts if p.startswith(ACT_MARKER)][-1]
    dossier1 = dossier_of(last_prompt)
    assert dossier1["act_index"] == 1
    assert any(c["righted_by"] == "Hero_a" and "steel" in (c["entry"] or "") for c in dossier1["chronicle"]), dossier1["chronicle"]
    assert dossier1["acts_so_far"][0]["climax_boss"] == "The Hollow Sovereign"
    assert "Rat" in dossier1["used_targets"] and "Hero_fin" in dossier1["heroes"]
    print("PASS  act two is authored from the Chronicle, the heroes, and the felled threat")

    # The second act's threat is a new boss; the old one stays felled.
    ensure_active_raid()
    boss2 = get_active_raid_boss()
    assert boss2 and boss2["raid_id"] == "raid_1" and boss2["name"] == "The Pale Matriarch", boss2
    assert get_item(boss2["trophy"]).name == "Hollow Crown" and boss2["hp"] > boss["max_hp"]  # act two hits harder
    assert R.undertake(mk("b"), "a1_the_harpy_s_crag").ok
    print("PASS  the next act's climax rises and its wrongs open")

    # ---- the campaign ends at its configured length ----
    fin2 = get_player("fin")
    for w in acts[1].wrongs:
        R.right_wrong(w.id, fin2)
    upsert_player(fin2)
    assert R.campaign_complete() and db.get_world_state("realm_restored") == "true"
    assert len(R.get_acts()) == 2                      # no act 3 with QUESTAI_CAMPAIGN_ACTS=2
    print("PASS  the realm is restored after the configured number of acts")

    # ---- fallback: when Miriel can't write an act, the authored one stands ----
    db2 = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False); db2.close()
    db.DB_PATH = db2.name
    db.init_db()
    seed_world_monsters()
    R._acts_cache.clear()
    install_test_responder(lambda q: "I cannot help with that.")
    acts = R.get_acts()
    assert acts[0].source == "authored" and acts[0].name == "The Town Besieged", acts[0]
    ensure_active_raid()
    assert get_active_raid_boss()["name"] == "The Ashen Dragon"
    print("PASS  without a usable answer the hand-authored act is the fallback")

    # ...and past the authored acts, a skeleton from the catalog.
    from app.campaigngen import skeleton_act
    sk = skeleton_act(3, world_dossier(3, acts), acts)
    assert sk["source"] == "skeleton" and len(sk["wrongs"]) == 5 and sk["wrongs"][-1]["deed_type"] == "climax"
    assert all(w["target"] in {m["name"] for m in world_dossier(3, acts)["monsters"]} for w in sk["wrongs"][:-1])
    print("PASS  beyond the authored acts a catalog skeleton keeps the campaign going")

    install_test_responder(None)
    os.unlink(db2.name)
    print("\nAll campaign generation tests passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
