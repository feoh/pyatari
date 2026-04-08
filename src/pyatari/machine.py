"""Initial top-level machine integration for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.constants import IRQBits, JoystickBits

from pyatari.antic import ANTIC
from pyatari.clock import MasterClock
from pyatari.constants import CYCLES_PER_FRAME, CYCLES_PER_SCANLINE
from pyatari.cpu import CPU, Opcode
from pyatari.display import DisplaySurface
from pyatari.gtia import GTIA
from pyatari.memory import MemoryBus
from pyatari.pia import PIA
from pyatari.pokey import POKEY
from pyatari.sio import DiskDrive, SIOBus, XEXImage


KEYCODE_MAP = {
    "a": 0x3F,
    "b": 0x15,
    "c": 0x12,
    "d": 0x3A,
    "e": 0x2A,
    "f": 0x38,
    "g": 0x3D,
    "h": 0x39,
    "i": 0x0D,
    "j": 0x01,
    "k": 0x05,
    "l": 0x00,
    "m": 0x25,
    "n": 0x23,
    "o": 0x08,
    "p": 0x0A,
    "q": 0x2F,
    "r": 0x28,
    "s": 0x3E,
    "t": 0x2D,
    "u": 0x0B,
    "v": 0x10,
    "w": 0x2E,
    "x": 0x16,
    "y": 0x2B,
    "z": 0x17,
    "0": 0x32,
    "1": 0x1F,
    "2": 0x1E,
    "3": 0x1A,
    "4": 0x18,
    "5": 0x1D,
    "6": 0x1B,
    "7": 0x33,
    "8": 0x35,
    "9": 0x30,
    "space": 0x21,
    "return": 0x0C,
}


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
    sio: SIOBus = field(default_factory=SIOBus)
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

    def load_xex(self, xex: bytes | XEXImage) -> XEXImage:
        image = xex if isinstance(xex, XEXImage) else XEXImage.from_bytes(xex)
        image.load_into(self.memory)
        if image.run_address is not None:
            self.cpu.pc = image.run_address
        return image

    def attach_disk(self, device_id: int, drive: DiskDrive) -> None:
        self.sio.attach_disk(device_id, drive)

    def press_key(self, key: str) -> None:
        self.pokey.press_key(KEYCODE_MAP[key.lower()])

    def release_key(self) -> None:
        self.pokey.release_key()

    def set_console_switches(
        self, *, start: bool | None = None, select: bool | None = None, option: bool | None = None
    ) -> None:
        self.gtia.set_console_switch(start=start, select=select, option=option)

    def press_reset(self) -> None:
        self.cpu.nmi()

    def press_break(self) -> None:
        self.pokey.irqst &= ~int(IRQBits.BREAK_KEY) & 0xFF
        if self.pokey.irqen & int(IRQBits.BREAK_KEY):
            self.cpu.irq()

    def release_break(self) -> None:
        self.pokey.irqst |= int(IRQBits.BREAK_KEY)

    def set_joystick(self, *, up: bool = False, down: bool = False, left: bool = False, right: bool = False) -> None:
        state = 0x0F
        if up:
            state &= ~int(JoystickBits.STICK0_UP)
        if down:
            state &= ~int(JoystickBits.STICK0_DOWN)
        if left:
            state &= ~int(JoystickBits.STICK0_LEFT)
        if right:
            state &= ~int(JoystickBits.STICK0_RIGHT)
        self.pia.set_joystick_state(stick0=state)

    def set_trigger(self, pressed: bool) -> None:
        self.gtia.set_trigger(0, pressed)

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
                antic_hscrol=self.antic.hscrol,
                antic_vscrol=self.antic.vscrol,
            )
