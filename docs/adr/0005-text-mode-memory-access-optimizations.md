# 0005: Text-Mode Memory Access Optimizations

## Status

Accepted

## Date

2026-05-08

## Context

After the player/missile and text-mode rendering improvements in ADR 0004,
the demo-screen frame rate was 5.7 fps and a third `cProfile` pass showed
`read_byte` as the second-largest cost:

| Call site | tottime | ncalls | Issue |
|-----------|---------|--------|-------|
| `_render_text_mode` | 1.31 s | 31,268 | 80 `read_byte` calls per scanline |
| `read_byte` | 0.78 s | 2,629,750 | 95% sourced from text mode |
| `_render_visible_scanlines` | 0.24 s | 42,670 | 930 K dict.get() calls |

`read_byte` carries ~296 ns overhead per call (handler dict lookup + ROM
overlay check + function call stack), all of which is unnecessary for the two
hot reads inside `_render_text_mode`:

- **Screen data** — ANTIC DMA addresses are always in RAM; no handlers are
  registered in screen memory; the ROM overlay check always returns `None`.
- **Glyph data** — when the character set is in OS ROM, the data never
  changes; even for RAM charsets in demo/ROM-free mode, the bytearray
  subscript is sufficient.

`_render_visible_scanlines` called `write_registers.get(addr, 0)` 25 times
per step (for 4 players + missiles). All registers are initialised to 0 in
`GTIA.__post_init__`, so the `.get()` default is never needed.

## Decision

### 1. Screen data: bytearray slice instead of 40 × read_byte

```python
# Before: 40 individual read_byte calls per scanline
chars = [self.memory.read_byte(line.screen_address + col) for col in range(columns)]

# After: one bytearray slice
scr_start = line.screen_address & 0xFFFF
chars = self.memory.ram[scr_start:scr_start + columns]
```

ANTIC DMA screen addresses are always in RAM by construction; no valid Atari
program registers read handlers in screen memory. A comment in the source
documents this invariant.

### 2. Glyph data: per-row cache for ROM, direct RAM subscript for RAM charsets

**ROM charsets** (chbase in `OS_ROM_START`–`OS_ROM_END`): pre-compute a
128-entry `list[int]` of pattern bytes for every `(chbase_page, glyph_row)`
pair. Stored in `GTIA._glyph_cache`. ROM is immutable, so entries are never
stale. A full mode-2 frame produces only 8 distinct `glyph_row` values, so
the cache fills in 8 misses and then provides O(1) lookups for the remaining
~3,119 text scanlines per frame.

**RAM charsets** (custom or demo; chbase below OS ROM): read each glyph byte
directly from `self.memory.ram[...]` in the column loop — one bytearray
subscript per character (~30 ns) instead of one `read_byte` call (~296 ns).
No caching: RAM data can change between scanlines.

### 3. GTIA register reads: direct subscript instead of dict.get

`_render_visible_scanlines` passed 25 `write_registers.get(addr, 0)` calls
per step to the render functions. Since all addresses are initialised in
`GTIA.__post_init__`, replaced with `wr = self.gtia.write_registers` and
direct `wr[addr]` subscript. Eliminates the default-value handling path in
930 K `dict.get` calls per 10 frames.

## Consequences

### Positive

Benchmark results compared to post-ADR-0004 baseline (Linux CPython 3.12):

| Benchmark | Before (ADR 0004) | After | Speedup |
|-----------|----------|-------|---------|
| `render_scanline_text` | 38.8 µs | 27.8 µs | **1.4×** |
| `render_full_frame` | 9.2 ms | 6.6 ms | **1.4×** |
| `machine_run_frame_demo` | 177 ms (5.7 fps) | 136 ms (7.3 fps) | **1.3×** |
| `read_byte` calls | 2,629,750 | 128,310 | **−95%** |

**Cumulative improvement from original 1.2 fps baseline → 7.3 fps = 6.1×.**

All 180 correctness tests continue to pass (test suite runtime also fell from
~5 s to ~1.5 s as a side-effect of fewer `read_byte` calls in test fixtures).

### Negative

- The screen-data slice bypasses the memory-bus handler dispatch. If a future
  feature registers a read handler in screen memory (e.g., a DMA snooper for
  debugging), it would not fire during text rendering. The comment at the call
  site documents this limitation.
- The glyph cache is never explicitly invalidated. If a program loads a new
  ROM image at the same chbase address (not a valid Atari use case, but
  theoretically possible in a test), the cached glyph row would be stale.
  `GTIA._glyph_cache` can be cleared by calling `gtia._glyph_cache.clear()`
  if needed.

### Ongoing Implications

- The dominant remaining cost in `_render_text_mode` is the 40-column loop
  with its per-character list comprehension (`[fg if p&m else bg for m in
  _PIXEL_MASKS]`) and slice assignment. Each list comprehension allocates a
  new 8-element list. The next meaningful speedup here would require
  eliminating that allocation — either via a pre-allocated row buffer, a
  compiled extension, or a restructured framebuffer type (e.g., bytearray
  with packed pixels).
- `render_player` and `render_missiles` are now called ~195 K times per
  10-frame run and consume 0.29 s combined. Reducing their call frequency
  (e.g., by only re-rendering when registers change) would require a
  "dirty register" tracking mechanism in GTIA.
