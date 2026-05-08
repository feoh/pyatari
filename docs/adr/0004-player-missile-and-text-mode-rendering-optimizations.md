# 0004: Player/Missile and Text-Mode Rendering Optimizations

## Status

Accepted

## Date

2026-05-08

## Context

After the GTIA color-table and loop-hoisting improvements in ADR 0003, a
second `cProfile` pass on 10 demo-screen frames revealed three new dominant
bottlenecks:

| Call site | tottime | ncalls | Issue |
|-----------|---------|--------|-------|
| `_render_text_mode` | 3.19 s | 31,268 | Inner `for subpixel in range(1)` loop + `(0x80 >> bit)` per bit |
| `_overlay_player_missile_graphics` | 2.52 s | 31,268 | 8 × 384-element Python loops even with no sprites |
| `render_player` | 1.07 s | 156,344 | Allocates a new `[0] * 384` list on every call |
| `render_missiles` | 0.89 s | 39,086 | Allocates 4 new `[0] * 384` lists on every call |

All four are called on every CPU step that falls on a visible scanline (the
demo machine executes ~4,000 steps per frame). The combined cost was 7.67 s
out of 10.28 s total for 10 frames.

## Decision

### 1. P/M DMA buffer reuse (render_player / render_missiles)

`render_player` previously replaced `self.player_dma[player]` with a freshly
allocated `[0 for _ in range(384)]` list on every call. With ~16K calls per
frame, this produced ~16K small-object allocations per frame (plus GC
pressure). Changed to in-place clear with `player_row[:] = _ZERO_ROW` where
`_ZERO_ROW = (0,) * DISPLAY_WIDTH` is a module-level tuple created once at
import time.

Added `if not graphics: return` early exit so that calls with no visible
sprite do no pixel work at all. Same treatment applied to `render_missiles`.

### 2. `_pm_any_active` flag and `begin_scanline_render()`

`_overlay_player_missile_graphics` previously iterated all 8 DMA rows ×
384 pixels = 3,072 Python iterations per scanline even when no player or
missile had any active pixels (i.e., all DMA buffers were zero). For the
demo screen this was pure overhead.

Added a `_pm_any_active: bool` field to GTIA. It is:

- reset to `False` by the new `begin_scanline_render()` method, called once
  per visible scanline from `Machine._render_visible_scanlines()` before the
  four `render_player()` and one `render_missiles()` calls
- set to `True` inside `render_player` or `render_missiles` only when
  `graphics != 0` (i.e., only when pixels are actually written)

`_overlay_player_missile_graphics` returns immediately when
`_pm_any_active` is False, skipping all 3,072 iterations.

### 3. Text-mode inner loop → slice assignment

The per-column inner loop in `_render_text_mode` wrote 8 pixels (or 16
for double-width modes) via individual indexed assignments:

```python
for bit in range(8):
    pixel = fg if pattern & (0x80 >> bit) else bg
    x = base_x + bit * subpixel_count
    for subpixel in range(subpixel_count):   # range(1) for 8-wide modes
        if x + subpixel < DISPLAY_WIDTH:     # always True for text modes
            out_row[x + subpixel] = pixel
```

All text modes produce `columns × cell_width == 320` pixels, which is always
less than `DISPLAY_WIDTH (384)`, so the bounds check is always True and was
removed. The `for subpixel in range(1)` inner loop for 8-wide modes was pure
overhead.

Replaced with slice assignment driven by the module-level `_PIXEL_MASKS`
tuple `(0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)`:

```python
# subpixel_count == 1 (modes 2, 3, 4, 5 — the common case)
out_row[base_x:base_x + 8] = [fg if pattern & m else bg for m in _PIXEL_MASKS]

# subpixel_count == 2 (modes 6, 7)
out_row[base_x:base_x + 16] = [c for m in _PIXEL_MASKS for c in (fg if pattern & m else bg,) * 2]
```

The list comprehension + one slice assignment is substantially faster than
eight individual index assignments in CPython.

## Consequences

### Positive

Benchmark results compared to post-ADR-0003 baseline (Linux CPython 3.12):

| Benchmark | Before | After | Speedup |
|-----------|--------|-------|---------|
| `render_scanline_text` | 143 µs | 38.8 µs | **3.7×** |
| `render_full_frame` | 33.9 ms | 9.2 ms | **3.7×** |
| `machine_run_frame_demo` | 688 ms (1.5 fps) | 177 ms (5.7 fps) | **3.9×** |
| `machine_run_frame` (NOP sled) | 27.5 ms (36 fps) | 30 ms (33 fps) | ≈ neutral |

The demo screen is now running at 5.7 fps — nearly 5× faster than the 1.2 fps
baseline from before any optimization work.

All 180 correctness tests continue to pass.

### Negative

- The demo screen (5.7 fps) is still below interactive speed. The dominant
  remaining cost is the Python-level memory reads for glyph and screen data
  (~2.6 M `read_byte` calls per 10 frames) plus the list-comprehension
  overhead in the text mode loop itself.
- `begin_scanline_render()` is a new API entry point on GTIA; callers must
  remember to call it before each set of `render_player`/`render_missiles`
  calls. This is enforced by `Machine._render_visible_scanlines()` which is
  the only such caller.

### Ongoing Implications

- The next meaningful speedup would likely require either:
  a. Caching rendered glyph rows (avoid repeated `read_byte` per scanline
     repetition for the same character), or
  b. Moving to a compiled/vectorised pixel fill (e.g., `bytearray` + `struct`)
     to eliminate Python per-pixel overhead entirely.
- The `_pm_any_active` flag assumes `begin_scanline_render()` is called
  before each scanline's P/M render sequence. If a new caller is added that
  calls `render_player`/`render_missiles` without first calling
  `begin_scanline_render()`, sprites will silently not be overlaid.
