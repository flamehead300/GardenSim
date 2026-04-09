# Garden Simulator — Agent Guidance

This file is the authoritative reference for any AI agent working on this
codebase. Read it in full before making changes. It records every deliberate
architectural decision, active constraints, and the feature backlog.

---

## Project layout

```
Garden_simulator/
├── main.py                        Entry point — creates GardenApp
└── garden_app/
    ├── app.py                     Kivy App subclass, wires model/controller/layout
    ├── model.py                   GardenModel — all observable state (Kivy properties)
    ├── controller.py              GardenController — all mutation logic, no UI code
    ├── commands.py                Undo/redo command objects (AddShape, DeleteShape, etc.)
    ├── constants.py               Color palette, CATEGORIES dict, strip dimensions
    ├── growth.py                  Plant growth state machine and tick logic
    ├── utils.py                   Pure geometry helpers, no Kivy imports
    ├── storage.py                 JSON save/load via StorageManager
    ├── file_io.py                 Open/Save As popup helpers
    ├── element_code_inspector.py  Right-click debug inspector (dev tool)
    ├── elevation_map.py           Generates a standalone Leaflet HTML terrain map
    ├── assets/
    │   └── plant_icons/           13 PNG icon sheets (64x64): tomato, pepper, root, …
    └── view/
        ├── canvas.py              GardenCanvas — StencilView, all drawing, touch proxy
        ├── layout.py              GardenLayout — root BoxLayout, all toolbar rows
        ├── plant_catalog.py       Searchable plant reference popup + placement trigger
        ├── plant_icons.py         Icon-key lookup and Kivy texture cache
        ├── property_panel.py      Selected-shape property editor panel
        ├── styles.py              Shared Kivy button/input style dicts (BTN_FLAT, etc.)
        └── terrain_map.py         TerrainMapPanel — persistent kivy_garden.mapview panel
```

---

## Architecture rules

### Model / Controller / View separation
- **GardenModel** holds every piece of observable state as a Kivy property.
  The canvas and layout bind to these properties for automatic redraws. Do not
  put logic in the model.
- **GardenController** owns all mutation. Never mutate `model.shapes` from a
  view file. Views call controller methods only.
- **GardenCanvas** is a pure renderer and touch proxy. It reads model state
  and passes world-coordinate events to the controller. It never writes to the
  model directly.
- **Commands** (`commands.py`) wrap every user-visible mutation so undo/redo
  works. Use `command_history.execute(SomeCommand(...))` for shape
  add/delete/move/modify. Do not bypass this for anything the user should be
  able to undo.

### Coordinate systems
- **World coordinates** — feet, origin (0,0) bottom-left, range
  `[0, width_ft] × [0, height_ft]`.
- **Canvas/screen coordinates** — pixels, Kivy origin bottom-left.
- Conversion: `canvas = offset + world * scale`. Both directions are
  implemented in `GardenCanvas.world_to_canvas` / `canvas_to_world`.
- All geometry stored in shapes uses world coordinates.

### Grid index — dict, not 2D array
The occupancy grid is a **plain Python dict** on the controller, not a Kivy
property and not a 2D list. Three attributes are maintained by
`_rebuild_garden_grid()` after every structural change:

```python
self._grid_index: dict        # (col, row) -> "plant" | "irrigation_hose" | "occupied"
self._active_hose_cells: set  # (col, row) keys for every hose piece
self._active_plant_cells: set # (col, row) keys for every placed plant
```

- `_grid_cell_is_empty(col, row)` — O(1) dict lookup: `(col, row) not in self._grid_index`.
- `_cell_has_water(col, row)` — checks `_active_hose_cells` for the cell and
  its 4 cardinal neighbours. No shape scan.
- `tick_growth()` iterates **only `_active_plant_cells`**, never the full
  shape list.

**Do not reintroduce a 2D list for occupancy.** The dict+set pattern scales to
large gardens without allocating memory proportional to garden area.

### Growth tick — delta pattern
When water flow is added (spigot → hose → soil → plant), follow the
two-phase pattern already described by the user:

1. Calculate all transfers / deltas without modifying current volumes.
2. Apply all deltas in a second pass.

This prevents water "teleporting" across the map in a single tick depending on
loop order. The `_cell_has_water` method is the correct insertion point for
water-level queries when that system is built.

