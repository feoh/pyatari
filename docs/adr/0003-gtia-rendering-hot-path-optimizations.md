# 0003: GTIA Rendering Hot-Path Optimizations

## Status

Accepted

## Date

2026-05-08

## Context

After establishing the benchmarking infrastructure (ADR 0002), profiling 30
demo-screen frames with `cProfile` revealed that GTIA rendering consumed the
large majority of total CPU time. The demo-screen frame benchmark ran at
1.2 fps, well below even minimal interactive use.

The top bottlenecks from the profiler (5 frames, 6.95 s total):

| Call site | tottime | ncalls |
|-----------|---------|--------|
| `_render_text_mode` | 2.40 s | 15,634 |
| `_overlay_player_missile_graphics` | 1.23 s | 19,544 |
| `builtins.max` | 0.88 s | 5,003,010 |
| `color_to_rgb` | 0.12 s (+ 0.02 s in `math.sqrt`) | 144,622 |

All four hot spots had semantically equivalent fixes that did not change
observable behavior or require restructuring the rendering model.

## Decision

Three changes to `src/pyatari/gtia.py`, each semantically identical to the
original:

### 1. `color_to_rgb` → module-level lookup table

`color_to_rgb` previously called `math.sqrt` for every color value (144,622
times per 5 frames). Since the Atari color register is 8 bits wide, there are
only 256 possible inputs. A module-level `_COLOR_TABLE` list pre-computes all
256 outputs once at import time using the same formula. `color_to_rgb` becomes
a single list index.

The original formula is preserved in the `_build_color_table` function so the
computation remains fully readable and auditable.

### 2. Hoist constants out of `_render_text_mode` inner loop

The inner bit loop contained two repeated computations that were constant for
the entire scanline:

- `max(1, cell_width // 8)` — computed once per bit per character (8 × 40 ×
  15,634 = **~5 million calls to `builtins.max`**). Since `cell_width` is
  always 8 or 16 (never 0), `cell_width // 8` is always 1 or 2; `max` is
  unnecessary. Replaced with `subpixel_count = cell_width // 8` computed once
  before the column loop.

- `fg = alt_fg if line.mode in {4, 5, 6, 7} else fg_color` — the mode is
  constant for the entire scanline. Hoisted outside the column loop.
  Eliminated ~625,000 set membership tests per 5 frames.

Also removed `inverse = bool(char_code & 0x80)` (unnecessary `bool()`
wrapper; replaced with `if char_code & 0x80:`).

### 3. Pre-compute `bg_color` once in `_overlay_player_missile_graphics`

This function previously called `self.color_to_rgb(self.write_registers[COLBK])`
inside the per-pixel loop for every missile and player pixel, repeatedly
computing the same background color. Moved to a single call before the loop.

## Consequences

### Positive

Benchmark results (Linux CPython 3.12 64-bit, same hardware):

| Benchmark | Before | After | Speedup |
|-----------|--------|-------|---------|
| `color_to_rgb` | 520 ns | 78 ns | **6.7×** |
| `render_scanline_text` | 197 µs | 143 µs | **1.38×** |
| `render_full_frame` | 46.2 ms | 33.9 ms | **1.36×** |
| `machine_run_frame_demo` | 822 ms (1.2 fps) | 688 ms (1.5 fps) | **+25%** |
| `machine_run_frame` (NOP sled) | 30.2 ms (33 fps) | 27.5 ms (36 fps) | **+10%** |

All 180 correctness tests continue to pass.

### Negative

- The demo screen frame rate (1.5 fps) is still far below interactive speed.
  The dominant remaining cost is the Python-level per-pixel loops in
  `_render_text_mode` and `_overlay_player_missile_graphics`. Eliminating
  those would require either a compiled extension or a fundamentally different
  rendering approach (e.g., only re-render changed regions, or use a bytearray
  framebuffer with bulk operations).

### Ongoing Implications

- `_COLOR_TABLE` is computed at import time; it adds ~0 overhead in practice.
  If the color formula ever changes, update `_build_color_table`.
- The next meaningful rendering speedup would likely require bulk array
  operations (e.g., `bytearray` + `struct.pack_into`) to replace per-pixel
  Python loops. That is a larger refactor and should be considered only after
  profiling confirms the per-pixel loop is still the dominant cost.
