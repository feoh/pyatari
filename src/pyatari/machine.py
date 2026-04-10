"""Initial top-level machine integration for PyAtari."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pyatari.constants import (
    ANTICRegister,
    CYCLES_PER_FRAME,
    CYCLES_PER_SCANLINE,
    DMACTLBits,
    FRAMES_PER_SECOND,
    GTIAWriteRegister,
    IRQBits,
    JoystickBits,
    ShadowRegister,
    SCANLINES_PER_FRAME,
)

from pyatari.antic import ANTIC
from pyatari.audio import AudioOutput
from pyatari.clock import MasterClock
from pyatari.cpu import CPU, Opcode
from pyatari.display import DisplaySurface
from pyatari.gtia import GTIA
from pyatari.memory import MemoryBus
from pyatari.peripherals import CassetteDeck, PrinterDevice
from pyatari.pia import PIA
from pyatari.pokey import DEFAULT_AUDIO_SAMPLE_RATE, POKEY
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

DEMO_DISPLAY_LIST_ADDRESS = 0x2400
DEMO_SCREEN_ADDRESS = 0x3000
DEMO_CHARSET_ADDRESS = 0x4000
OS_DEFAULT_DISPLAY_LIST_ADDRESS = 0x9C20
OS_DEFAULT_SCREEN_ADDRESS = 0x9C40
OS_DEFAULT_RAMTOP_PAGE = 0xA0
DEMO_COLUMNS = 40
DEMO_ROWS = 24
DEMO_MODE_2_INSTRUCTION = 0x02
BOOT_BASIC = "basic"
BOOT_MEMO_PAD = "memo_pad"
SCREEN_CODE_SPACE = 0x00
DEMO_FONT: dict[str, tuple[int, ...]] = {
    " ": (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    "A": (0x18, 0x24, 0x42, 0x7E, 0x42, 0x42, 0x42, 0x00),
    "C": (0x3C, 0x42, 0x40, 0x40, 0x40, 0x42, 0x3C, 0x00),
    "D": (0x78, 0x44, 0x42, 0x42, 0x42, 0x44, 0x78, 0x00),
    "E": (0x7E, 0x40, 0x40, 0x7C, 0x40, 0x40, 0x7E, 0x00),
    "G": (0x3C, 0x42, 0x40, 0x4E, 0x42, 0x42, 0x3C, 0x00),
    "H": (0x42, 0x42, 0x42, 0x7E, 0x42, 0x42, 0x42, 0x00),
    "I": (0x3C, 0x08, 0x08, 0x08, 0x08, 0x08, 0x3C, 0x00),
    "L": (0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x7E, 0x00),
    "M": (0x42, 0x66, 0x5A, 0x42, 0x42, 0x42, 0x42, 0x00),
    "O": (0x3C, 0x42, 0x42, 0x42, 0x42, 0x42, 0x3C, 0x00),
    "P": (0x7C, 0x42, 0x42, 0x7C, 0x40, 0x40, 0x40, 0x00),
    "R": (0x7C, 0x42, 0x42, 0x7C, 0x48, 0x44, 0x42, 0x00),
    "T": (0x7F, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x00),
    "X": (0x42, 0x24, 0x18, 0x18, 0x18, 0x24, 0x42, 0x00),
    "Y": (0x42, 0x24, 0x18, 0x08, 0x08, 0x08, 0x08, 0x00),
    "8": (0x3C, 0x42, 0x42, 0x3C, 0x42, 0x42, 0x3C, 0x00),
    "0": (0x3C, 0x46, 0x4A, 0x52, 0x62, 0x42, 0x3C, 0x00),
}


@dataclass(slots=True)
class MachineStatus:
    pc: int
    scanline: int
    frame: int
    fps: int
    turbo: bool
    total_cycles: int


@dataclass(slots=True)
class BootProgramLine:
    number: int
    text: str


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
    audio: AudioOutput = field(default_factory=AudioOutput)
    cassette: CassetteDeck = field(default_factory=CassetteDeck)
    printer: PrinterDevice = field(default_factory=PrinterDevice)
    turbo: bool = False
    boot_mode: str | None = None
    boot_input_row: int = 0
    boot_input_col: int = 0
    boot_input_buffer: str = ""
    boot_output_row: int = 0
    boot_cursor_visible: bool = True
    boot_program: dict[int, BootProgramLine] = field(default_factory=dict)
    boot_running: bool = False
    boot_next_line: int | None = None

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
        self._initialize_os_shadows()
        self.boot_mode = None
        self.boot_input_row = 0
        self.boot_input_col = 0
        self.boot_input_buffer = ""
        self.boot_output_row = 0
        self.boot_cursor_visible = True
        self.boot_program.clear()
        self.boot_running = False
        self.boot_next_line = None

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
        if self.antic.scanline == 248:
            self._sync_os_shadows_to_hardware()
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

    def run_frame(self, *, queue_audio: bool = True, audio_samples: int | None = None) -> int:
        if self.boot_mode is not None:
            return self._run_boot_frame(queue_audio=queue_audio, audio_samples=audio_samples)
        target_cycles = self.clock.total_cycles + CYCLES_PER_FRAME
        steps = 0
        while self.clock.total_cycles < target_cycles:
            self.step()
            steps += 1
        if queue_audio:
            sample_count = audio_samples if audio_samples is not None else self._samples_per_frame()
            self.audio.queue_from_pokey(self.pokey, sample_count)
        return steps

    def load_xex(self, xex: bytes | XEXImage) -> XEXImage:
        self._deactivate_boot_mode()
        image = xex if isinstance(xex, XEXImage) else XEXImage.from_bytes(xex)
        image.load_into(self.memory)
        if image.run_address is not None:
            self.cpu.pc = image.run_address
        return image

    def attach_disk(self, device_id: int, drive: DiskDrive) -> None:
        self.sio.attach_disk(device_id, drive)

    def set_turbo(self, enabled: bool) -> None:
        self.turbo = enabled

    def status(self) -> MachineStatus:
        return MachineStatus(
            pc=self.cpu.pc,
            scanline=self.clock.scanline,
            frame=self.clock.frame,
            fps=FRAMES_PER_SECOND,
            turbo=self.turbo,
            total_cycles=self.clock.total_cycles,
        )

    def boot_xex(self, xex: bytes | XEXImage, *, max_steps: int = 100_000) -> int:
        image = self.load_xex(xex)
        if image.run_address is None:
            msg = "XEX image has no run address"
            raise ValueError(msg)
        return self.run_until(image.run_address, max_steps=max_steps)

    def run_program(self, program: bytes, *, start: int = 0x2000, steps: int = 1) -> int:
        self._deactivate_boot_mode()
        self.memory.load_ram(start, program)
        self.memory.write_word(0xFFFC, start)
        self.reset()
        self.cpu.pc = start
        self.run_steps(steps)
        return self.cpu.pc

    def load_demo_screen(self) -> None:
        """Install a small ROM-free text demo so the frontend has visible output."""
        self._deactivate_boot_mode()
        self._install_text_display(chbase_high=DEMO_CHARSET_ADDRESS >> 8)
        screen = self._blank_screen()
        self._write_demo_text(screen, row=8, text="PYATARI 800XL")
        self._write_demo_text(screen, row=11, text="GRAPHICS DEMO")
        self._write_demo_text(screen, row=14, text="LOAD A ROM OR XEX")
        self._write_screen(screen)
        for char, glyph in DEMO_FONT.items():
            glyph_address = DEMO_CHARSET_ADDRESS + (self._screen_code_for_char(char) * 8)
            self.memory.load_ram(glyph_address, bytes(glyph))
        self._set_text_colors(bg=0x00, pf0=0x24, pf1=0x0E, pf2=0x58, pf3=0xC6)

    def load_basic_screen(self) -> None:
        self._activate_boot_mode(BOOT_BASIC)
        self._render_basic_home()

    def load_memo_pad_screen(self) -> None:
        self._activate_boot_mode(BOOT_MEMO_PAD)
        screen = self._blank_screen()
        self._write_demo_text(screen, row=0, text="MEMO PAD")
        self._write_demo_text(screen, row=2, text="TYPE NOTES HERE")
        self._write_screen(screen)
        self._set_boot_input(row=4, col=0)
        self.boot_output_row = 5

    def has_visible_output(self) -> bool:
        """Return True when the current framebuffer contains any non-background pixels."""
        background = self.gtia.color_to_rgb(
            self.gtia.write_registers[int(GTIAWriteRegister.COLBK)]
        )
        return any(
            pixel != background
            for row in self.gtia.framebuffer
            for pixel in row
        )

    def press_key(self, key: str) -> None:
        normalized = key.lower()
        keycode = KEYCODE_MAP.get(normalized)
        if keycode is not None:
            self.pokey.press_key(keycode)
        if self.boot_mode is not None:
            self._boot_handle_key(normalized)

    def release_key(self) -> None:
        self.pokey.release_key()

    def set_console_switches(
        self, *, start: bool | None = None, select: bool | None = None, option: bool | None = None
    ) -> None:
        self.gtia.set_console_switch(start=start, select=select, option=option)

    def press_reset(self) -> None:
        if self.boot_mode == BOOT_BASIC:
            self._render_basic_home()
            return
        if self.boot_mode == BOOT_MEMO_PAD:
            self.load_memo_pad_screen()
            return
        self.cpu.nmi()

    def press_break(self) -> None:
        self.pokey.irqst &= ~int(IRQBits.BREAK_KEY) & 0xFF
        if self.pokey.irqen & int(IRQBits.BREAK_KEY):
            self.cpu.irq()

    def release_break(self) -> None:
        self.pokey.irqst |= int(IRQBits.BREAK_KEY)

    def set_joystick(
        self,
        *,
        up: bool = False,
        down: bool = False,
        left: bool = False,
        right: bool = False,
        port: int = 0,
    ) -> None:
        state = 0x0F
        if up:
            state &= ~int(JoystickBits.STICK0_UP)
        if down:
            state &= ~int(JoystickBits.STICK0_DOWN)
        if left:
            state &= ~int(JoystickBits.STICK0_LEFT)
        if right:
            state &= ~int(JoystickBits.STICK0_RIGHT)
        if port == 0:
            self.pia.set_joystick_state(stick0=state)
        elif port == 1:
            self.pia.set_joystick_state(stick1=state)
        else:
            msg = "joystick port must be 0 or 1"
            raise ValueError(msg)

    def set_trigger(self, pressed: bool, *, port: int = 0) -> None:
        self.gtia.set_trigger(port, pressed)

    def set_paddle(self, paddle: int, value: int) -> None:
        self.pokey.set_paddle(paddle, value)

    def load_cassette(self, data: bytes) -> None:
        self.cassette.load_tape(data)

    def read_cassette_block(self, size: int) -> bytes:
        return self.cassette.read_block(size)

    def printer_write(self, text: str) -> None:
        self.printer.write(text)

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

    def _samples_per_frame(self) -> int:
        return max(1, DEFAULT_AUDIO_SAMPLE_RATE // FRAMES_PER_SECOND)

    def _initialize_os_shadows(self) -> None:
        """Seed common Atari OS shadow defaults for real-ROM boot."""
        if self.memory.os_rom is None:
            return
        self._install_default_os_display()
        self.memory.write_word(int(ShadowRegister.SAVMSC), OS_DEFAULT_SCREEN_ADDRESS)
        self.memory.write_word(int(ShadowRegister.DLPTR), OS_DEFAULT_DISPLAY_LIST_ADDRESS)
        self.memory.write_byte(int(ShadowRegister.RAMTOP), OS_DEFAULT_RAMTOP_PAGE)
        self.memory.write_byte(int(ShadowRegister.SDMCTL), int(DMACTLBits.DL_DMA | DMACTLBits.NORMAL_PLAYFIELD))
        self.memory.write_word(int(ShadowRegister.SDLSTL), OS_DEFAULT_DISPLAY_LIST_ADDRESS)
        self.memory.write_byte(int(ShadowRegister.CHART), 0x02)
        self.memory.write_byte(int(ShadowRegister.CHBAS), 0xE0)
        self.memory.write_byte(int(ShadowRegister.GPRIOR), 0x00)
        self.memory.write_byte(int(ShadowRegister.PCOLR0), 0x00)
        self.memory.write_byte(int(ShadowRegister.PCOLR1), 0x00)
        self.memory.write_byte(int(ShadowRegister.PCOLR2), 0x00)
        self.memory.write_byte(int(ShadowRegister.PCOLR3), 0x00)
        self.memory.write_byte(int(ShadowRegister.COLOR0), 0x00)
        self.memory.write_byte(int(ShadowRegister.COLOR1), 0x00)
        self.memory.write_byte(int(ShadowRegister.COLOR2), 0x00)
        self.memory.write_byte(int(ShadowRegister.COLOR3), 0x00)
        self.memory.write_byte(int(ShadowRegister.COLOR4), 0x00)
        self.memory.write_byte(int(ShadowRegister.LMARGIN), 0x02)
        self.memory.write_byte(int(ShadowRegister.RMARGIN), 0x27)
        self.memory.write_byte(int(ShadowRegister.ROWCRS), 0x00)
        self.memory.write_word(int(ShadowRegister.COLCRS), 0x0002)

    def _install_default_os_display(self) -> None:
        display_list = bytearray([0x70, DEMO_MODE_2_INSTRUCTION | 0x40])
        display_list.extend(OS_DEFAULT_SCREEN_ADDRESS.to_bytes(2, "little"))
        display_list.extend([DEMO_MODE_2_INSTRUCTION] * (DEMO_ROWS - 1))
        display_list.extend([0x41])
        display_list.extend(OS_DEFAULT_DISPLAY_LIST_ADDRESS.to_bytes(2, "little"))
        self.memory.load_ram(OS_DEFAULT_DISPLAY_LIST_ADDRESS, bytes(display_list))
        self.memory.load_ram(
            OS_DEFAULT_SCREEN_ADDRESS,
            bytes([SCREEN_CODE_SPACE] * (DEMO_COLUMNS * DEMO_ROWS)),
        )

    def _sync_os_shadows_to_hardware(self) -> None:
        """Apply OS-maintained display shadows to the live ANTIC/GTIA state."""
        if self.memory.os_rom is None:
            return
        self.memory.write_byte(int(ANTICRegister.DMACTL), self.memory.read_byte(int(ShadowRegister.SDMCTL)))
        self.memory.write_byte(int(ANTICRegister.DLISTL), self.memory.read_byte(int(ShadowRegister.SDLSTL)))
        self.memory.write_byte(int(ANTICRegister.DLISTH), self.memory.read_byte(int(ShadowRegister.SDLSTH)))
        self.memory.write_byte(int(ANTICRegister.CHACTL), self.memory.read_byte(int(ShadowRegister.CHART)))
        self.memory.write_byte(int(ANTICRegister.CHBASE), self.memory.read_byte(int(ShadowRegister.CHBAS)))
        self.memory.write_byte(int(GTIAWriteRegister.PRIOR), self.memory.read_byte(int(ShadowRegister.GPRIOR)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPM0), self.memory.read_byte(int(ShadowRegister.PCOLR0)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPM1), self.memory.read_byte(int(ShadowRegister.PCOLR1)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPM2), self.memory.read_byte(int(ShadowRegister.PCOLR2)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPM3), self.memory.read_byte(int(ShadowRegister.PCOLR3)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPF0), self.memory.read_byte(int(ShadowRegister.COLOR0)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPF1), self.memory.read_byte(int(ShadowRegister.COLOR1)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPF2), self.memory.read_byte(int(ShadowRegister.COLOR2)))
        self.memory.write_byte(int(GTIAWriteRegister.COLPF3), self.memory.read_byte(int(ShadowRegister.COLOR3)))
        self.memory.write_byte(int(GTIAWriteRegister.COLBK), self.memory.read_byte(int(ShadowRegister.COLOR4)))

    def _run_boot_frame(self, *, queue_audio: bool, audio_samples: int | None) -> int:
        del audio_samples
        self.clock.tick(CYCLES_PER_FRAME)
        self.gtia.clear_framebuffer()
        self._update_boot_cursor()
        if self.boot_mode == BOOT_BASIC and self.boot_running:
            self._basic_step_program()
        self.antic.scanline = 0
        self.antic.cycles_into_scanline = 0
        self.antic.display_list_pc = self.antic.dlist
        self.antic.screen_memory_address = 0
        self.antic.current_line = None
        self.antic.current_line_remaining = 0
        for _ in range(SCANLINES_PER_FRAME):
            line = self.antic.step_scanline(trigger_nmi=False)
            row = self.antic.scanline - 1
            if line is not None and 0 <= row < self.display.height:
                self.gtia.render_scanline(
                    line,
                    row=row,
                    antic_chbase=self.antic.chbase,
                    antic_chactl=self.antic.chactl,
                    antic_hscrol=self.antic.hscrol,
                    antic_vscrol=self.antic.vscrol,
                )
        if queue_audio:
            self.audio.queue_from_pokey(self.pokey, self._samples_per_frame())
        return SCANLINES_PER_FRAME

    def _activate_boot_mode(self, mode: str) -> None:
        self._deactivate_boot_mode()
        self.boot_mode = mode
        self.boot_program = {}
        self.boot_running = False
        self.boot_next_line = None
        self._install_text_display(chbase_high=0xE0 if self.memory.os_rom is not None else DEMO_CHARSET_ADDRESS >> 8)
        if self.memory.os_rom is None:
            for char, glyph in DEMO_FONT.items():
                glyph_address = DEMO_CHARSET_ADDRESS + (self._screen_code_for_char(char) * 8)
                self.memory.load_ram(glyph_address, bytes(glyph))
        self._set_text_colors(bg=0x00, pf0=0x24, pf1=0x0E, pf2=0x58, pf3=0xC6)

    def _deactivate_boot_mode(self) -> None:
        self.boot_mode = None
        self.boot_input_row = 0
        self.boot_input_col = 0
        self.boot_input_buffer = ""
        self.boot_output_row = 0
        self.boot_cursor_visible = True
        self.boot_running = False
        self.boot_next_line = None
        self.boot_program.clear()

    def _install_text_display(self, *, chbase_high: int) -> None:
        display_list = bytearray([0x70, DEMO_MODE_2_INSTRUCTION | 0x40])
        display_list.extend(DEMO_SCREEN_ADDRESS.to_bytes(2, "little"))
        display_list.extend([DEMO_MODE_2_INSTRUCTION] * (DEMO_ROWS - 1))
        display_list.extend([0x41])
        display_list.extend(DEMO_DISPLAY_LIST_ADDRESS.to_bytes(2, "little"))
        self.memory.load_ram(DEMO_DISPLAY_LIST_ADDRESS, bytes(display_list))
        self.memory.write_byte(
            int(ANTICRegister.DMACTL),
            int(DMACTLBits.DL_DMA | DMACTLBits.NORMAL_PLAYFIELD),
        )
        self.memory.write_word(int(ANTICRegister.DLISTL), DEMO_DISPLAY_LIST_ADDRESS)
        self.memory.write_byte(int(ANTICRegister.CHBASE), chbase_high)

    def _set_text_colors(self, *, bg: int, pf0: int, pf1: int, pf2: int, pf3: int) -> None:
        self.memory.write_byte(int(GTIAWriteRegister.COLBK), bg)
        self.memory.write_byte(int(GTIAWriteRegister.COLPF0), pf0)
        self.memory.write_byte(int(GTIAWriteRegister.COLPF1), pf1)
        self.memory.write_byte(int(GTIAWriteRegister.COLPF2), pf2)
        self.memory.write_byte(int(GTIAWriteRegister.COLPF3), pf3)

    def _blank_screen(self) -> bytearray:
        return bytearray([SCREEN_CODE_SPACE] * (DEMO_COLUMNS * DEMO_ROWS))

    def _write_screen(self, screen: bytearray) -> None:
        self.memory.load_ram(DEMO_SCREEN_ADDRESS, bytes(screen))

    def _screen_as_bytes(self) -> bytearray:
        return bytearray(
            self.memory.read_byte(DEMO_SCREEN_ADDRESS + offset)
            for offset in range(DEMO_COLUMNS * DEMO_ROWS)
        )

    def _render_basic_home(self) -> None:
        screen = self._blank_screen()
        self._write_demo_text(screen, row=0, text="ATARI BASIC")
        self._write_demo_text(screen, row=2, text="READY")
        self._write_screen(screen)
        self.boot_program.clear()
        self.boot_running = False
        self.boot_next_line = None
        self._set_boot_input(row=4, col=0)
        self.boot_output_row = 5

    def _set_boot_input(self, *, row: int, col: int) -> None:
        self.boot_input_row = row
        self.boot_input_col = col
        self.boot_input_buffer = ""
        self.boot_cursor_visible = True
        self._update_boot_cursor()

    def _boot_handle_key(self, key: str) -> None:
        if key == "return":
            self._boot_submit_line()
            return
        if key == "space":
            char = " "
        elif key == "backspace":
            self._boot_backspace()
            return
        elif len(key) == 1:
            char = key.upper()
        else:
            return
        if self.boot_input_col >= DEMO_COLUMNS:
            return
        self._write_boot_char(char)

    def _write_boot_char(self, char: str) -> None:
        screen = self._screen_as_bytes()
        self._clear_cursor(screen)
        index = (self.boot_input_row * DEMO_COLUMNS) + self.boot_input_col
        screen[index] = self._screen_code_for_char(char)
        self.boot_input_buffer += char
        self.boot_input_col += 1
        self._write_screen(screen)
        self._update_boot_cursor()

    def _boot_backspace(self) -> None:
        if not self.boot_input_buffer or self.boot_input_col <= 0:
            return
        screen = self._screen_as_bytes()
        self._clear_cursor(screen)
        self.boot_input_col -= 1
        self.boot_input_buffer = self.boot_input_buffer[:-1]
        index = (self.boot_input_row * DEMO_COLUMNS) + self.boot_input_col
        screen[index] = SCREEN_CODE_SPACE
        self._write_screen(screen)
        self._update_boot_cursor()

    def _boot_submit_line(self) -> None:
        line = self.boot_input_buffer.rstrip()
        if self.boot_mode == BOOT_BASIC:
            self._basic_submit_line(line)
        elif self.boot_mode == BOOT_MEMO_PAD:
            self._memo_submit_line()

    def _memo_submit_line(self) -> None:
        next_row = min(DEMO_ROWS - 1, self.boot_input_row + 1)
        if next_row == DEMO_ROWS - 1 and self.boot_input_row == DEMO_ROWS - 1:
            self._scroll_boot_area(start_row=4)
            next_row = DEMO_ROWS - 1
        self._set_boot_input(row=next_row, col=0)

    def _basic_submit_line(self, line: str) -> None:
        command = line.strip().upper()
        self.boot_output_row = max(self.boot_output_row, self.boot_input_row + 1)
        if command:
            self._basic_execute_input(command)
        if not self.boot_running:
            self._basic_write_output("READY")
            self._set_boot_input(row=min(self.boot_output_row, DEMO_ROWS - 1), col=0)

    def _basic_execute_input(self, command: str) -> None:
        line_match = re.fullmatch(r"(\d+)\s+(.+)", command)
        if line_match:
            line_number = int(line_match.group(1))
            self.boot_program[line_number] = BootProgramLine(
                number=line_number,
                text=line_match.group(2),
            )
            return
        if command == "RUN":
            self._basic_start_program()
            return
        if command == "LIST":
            self._basic_list_program()
            return
        if not self._basic_execute_statement(command):
            self._basic_write_output("?SYNTAX ERROR")

    def _basic_start_program(self) -> None:
        if not self.boot_program:
            self._basic_write_output("READY")
            return
        self.boot_running = True
        self.boot_next_line = min(self.boot_program)

    def _basic_list_program(self) -> None:
        if not self.boot_program:
            self._basic_write_output("READY")
            return
        for line_number in sorted(self.boot_program):
            program_line = self.boot_program[line_number]
            self._basic_write_output(f"{program_line.number} {program_line.text}")

    def _basic_step_program(self) -> None:
        if not self.boot_running or self.boot_next_line is None:
            return
        program_line = self.boot_program.get(self.boot_next_line)
        if program_line is None:
            self.boot_running = False
            self.boot_next_line = None
            self._basic_write_output("READY")
            self._set_boot_input(row=min(self.boot_output_row, DEMO_ROWS - 1), col=0)
            return
        next_line = self._basic_execute_program_line(program_line.text)
        if next_line is None:
            ordered = sorted(number for number in self.boot_program if number > program_line.number)
            self.boot_next_line = ordered[0] if ordered else None
            if self.boot_next_line is None:
                self.boot_running = False
                self._basic_write_output("READY")
                self._set_boot_input(row=min(self.boot_output_row, DEMO_ROWS - 1), col=0)
        else:
            self.boot_next_line = next_line

    def _basic_execute_program_line(self, statement: str) -> int | None:
        print_match = re.fullmatch(
            r'PRINT\s*(?:\(\s*)?"([^"]*)"(?:\s*\))?(?:\s*:\s*GOTO\s+(\d+))?',
            statement,
        )
        if print_match is None:
            self.boot_running = False
            self._basic_write_output("?SYNTAX ERROR")
            return None
        self._basic_write_output(print_match.group(1))
        goto_target = print_match.group(2)
        return int(goto_target) if goto_target is not None else None

    def _basic_execute_statement(self, command: str) -> bool:
        print_match = re.fullmatch(r'PRINT\s*(?:\(\s*)?"([^"]*)"(?:\s*\))?', command)
        if print_match is not None:
            self._basic_write_output(print_match.group(1))
            return True
        return False

    def _write_status_line(self, row: int, text: str) -> None:
        row = min(max(row, 0), DEMO_ROWS - 1)
        screen = self._screen_as_bytes()
        start = row * DEMO_COLUMNS
        screen[start:start + DEMO_COLUMNS] = bytes([SCREEN_CODE_SPACE] * DEMO_COLUMNS)
        encoded = bytes(self._screen_code_for_char(char) for char in text[:DEMO_COLUMNS])
        screen[start:start + len(encoded)] = encoded
        self._write_screen(screen)

    def _basic_write_output(self, text: str) -> None:
        row = self.boot_output_row
        if row >= DEMO_ROWS:
            self._scroll_boot_area(start_row=2)
            row = DEMO_ROWS - 1
            self.boot_output_row = row
        self._write_status_line(row, text)
        self.boot_output_row = min(row + 1, DEMO_ROWS)

    def _scroll_boot_area(self, *, start_row: int) -> None:
        screen = self._screen_as_bytes()
        for row in range(start_row, DEMO_ROWS - 1):
            dest = row * DEMO_COLUMNS
            src = (row + 1) * DEMO_COLUMNS
            screen[dest:dest + DEMO_COLUMNS] = screen[src:src + DEMO_COLUMNS]
        last_row = (DEMO_ROWS - 1) * DEMO_COLUMNS
        screen[last_row:last_row + DEMO_COLUMNS] = bytes([SCREEN_CODE_SPACE] * DEMO_COLUMNS)
        self._write_screen(screen)

    def _update_boot_cursor(self) -> None:
        if self.boot_mode is None:
            return
        screen = self._screen_as_bytes()
        self._clear_cursor(screen)
        if self.boot_cursor_visible and self.boot_input_col < DEMO_COLUMNS:
            index = (self.boot_input_row * DEMO_COLUMNS) + self.boot_input_col
            screen[index] = SCREEN_CODE_SPACE | 0x80
        self._write_screen(screen)
        self.boot_cursor_visible = not self.boot_cursor_visible

    def _clear_cursor(self, screen: bytearray) -> None:
        if self.boot_input_col >= DEMO_COLUMNS:
            return
        index = (self.boot_input_row * DEMO_COLUMNS) + self.boot_input_col
        if screen[index] & 0x80:
            screen[index] = SCREEN_CODE_SPACE

    def _write_demo_text(self, screen: bytearray, *, row: int, text: str) -> None:
        text = text[:DEMO_COLUMNS]
        start = row * DEMO_COLUMNS + max(0, (DEMO_COLUMNS - len(text)) // 2)
        screen[start:start + len(text)] = bytes(self._screen_code_for_char(char) for char in text)

    def _screen_code_for_char(self, char: str) -> int:
        if len(char) != 1:
            msg = "screen code conversion expects a single character"
            raise ValueError(msg)
        if " " <= char <= "_":
            return ord(char) - 32
        return SCREEN_CODE_SPACE


def main() -> None:
    """Entry point for the ``pyatari`` console script."""
    import argparse
    from pathlib import Path

    from pyatari.rom_loader import find_self_test_rom, load_basic_rom, load_self_test_rom, load_xl_rom_bundle

    parser = argparse.ArgumentParser(description="PyAtari — Atari 800 emulator")
    parser.add_argument("xex", nargs="?", help="XEX executable to load")
    parser.add_argument(
        "--frames", type=int, default=None,
        help="run N frames headless (omit for interactive pygame window)",
    )
    parser.add_argument(
        "--scale", type=int, default=2,
        help="integer display scale factor (default: 2)",
    )
    parser.add_argument(
        "--rom-dir", type=Path, default=None,
        help="directory containing ROM files (default: roms/ next to package)",
    )
    parser.add_argument(
        "--real-rom-boot",
        action="store_true",
        help="bypass the synthetic READY/MEMO PAD shell and run the actual ROM boot path",
    )
    args = parser.parse_args()

    # Locate ROM directory: explicit flag, or roms/ beside the source tree
    rom_dir: Path = args.rom_dir or Path(__file__).resolve().parent.parent.parent / "roms"

    machine = Machine()

    # Load ROMs if available
    os_rom_path = rom_dir / "atarixl.rom"
    basic_rom_path = rom_dir / "ataribas.rom"
    self_test_rom_path = find_self_test_rom(rom_dir)
    if os_rom_path.exists():
        os_rom, bundled_self_test_rom = load_xl_rom_bundle(os_rom_path)
        machine.memory.load_os_rom(os_rom.data)
        print(f"Loaded OS ROM: {os_rom_path}")
        if bundled_self_test_rom is not None:
            machine.memory.load_self_test_rom(bundled_self_test_rom.data)
            print(f"Loaded bundled self-test ROM from: {os_rom_path}")
    else:
        print(f"Warning: OS ROM not found at {os_rom_path}")
    if basic_rom_path.exists():
        basic_rom = load_basic_rom(basic_rom_path)
        machine.memory.load_basic_rom(basic_rom.data)
        print(f"Loaded BASIC ROM: {basic_rom_path}")
    if self_test_rom_path is not None:
        self_test_rom = load_self_test_rom(self_test_rom_path)
        machine.memory.load_self_test_rom(self_test_rom.data)
        print(f"Loaded self-test ROM: {self_test_rom_path}")
    elif (
        args.real_rom_boot
        and args.xex is None
        and os_rom_path.exists()
        and machine.memory.self_test_rom is None
    ):
        print(
            "Warning: self-test ROM not found; real cold boot may divert into the "
            "self-test checksum path instead of reaching BASIC."
        )

    machine.reset()

    if args.xex:
        from pathlib import Path

        xex_path = Path(args.xex)
        xex_data = xex_path.read_bytes()
        image = machine.load_xex(xex_data)
        run_addr = (
            f"${image.run_address:04X}" if image.run_address is not None else "none"
        )
        print(
            f"Loaded {xex_path.name}: "
            f"{len(image.segments)} segment(s), run address {run_addr}"
        )

    if args.xex is None and not args.real_rom_boot:
        if os_rom_path.exists() and basic_rom_path.exists():
            machine.load_basic_screen()
            print("Loaded BASIC READY boot screen")
        elif os_rom_path.exists():
            machine.load_memo_pad_screen()
            print("Loaded MEMO PAD boot screen")
        else:
            machine.load_demo_screen()
            print("Loaded built-in graphics demo (no ROMs or XEX supplied)")
    elif args.real_rom_boot and args.xex is None:
        print("Running real ROM boot path (synthetic shell disabled)")

    if args.frames is not None:
        for _ in range(args.frames):
            machine.run_frame(queue_audio=False)

        st = machine.status()
        print(
            f"PyAtari: {st.frame} frame(s) executed, "
            f"PC=${st.pc:04X}, {st.total_cycles} cycles"
        )
    else:
        from pyatari.frontend import run

        run(machine, scale=args.scale)
