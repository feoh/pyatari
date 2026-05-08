"""Initial top-level machine integration for PyAtari."""

from __future__ import annotations

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
    SIO_COMMAND_FRAME_SIZE,
    SIO_ERROR_NO_DEVICE,
    SIOCommand,
    SIOResponse,
    SIO_VECTOR,
    SIOWorkspace,
)

from pyatari.antic import ANTIC
from pyatari.audio import AudioOutput
from pyatari.clock import MasterClock
from pyatari.cpu import CPU, Opcode
from pyatari.display import DisplaySurface
from pyatari.gtia import GTIA
from pyatari.memory import MemoryBus
from pyatari.opcodes import OPCODES
from pyatari.peripherals import CassetteDeck, PrinterDevice
from pyatari.pia import PIA
from pyatari.pokey import DEFAULT_AUDIO_SAMPLE_RATE, POKEY
from pyatari.sio import DiskDrive, SIOBus, XEXImage


KEYCODE_MAP: dict[str, int] = {
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
    ";": 0x02,
    "+": 0x06,
    "*": 0x07,
    "-": 0x0E,
    "=": 0x0F,
    ",": 0x20,
    ".": 0x22,
    "/": 0x26,
    "'": 0x33,
    "<": 0x36,
    ">": 0x37,
}
SHIFTED_KEYCODE_MAP: dict[str, int] = {
    "!": 0x1F,
    '"': 0x1E,
    "#": 0x1A,
    "$": 0x18,
    "%": 0x1D,
    "&": 0x1B,
    "(": 0x30,
    ")": 0x32,
    ":": 0x02,
    "\\": 0x06,
    "^": 0x07,
    "_": 0x0E,
    "|": 0x0F,
    "[": 0x20,
    "]": 0x22,
    "?": 0x26,
    "@": 0x35,
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
SCREEN_CODE_SPACE = 0x00
OS_RESET_CHECKSUM_GATE = 0xC3AB
OS_COLDSTART_STATUS = 0x0001
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
class ROMBootState:
    pc: int
    frame: int
    scanline: int
    portb: int
    coldstart_status: int
    dmactl: int
    dlist: int
    chbase: int
    sdmctl: int
    sdlstl: int
    chbas_shadow: int
    savmsc: int
    visible_output: bool


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
    sio_command_frame: bytearray = field(default_factory=bytearray)
    sio_output_index: int = 0

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
        self.pia.reset()
        self.antic.reset()
        self.gtia.reset()
        self.pokey.reset()
        self.cpu.reset()
        self._initialize_os_shadows()
        self._sync_os_shadows_to_hardware()
        self.sio_command_frame.clear()
        self.sio_output_index = 0

    def continue_without_self_test(self, *, max_steps: int = 800_000) -> bool:
        """Advance real ROM boot to the post-checksum branch when self-test ROM is absent.

        XL cold boot verifies the self-test-mapped ROM region before continuing into
        the normal BASIC/editor startup path. Without a self-test ROM image, that
        check fails and boot diverts into the self-test branch. This helper keeps the
        cold-start trace explicit, but lets us continue exercising real OS/BASIC code
        past the checksum gate until a real self-test ROM is available.
        """
        if self.memory.os_rom is None or self.memory.self_test_rom is not None:
            return False

        self.run_until(OS_RESET_CHECKSUM_GATE, max_steps=max_steps)
        self.memory.write_byte(OS_COLDSTART_STATUS, 0x01)
        return True

    def step(self) -> Opcode:
        intercepted_opcode = self._intercept_os_siov()
        if intercepted_opcode is not None:
            return intercepted_opcode

        if self.antic.consume_wsync():
            remaining = (-self.antic.cycles_into_scanline) % CYCLES_PER_SCANLINE
            if remaining:
                self.clock.tick(remaining)
                events = self.antic.tick(remaining)
                if self.pokey.tick(remaining):
                    self.cpu.irq()
                if self.antic.consume_nmi() or "dli" in events or "vbi" in events:
                    self.cpu.nmi()

        before = self.cpu.cycles
        opcode = self.cpu.step()
        elapsed = self.cpu.cycles - before
        self.clock.tick(elapsed)
        events = self.antic.tick(elapsed)
        if self.pokey.tick(elapsed):
            self.cpu.irq()
        self._service_serial_bus()
        if self.antic.scanline == 248:
            self._sync_os_shadows_to_hardware()
        if self.antic.consume_nmi() or "dli" in events or "vbi" in events:
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

    def rom_boot_state(self) -> ROMBootState:
        return ROMBootState(
            pc=self.cpu.pc,
            frame=self.clock.frame,
            scanline=self.clock.scanline,
            portb=self.memory.portb,
            coldstart_status=self.memory.read_byte(OS_COLDSTART_STATUS),
            dmactl=self.antic.dmactl,
            dlist=self.antic.dlist,
            chbase=self.antic.chbase,
            sdmctl=self.memory.read_byte(int(ShadowRegister.SDMCTL)),
            sdlstl=self.memory.read_word(int(ShadowRegister.SDLSTL)),
            chbas_shadow=self.memory.read_byte(int(ShadowRegister.CHBAS)),
            savmsc=self.memory.read_word(int(ShadowRegister.SAVMSC)),
            visible_output=self.has_visible_output(),
        )

    def boot_xex(self, xex: bytes | XEXImage, *, max_steps: int = 100_000) -> int:
        image = self.load_xex(xex)
        if image.run_address is None:
            msg = "XEX image has no run address"
            raise ValueError(msg)
        return self.run_until(image.run_address, max_steps=max_steps)

    def run_program(self, program: bytes, *, start: int = 0x2000, steps: int = 1) -> int:
        self.memory.load_ram(start, program)
        self.memory.write_word(0xFFFC, start)
        self.reset()
        self.cpu.pc = start
        self.run_steps(steps)
        return self.cpu.pc

    def load_demo_screen(self) -> None:
        """Install a small ROM-free text demo so the frontend has visible output."""
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
        shift = False
        if keycode is None:
            keycode = SHIFTED_KEYCODE_MAP.get(key)
            shift = keycode is not None
        if keycode is not None and self.pokey.press_key(keycode, shift=shift):
            self.cpu.irq()

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

    def _service_serial_bus(self) -> None:
        while self.sio_output_index < len(self.pokey.serial_output_bytes):
            self.sio_command_frame.append(self.pokey.serial_output_bytes[self.sio_output_index])
            self.sio_output_index += 1
            if len(self.sio_command_frame) == SIO_COMMAND_FRAME_SIZE:
                self._handle_sio_command_frame(bytes(self.sio_command_frame))
                self.sio_command_frame.clear()

    def _handle_sio_command_frame(self, frame: bytes) -> None:
        device_id, command, aux1, aux2, _checksum = frame

        try:
            if command == int(SIOCommand.STATUS):
                response = self.sio.send_command(device_id, command)
            elif command == int(SIOCommand.READ_SECTOR):
                sector = aux1 | (aux2 << 8)
                response = self.sio.send_command(device_id, command, sector=sector)
            else:
                return
        except KeyError:
            # Per Altirra's SIO protocol documentation, a device not addressed on
            # the bus simply ignores the command; the host must timeout and retry.
            return

        self.memory.write_byte(int(SIOWorkspace.STATUS), 0x00)
        framed_response = self._build_sio_response_frame(response)
        for byte in framed_response:
            self.pokey.queue_serial_input(byte)

    def _build_sio_response_frame(self, payload: bytes) -> bytes:
        checksum = self._sio_checksum(payload)
        return bytes([int(SIOResponse.ACK), int(SIOResponse.COMPLETE), *payload, checksum])

    def _sio_checksum(self, payload: bytes) -> int:
        checksum = 0
        for byte in payload:
            checksum += byte
            checksum = (checksum & 0xFF) + (checksum >> 8)
        return checksum & 0xFF

    def _intercept_os_siov(self) -> Opcode | None:
        if self.cpu.pc != SIO_VECTOR:
            return None

        payload = b""
        status = 0x01
        device_id = self.memory.read_byte(int(SIOWorkspace.DDEVIC))
        command = self.memory.read_byte(int(SIOWorkspace.DCMND))
        buffer_address = self.memory.read_word(int(SIOWorkspace.DBUFLO))
        transfer_length = self.memory.read_word(int(SIOWorkspace.DBYTLO))
        sector = self.memory.read_word(int(SIOWorkspace.DAUX1))

        try:
            if command == int(SIOCommand.STATUS):
                payload = self.sio.send_command(device_id, command)
            elif command == int(SIOCommand.READ_SECTOR):
                payload = self.sio.send_command(device_id, command, sector=sector)
            else:
                status = SIO_ERROR_NO_DEVICE
        except KeyError:
            status = SIO_ERROR_NO_DEVICE

        if payload and transfer_length:
            self.memory.load_ram(buffer_address, payload[:transfer_length])

        self.memory.write_byte(int(SIOWorkspace.DSTATS), status)
        self.memory.write_byte(int(SIOWorkspace.STATUS), status)
        self.cpu.a = status
        self.cpu.y = status
        self.cpu.status.carry = status != 0x01
        self.cpu.status.zero = status == 0
        self.cpu.status.negative = bool(status & 0x80)
        self.cpu.pc = (self.cpu._pop_word() + 1) & 0xFFFF

        intercepted_opcode = OPCODES[0x60]
        self.cpu.last_opcode = intercepted_opcode
        self.cpu.cycles += intercepted_opcode.cycles
        self.clock.tick(intercepted_opcode.cycles)
        events = self.antic.tick(intercepted_opcode.cycles)
        if self.pokey.tick(intercepted_opcode.cycles):
            self.cpu.irq()
        if self.antic.scanline == 248:
            self._sync_os_shadows_to_hardware()
        if self.antic.consume_nmi() or "dli" in events or "vbi" in events:
            self.cpu.nmi()
        self._render_visible_scanlines()
        return intercepted_opcode

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
        help="run the actual ROM boot path (default when OS ROM is present)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="force the ROM-free graphics demo instead of booting available ROMs",
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
        not args.demo
        and args.xex is None
        and os_rom_path.exists()
        and machine.memory.self_test_rom is None
    ):
        print(
            "Warning: self-test ROM not found; real cold boot may divert into the "
            "self-test checksum path instead of reaching BASIC."
        )

    machine.reset()
    boot_real_rom = args.xex is None and not args.demo and os_rom_path.exists()
    if boot_real_rom and basic_rom_path.exists():
        print("Boot configuration: OPTION not held, so built-in BASIC remains enabled.")
    if boot_real_rom and machine.memory.self_test_rom is None:
        if machine.continue_without_self_test():
            print(
                "Continuing from post-checksum warm-start fallback because self-test "
                "ROM is unavailable."
            )

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

    if args.xex is None and not boot_real_rom:
        machine.load_demo_screen()
        if args.demo:
            print("Loaded built-in graphics demo (--demo requested)")
        else:
            print("Loaded built-in graphics demo (no ROMs or XEX supplied)")
    elif args.xex is None:
        print("Running real ROM boot path")

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
