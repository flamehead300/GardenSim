"""Water spigot simulation entity."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import DEFAULT_SPIGOT_FLOW_RATE
from .base import GridEntity


@dataclass(eq=False)
class SpigotEntity(GridEntity):
    flow_rate: float = DEFAULT_SPIGOT_FLOW_RATE

    def __post_init__(self) -> None:
        self.entity_type = "spigot"
        self.flow_rate = float(self.flow_rate)
        super().__post_init__()

    def serialize(self) -> dict:
        payload = super().serialize()
        payload["flow_rate"] = self.flow_rate
        return payload

    @classmethod
    def deserialize(cls, payload: dict, world=None) -> "SpigotEntity":
        return cls(
            grid_x=int(payload["grid_x"]),
            grid_y=int(payload["grid_y"]),
            entity_id=payload.get("entity_id"),
            flow_rate=float(payload.get("flow_rate", DEFAULT_SPIGOT_FLOW_RATE)),
            _world=world,
        )
