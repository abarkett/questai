"""
Offline tests for the equipment system (Phase 4 slice 3).

Covers equip/unequip, stat bonuses (weapon damage, armor defense), swap
behavior, DB persistence, error cases, and gear flowing in as monster loot.

Run from server_py/:  python3 test_equipment.py
"""

import os
import tempfile

import app.db as db

_t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_t.close()
db.DB_PATH = _t.name
db.init_db()

from app.engine.entities import seed_world_monsters  # noqa: E402
seed_world_monsters()

from app.types import Player  # noqa: E402
from app.db import upsert_player, get_player  # noqa: E402
from app.engine.actions.equip import equip, unequip  # noqa: E402
from app.engine.actions.attack import attack  # noqa: E402
from app.progression import total_attack_damage, defense_bonus  # noqa: E402


def mk(**kw) -> Player:
    base = dict(player_id="e", location="town_square", level=1, xp=0, hp=30, max_hp=30)
    base.update(kw)
    base.setdefault("name", f"Hero_{base['player_id']}")  # unique name per id
    return Player(**base)


def main() -> None:
    # Equip a weapon -> damage goes up, item leaves inventory
    p = mk(inventory={"rusty_dagger": 1})
    upsert_player(p)
    assert total_attack_damage(p) == 3
    r = equip(p, "rusty dagger")
    assert r.ok and p.equipment.get("weapon") == "rusty_dagger"
    assert "rusty_dagger" not in p.inventory
    assert total_attack_damage(p) == 5  # 3 + 2
    print("PASS  equip weapon adds damage")

    # Swap weapon -> old one returns to inventory
    p.inventory["iron_sword"] = 1
    equip(p, "iron_sword")
    assert p.equipment["weapon"] == "iron_sword"
    assert p.inventory.get("rusty_dagger") == 1
    assert total_attack_damage(p) == 8  # 3 + 5
    print("PASS  swapping weapon returns the old one")

    # Equip armor -> defense
    p.inventory["leather_armor"] = 1
    equip(p, "leather armor")
    assert defense_bonus(p) == 2
    print("PASS  equip armor adds defense")

    # Unequip -> back to inventory
    r = unequip(p, "armor")
    assert r.ok and "armor" not in p.equipment and p.inventory.get("leather_armor") == 1
    assert defense_bonus(p) == 0
    print("PASS  unequip returns item to inventory")

    # Errors: non-gear and unowned
    assert equip(mk(inventory={"healing_herb": 1}), "healing_herb").ok is False
    assert equip(mk(), "iron_sword").ok is False
    print("PASS  cannot equip non-gear or unowned items")

    # Persistence through the DB
    pd = mk(player_id="e", inventory={"iron_sword": 1})
    equip(pd, "iron_sword")
    loaded = get_player("e")
    assert loaded.equipment.get("weapon") == "iron_sword", loaded.equipment
    print("PASS  equipment persists through the DB")

    # Armor reduces retaliation to the floor in real combat
    pa = mk(player_id="z", location="deep_forest", equipment={"armor": "steel_armor"}, inventory={})
    upsert_player(pa)
    before = pa.hp
    attack(pa, "Goblin")  # goblin attack 3 - defense 4 -> floored at 1
    assert pa.hp == before - 1, (before, pa.hp)
    print("PASS  armor reduces retaliation to the minimum")

    # Gear drops as loot on kill
    pk = mk(player_id="k", location="deep_forest", level=10, hp=99, max_hp=99, inventory={})
    upsert_player(pk)
    r = attack(pk, "Goblin")  # level 10 -> 12 dmg, one-shots the 12-hp goblin
    assert pk.inventory.get("rusty_dagger", 0) >= 1, (pk.inventory, r.messages)
    print(f"PASS  gear drops as loot on kill: {dict(pk.inventory)}")

    print("\nALL EQUIPMENT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        os.unlink(_t.name)
