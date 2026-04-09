"""Entity payload reconstruction helpers."""

from __future__ import annotations

from .base import GridEntity
from .hose import HoseEntity
from .plant import PlantEntity
from .spigot import SpigotEntity


ENTITY_TYPES = {
    "entity": GridEntity,
    "hose": HoseEntity,
    "plant": PlantEntity,
    "spigot": SpigotEntity,
}


def entity_from_payload(payload: dict, world=None) -> GridEntity:
    entity_cls = ENTITY_TYPES.get(str(payload.get("entity_type", "entity")), GridEntity)
    return entity_cls.deserialize(payload, world=world)
