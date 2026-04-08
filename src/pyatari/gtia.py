"""GTIA color and playfield rendering for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.antic import DisplayListLine
from pyatari.constants import (
    ANTIC_MODES,
    CHACTLBits,
    GTIAReadRegister,
    GTIAWriteRegister,
    PM_SIZE_DOUBLE,
    PM_SIZE_QUAD,
)
from pyatari.memory import MemoryBus

GTIA_MIRROR_BASE = 0xD000
GTIA_MIRROR_MASK = 0x1F
DISPLAY_WIDTH = 384
DISPLAY_HEIGHT = 240


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

    def __post_init__(self) -> None:
        for register in GTIAWriteRegister:
            self.write_registers[int(register)] = 0
        for register in GTIAReadRegister:
            self.read_registers[int(register)] = 0

    def install(self) -> None:
        self.memory.register_read_handler(0xD000, 0xD01F, self.read_register)
        self.memory.register_write_handler(0xD000, 0xD01F, self.write_register)

    def reset(self) -> None:
        for register in self.write_registers:
            self.write_registers[register] = 0
        for register in self.read_registers:
            self.read_registers[register] = 0
        self.clear_framebuffer()
        self._clear_pm_buffers()

    def read_register(self, address: int) -> int:
        register = self._normalize(address)
        if register in self.read_registers:
            return self.read_registers[register]
        if register in self.write_registers:
            return self.write_registers[register]
        return 0

    def write_register(self, address: int, value: int) -> None:
        register = self._normalize(address)
        value &= 0xFF
        if register == int(GTIAWriteRegister.HITCLR):
            for key in self.read_registers:
                self.read_registers[key] = 0
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
        value &= 0xFF
        hue = (value >> 4) & 0x0F
        luminance = value & 0x0F
        brightness = min(255, luminance * 16 + 15)
        phase = hue / 16.0
        red = int(brightness * (0.55 + 0.45 * ((phase + 0.00) % 1.0))) & 0xFF
        green = int(brightness * (0.55 + 0.45 * ((phase + 0.33) % 1.0))) & 0xFF
        blue = int(brightness * (0.55 + 0.45 * ((phase + 0.66) % 1.0))) & 0xFF
        return (red << 16) | (green << 8) | blue

    def render_scanline(
        self,
        line: DisplayListLine | None,
        *,
        row: int,
        antic_chbase: int = 0,
        antic_chactl: int = 0,
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
            )
        else:
            self._render_bitmap_mode(line, row=row)

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
    ) -> None:
        chars = [self.memory.read_byte(line.screen_address + column) for column in range(columns)]
        glyph_row = row % ANTIC_MODES[line.mode].scanlines_per_row
        fg_color = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF1)])
        bg_color = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)])
        alt_fg = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF2)])
        alt_bg = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLPF0)])
        out_row = self.framebuffer[row]

        if antic_chactl & int(CHACTLBits.REFLECT):
            glyph_row = 7 - (glyph_row % 8)
        else:
            glyph_row %= 8

        for column, char_code in enumerate(chars):
            glyph_address = ((antic_chbase & 0xFF) << 8) + ((char_code & 0x7F) * 8) + glyph_row
            pattern = self.memory.read_byte(glyph_address)
            inverse = bool(char_code & 0x80)
            fg = alt_fg if line.mode in {4, 5, 6, 7} else fg_color
            bg = alt_bg if line.mode in {4, 5, 6, 7} else bg_color
            if inverse:
                if antic_chactl & int(CHACTLBits.INVERSE):
                    pattern = 0
                else:
                    pattern ^= 0xFF
            base_x = column * cell_width
            for bit in range(8):
                pixel = fg if pattern & (0x80 >> bit) else bg
                x = base_x + bit * (cell_width // 8)
                repeat = max(1, cell_width // 8)
                for subpixel in range(repeat):
                    if x + subpixel < DISPLAY_WIDTH:
                        out_row[x + subpixel] = pixel

        fill_from = min(DISPLAY_WIDTH, columns * cell_width)
        for x in range(fill_from, DISPLAY_WIDTH):
            out_row[x] = bg_color

    def _render_bitmap_mode(self, line: DisplayListLine, *, row: int) -> None:
        mode_info = ANTIC_MODES[line.mode]
        data = [self.memory.read_byte(line.screen_address + index) for index in range(mode_info.bytes_per_line)]
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
        self.player_dma[player] = [0 for _ in range(DISPLAY_WIDTH)]
        width = self._pm_size_multiplier(size)
        color_rgb = self.color_to_rgb(color)
        for bit in range(8):
            if not (graphics & (0x80 >> bit)):
                continue
            start = xpos + (bit * width)
            for offset in range(width):
                x = start + offset
                if 0 <= x < DISPLAY_WIDTH:
                    self.player_dma[player][x] = color_rgb

    def render_missiles(self, *, xpos: list[int], graphics: int, size_mask: int, color: int) -> None:
        for missile in range(4):
            self.missile_dma[missile] = [0 for _ in range(DISPLAY_WIDTH)]
            if not (graphics & (1 << missile)):
                continue
            width_code = (size_mask >> (missile * 2)) & 0x03
            width = self._pm_size_multiplier(width_code) * 2
            color_rgb = self.color_to_rgb(color)
            for offset in range(width):
                x = xpos[missile] + offset
                if 0 <= x < DISPLAY_WIDTH:
                    self.missile_dma[missile][x] = color_rgb

    def _overlay_player_missile_graphics(self, row: int) -> None:
        out_row = self.framebuffer[row]
        for missile in range(4):
            missile_row = self.missile_dma[missile]
            for x, pixel in enumerate(missile_row):
                if pixel:
                    if out_row[x] != self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)]):
                        self.read_registers[int(GTIAReadRegister.M0PF) + missile] = 0x0F
                    out_row[x] = pixel
        for player in range(4):
            player_row = self.player_dma[player]
            for x, pixel in enumerate(player_row):
                if pixel:
                    if out_row[x] != self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)]):
                        self.read_registers[int(GTIAReadRegister.P0PF) + player] = 0x0F
                    for other in range(4):
                        if other != player and self.player_dma[other][x]:
                            self.read_registers[int(GTIAReadRegister.P0PL) + player] |= 1 << other
                    out_row[x] = pixel

    def _clear_pm_buffers(self) -> None:
        for player in range(4):
            self.player_dma[player] = [0 for _ in range(DISPLAY_WIDTH)]
            self.missile_dma[player] = [0 for _ in range(DISPLAY_WIDTH)]

    def _pm_size_multiplier(self, size: int) -> int:
        if size == PM_SIZE_DOUBLE:
            return 2
        if size == PM_SIZE_QUAD:
            return 4
        return 1

    def _fill_row(self, row: int, color_value: int) -> None:
        color = self.color_to_rgb(color_value)
        out_row = self.framebuffer[row]
        for x in range(DISPLAY_WIDTH):
            out_row[x] = color

    def _normalize(self, address: int) -> int:
        return GTIA_MIRROR_BASE + ((address - GTIA_MIRROR_BASE) & GTIA_MIRROR_MASK)
