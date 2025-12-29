from __future__ import annotations

from typing import List
from ..types_entities import Entity
from ..world_entities import WORLD_ENTITIES


def get_entities_at(location_id: str) -> List[Entity]:
    return WORLD_ENTITIES.get(location_id, [])


def find_entity(location_id: str, name: str) -> Entity | None:
    name = name.lower()
    for e in WORLD_ENTITIES.get(location_id, []):
        if e.name.lower() == name or e.entity_id.lower() == name:
            return e
    return None


def remove_entity(location_id: str, entity: Entity) -> None:
    WORLD_ENTITIES[location_id] = [
        e for e in WORLD_ENTITIES.get(location_id, []) if e.entity_id != entity.entity_id
    ]