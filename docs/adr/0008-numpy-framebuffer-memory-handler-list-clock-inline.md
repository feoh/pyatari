# 0008: NumPy Framebuffer, Memory Handler List, and Clock Inline

## Status

Accepted

## Date

2026-05-27

## Context

After the CPU optimizations in ADR 0007, profiling shifted the dominant costs
to the GTIA rendering pipeline and the memory subsystem:

1. **Memory handler dispatch via dict (~0.08 s/20 frames).**
   `read_byte()` and `write_byte()` used `dict.get()` to locate hardware
   register handlers.  Python dict hash lookups have fixed overhead per call,
   and these methods are called millions of times per frame.

2. **ROM overlay check on every RAM read.**
   The `read_byte()` fast path always called `_read_rom_overlay()` even for
   addresses in the lower 20 KB (≤ `0x4FFF`) where no ROM overlay can ever
   exist.

3. **GTIA framebuffer as a Python list of lists.**
   `_fill_row()` assigned to a list slice, and `clear_framebuffer()` did a
   double loop.  Bulk row-fill operations had no C-level acceleration.

4. **`_render_bitmap_mode` per-pixel Python loop.**
   Each pixel of a bitmap scanline was computed and appended individually in
   Python, then written into the framebuffer one element at a time.

5. **`clock.tick()` method call overhead.**
   `Machine.step()` called `self.clock.tick(elapsed)` every instruction.  The
   `Clock.tick()` method did one thing: add `elapsed` to `total_cycles`.

## Decision

### 1. Replace memory handler dicts with 65 536-element lists

`_read_handler_table` and `_write_handler_table` are now
`list[handler | None]` of length `0x10000`, initialised with `None`.
Dispatching by address becomes a direct list subscript — O(1) with no hashing:

```python
handler = self._read_handler_table[address]
if handler is not None:
    return handler(address) & 0xFF
```

Register/unregister operations write directly to the appropriate index.

### 2. Low-address fast path in `read_byte` / `write_byte`

The Atari 800XL memory map places all ROM overlays at `0x5000` and above
(Self-Test ROM, OS ROM, BASIC ROM).  For any `address < 0x5000` we can return
`self.ram[address]` immediately without calling `_read_rom_overlay()`:

```python
if address < 0x5000:
    return self.ram[address]
```

### 3. NumPy framebuffer

`GTIA.framebuffer` is now `np.ndarray` of shape `(240, 384)` with
`dtype=np.uint32`.  This enables three C-level bulk operations:

- `_fill_row(row, color)` → `self.framebuffer[row] = packed_rgb_scalar`
  (NumPy broadcasts a scalar across the entire 384-element row.)
- `clear_framebuffer()` → `self.framebuffer[:] = packed_rgb_scalar`
- `_apply_horizontal_scroll` → slice assignment for the whole row.

### 4. Hybrid text rendering: Python pixel cache + single NumPy commit

Fully vectorising `_render_text_mode` with NumPy (`frombuffer`, fancy
indexing, `np.where`) was benchmarked and found to be **slower** than the
existing Python pixel cache.  The root cause is NumPy's per-call array
allocation overhead (~2–5 µs each); 7–8 array creations per 40-character
scanline accumulates to 15–40 µs, which exceeds any computation savings for
such small arrays.

The solution retains the Python pixel cache for the inner loop, but collects
pixel values into a plain Python list (`out_row`) and commits to the
framebuffer with a single NumPy assignment at the end of the scanline:

```python
out_row: list[int] = [bg_color] * DISPLAY_WIDTH
# ... inner Python loop fills out_row ...
self.framebuffer[row] = out_row   # single C-level commit
```

### 5. `_render_bitmap_mode` uses NumPy for pixel expansion

For bitmap modes the per-pixel arrays are large enough that NumPy vectorisation
wins.  `np.repeat()` expands pixel colour values to the correct width in one
C call:

```python
expanded = np.repeat(np.array(pixels, dtype=np.uint32), repeat)
self.framebuffer[row, :n] = expanded[:n]
```

### 6. Inline `clock.tick()` in `Machine.step()`

`Clock.tick()` only increments `total_cycles`.  Calling a method for a single
addition per instruction costs more than the addition itself.  The call is
replaced with an in-line attribute increment at both the normal and WSYNC code
paths:

```python
self.clock.total_cycles += elapsed  # was: self.clock.tick(elapsed)
```

## Consequences

- **Correctness unchanged**: all 182 tests continue to pass.
- **Performance**: NOP-sled frame rate improved from ~24.8 fps (pre-ADR 0007
  baseline) to ~53.5 fps after ADR 0007 + 0008 combined.  Demo-screen
  throughput is ~10.4 fps.  The memory handler list and ROM fast path
  contribute measurably to both paths.
- **NumPy is now a runtime dependency** of `pyatari.gtia` (it was already a
  dev/test dependency; the framebuffer field makes it a hard import).
- **`display.py` returns `np.ndarray`** from `frame_from_gtia()`.  Callers
  expecting a Python list must be updated — currently only tests and the
  placeholder display helper use this API.
- **Avoid NumPy for small (<128 element) inner loops**: the bitmap vs. text
  mode decision shows clearly that NumPy overhead dominates when arrays are
  allocated per-call on small data.  Future optimisations should benchmark
  before assuming NumPy is faster.
