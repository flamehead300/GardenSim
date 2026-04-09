"""Irrigation hose simulation entity."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import (
    DEFAULT_HOSE_CAPACITY,
    DEFAULT_HOSE_FLOW_RATE,
    DEFAULT_HOSE_INITIAL_WATER,
    EPSILON_WATER,
    HOSE_EQUALIZATION_DIVISOR,
    MIN_WATER_LEVEL,
)
from ..types import GridPos
from .base import GridEntity


@dataclass(eq=False)
class HoseEntity(GridEntity):
    water_level: float = DEFAULT_HOSE_INITIAL_WATER
    max_capacity: float = DEFAULT_HOSE_CAPACITY
    flow_rate: float = DEFAULT_HOSE_FLOW_RATE
    is_active: bool = False

    def __post_init__(self) -> None:
        self.entity_type = "hose"
        self.max_capacity = float(self.max_capacity)
        self.flow_rate = float(self.flow_rate)
        self.water_level = max(
            MIN_WATER_LEVEL,
            min(float(self.water_level), self.max_capacity),
        )
        self.is_active = self.water_level > EPSILON_WATER
        super().__post_init__()

    def update_activity_state(self) -> bool:
        self.water_level = max(
            MIN_WATER_LEVEL,
            min(float(self.water_level), self.max_capacity),
        )
        next_active = self.water_level > EPSILON_WATER
        changed = next_active != self.is_active
        self.is_active = next_active
        world = self._world
        if world is not None:
            if self.is_active:
                world.active_hoses.add(self.grid_pos)
            else:
                world.active_hoses.discard(self.grid_pos)
        return changed

    def get_connected_neighbors(self, world) -> tuple[tuple[GridPos, "HoseEntity"], ...]:
        neighbors = []
        for neighbor_pos in world.get_neighbors4(*self.grid_pos):
            neighbor = world.get_entity(*neighbor_pos)
            if isinstance(neighbor, HoseEntity):
                neighbors.append((neighbor_pos, neighbor))
        return tuple(neighbors)

    def request_outflows(
        self,
        world,
        processed_edges: set[frozenset[GridPos]] | None = None,
    ) -> dict[GridPos, float]:
        self.update_activity_state()
        if not self.is_active:
            return {}

        deltas: dict[GridPos, float] = {}
        own_pos = self.grid_pos
        for neighbor_pos, neighbor in self.get_connected_neighbors(world):
            edge = frozenset((own_pos, neighbor_pos))
            if processed_edges is not None:
                if edge in processed_edges:
                    continue
                processed_edges.add(edge)

            difference = self.water_level - neighbor.water_level
            if abs(difference) <= EPSILON_WATER:
                continue

            if difference > MIN_WATER_LEVEL:
                source_pos, source = own_pos, self
                target_pos, target = neighbor_pos, neighbor
            else:
                source_pos, source = neighbor_pos, neighbor
                target_pos, target = own_pos, self

            source_available = max(MIN_WATER_LEVEL, source.water_level - MIN_WATER_LEVEL)
            target_capacity = max(MIN_WATER_LEVEL, target.max_capacity - target.water_level)
            amount = min(
                abs(difference) / HOSE_EQUALIZATION_DIVISOR,
                source.flow_rate,
                target.flow_rate,
                source_available,
                target_capacity,
            )
            if amount <= EPSILON_WATER:
                continue

            deltas[source_pos] = deltas.get(source_pos, MIN_WATER_LEVEL) - amount
            deltas[target_pos] = deltas.get(target_pos, MIN_WATER_LEVEL) + amount
        return deltas

    def serialize(self) -> dict:
        payload = super().serialize()
        payload.update(
            {
                "water_level": self.water_level,
                "max_capacity": self.max_capacity,
                "flow_rate": self.flow_rate,
                "is_active": self.is_active,
            }
        )
        return payload

    @classmethod
    def deserialize(cls, payload: dict, world=None) -> "HoseEntity":
        return cls(
            grid_x=int(payload["grid_x"]),
            grid_y=int(payload["grid_y"]),
            entity_id=payload.get("entity_id"),
            water_level=float(payload.get("water_level", DEFAULT_HOSE_INITIAL_WATER)),
            max_capacity=float(
                payload.get("max_capacity", payload.get("capacity", DEFAULT_HOSE_CAPACITY))
            ),
            flow_rate=float(payload.get("flow_rate", DEFAULT_HOSE_FLOW_RATE)),
            is_active=bool(payload.get("is_active", False)),
            _world=world,
        )
