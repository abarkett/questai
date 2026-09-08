"""
Tests for Miriel-authored region themes: a frontier opens onto a region whose
kind, places, creatures, boss, material and gear were written for it — under
the same stat referee as the bank, with the bank as the fallback.

Run from server_py/:  python3 test_regiongen_miriel.py
"""

import json
import os
import tempfile

os.environ.setdefault("QUESTAI_AP_REGEN_SECONDS", "0")
os.environ.pop("MIRIEL_API_KEY", None)

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402

seed_world_monsters()

from app.services.miriel_client import install_test_responder  # noqa: E402
from app.types import Player  # noqa: E402
from app.db import upsert_player, get_monsters_at  # noqa: E402
from app.regiongen import THEME_MARKER, THEMES, validate_theme, ThemeValidationError, _existing_names  # noqa: E402
from app.engine.actions.explore import explore  # noqa: E402
from app.items import get_item, get_recipe  # noqa: E402


def theme_json(*, name="Salt-Glass Reliquary", bad_monster=False) -> str:
    return json.dumps({
        "name": name, "outdoor": False,
        "loc_names": ["Brine Steps", "Glass Ossuary", "Reliquary Nave", "Weeping Font",
                      "Salt Choir", "Drowned Sacristy", "Pilgrim's Cistern", "The Last Altar"],
        "scenery": ["Salt crusts every surface like frost.", "Glass reliquaries hum faintly.",
                    "Water drips somewhere it should not.", "The air tastes of brine and candle-smoke."],
        "monsters": ["Rat" if bad_monster else "Brine Choirist", "Glass Pilgrim", "Salt Wight", "Font Leech"],
        "boss": "The Reliquary Warden",
        "boss_effect": "weaken",
        "material": "Salt Glass", "weapon": "Reliquary Blade", "armor": "Brine Mail",
        "npc": "Sexton of the Salt Choir",
        "entry_flavor": "Stairs of crusted salt descend into a humming dark.",
    })


class Loremaster:
    def __init__(self):
        self.prompts, self.answers = [], []

    def __call__(self, q: str) -> str:
        self.prompts.append(q)
        if q.startswith(THEME_MARKER):
            return self.answers.pop(0) if self.answers else theme_json()
        return "Test prose."


def mk(pid: str, **kw) -> Player:
    base = dict(player_id=pid, name=f"Hero_{pid}", location="riverside", level=3, xp=0, hp=30, max_hp=30)
    base.update(kw)
    p = Player(**base)
    upsert_player(p)
    return p


def main() -> None:
    lore = Loremaster()
    install_test_responder(lore)

    # ---- the referee ----
    existing = _existing_names()
    try:
        validate_theme(json.loads(theme_json(bad_monster=True)), existing)
        assert False, "an existing creature must be rejected"
    except ThemeValidationError as e:
        assert any("Rat" in p for p in e.problems), e.problems
    try:
        validate_theme(json.loads(theme_json(name="Verdant Maze")), existing)
        assert False, "a bank region name must be rejected"
    except ThemeValidationError as e:
        assert any("already exists" in p for p in e.problems), e.problems
    t = validate_theme(json.loads(theme_json()), existing)
    assert t["key"] == "salt_glass_reliquary" and t["material"] == ("salt_glass", "Salt Glass")
    assert t["boss_inflicts"] == {"effect": "weaken", "magnitude": 3, "turns": 3}
    print("PASS  the referee rejects reused names and slugs the rest")

    # ---- a frontier opens onto the authored region (after one repair) ----
    lore.answers = [theme_json(bad_monster=True), theme_json()]
    scout = mk("scout")
    r = explore(scout)
    assert r.ok and "Salt-Glass Reliquary" in " ".join(r.messages), r.messages
    theme_prompts = [p for p in lore.prompts if p.startswith(THEME_MARKER)]
    assert len(theme_prompts) == 2 and "rejected" in theme_prompts[1] and "Rat" in theme_prompts[1]
    assert "Riverside" in theme_prompts[0] and "towpath" in theme_prompts[0]      # written FROM the frontier
    region = db.get_region_by_origin("riverside")
    assert region["name"] == "Salt-Glass Reliquary" and region["data"]["theme_source"] == "miriel"
    assert region["data"]["theme_spec"]["boss"] == "The Reliquary Warden"
    print("PASS  the region behind the towpath is the one Miriel wrote for it")

    # Its creatures prowl, budgeted; its gear exists with recipes; its keeper waits.
    rid = region["region_id"]
    names = set()
    for row in db.get_all_gen_entities():
        if row["entity_id"].startswith(rid) and row["type"] == "monster":
            names.add(row["name"])
    assert {"Brine Choirist", "Glass Pilgrim", "Salt Wight", "Font Leech", "The Reliquary Warden"} & names, names
    assert "The Reliquary Warden" in names
    seeded = sum(len(get_monsters_at(l["location_id"])) for l in db.get_all_gen_locations() if l["region_id"] == rid)
    assert seeded >= 2
    assert get_item(f"salt_glass_{rid}").name == "Salt Glass"
    assert get_recipe(f"reliquary_blade_{rid}")["inputs"] == {f"salt_glass_{rid}": 4}
    assert any(row["name"] == "Sexton of the Salt Choir" for row in db.get_all_gen_entities())
    print("PASS  its creatures, gear and keeper are real and budgeted")

    # A second theme can't reuse the first's creatures: they are 'existing' now.
    assert "Brine Choirist" in _existing_names()["monsters"]
    assert "Salt-Glass Reliquary" in _existing_names()["regions"]
    print("PASS  what was written becomes canon the next author must avoid")

    # ---- fallback: when no sound theme comes back, the bank stands in ----
    lore.answers = ["no json here", "still nothing"]
    other = mk("other", location="tavern")
    r = explore(other)
    assert r.ok, r.error
    region2 = db.get_region_by_origin("tavern")
    assert region2["data"]["theme_source"] == "bank" and region2["name"] in {t["name"] for t in THEMES}, region2["name"]
    print("PASS  without a usable theme the bank is the fallback")

    install_test_responder(None)
    print("\nAll Miriel region theme tests passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
