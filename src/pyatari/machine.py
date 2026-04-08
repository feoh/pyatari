"""Initial top-level machine integration for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.antic import ANTIC
from pyatari.clock import MasterClock
from pyatari.constants import CYCLES_PER_FRAME, CYCLES_PER_SCANLINE
from pyatari.cpu import CPU, Opcode
from pyatari.display import DisplaySurface
from pyatari.gtia import GTIA
from pyatari.memory import MemoryBus
from pyatari.pia import PIA
from pyatari.pokey import POKEY


@dataclass(slots=True)
class Machine:
    """Own the major emulator subsystems and drive execution."""

    memory: MemoryBus = field(default_factory=MemoryBus)
    cpu: CPU = field(init=False)
    clock: MasterClock = field(default_factory=MasterClock)
    pia: PIA = field(init=False)
    antic: ANTIC = field(init=False)
    gtia: GTIA = field(init=False)
    pokey: POKEY = field(init=False)
    display: DisplaySurface = field(default_factory=DisplaySurface)

    def __post_init__(self) -> None:
        self.cpu = CPU(memory=self.memory)
        self.pia = PIA(memory=self.memory)
        self.pia.install()
        self.antic = ANTIC(memory=self.memory)
        self.antic.install()
        self.gtia = GTIA(memory=self.memory)
        self.gtia.install()
        self.pokey = POKEY(memory=self.memory)
        self.pokey.install()

    def reset(self) -> None:
        self.clock.reset()
        self.antic.reset()
        self.gtia.reset()
        self.pokey.reset()
        self.cpu.reset()

    def step(self) -> Opcode:
        if self.antic.consume_wsync():
            remaining = (-self.antic.cycles_into_scanline) % CYCLES_PER_SCANLINE
            if remaining:
                self.clock.tick_instruction(remaining)
                events = self.antic.tick(remaining)
                if self.pokey.tick(remaining):
                    self.cpu.irq()
                if "dli" in events or "vbi" in events:
                    self.cpu.nmi()

        before = self.cpu.cycles
        opcode = self.cpu.step()
        elapsed = self.cpu.cycles - before
        self.clock.tick_instruction(elapsed)
        events = self.antic.tick(elapsed)
        if self.pokey.tick(elapsed):
            self.cpu.irq()
        if "dli" in events or "vbi" in events:
            self.cpu.nmi()
        self._render_visible_scanlines()
        return opcode

    def run_steps(self, steps: int) -> list[Opcode]:
        if steps < 0:
            msg = "steps must be non-negative"
            raise ValueError(msg)
        return [self.step() for _ in range(steps)]

    def run_until(self, address: int, max_steps: int = 100_000) -> int:
        address &= 0xFFFF
        if self.cpu.pc == address:
            return 0

        for executed in range(1, max_steps + 1):
            self.step()
            if self.cpu.pc == address:
                return executed

        msg = f"CPU did not reach address {address:#06x} within {max_steps} steps"
        raise TimeoutError(msg)

    def run_frame(self) -> int:
        target_cycles = self.clock.total_cycles + CYCLES_PER_FRAME
        steps = 0
        while self.clock.total_cycles < target_cycles:
            self.step()
            steps += 1
        return steps

    def _render_visible_scanlines(self) -> None:
        row = self.antic.scanline - 1
        if self.antic.current_line is not None and 0 <= row < self.display.height:
            self.gtia.render_player(
                0,
                xpos=self.gtia.write_registers.get(0xD000, 0),
                graphics=self.gtia.write_registers.get(0xD00D, 0),
                size=self.gtia.write_registers.get(0xD008, 0),
                color=self.gtia.write_registers.get(0xD012, 0),
            )
            self.gtia.render_player(
                1,
                xpos=self.gtia.write_registers.get(0xD001, 0),
                graphics=self.gtia.write_registers.get(0xD00E, 0),
                size=self.gtia.write_registers.get(0xD009, 0),
                color=self.gtia.write_registers.get(0xD013, 0),
            )
            self.gtia.render_player(
                2,
                xpos=self.gtia.write_registers.get(0xD002, 0),
                graphics=self.gtia.write_registers.get(0xD00F, 0),
                size=self.gtia.write_registers.get(0xD00A, 0),
                color=self.gtia.write_registers.get(0xD014, 0),
            )
            self.gtia.render_player(
                3,
                xpos=self.gtia.write_registers.get(0xD003, 0),
                graphics=self.gtia.write_registers.get(0xD010, 0),
                size=self.gtia.write_registers.get(0xD00B, 0),
                color=self.gtia.write_registers.get(0xD015, 0),
            )
            self.gtia.render_missiles(
                xpos=[
                    self.gtia.write_registers.get(0xD004, 0),
                    self.gtia.write_registers.get(0xD005, 0),
                    self.gtia.write_registers.get(0xD006, 0),
                    self.gtia.write_registers.get(0xD007, 0),
                ],
                graphics=self.gtia.write_registers.get(0xD011, 0),
                size_mask=self.gtia.write_registers.get(0xD00C, 0),
                color=self.gtia.write_registers.get(0xD012, 0),
            )
            self.gtia.render_scanline(
                self.antic.current_line,
                row=row,
                antic_chbase=self.antic.chbase,
                antic_chactl=self.antic.chactl,
            )