### Sunlight overlay — background thread
`build_sunlight_overlay()` is expensive (42 sun samples × 256 grid cells ×
N shapes). It must **never** run on the main thread. The existing pattern in
`_start_sunlight_computation()` is correct:

1. Increment `_sunlight_token` (cancellation guard).
2. Spawn a `daemon=True` thread.
3. Post the result back via `Clock.schedule_once`.
4. Discard stale results by checking the token before writing to the model.

Do not call `build_sunlight_overlay()` synchronously from any user-facing
method.

---

## Shape data contract

Shapes are plain dicts stored in `model.shapes`. Required keys for all types:

```python
{
    "type":               "rect" | "circle" | "polygon" | "strip",
    "category":           key from CATEGORIES (or "Plant" / "Irrigation Hose"),
    "height_ft":          float,
    "locked_orientation": bool,
    "geom":               varies by type (see below),
}
```

Geometry by type:
- `rect` — `(x1, y1, x2, y2)` world feet
- `circle` — `(cx, cy, radius)` world feet
- `polygon` — `tuple of (x, y)` pairs, open ring (first ≠ last)
- `strip` — `((ax, ay), (bx, by))` centerline endpoints

Extra keys used by specific shape subtypes:

| Key | Present on | Meaning |
|---|---|---|
| `plant` | circle with a catalog plant | growth/icon/score metadata dict |
| `grid_item` | `"irrigation_hose"` or `"carrot_seed"` | identifies stamped grid items |
| `grid_cell` | any circle with plant or grid_item | `(col, row)` int tuple |
| `sun_score` | placed plant | 0–1 sunlight fraction at placement time |
| `hose_connections` | irrigation_hose | tuple of direction strings `("N","E",…)` |
| `hose_sprite` | irrigation_hose | `"isolated"/"end"/"straight"/"corner"/"tee"/"cross"` |
| `hose_rotation` | irrigation_hose | degrees for sprite rendering |
| `width_ft` | strip | visual width in feet |

**`grid_cell` values may be lists after JSON round-trip.** Always normalise
with `tuple(cell)` or `(int(cell[0]), int(cell[1]))` before using as a dict key.

---

## Plant growth system (`growth.py`)

- Progress is a **0–100 float** (`MAX_GROWTH_PROGRESS = 100.0`).
- `progress_per_day = 100.0 / maturity_days` — stored on each plant dict.
- State thresholds (in `growth_state_for_progress`):
  - `< 20` → `SEED`
  - `20–54` → `SPROUT`
  - `55–84` → `MATURE`
  - `≥ 85` → `FRUITING`
  - `DEAD` is sticky — once set, never changes back.
- `update_growth(plant, tick_days, has_water, has_fertilizer)` mutates the
  dict in-place and returns `True` if anything changed.
- `ensure_growth_payload(plant)` fills missing keys with safe defaults. Always
  call this before reading growth fields on a shape's plant dict.
- Water gate: `has_water=True` requires a hose in the same or adjacent grid
  cell (`_cell_has_water`).
- Fertilizer gate: `fertilizer` key on the plant dict, defaults to `1.0`.
  Set to `0.0` to block growth.
- On reaching 100%, `output` is set to a readable harvest string
  (`"Ripe Tomatoes"`, etc.).

---

## Catalog plants and icons

**Plant catalog** (`view/plant_catalog.py`):
- 59 named varieties in `PLANT_CATALOG`, keyed by `id` 1–59.
- `build_placeable_plant(plant)` enriches a catalog entry with
  `icon_key`, `icon_source`, `root_radius_ft`, `progress_per_day`,
  and `maturity_days` from `growth.py`.

**Icons** (`view/plant_icons.py` + `assets/plant_icons/`):
- 13 PNG spritesheets: `tomato`, `pepper`, `eggplant`, `vine`, `squash`,
  `corn`, `legume`, `root`, `brassica`, `leafy`, `herb`, `flower`, `generic`.
- `icon_key_for_plant(plant)` resolves a key from the `icon_key` field or
  by keyword-matching the plant name.
- `texture_for_icon(plant)` returns a cached Kivy texture or `None`.
  The canvas falls back to a 3-letter text label if `None`.
