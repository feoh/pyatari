"""Master timing helpers for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass

from pyatari.constants import CYCLES_PER_FRAME, CYCLES_PER_SCANLINE, SCANLINES_PER_FRAME, VBLANK_START_SCANLINE


@dataclass(slots=True)
class MasterClock:
    """Track emulator time in CPU cycles, scanlines, and frames."""

    total_cycles: int = 0
    frame: int = 0
    scanline: int = 0
    cycle_in_scanline: int = 0

    @property
    def in_vblank(self) -> bool:
        return self.scanline >= VBLANK_START_SCANLINE

    def tick(self, cycles: int) -> None:
        if cycles < 0:
            msg = "cycles must be non-negative"
            raise ValueError(msg)

        self.total_cycles += cycles
        total_scanline_cycles = self.cycle_in_scanline + cycles
        scanlines_advanced, self.cycle_in_scanline = divmod(total_scanline_cycles, CYCLES_PER_SCANLINE)

        if scanlines_advanced:
            absolute_scanline = self.scanline + scanlines_advanced
            frames_advanced, self.scanline = divmod(absolute_scanline, SCANLINES_PER_FRAME)
            self.frame += frames_advanced

    def tick_instruction(self, elapsed_cycles: int) -> None:
        self.tick(elapsed_cycles)

    def reset(self) -> None:
        self.total_cycles = 0
        self.frame = 0
        self.scanline = 0
        self.cycle_in_scanline = 0

    @property
    def cycle_in_frame(self) -> int:
        return (self.scanline * CYCLES_PER_SCANLINE) + self.cycle_in_scanline

    @property
    def total_frames_cycles(self) -> int:
        return self.frame * CYCLES_PER_FRAME + self.cycle_in_frame
