# 0010: Inverse Text Cursor and Scanline Render Gating

## Status

Accepted

## Date

2026-06-04

## Context

Real Atari BASIC displays the input cursor by writing an inverse-video space
(screen code `$80`) at the current editor cursor position and enabling ANTIC's
inverse-character display control. At the `READY` prompt the emulator reached
BASIC and memory contained the expected `$80` cursor byte, but the visible
framebuffer did not show the white blinking square.

The GTIA text renderer treated inverse characters as blank when `CHACTL` bit 1
was set. That behavior made an inverse space remain visually empty, so BASIC's
standard cursor mechanism was invisible.

While investigating the cursor, another hot path was visible: `Machine.step()`
called `_render_visible_scanlines()` after every CPU instruction, even when the
elapsed CPU cycles had not advanced ANTIC to a new scanline. Rendering is useful
only once per scanline, so those calls were redundant overhead.

## Decision

### 1. Render high-bit text characters as inverse video

For text modes, GTIA now reads the base glyph using the low seven bits of the
screen code and XORs the glyph pattern with `$FF` whenever the high bit is set.
This makes `$80` render as a solid inverse space when the base space glyph is
blank, matching the BASIC editor cursor representation.

The implementation keeps inverse handling in the glyph-pattern phase, so the
existing scanline cache continues to key on the actual post-inversion pattern
bytes. No separate inverse flag is needed in the cache key.

### 2. Gate scanline rendering on ANTIC scanline advancement

`Machine.step()` and the SIO-intercept path now call `_render_visible_scanlines()`
only when `ANTIC.tick()` reports a `"scanline"` event. This preserves the one
render pass needed for each completed visible scanline while avoiding repeated
no-op redraw attempts between scanline boundaries.

The WSYNC path also renders when the skipped cycles advance ANTIC through one or
more scanlines.

### 3. Keep touched tooling clean

A small ruff/type cleanup was made in `benchmarks/report.py` while validating the
change set: unused imports were removed, placeholder-free f-strings were changed
to normal strings, and local benchmark metadata types were clarified.

## Consequences

- The BASIC `READY` prompt cursor is visible: the editor's `$80` inverse-space
  cell renders as a solid bright cursor block.
- Existing text scanline caching remains valid because inverse characters are
  represented by their final glyph pattern bytes before cache lookup.
- Rendering work is reduced by avoiding per-instruction calls when ANTIC has not
  advanced a scanline.
- The emulator still prioritizes clarity: the render gate is based on the
  existing ANTIC event list rather than introducing another timing mechanism.
- Regression tests cover inverse text rendering and the inverse-space cursor
  case.