- The catalog row previously used emoji; it now uses a `PlantIconButton`
  (ButtonBehavior + Image) bound to the PNG source.

---

## Drag-to-stamp grid tools

Two modes stamped one item per newly-entered grid cell during a drag:

- `"irrigation_hose"` — places a circle with `category="Irrigation Hose"`,
  `grid_item="irrigation_hose"`. After each stamp, all adjacent hose sprites
  are recalculated (`_refresh_hose_sprites`). Canvas renders connected lines
  instead of a filled circle.
- `"carrot_seed"` — places a small circle with `category="Plant"`,
  `grid_item="carrot_seed"`, and a minimal plant dict (no catalog id).

Both tools:
- Use Bresenham cell interpolation (`_grid_line_cells`) so fast drags fill
  skipped cells.
- Skip occupied cells silently (no alert).
- Keep the mode active after release so repeated strokes work without
  re-selecting.
- Check `_grid_stamp_touch_active` — stamps only fire while a touch is held,
  never on hover.

---

## Canvas rendering pipeline

Order inside `GardenCanvas.redraw()`:
1. `_add_static_canvas()` — background, grid lines, axis labels. Cached as an
   `InstructionGroup`; only rebuilt when the static signature changes
   (pan/zoom/size/grid).
2. `_draw_sunlight_overlay()` — coloured cells from `model.sunlight_overlay`.
3. Shadows — `get_shadow_poly` per shape, drawn before shapes.
4. Shapes — fill, outline, label. For plant circles: growth ring
   (`_add_growth_stage_px`) + icon (`_draw_plant_icon_px`) + state label.
   For hose circles: `_draw_hose_piece` connected-line renderer.
5. `_draw_plant_preview()` — placement ghost during drag (green = ok, red = occupied).
6. Drawing previews — `drag_rect`, `drag_circle`, `drag_strip`, polygon points.
7. Snap indicator, sun arrow.

**Canvas redraws are debounced** via `Clock.schedule_once`. Multiple model
property changes in the same frame coalesce into one redraw.

**Text rendering is cached** — `_text_texture(text, font_size, color)` stores
`CoreLabel` textures in `_text_texture_cache`. The cache is cleared when it
exceeds 400 entries.

---

## Terrain map panel

`TerrainMapPanel` (`view/terrain_map.py`) is a persistent panel to the right
of the canvas (not a popup). It requires `kivy_garden.mapview`; if that is not
installed it shows a plain install hint label — this is intentional, not a bug.

Diagnostic environment switches for black-screen isolation:
- `GARDEN_DISABLE_TERRAIN_MAP=1` skips `MapView` construction entirely and
  shows a placeholder label.
- `GARDEN_TERRAIN_MAP_SOURCE=street` uses standard OpenStreetMap street tiles
  and is the default because it supports deeper zoom for yard-scale work.
- `GARDEN_TERRAIN_MAP_SOURCE=topo` uses OpenTopoMap tiles and preserves the
  older topographic view with the lower zoom ceiling.
- `GARDEN_TERRAIN_MAP_STAGE=map_only` creates raw `MapView` only.
- `GARDEN_TERRAIN_MAP_STAGE=marker_only` creates `MapView` plus marker only.
- `GARDEN_TERRAIN_MAP_STAGE=layer_no_edit` creates `MapView`, marker, and
  `GardenMapLayer`, but disables custom map editing/touch routing.
- `GARDEN_TERRAIN_MAP_STAGE=full` is the default full integration path.
- `GARDEN_DISABLE_MAP_EDITING=1` keeps the map/layer but disables custom map
  editing/touch routing.
- `GARDEN_DEBUG_TERRAIN_MAP=1` prints narrow construction, containment, layer,
  and projection checkpoints. Use it only for focused diagnostics.

Address search defaults to OpenStreetMap Nominatim via
`https://nominatim.openstreetmap.org/search` with a custom app User-Agent.
Override via `GARDEN_GEOCODER_URL`, `GARDEN_GEOCODER_USER_AGENT`, and optional
`GARDEN_GEOCODER_EMAIL` if the deployment needs a different geocoder or
contactable identity.
Timezone matching for selected coordinates uses offline `timezonefinder`
lookups. If the package is unavailable, the app falls back to the currently
selected timezone value instead of hard-failing.

