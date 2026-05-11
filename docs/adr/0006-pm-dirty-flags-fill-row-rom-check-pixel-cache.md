# 0006: P/M Dirty Flags, Fill-Row Slice, ROM Check Reorder, and Per-Scanline Pixel Cache

## Status

Accepted

## Date

2026-05-11

## Context

After ADR 0005 the demo-screen frame rate was 7.3 fps. A fourth `cProfile`
pass over 10 frames surfaced four independent bottlenecks:

| Call site | tottime | ncalls | Issue |
|-----------|---------|--------|-------|
| `_render_text_mode` | 1.069 s | 31,268 | per-character list comprehension for each of 40 columns |
| `render_player` | 0.201 s | 195,460 | clearing all 384 pixels of 4 player buffers every scanline |
| `render_missiles` | 0.194 s | 195,460 | clearing all 384 pixels of 4 missile buffers every scanline |
| `_fill_row` | — | 42,670 | 384-iteration Python `for` loop to fill background color |

Additionally, `_read_rom_overlay` called `_os_rom_enabled()` (a method call
with `self.portb` check) unconditionally before testing `self.os_rom is not
None`, wasting 213 K method calls per 10-frame run in ROM-free configurations.

## Decision

### 1. Player/missile dirty flags

`render_player` and `render_missiles` previously cleared their DMA buffers
unconditionally at the start of every call, even when no sprites were active.
Two boolean tracking fields were added to `GTIA`:

```python
_player_dirty: list[bool]  # one per player (0–3)
_missiles_dirty: bool
```

Each `render_player` / `render_missiles` call now clears the buffer **only if**
the corresponding dirty flag is set (i.e., the buffer was written last
scanline). If the graphics value is zero the function returns early without
marking dirty — so a completely sprite-inactive frame pays only a flag check,
not a 384-element list write per buffer.

`_clear_pm_buffers` (called once per frame at frame start) resets all dirty
flags unconditionally.

### 2. `_fill_row` slice assignment

```python
# Before: 384-iteration Python loop
for x in range(DISPLAY_WIDTH):
    self.framebuffer[row][x] = color_value

# After: single slice assignment (C-level memcpy equivalent)
self.framebuffer[row][:] = [self.color_to_rgb(color_value)] * DISPLAY_WIDTH
```

`[color] * N` constructs the list at C speed; the slice assignment writes it
with a single `memcpy`-equivalent call, replacing 384 Python bytecode
dispatches with one.

### 3. ROM check reorder in `_read_rom_overlay` / `_is_rom_address`

```python
# Before: method call precedes None check
if self._os_rom_enabled() and self.os_rom is not None:

# After: cheap attribute check first
if self.os_rom is not None and self._os_rom_enabled():
```

When `os_rom` is `None` (ROM-free mode), Python short-circuits before calling
`_os_rom_enabled()`. Eliminates ~213 K method calls per 10-frame run.

### 4. Per-scanline 256-element list pixel cache in `_render_text_mode`

Each column in text mode requires an 8-element list of pixel values derived
from a pattern byte and two colors (fg / bg). For any given scanline, `fg` and
`bg` are constant across all 40 columns, so many columns share the same
pattern byte (most commonly 0x00 for space characters).

A `[None] * 256` list is allocated once per scanline call and indexed directly
by pattern byte:

```python
pixel_cache: list[list[int] | None] = [None] * 256
# ... inside column loop:
pixels = pixel_cache[pattern]
if pixels is None:
    pixel_cache[pattern] = pixels = [fg if pattern & m else bg for m in _PIXEL_MASKS]
out_row[column * 8:column * 8 + 8] = pixels
```

A 256-element list gives O(1) direct array subscript access with no hashing —
faster than `dict.get()` for the 40-lookup-per-scanline hot path. On a typical
BASIC screen with many space characters, only a handful of distinct patterns
appear per scanline, so the list comprehension runs far fewer than 40 times.

## Consequences

### Positive

Benchmark results compared to post-ADR-0005 baseline (Linux CPython 3.12):

| Benchmark | Before (ADR 0005) | After | Speedup |
|-----------|-------------------|-------|---------|
| `render_scanline_text` | 27.8 µs | 21.0 µs | **1.3×** |
| `render_full_frame` | 6.6 ms | 4.8 ms | **1.4×** |
| `machine_run_frame_demo` | 136 ms (7.3 fps) | 90 ms (11.1 fps) | **1.5×** |
| P/M render (sprite-inactive) | 0.395 s/10 frames | ~0.022 s/10 frames | **~18×** |

**Cumulative improvement from original 1.2 fps baseline → 11.1 fps = 9.25×.**

All 182 correctness tests continue to pass.

### Negative

- The dirty-flag logic assumes `_clear_pm_buffers` is called exactly once per
  frame before the scanline loop. If the call order changes, a dirty flag could
  be left set from the previous frame, causing a spurious buffer clear.
- The pixel cache is a `[None] * 256` list allocated per `render_scanline`
  call. For very short scanlines or low-text-density screens, the allocation
  overhead slightly offsets the savings. This is unlikely to matter in practice
  since text-mode frames always render 40 columns.

### Ongoing Implications

- `_render_text_mode` still dominates demo-screen frame time. The remaining
  cost is the 40-column slice assignment loop and `color_to_rgb` calls from
  `_fill_row`. The next meaningful speedup would require a compiled extension
  (Cython / C) or a restructured framebuffer type (e.g., a numpy array with
  vectorised color mapping).
- The NOP-sled frame rate (~25 fps) is now bounded by ANTIC tick overhead
  rather than rendering; further gains there require reducing tick granularity
  or batching tick calls.
