# 0011: Line-Relative Text Scanline Rendering

## Status

Accepted

## Date

2026-06-04

## Context

BASIC `GRAPHICS 2` (`GR.2`) uses ANTIC text mode 7: a 20-column, double-width,
double-height character mode with 16 scanlines per text row. Printing to the
screen device (`#6`) produced duplicate-looking text lines because GTIA chose the
glyph row from the absolute framebuffer row. That accidentally worked for some
8-scanline text modes, but it lost the relationship between the currently active
ANTIC display-list line and the scanline inside that line.

For double-height text modes, each glyph row should be displayed for two
consecutive scanlines within the same display-list line. Using the framebuffer row
instead made glyph-row selection depend on where the text line appeared on the
screen, not on ANTIC's current scanline within the character row.

## Decision

`Machine._render_visible_scanlines()` now computes the current scanline relative
to the active ANTIC display-list line and passes that value into GTIA.

GTIA text rendering uses this line-relative scanline to select the glyph row. For
ANTIC modes 5 and 7, which are 16-scanline double-height text modes, GTIA maps two
successive scanlines to each glyph row by dividing the line-relative glyph offset
by two.

Direct GTIA unit-test calls can omit the line-relative value; the renderer keeps a
backward-compatible fallback for those tests and simple callers.

## Consequences

- BASIC `GR.2` output no longer renders duplicate text rows caused by absolute
  framebuffer-row glyph selection.
- Text rendering better matches ANTIC's display-list model: glyph rows are based
  on position within the active mode line.
- The fix is isolated to text-mode glyph-row selection and does not change screen
  memory advancement.
- A regression test covers double-height ANTIC mode 7 line-relative glyph-row
  selection.
