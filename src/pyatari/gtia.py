"""GTIA color and playfield rendering for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

from pyatari.antic import DisplayListLine
from pyatari.constants import (
    ANTIC_MODES,
    CHACTLBits,
    GTIAReadRegister,
    GTIAWriteRegister,
    PM_SIZE_DOUBLE,
    PM_SIZE_QUAD,
    PORTBBits,
)
from pyatari.memory import MemoryBus

GTIA_MIRROR_BASE = 0xD000
GTIA_MIRROR_MASK = 0x1F
DISPLAY_WIDTH = 384
DISPLAY_HEIGHT = 240
GTIA_HUE_RGB = {
    0x1: (192, 116, 0),
    0x2: (208, 72, 32),
    0x3: (192, 48, 88),
    0x4: (144, 64, 152),
    0x5: (96, 72, 192),
    0x6: (48, 96, 208),
    0x7: (24, 132, 192),
    0x8: (24, 156, 144),
    0x9: (0, 150, 255),
    0xA: (88, 168, 88),
    0xB: (136, 160, 56),
    0xC: (176, 144, 40),
    0xD: (208, 128, 32),
    0xE: (224, 112, 24),
    0xF: (216, 104, 8),
}


def _build_color_table() -> list[int]:
    """Pre-compute all 256 Atari color register values to packed RGB ints."""
    result = []
    for value in range(256):
        hue = (value >> 4) & 0x0F
        luminance = value & 0x0E
        brightness = sqrt(luminance / 14.0)
        if hue == 0:
            gray = int(255 * brightness)
            result.append((gray << 16) | (gray << 8) | gray)
        else:
            r, g, b = GTIA_HUE_RGB[hue]
            result.append((int(r * brightness) << 16) | (int(g * brightness) << 8) | int(b * brightness))
    return result


_COLOR_TABLE: list[int] = _build_color_table()

# Pre-computed pixel bit masks and zero-row sentinel used by hot render paths.
_PIXEL_MASKS: tuple[int, ...] = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)
_ZERO_ROW: tuple[int, ...] = (0,) * DISPLAY_WIDTH


@dataclass(slots=True)
class GTIA:
    """Minimal GTIA model focused on color registers and text-mode scanlines."""

    memory: MemoryBus
    write_registers: dict[int, int] = field(default_factory=dict)
    read_registers: dict[int, int] = field(default_factory=dict)
    framebuffer: list[list[int]] = field(
        default_factory=lambda: [[0 for _ in range(DISPLAY_WIDTH)] for _ in range(DISPLAY_HEIGHT)]
    )
    player_dma: list[list[int]] = field(
        default_factory=lambda: [[0 for _ in range(DISPLAY_WIDTH)] for _ in range(4)]
    )
    missile_dma: list[list[int]] = field(
        default_factory=lambda: [[0 for _ in range(DISPLAY_WIDTH)] for _ in range(4)]
    )
    _pm_any_active: bool = False

    def __post_init__(self) -> None:
        for register in GTIAWriteRegister:
            self.write_registers[int(register)] = 0
        for register in GTIAReadRegister:
            self.read_registers[int(register)] = 0
        self._reset_input_registers()

    def install(self) -> None:
        self.memory.register_read_handler(0xD000, 0xD01F, self.read_register)
        self.memory.register_write_handler(0xD000, 0xD01F, self.write_register)

    def reset(self) -> None:
        for register in self.write_registers:
            self.write_registers[register] = 0
        for register in self.read_registers:
            self.read_registers[register] = 0
        self._reset_input_registers()
        self.clear_framebuffer()
        self._clear_pm_buffers()

    def begin_scanline_render(self) -> None:
        """Reset the P/M active flag before rendering each scanline's sprites."""
        self._pm_any_active = False

    def read_register(self, address: int) -> int:
        register = self._normalize(address)
        if register == int(GTIAReadRegister.TRIG3):
            return 0x01 if (self.memory.portb & int(PORTBBits.BASIC_ROM_ENABLE)) else 0x00
        if register in self.read_registers:
            return self.read_registers[register]
        if register in self.write_registers:
            return self.write_registers[register]
        return 0

    def write_register(self, address: int, value: int) -> None:
        register = self._normalize(address)
        value &= 0xFF
        if register == int(GTIAWriteRegister.HITCLR):
            self._clear_collision_registers()
            return
        if register in self.write_registers:
            self.write_registers[register] = value

    def clear_framebuffer(self) -> None:
        background = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)])
        for y in range(DISPLAY_HEIGHT):
            row = self.framebuffer[y]
            for x in range(DISPLAY_WIDTH):
                row[x] = background

    def color_to_rgb(self, value: int) -> int:
        return _COLOR_TABLE[value & 0xFF]

    def render_scanline(
        self,
        line: DisplayListLine | None,
        *,
        row: int,
        antic_chbase: int = 0,
        antic_chactl: int = 0,
        antic_hscrol: int = 0,
        antic_vscrol: int = 0,
    ) -> None:
        if not (0 <= row < DISPLAY_HEIGHT):
            return
        if line is None or line.mode is None or line.screen_address is None:
            self._fill_row(row, self.write_registers[int(GTIAWriteRegister.COLBK)])
            return

        mode_info = ANTIC_MODES.get(line.mode)
        if mode_info is None:
            self._fill_row(row, self.write_registers[int(GTIAWriteRegister.COLBK)])
            return

        if mode_info.is_text:
            self._render_text_mode(
                line,
                row=row,
                antic_chbase=antic_chbase,
                antic_chactl=antic_chactl,
                columns=mode_info.bytes_per_line,
                cell_width=8 if line.mode in {2, 3, 4, 5} else 16,
                vertical_offset=self._vertical_scroll_offset(line, antic_vscrol),
            )
        else:
            self._render_bitmap_mode(line, row=row, vertical_offset=self._vertical_scroll_offset(line, antic_vscrol))

        if line.hscroll:
            self._apply_horizontal_scroll(row, self._horizontal_scroll_offset(line, antic_hscrol))

        self._overlay_player_missile_graphics(row)

    def _render_text_mode(
        self,
        line: DisplayListLine,
        *,
        row: int,
        antic_chbase: int,
        antic_chactl: int,
        columns: int,
        cell_width: int,
        vertical_offset: int = 0,
    ) -> None:
        chars = [self.memory.read_byte(line.screen_address + column) for column in range(columns)]
        glyph_row = (row + vertical_offset) % ANTIC_MODES[line.mode].scanlines_per_row
        if line.mode in {2, 3}:
            fg_color = self._hires_luminance_color()
            bg_color = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF2)])
        else:
            fg_color = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF1)])
            bg_color = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)])
        alt_fg = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF2)])
        alt_bg = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF0)])
        out_row = self.framebuffer[row]

        if antic_chactl & int(CHACTLBits.REFLECT):
            glyph_row = 7 - (glyph_row % 8)
        else:
            glyph_row %= 8

        # Hoist per-scanline constants out of the per-character and per-bit loops.
        # cell_width is always 8 or 16, so subpixel_count is always 1 or 2 (never 0).
        # All text modes produce columns*cell_width == 320 <= DISPLAY_WIDTH (384),
        # so no per-pixel bounds check is needed.
        subpixel_count = cell_width // 8
        fg = alt_fg if line.mode in {4, 5, 6, 7} else fg_color
        bg = alt_bg if line.mode in {4, 5, 6, 7} else bg_color

        if subpixel_count == 1:
            for column, char_code in enumerate(chars):
                glyph_address = ((antic_chbase & 0xFF) << 8) + ((char_code & 0x7F) * 8) + glyph_row
                pattern = self.memory.read_byte(glyph_address)
                if char_code & 0x80:
                    pattern = 0 if antic_chactl & int(CHACTLBits.INVERSE) else pattern ^ 0xFF
                base_x = column * 8
                out_row[base_x:base_x + 8] = [fg if pattern & m else bg for m in _PIXEL_MASKS]
        else:
            for column, char_code in enumerate(chars):
                glyph_address = ((antic_chbase & 0xFF) << 8) + ((char_code & 0x7F) * 8) + glyph_row
                pattern = self.memory.read_byte(glyph_address)
                if char_code & 0x80:
                    pattern = 0 if antic_chactl & int(CHACTLBits.INVERSE) else pattern ^ 0xFF
                base_x = column * 16
                out_row[base_x:base_x + 16] = [c for m in _PIXEL_MASKS for c in (fg if pattern & m else bg,) * 2]

        fill_from = columns * cell_width
        for x in range(fill_from, DISPLAY_WIDTH):
            out_row[x] = bg_color

    def _render_bitmap_mode(self, line: DisplayListLine, *, row: int, vertical_offset: int = 0) -> None:
        mode_info = ANTIC_MODES[line.mode]
        row_block = vertical_offset // max(1, mode_info.scanlines_per_row)
        base_address = (line.screen_address + (row_block * mode_info.bytes_per_line)) & 0xFFFF
        data = [self.memory.read_byte(base_address + index) for index in range(mode_info.bytes_per_line)]
        out_row = self.framebuffer[row]
        colors = [
            self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)]),
            self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF0)]),
            self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF1)]),
            self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF2)]),
        ]

        pixels: list[int] = []
        if line.mode in {8, 10, 13, 14}:
            for byte in data:
                for shift in (6, 4, 2, 0):
                    pixels.append(colors[(byte >> shift) & 0x03])
        elif line.mode in {9, 11, 12, 15}:
            if line.mode == 15:
                fg = self._hires_luminance_color()
                bg = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF2)])
            else:
                fg = colors[1]
                bg = colors[0]
            for byte in data:
                for bit in range(8):
                    pixels.append(fg if byte & (0x80 >> bit) else bg)
        else:
            self._fill_row(row, self.write_registers[int(GTIAWriteRegister.COLBK)])
            return

        repeat = max(1, DISPLAY_WIDTH // max(1, len(pixels)))
        x = 0
        for pixel in pixels:
            for _ in range(repeat):
                if x >= DISPLAY_WIDTH:
                    break
                out_row[x] = pixel
                x += 1
            if x >= DISPLAY_WIDTH:
                break
        while x < DISPLAY_WIDTH:
            out_row[x] = colors[0]
            x += 1

    def render_player(self, player: int, *, xpos: int, graphics: int, size: int, color: int) -> None:
        player_row = self.player_dma[player]
        player_row[:] = _ZERO_ROW
        if not graphics:
            return
        self._pm_any_active = True
        width = self._pm_size_multiplier(size)
        color_rgb = self.color_to_rgb(color)
        for bit in range(8):
            if not (graphics & (0x80 >> bit)):
                continue
            start = xpos + (bit * width)
            for offset in range(width):
                x = start + offset
                if 0 <= x < DISPLAY_WIDTH:
                    player_row[x] = color_rgb

    def render_missiles(self, *, xpos: list[int], graphics: int, size_mask: int, color: int) -> None:
        for missile in range(4):
            self.missile_dma[missile][:] = _ZERO_ROW
        if not (graphics & 0x0F):
            return
        self._pm_any_active = True
        color_rgb = self.color_to_rgb(color)
        for missile in range(4):
            if not (graphics & (1 << missile)):
                continue
            width_code = (size_mask >> (missile * 2)) & 0x03
            width = self._pm_size_multiplier(width_code) * 2
            for offset in range(width):
                x = xpos[missile] + offset
                if 0 <= x < DISPLAY_WIDTH:
                    self.missile_dma[missile][x] = color_rgb

    def _overlay_player_missile_graphics(self, row: int) -> None:
        if not self._pm_any_active:
            return
        out_row = self.framebuffer[row]
        bg_color = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)])
        for missile in range(4):
            missile_row = self.missile_dma[missile]
            for x, pixel in enumerate(missile_row):
                if pixel:
                    if out_row[x] != bg_color:
                        self.read_registers[int(GTIAReadRegister.M0PF) + missile] = 0x0F
                    out_row[x] = pixel
        for player in range(4):
            player_row = self.player_dma[player]
            for x, pixel in enumerate(player_row):
                if pixel:
                    if out_row[x] != bg_color:
                        self.read_registers[int(GTIAReadRegister.P0PF) + player] = 0x0F
                    for other in range(4):
                        if other != player and self.player_dma[other][x]:
                            self.read_registers[int(GTIAReadRegister.P0PL) + player] |= 1 << other
                    out_row[x] = pixel

    def set_trigger(self, trigger: int, pressed: bool) -> None:
        register = int(GTIAReadRegister.TRIG0) + trigger
        self.read_registers[register] = 0x00 if pressed else 0x01

    def set_console_switch(self, *, start: bool | None = None, select: bool | None = None, option: bool | None = None) -> None:
        consol = self.read_registers[int(GTIAReadRegister.CONSOL)] & 0x07
        if start is not None:
            consol = (consol & ~0x01) | (0x00 if start else 0x01)
        if select is not None:
            consol = (consol & ~0x02) | (0x00 if select else 0x02)
        if option is not None:
            consol = (consol & ~0x04) | (0x00 if option else 0x04)
        self.read_registers[int(GTIAReadRegister.CONSOL)] = consol

    def _clear_pm_buffers(self) -> None:
        for i in range(4):
            self.player_dma[i][:] = _ZERO_ROW
            self.missile_dma[i][:] = _ZERO_ROW
        self._pm_any_active = False

    def _pm_size_multiplier(self, size: int) -> int:
        if size == PM_SIZE_DOUBLE:
            return 2
        if size == PM_SIZE_QUAD:
            return 4
        return 1

    def _horizontal_scroll_offset(self, line: DisplayListLine, antic_hscrol: int) -> int:
        return antic_hscrol & 0x0F if line.hscroll else 0

    def _vertical_scroll_offset(self, line: DisplayListLine, antic_vscrol: int) -> int:
        return antic_vscrol & 0x0F if line.vscroll else 0

    def _apply_horizontal_scroll(self, row: int, offset: int) -> None:
        if offset <= 0:
            return
        bg = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)])
        out_row = self.framebuffer[row]
        shifted = [bg] * DISPLAY_WIDTH
        for x in range(offset, DISPLAY_WIDTH):
            shifted[x] = out_row[x - offset]
        self.framebuffer[row] = shifted

    def _reset_input_registers(self) -> None:
        self._clear_collision_registers()
        for register in range(int(GTIAReadRegister.TRIG0), int(GTIAReadRegister.TRIG2) + 1):
            self.read_registers[register] = 0x01
        self.read_registers[int(GTIAReadRegister.CONSOL)] = 0x07
        self.read_registers[int(GTIAReadRegister.PAL)] = 0x01

    def _clear_collision_registers(self) -> None:
        for register in range(int(GTIAReadRegister.M0PF), int(GTIAReadRegister.P3PL) + 1):
            self.read_registers[register] = 0x00

    def _fill_row(self, row: int, color_value: int) -> None:
        color = self.color_to_rgb(color_value)
        out_row = self.framebuffer[row]
        for x in range(DISPLAY_WIDTH):
            out_row[x] = color

    def _hires_luminance_color(self) -> int:
        pf2 = self.write_registers[int(GTIAWriteRegister.COLPF2)]
        pf1 = self.write_registers[int(GTIAWriteRegister.COLPF1)]
        return self.color_to_rgb((pf2 & 0xF0) | (pf1 & 0x0E))

    def _normalize(self, address: int) -> int:
        return GTIA_MIRROR_BASE + ((address - GTIA_MIRROR_BASE) & GTIA_MIRROR_MASK)
