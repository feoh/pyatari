# 0009: Text Scanline Output Cache and Persistent Pixel Table

## Status

Accepted

## Date

2026-05-31

## Context

After the CPU and memory hot-path rewrites in ADRs 0007–0008, profiling of the demo
screen identified `_render_text_mode` as consuming **46.8% of total frame time**
(~21 µs per scanline call, ~93 806 calls per 30 profiled frames).

Three independent bottlenecks were visible:

1. **Per-scanline pixel cache setup** — `[None] * 256` allocated on every call, plus
   a per-character `if pixels is None:` check and an 8-element list comprehension on
   every cache miss.  For a 40-character line with ~25 unique pattern bytes, this
   produced ~25 list comprehension allocations per scanline.

2. **Repeated colour computation** — four `write_registers` dict lookups plus
   `color_to_rgb()` / `_hires_luminance_color()` calls on every scanline even when
   colours never changed between frames.

3. **No cross-frame result reuse** — a static text screen renders the same 22 unique
   scanline outputs on every frame at 60 fps, yet each call repeated the full inner
   loop (glyph lookup + pixel expansion + list→numpy conversion).

## Decision

### 1. Persistent pixel table keyed by `(fg, bg, subpixel_count)`

Replace the per-scanline `pixel_cache: list[list[int] | None] = [None] * 256` with a
persistent `_pixel_table` dict on the GTIA instance, keyed by
`(fg, bg, subpixel_count)`.  On first use for a colour combination, the full 256-entry
table is built at once; on subsequent calls it is a single `dict.get` hit.

This eliminates:
- The `[None] * 256` allocation on every scanline
- The `if pixels is None:` branch per character
- The 8-element list comprehension on every cache miss

### 2. Scanline output cache with phased key construction

Add a `_scanline_cache` dict (numpy row storage, cleared when it exceeds
`_SCANLINE_CACHE_MAX = 2048` entries) that caches the fully-rendered numpy row for each
unique scanline.

**Key structure**: `(COLPF0, COLPF1, COLPF2, COLBK, mode, bytes(patterns))`

- **Raw register values** (not colour_to_rgb output) defer expensive colour computation
  until after the cache check.
- **`bytes(patterns)`** is the 40-byte sequence of actual glyph pattern bytes computed
  from the characters and charset. For ROM charsets these come from `_glyph_cache`
  (fast); for RAM charsets they come from direct `memory.ram` reads (~4 µs).
  Including the actual byte values rather than character codes means RAM charsets that
  change mid-frame are automatically detected (different bytes → different key → miss).
  This also makes `glyph_row` and `chactl_inv` redundant in the key: they are already
  encoded in the pattern data.

**On a cache hit** (every frame after warmup for a static screen): the pre-rendered
numpy row is copied into `framebuffer[row]` directly (`np.ndarray` → `np.ndarray`),
bypassing colour computation, pixel expansion, list allocation, and list→numpy
conversion.

**On a cache miss**: the function proceeds with full computation, then stores
`framebuffer[row].copy()` (a 1-D `uint32` array) in the cache for future hits.

### 3. Phased function structure

`_render_text_mode` is restructured into six explicit phases:

1. **Cheap invariants** — `chars`, `glyph_row`, `chactl_inv`, `chbase_page`
2. **Glyph pattern bytearray** — one pass over `chars` that reads glyph data and
   applies inverse-character handling, producing the `patterns` bytearray used for
   both the cache key and pixel expansion
3. **Scanline cache check** — builds `sc_key` from raw registers + `bytes(patterns)`;
   returns immediately on hit
4. **Colour computation** (cache miss only) — `color_to_rgb` / hires-luminance logic
5. **Pixel expansion** (cache miss only) — iterates `patterns` (no second glyph read)
   using the persistent `pixel_table`
6. **Commit + cache store** — writes `out_row` to framebuffer; stores numpy copy

Colour computation (formerly ~5 µs per scanline) now runs only on cache misses.

### 4. Inline colour table access on cache miss

`_hires_luminance_color()` and `color_to_rgb()` method calls on cache misses are
replaced with direct `_COLOR_TABLE[...]` lookups (integer indexing, no method call
overhead) using pre-computed module-level register constants `_REG_COLPF0` etc.

## Consequences

- **Performance**: demo screen frame rate improved from 11.4 fps to **26.9 fps**
  (2.36×).  `render_scanline_text` benchmark improved from 26 µs → 7.5 µs (3.5×);
  `render_full_frame` from 5.35 ms → 1.71 ms (3.1×).
- **Correctness unchanged**: 182 tests pass.  RAM charsets that change mid-frame
  produce cache misses automatically (different pattern bytes → different key).
- **Cache memory**: each cache entry stores a 384-element `uint32` numpy array
  (1.5 KB).  A typical text screen with 192 unique scanlines uses ~288 KB.  The
  cache clears itself when entries exceed `_SCANLINE_CACHE_MAX = 2048`.
- **Animated / scrolling screens**: cache miss rate stays proportional to the rate
  of unique new scanlines.  For fully dynamic content, the overhead is one extra
  `bytes(patterns)` allocation and dict lookup per scanline — acceptable given that
  the pixel expansion savings on misses still apply (glyph reads separated from
  pixel expansion, no [None]×256 setup).
- **ROM vs RAM charset**: both paths produce correct cached outputs.  ROM charset
  hits are slightly cheaper (glyph_cache list lookup ~1 µs vs RAM read ~4 µs for
  the key patterns), but both benefit equally from the cached framebuffer write.