Recentering behaviour:
- Marker moves whenever `model.lat` or `model.lon` changes.
- Map view **only recenters** when: the map has never been centered before, or
  the user is not actively touching the map, or `force=True` is passed.
- This prevents the map from jumping while the user is panning it.

The separate `elevation_map.py` generates a **standalone HTML file** using
Leaflet (browser-based), separate from the panel. The "Terrain Map" button in
the toolbar opens this HTML file — it is independent of `TerrainMapPanel`.

---

### Map overlay calibration

The garden overlay on `TerrainMapPanel` is a `MapLayer`, not a standalone
`GardenCanvas` stacked above the map.

Coordinate convention:
- local origin `(0, 0)` is the calibrated garden reference point A
- local `+x` is the calibrated A-to-B garden axis
- local `+y` defaults to the right-handed perpendicular from `+x`
- if the user toggles `Y +Down`, local `+y` is mirrored to the opposite
  perpendicular from `+x`

Persist `map_overlay_y_axis_sign` with the rest of the calibration payload.
Use `garden_app.map_projection` helpers for feet-to-geographic math rather
than reimplementing the transform in view code.

Overlay anchor state is explicit:
- `map_overlay_anchor_locked=False` means location/site updates move the whole
  overlay anchor to the current `model.lat/lon`.
- `map_overlay_anchor_locked=True` means location/site updates affect sun/map
  metadata but preserve the overlay's calibrated geographic placement.
- `map_overlay_calibration_mode` is an enum-like string. Use `"idle"` when no
  calibration flow is active and `"two_point"` while the two-tap calibration
  flow is active. Do not infer anchor-following from coordinate equality.

Interactive map editing must use the inverse transform:
`map touch -> widget x/y -> lat/lon -> local feet`. The MapView layer or panel
may translate touches, but all model mutations must still go through
`GardenController` so undo/redo, hit testing, property panels, grid metadata,
and simulation sync stay consistent with the normal canvas.

Width-bearing map overlay geometry must be generated in local feet before
projection. Circles and plant markers use sampled rings, strips use
`strip_polygon_from_centerline`, and hose pieces use foot-width polygons; do
not render these as center points plus a screen-space pixel radius on the map.

---

## Simulation clock (planned)

The `tick_growth(tick_days)` / `tick_growth_minutes(minutes)` methods exist
but are currently driven manually by the "Grow 1 Day" button in the toolbar.

When a continuous simulation clock is added, attach it as:
```python
Clock.schedule_interval(lambda dt: self.controller.tick_growth(dt / 86400), 1.0)
```
The update sequence when spigots are added should be:
1. `run_spigots()` — add water to hose network
2. `update_water_flow()` — two-phase delta equalisation across hose graph
3. `update_soil_saturation()` — soil absorbs from leaking hoses
4. `tick_growth()` — plants consume soil water and grow
   (Kivy properties trigger canvas redraw automatically)

---

## Known constraints and anti-patterns to avoid

- **Do not iterate `model.shapes` to compute hose sets or water availability.**
  Use `_active_hose_cells` and `_active_plant_cells` directly. Rebuild them
  only in `_rebuild_garden_grid()`, which is already called after every
  structural change.
- **Do not add a 2D occupancy array.** Occupancy is `_grid_index` (dict).
- **Do not call `build_sunlight_overlay()` on the main thread.**
- **Do not write to `model.shapes` outside a Command object** unless the
  change is transient (preview during drag). Persistent changes must be
  undoable.
- **`grid_cell` is a tuple of ints.** Normalise before dict/set use.
- **`growth_progress` is 0–100, not 0–1.** `progress_per_day` is
  `100.0 / maturity_days`.
- **`EMPTY`/`OCCUPIED` constants are removed.** Do not reintroduce them.
- **Style dicts live in `view/styles.py`** (`BTN_FLAT`, `BTN_ACTION`,
  `BTN_DANGER`, `BTN_BLUE`, `INPUT_FLAT`). Import from there rather than
  redefining inline.
- **Do not add docstrings or comments to code you didn't change.**
- **Do not create backwards-compatibility shims** (re-exports, `# removed`
  comments, unused `_var` renames).
