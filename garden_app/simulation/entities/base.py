"""Common simulation entity base type."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..types import GridPos


@dataclass(eq=False)
class GridEntity:
    """Common base class for entities stored in the sparse simulation grid."""

    grid_x: int
    grid_y: int
    entity_id: str | None = None
    entity_type: str = "entity"
    _world: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.grid_x = int(self.grid_x)
        self.grid_y = int(self.grid_y)
        if not self.entity_id:
            self.entity_id = uuid4().hex
        if self._world is not None:
            world = self._world
            self._world = None
            world.add_entity(self)

    @property
    def grid_pos(self) -> GridPos:
        return self.grid_x, self.grid_y

    def destroy(self) -> None:
        if self._world is not None:
            self._world.remove_entity(self)

    def serialize(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
        }

    @classmethod
    def deserialize(cls, payload: dict, world=None) -> "GridEntity":
        return cls(
            grid_x=int(payload["grid_x"]),
            grid_y=int(payload["grid_y"]),
            entity_id=payload.get("entity_id"),
            entity_type=payload.get("entity_type", "entity"),
            _world=world,
        )
