"""Sparse, headless simulation world using spatial hashing."""

from __future__ import annotations

from .constants import (
    GROWTH_STATE_FRUITING,
    GROWTH_STATE_MATURE,
    GROWTH_STATE_SEED,
    GROWTH_STATE_SPROUT,
    MIN_PLANT_FERTILIZER,
    MIN_WATER_LEVEL,
    GROWTH_FRUITING_THRESHOLD,
    GROWTH_MATURE_THRESHOLD,
    GROWTH_SPROUT_THRESHOLD,
)
from .entities.base import GridEntity
from .entities.factory import entity_from_payload
from .entities.hose import HoseEntity
from .entities.plant import PlantEntity
from .entities.spigot import SpigotEntity
from .types import GridPos


class SimulationWorld:
    """Headless sparse-grid simulation state."""

    def __init__(self) -> None:
        self.garden_grid: dict[GridPos, GridEntity] = {}
        self.active_hoses: set[GridPos] = set()
        self.active_plants: set[GridPos] = set()
        self.active_spigots: set[GridPos] = set()
        self._entity_positions: dict[str, GridPos] = {}
        self.tick_count = 0

    def add_entity(self, entity: GridEntity) -> GridEntity:
        entity_id = str(entity.entity_id)
        pos = entity.grid_pos
        if entity_id in self._entity_positions:
            existing_pos = self._entity_positions[entity_id]
            if self.garden_grid.get(existing_pos) is entity:
                return entity
            raise ValueError(f"Duplicate entity_id: {entity_id}")
        existing = self.garden_grid.get(pos)
        if existing is not None and existing is not entity:
            raise ValueError(f"Grid position already occupied: {pos}")

        self.garden_grid[pos] = entity
        self._entity_positions[entity_id] = pos
        entity._world = self
        self._register_active(entity, pos)
        return entity

    def remove_entity(self, entity: GridEntity) -> None:
        entity_id = str(entity.entity_id)
        pos = self._entity_positions.pop(entity_id, None)
        if pos is None:
            entity._world = None
            return

        if self.garden_grid.get(pos) is entity:
            self.garden_grid.pop(pos, None)
        self._unregister_active(entity, pos)
        entity._world = None

    def move_entity(self, entity: GridEntity, new_x: int, new_y: int) -> None:
        entity_id = str(entity.entity_id)
        old_pos = self._entity_positions.get(entity_id)
        if old_pos is None:
            raise ValueError("Cannot move an entity that is not registered.")

        new_pos = (int(new_x), int(new_y))
        existing = self.garden_grid.get(new_pos)
        if existing is not None and existing is not entity:
            raise ValueError(f"Grid position already occupied: {new_pos}")

        self.garden_grid.pop(old_pos, None)
        self._unregister_active(entity, old_pos)
        entity.grid_x, entity.grid_y = new_pos
        self.garden_grid[new_pos] = entity
        self._entity_positions[entity_id] = new_pos
        self._register_active(entity, new_pos)

    def get_entity(self, x: int, y: int) -> GridEntity | None:
        return self.garden_grid.get((int(x), int(y)))

    def get_entity_by_id(self, entity_id: str) -> GridEntity | None:
        pos = self._entity_positions.get(str(entity_id))
        if pos is None:
            return None
        return self.garden_grid.get(pos)

    def get_neighbors4(self, x: int, y: int) -> tuple[GridPos, GridPos, GridPos, GridPos]:
        grid_x = int(x)
        grid_y = int(y)
        return (
            (grid_x, grid_y + 1),
            (grid_x + 1, grid_y),
            (grid_x, grid_y - 1),
            (grid_x - 1, grid_y),
        )

    def serialize(self) -> dict:
        return {
            "tick_count": self.tick_count,
            "entities": [
                entity.serialize()
                for _pos, entity in sorted(self.garden_grid.items())
            ],
        }

    @classmethod
    def deserialize(cls, payload: dict) -> "SimulationWorld":
        world = cls()
        world.tick_count = int(payload.get("tick_count", 0))
        for entity_payload in payload.get("entities", []):
            entity_from_payload(entity_payload, world=world)
        return world

    def _register_active(self, entity: GridEntity, pos: GridPos) -> None:
        if isinstance(entity, HoseEntity):
            entity.update_activity_state()
        elif isinstance(entity, PlantEntity):
            if not entity.is_dead():
                self.active_plants.add(pos)
        elif isinstance(entity, SpigotEntity):
            self.active_spigots.add(pos)

    def _unregister_active(self, entity: GridEntity, pos: GridPos) -> None:
        if isinstance(entity, HoseEntity):
            self.active_hoses.discard(pos)
        elif isinstance(entity, PlantEntity):
            self.active_plants.discard(pos)
        elif isinstance(entity, SpigotEntity):
            self.active_spigots.discard(pos)

    def inject_spigots(self) -> dict[GridPos, float]:
        water_deltas: dict[GridPos, float] = {}
        for spigot_pos in tuple(self.active_spigots):
            spigot = self.get_entity(*spigot_pos)
            if not isinstance(spigot, SpigotEntity):
                continue
            hose_positions = [
                pos
                for pos in (spigot_pos, *self.get_neighbors4(*spigot_pos))
                if isinstance(self.get_entity(*pos), HoseEntity)
            ]
            if not hose_positions:
                continue
            amount = spigot.flow_rate / len(hose_positions)
            for hose_pos in hose_positions:
                water_deltas[hose_pos] = water_deltas.get(hose_pos, MIN_WATER_LEVEL) + amount
        self.apply_hose_water_deltas(water_deltas)
        return water_deltas

    def calculate_flow_requests(self) -> dict[GridPos, float]:
        water_deltas: dict[GridPos, float] = {}
        processed_edges: set[frozenset[GridPos]] = set()
        for hose_pos in tuple(self.active_hoses):
            hose = self.get_entity(*hose_pos)
            if not isinstance(hose, HoseEntity):
                continue
            for delta_pos, delta in hose.request_outflows(self, processed_edges).items():
                water_deltas[delta_pos] = water_deltas.get(delta_pos, MIN_WATER_LEVEL) + delta
        return water_deltas

    def consume_plant_water(self) -> set[GridPos]:
        water_deltas: dict[GridPos, float] = {}
        watered_plants: set[GridPos] = set()
        for plant_pos in tuple(self.active_plants):
            plant = self.get_entity(*plant_pos)
            if not isinstance(plant, PlantEntity):
                continue
            if plant.is_dead():
                self.active_plants.discard(plant_pos)
                continue
            if plant.consume_water(self, water_deltas):
                watered_plants.add(plant_pos)
        self.apply_hose_water_deltas(water_deltas)
        return watered_plants

    def apply_hose_water_deltas(self, water_deltas: dict[GridPos, float]) -> None:
        for hose_pos, delta in water_deltas.items():
            hose = self.get_entity(*hose_pos)
            if not isinstance(hose, HoseEntity):
                continue
            hose.water_level = max(
                MIN_WATER_LEVEL,
                min(hose.max_capacity, hose.water_level + delta),
            )
            hose.update_activity_state()

    def update_plants(self, watered_plants: set[GridPos]) -> None:
        for plant_pos in tuple(self.active_plants):
            plant = self.get_entity(*plant_pos)
            if not isinstance(plant, PlantEntity):
                continue

            has_water = plant_pos in watered_plants
            plant.has_water = has_water
            if plant.is_dead():
                self.active_plants.discard(plant_pos)
                continue

            if has_water and plant.fertilizer > MIN_PLANT_FERTILIZER:
                plant.advance_growth()
                plant.recover_health()
            else:
                plant.degrade_health()

            if plant.is_dead():
                self.active_plants.discard(plant_pos)

    def refresh_active_sets(self) -> None:
        self.active_hoses.clear()
        self.active_plants.clear()
        self.active_spigots.clear()
        for pos, entity in tuple(self.garden_grid.items()):
            if isinstance(entity, HoseEntity):
                entity.update_activity_state()
            elif isinstance(entity, PlantEntity):
                if not entity.is_dead():
                    self.active_plants.add(pos)
            elif isinstance(entity, SpigotEntity):
                self.active_spigots.add(pos)

    @staticmethod
    def _growth_state_for_progress(progress: float) -> str:
        if progress < GROWTH_SPROUT_THRESHOLD:
            return GROWTH_STATE_SEED
        if progress < GROWTH_MATURE_THRESHOLD:
            return GROWTH_STATE_SPROUT
        if progress < GROWTH_FRUITING_THRESHOLD:
            return GROWTH_STATE_MATURE
        return GROWTH_STATE_FRUITING
