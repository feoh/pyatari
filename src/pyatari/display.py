"""Minimal display helpers for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass

from pyatari.gtia import DISPLAY_HEIGHT, DISPLAY_WIDTH, GTIA


@dataclass(slots=True)
class DisplaySurface:
    """Tiny framebuffer wrapper for tests and future pygame integration."""

    width: int = DISPLAY_WIDTH
    height: int = DISPLAY_HEIGHT

    def frame_from_gtia(self, gtia: GTIA) -> list[list[int]]:
        return [row[:] for row in gtia.framebuffer]
