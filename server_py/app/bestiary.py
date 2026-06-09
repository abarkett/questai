"""
Bestiary catalog: a per-name view of every monster defined in the world,
built from the world entity tables. Players discover entries by seeing or
fighting monsters; discovery is stored per-player on the Player model.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .world_entities import WORLD_ENTITIES
from .world import WORLD
from .types import Player


def _build_catalog() -> Dict[str, dict]:
    catalog: Dict[str, dict] = {}
    for loc_id, entities in WORLD_ENTITIES.items():
        for e in entities:
            if e.type != "monster":
                continue
            entry = catalog.setdefault(
                e.name,
                {
                    "name": e.name,
                    "max_hp": e.hp,
                    "attack": e.attack,
                    "xp_reward": e.xp_reward,
                    "loot": dict(e.loot or {}),
                    "inflicts": (e.inflicts or {}).get("effect") if e.inflicts else None,
                    "locations": [],
                },
            )
            loc_name = WORLD[loc_id].name if loc_id in WORLD else loc_id
            if loc_name not in entry["locations"]:
                entry["locations"].append(loc_name)
    return catalog


MONSTER_CATALOG: Dict[str, dict] = _build_catalog()


def _generated_catalog() -> Dict[str, dict]:
    """Bestiary entries for minted-region monsters (queried live, not import-time)."""
    from .content import monster_catalog, get_location_or_none

    catalog: Dict[str, dict] = {}
    for loc_id, e in monster_catalog():
        if e.name in MONSTER_CATALOG:
            continue
        entry = catalog.setdefault(
            e.name,
            {
                "name": e.name,
                "max_hp": e.hp,
                "attack": e.attack,
                "xp_reward": e.xp_reward,
                "loot": dict(e.loot or {}),
                "inflicts": (e.inflicts or {}).get("effect") if e.inflicts else None,
                "locations": [],
            },
        )
        loc = get_location_or_none(loc_id)
        loc_name = loc.name if loc else loc_id
        if loc_name not in entry["locations"]:
            entry["locations"].append(loc_name)
    return catalog


def known_monster(name: str) -> bool:
    return name in MONSTER_CATALOG or name in _generated_catalog()


def catalog_entry(name: str) -> Optional[dict]:
    return MONSTER_CATALOG.get(name) or _generated_catalog().get(name)


def all_monster_names() -> List[str]:
    return list(MONSTER_CATALOG.keys()) + list(_generated_catalog().keys())


def discover(player: Player, name: str) -> bool:
    """Record a monster in the player's bestiary. Returns True if newly added."""
    if known_monster(name) and name not in player.discovered_monsters:
        player.discovered_monsters.append(name)
        return True
    return False
