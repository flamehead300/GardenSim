"""Top-level deterministic simulation engine orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    BASE_TICK_SECONDS,
    DEFAULT_CATCHUP_CHUNK_TICKS,
    DEFAULT_ENGINE_SYNC_INTERVAL_TICKS,
    MIN_ELAPSED_SECONDS,
    OFFLINE_CATCHUP_MAX_TICKS,
)
from .types import GridPos


TICK_ORDER = (
    "spigot injection",
    "flow request calculation",
    "flow application",
    "plant consumption and health updates",
    "cleanup / active-set refresh",
    "persistence sync checkpoint if needed",
)


@dataclass
class SimulationEngine:
    """Owns the strict top-level tick order documented by TICK_ORDER."""

    world: Any
    repositories: tuple[Any, ...] = ()
    sync_interval_ticks: int = DEFAULT_ENGINE_SYNC_INTERVAL_TICKS
    catch_up_chunk_ticks: int = DEFAULT_CATCHUP_CHUNK_TICKS
    last_sync_time: float | None = None
    last_simulated_unix_time: float | None = None
    last_persisted_tick: int | None = None
    tick_count: int = field(init=False)
    _accumulated_seconds: float = field(default=MIN_ELAPSED_SECONDS, init=False)
    _pending_flow_deltas: dict[GridPos, float] = field(default_factory=dict, init=False)
    _watered_plants: set[GridPos] = field(default_factory=set, init=False)
    _last_persisted_tick: int = field(default=0, init=False)
    _catch_up_active: bool = field(default=False, init=False)
    _defer_persistence: bool = field(default=False, init=False)
    _last_catch_up_monotonic_seconds: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.repositories = tuple(self.repositories or ())
        self.tick_count = int(getattr(self.world, "tick_count", 0))
        self.world.tick_count = self.tick_count
        if self.last_persisted_tick is None:
            self._last_persisted_tick = self.tick_count
        else:
            self._last_persisted_tick = int(self.last_persisted_tick)
        if self.last_simulated_unix_time is None and self.last_sync_time is not None:
            self.last_simulated_unix_time = float(self.last_sync_time)

    def tick(self, dt: float) -> int:
        seconds = self._coerce_seconds(dt)
        self._accumulated_seconds += seconds
        ticks = int(self._accumulated_seconds // BASE_TICK_SECONDS)
        if ticks <= 0:
            return 0
        self._accumulated_seconds -= ticks * BASE_TICK_SECONDS
        return self.run_ticks(ticks)

    def run_ticks(self, ticks: int) -> int:
        count = max(0, int(ticks))
        for _index in range(count):
            self.perform_logic_tick()
        return count

    def catch_up_simulation(self, seconds_passed: float, max_ticks: int | None = None) -> int:
        if self._catch_up_active:
            return 0
        tick_limit = OFFLINE_CATCHUP_MAX_TICKS if max_ticks is None else int(max_ticks)
        ticks = int(self._coerce_seconds(seconds_passed) // BASE_TICK_SECONDS)
        total_ticks = max(0, min(ticks, tick_limit))
        if total_ticks <= 0:
            return 0

        self._catch_up_active = True
        self._defer_persistence = True
        started_wall = time.time()
        started_monotonic = time.monotonic()
        start_simulated = self.last_simulated_unix_time
        if start_simulated is None:
            start_simulated = started_wall - (total_ticks * BASE_TICK_SECONDS)

        ran = 0
        try:
            chunk_size = max(1, int(self.catch_up_chunk_ticks))
            while ran < total_ticks:
                chunk = min(chunk_size, total_ticks - ran)
                self.run_ticks(chunk)
                ran += chunk
                self.last_simulated_unix_time = start_simulated + (ran * BASE_TICK_SECONDS)
                self.sync_persistence_checkpoint(
                    force=True,
                    saved_at=self.last_simulated_unix_time,
                )
        finally:
            self._defer_persistence = False
            self._catch_up_active = False
            self._last_catch_up_monotonic_seconds = time.monotonic() - started_monotonic
        return ran

    def perform_logic_tick(self) -> None:
        self.inject_spigots()
        self.calculate_flow_requests()
        self.apply_flow_requests()
        self.update_plants()
        self.cleanup_active_sets()
        self.tick_count += 1
        self.world.tick_count = self.tick_count
        if not self._catch_up_active:
            self.last_simulated_unix_time = time.time()
        self.sync_persistence_checkpoint()

    def inject_spigots(self) -> dict[GridPos, float]:
        return self.world.inject_spigots()

    def calculate_flow_requests(self) -> dict[GridPos, float]:
        self._pending_flow_deltas = self.world.calculate_flow_requests()
        return dict(self._pending_flow_deltas)

    def apply_flow_requests(self, flow_deltas: dict[GridPos, float] | None = None) -> None:
        deltas = self._pending_flow_deltas if flow_deltas is None else flow_deltas
        self.world.apply_hose_water_deltas(deltas)
        if flow_deltas is None:
            self._pending_flow_deltas = {}

    def update_plants(self) -> set[GridPos]:
        self._watered_plants = self.world.consume_plant_water()
        self.world.update_plants(self._watered_plants)
        return set(self._watered_plants)

    def cleanup_active_sets(self) -> None:
        self.world.refresh_active_sets()

    def sync_persistence_checkpoint(
        self,
        force: bool = False,
        saved_at: float | None = None,
    ) -> bool:
        if self._defer_persistence and not force:
            return False
        if not self.repositories:
            return False
        if self.sync_interval_ticks <= 0 and not force:
            return False
        if (
            not force
            and self.tick_count - self._last_persisted_tick < self.sync_interval_ticks
        ):
            return False

        saved_at = (
            float(saved_at)
            if saved_at is not None
            else float(self.last_simulated_unix_time or time.time())
        )
        for repository in self.repositories:
            repository.save_world(self.world, saved_at=saved_at)
        self.last_sync_time = saved_at
        self.last_simulated_unix_time = saved_at
        self._last_persisted_tick = self.tick_count
        return True

    @staticmethod
    def _coerce_seconds(value: float) -> float:
        try:
            return max(MIN_ELAPSED_SECONDS, float(value))
        except (TypeError, ValueError):
            return MIN_ELAPSED_SECONDS
