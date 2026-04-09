"""Plant simulation entity."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import (
    DEFAULT_PLANT_FERTILIZER,
    DEFAULT_PLANT_GROWTH_RATE,
    DEFAULT_PLANT_HEALTH,
    DEFAULT_PLANT_MAX_HEALTH,
    DEFAULT_PLANT_NAME,
    DEFAULT_PLANT_VITALITY,
    DEFAULT_PLANT_WATER_CONSUMPTION,
    GROWTH_STATE_DEAD,
    GROWTH_STATE_FRUITING,
    GROWTH_STATE_MATURE,
    GROWTH_STATE_SEED,
    GROWTH_STATE_SPROUT,
    HEALTH_DEAD_THRESHOLD,
    HEALTH_DECAY_PER_DRY_TICK,
    HEALTH_RECOVERY_PER_WET_TICK,
    MAX_GROWTH_PROGRESS,
    MIN_GROWTH_PROGRESS,
    MIN_PLANT_VITALITY,
    MIN_WATER_LEVEL,
    PLANT_VISUAL_FRUIT_THRESHOLD,
    PLANT_VISUAL_MATURE_THRESHOLD,
    PLANT_VISUAL_STAGE_FRUIT,
    PLANT_VISUAL_STAGE_MATURE,
    PLANT_VISUAL_STAGE_SEED,
    PLANT_VISUAL_STAGE_SPROUT,
    PLANT_VISUAL_STAGE_WITHERED,
    PLANT_VISUAL_SPROUT_THRESHOLD,
    VITALITY_DECAY_PER_DRY_TICK,
    VITALITY_RECOVERY_PER_WET_TICK,
)
from ..types import GridPos
from .base import GridEntity
from .hose import HoseEntity


@dataclass(eq=False)
class PlantEntity(GridEntity):
    plant_name: str = DEFAULT_PLANT_NAME
    growth_progress: float = MIN_GROWTH_PROGRESS
    health: float = DEFAULT_PLANT_HEALTH
    water_consumption_per_tick: float = DEFAULT_PLANT_WATER_CONSUMPTION
    growth_rate_per_tick: float = DEFAULT_PLANT_GROWTH_RATE
    visual_stage: str = PLANT_VISUAL_STAGE_SEED
    sprite_source: str = PLANT_VISUAL_STAGE_SEED
    growth_state: str | None = None
    growth_rate: float | None = None
    water_consumption: float | None = None
    max_health: float = DEFAULT_PLANT_MAX_HEALTH
    vitality: float = DEFAULT_PLANT_VITALITY
    fertilizer: float = DEFAULT_PLANT_FERTILIZER
    has_water: bool = False

    def __post_init__(self) -> None:
        self.entity_type = "plant"
        self.plant_name = str(self.plant_name or DEFAULT_PLANT_NAME)
        if self.growth_rate is not None:
            self.growth_rate_per_tick = self.growth_rate
        if self.water_consumption is not None:
            self.water_consumption_per_tick = self.water_consumption
        self.growth_progress = max(
            MIN_GROWTH_PROGRESS,
            min(MAX_GROWTH_PROGRESS, float(self.growth_progress)),
        )
        self.health = float(self.health)
        if self.health <= HEALTH_DEAD_THRESHOLD:
            self.health = HEALTH_DEAD_THRESHOLD
        self.max_health = float(self.max_health)
        self.vitality = float(self.vitality)
        self.water_consumption_per_tick = float(self.water_consumption_per_tick)
        self.growth_rate_per_tick = float(self.growth_rate_per_tick)
        self.fertilizer = float(self.fertilizer)
        self.has_water = bool(self.has_water)
        self.update_visual_state()
        super().__post_init__()

    def consume_water(self, world, water_deltas: dict[GridPos, float] | None = None) -> bool:
        water_deltas = {} if water_deltas is None else water_deltas
        for hose_pos in (self.grid_pos, *world.get_neighbors4(*self.grid_pos)):
            hose = world.get_entity(*hose_pos)
            if not isinstance(hose, HoseEntity):
                continue
            available = hose.water_level + water_deltas.get(hose_pos, MIN_WATER_LEVEL)
            if available < self.water_consumption_per_tick:
                continue
            water_deltas[hose_pos] = (
                water_deltas.get(hose_pos, MIN_WATER_LEVEL) - self.water_consumption_per_tick
            )
            self.has_water = True
            return True
        self.has_water = False
        return False

    def advance_growth(self) -> bool:
        if self.is_dead():
            return False
        before = self.growth_progress
        self.growth_progress = min(
            MAX_GROWTH_PROGRESS,
            self.growth_progress + self.growth_rate_per_tick,
        )
        self.update_visual_state()
        return self.growth_progress != before

    def degrade_health(self) -> bool:
        before = (self.health, self.vitality, self.visual_stage)
        self.health = max(HEALTH_DEAD_THRESHOLD, self.health - HEALTH_DECAY_PER_DRY_TICK)
        self.vitality = max(MIN_PLANT_VITALITY, self.vitality - VITALITY_DECAY_PER_DRY_TICK)
        self.update_visual_state()
        return before != (self.health, self.vitality, self.visual_stage)

    def recover_health(self) -> bool:
        if self.is_dead():
            return False
        before = (self.health, self.vitality, self.visual_stage)
        self.health = min(self.max_health, self.health + HEALTH_RECOVERY_PER_WET_TICK)
        self.vitality = min(DEFAULT_PLANT_VITALITY, self.vitality + VITALITY_RECOVERY_PER_WET_TICK)
        self.update_visual_state()
        return before != (self.health, self.vitality, self.visual_stage)

    def update_visual_state(self) -> str:
        if self.health <= HEALTH_DEAD_THRESHOLD:
            self.visual_stage = PLANT_VISUAL_STAGE_WITHERED
            self.sprite_source = PLANT_VISUAL_STAGE_WITHERED
            self.growth_state = GROWTH_STATE_DEAD
        elif self.growth_progress >= PLANT_VISUAL_FRUIT_THRESHOLD:
            self.visual_stage = PLANT_VISUAL_STAGE_FRUIT
            self.sprite_source = PLANT_VISUAL_STAGE_FRUIT
            self.growth_state = GROWTH_STATE_FRUITING
        elif self.growth_progress >= PLANT_VISUAL_MATURE_THRESHOLD:
            self.visual_stage = PLANT_VISUAL_STAGE_MATURE
            self.sprite_source = PLANT_VISUAL_STAGE_MATURE
            self.growth_state = GROWTH_STATE_MATURE
        elif self.growth_progress >= PLANT_VISUAL_SPROUT_THRESHOLD:
            self.visual_stage = PLANT_VISUAL_STAGE_SPROUT
            self.sprite_source = PLANT_VISUAL_STAGE_SPROUT
            self.growth_state = GROWTH_STATE_SPROUT
        else:
            self.visual_stage = PLANT_VISUAL_STAGE_SEED
            self.sprite_source = PLANT_VISUAL_STAGE_SEED
            self.growth_state = GROWTH_STATE_SEED
        self.growth_rate = self.growth_rate_per_tick
        self.water_consumption = self.water_consumption_per_tick
        return self.visual_stage

    def is_dead(self) -> bool:
        return (
            self.health <= HEALTH_DEAD_THRESHOLD
            or self.visual_stage == PLANT_VISUAL_STAGE_WITHERED
            or self.growth_state == GROWTH_STATE_DEAD
        )

    def is_withered(self) -> bool:
        return self.is_dead()

    def serialize(self) -> dict:
        payload = super().serialize()
        payload.update(
            {
                "plant_name": self.plant_name,
                "growth_progress": self.growth_progress,
                "health": self.health,
                "water_consumption_per_tick": self.water_consumption_per_tick,
                "growth_rate_per_tick": self.growth_rate_per_tick,
                "visual_stage": self.visual_stage,
                "sprite_source": self.sprite_source,
                "growth_state": self.growth_state,
                "growth_rate": self.growth_rate_per_tick,
                "water_consumption": self.water_consumption_per_tick,
                "max_health": self.max_health,
                "vitality": self.vitality,
                "fertilizer": self.fertilizer,
                "has_water": self.has_water,
            }
        )
        return payload

    @classmethod
    def deserialize(cls, payload: dict, world=None) -> "PlantEntity":
        return cls(
            grid_x=int(payload["grid_x"]),
            grid_y=int(payload["grid_y"]),
            entity_id=payload.get("entity_id"),
            plant_name=payload.get("plant_name", DEFAULT_PLANT_NAME),
            growth_progress=float(payload.get("growth_progress", MIN_GROWTH_PROGRESS)),
            health=float(payload.get("health", DEFAULT_PLANT_HEALTH)),
            water_consumption_per_tick=float(
                payload.get(
                    "water_consumption_per_tick",
                    payload.get("water_consumption", DEFAULT_PLANT_WATER_CONSUMPTION),
                )
            ),
            growth_rate_per_tick=float(
                payload.get(
                    "growth_rate_per_tick",
                    payload.get("growth_rate", DEFAULT_PLANT_GROWTH_RATE),
                )
            ),
            visual_stage=payload.get(
                "visual_stage",
                payload.get("sprite_source", PLANT_VISUAL_STAGE_SEED),
            ),
            sprite_source=payload.get("sprite_source", PLANT_VISUAL_STAGE_SEED),
            growth_state=payload.get("growth_state"),
            growth_rate=payload.get("growth_rate"),
            water_consumption=payload.get("water_consumption"),
            max_health=float(payload.get("max_health", DEFAULT_PLANT_MAX_HEALTH)),
            vitality=float(payload.get("vitality", DEFAULT_PLANT_VITALITY)),
            fertilizer=float(payload.get("fertilizer", DEFAULT_PLANT_FERTILIZER)),
            has_water=bool(payload.get("has_water", False)),
            _world=world,
        )
