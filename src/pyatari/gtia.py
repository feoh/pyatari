"""GTIA color and playfield rendering for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

import numpy as np

from pyatari.antic import DisplayListLine
from pyatari.constants import (
    ANTIC_MODES,
    CHACTLBits,
    GTIAReadRegister,
    GTIAWriteRegister,
    OS_ROM_END,
    OS_ROM_START,
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

# Bit masks for pixel extraction — plain tuple for pixel cache, numpy for bitmap mode.
_PIXEL_MASKS: tuple[int, ...] = (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01)
_BIT_MASKS_NP = np.array(_PIXEL_MASKS, dtype=np.uint8)
_CHACTL_REFLECT: int = int(CHACTLBits.REFLECT)
_CHACTL_INVERSE: int = int(CHACTLBits.INVERSE)
# Max scanline cache entries before a full clear. 24 text rows × 8 glyph rows = 192
# unique entries for a typical text screen; 2048 gives ample headroom for multi-page apps.
_SCANLINE_CACHE_MAX: int = 2048
# Pre-computed integer keys for the four GTIA colour registers used in text rendering.
# Used in the scanline cache key to avoid repeated IntEnum → int conversion.
_REG_COLPF0: int = int(GTIAWriteRegister.COLPF0)
_REG_COLPF1: int = int(GTIAWriteRegister.COLPF1)
_REG_COLPF2: int = int(GTIAWriteRegister.COLPF2)
_REG_COLBK: int = int(GTIAWriteRegister.COLBK)

# Sentinel used to clear player/missile DMA buffers in-place via slice assignment.
_ZERO_ROW: tuple[int, ...] = (0,) * DISPLAY_WIDTH


@dataclass(slots=True)
class GTIA:
    """Minimal GTIA model focused on color registers and text-mode scanlines."""

    memory: MemoryBus
    write_registers: dict[int, int] = field(default_factory=dict)
    read_registers: dict[int, int] = field(default_factory=dict)
    framebuffer: np.ndarray = field(
        default_factory=lambda: np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH), dtype=np.uint32)
    )
    player_dma: list[list[int]] = field(
        default_factory=lambda: [[0 for _ in range(DISPLAY_WIDTH)] for _ in range(4)]
    )
    missile_dma: list[list[int]] = field(
        default_factory=lambda: [[0 for _ in range(DISPLAY_WIDTH)] for _ in range(4)]
    )
    _pm_any_active: bool = False
    # Per-player and per-missile dirty flags: True means the DMA buffer was
    # written last scanline and must be cleared before the next render.
    # Avoids clearing 384-element buffers every scanline when sprites are inactive.
    _player_dirty: list[bool] = field(default_factory=lambda: [False, False, False, False])
    _missiles_dirty: bool = False
    # Glyph-row cache: (chbase_page, glyph_row) → list of 128 pattern bytes.
    # ROM is immutable so entries are never stale; custom RAM charsets bypass
    # the cache and always fall back to read_byte.
    _glyph_cache: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    # Cross-scanline pixel table: (fg, bg, subpixel_count) → list[256] of pixel lists.
    # Built once per unique color+mode combination; eliminates per-scanline [None]*256
    # setup and all per-character cache-miss list comprehensions.
    _pixel_table: dict[tuple[int, int, int], list[list[int]]] = field(default_factory=dict)
    # Scanline output cache: maps (fg, bg, subpixel_count, chbase_page, glyph_row,
    # chactl_inv, chars_bytes) → pre-rendered numpy row (1-D uint32 array of DISPLAY_WIDTH).
    # Only caches ROM charset scanlines (glyph data is immutable). On cache hit the row
    # is copied directly into the framebuffer, bypassing the entire inner loop.
    _scanline_cache: dict = field(default_factory=dict)

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
        self.framebuffer[:] = self.color_to_rgb(self.write_registers[int(GTIAWriteRegister.COLBK)])

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
        # ── Phase 1: Cheap invariants (no colour lookups, no glyph reads) ────────────
        scr_start = line.screen_address & 0xFFFF
        chars = self.memory.ram[scr_start:scr_start + columns]
        chactl_inv = antic_chactl & _CHACTL_INVERSE
        subpixel_count = cell_width // 8
        chbase_page = (antic_chbase & 0xFF) << 8

        glyph_row = (row + vertical_offset) % ANTIC_MODES[line.mode].scanlines_per_row
        if antic_chactl & _CHACTL_REFLECT:
            glyph_row = 7 - (glyph_row % 8)
        else:
            glyph_row %= 8

        # ── Phase 2: Glyph pattern bytearray ────────────────────────────────────────
        # Read actual glyph pattern bytes for each character on this scanline into a
        # compact bytearray. This serves two purposes:
        # (a) scanline cache key component — captures exact glyph data, not just char codes,
        #     so RAM charsets that change between frames are automatically detected;
        # (b) pixel expansion source on cache miss — no second RAM read needed.
        # Inverse-character handling is applied here so the resulting bytes uniquely
        # identify the visual output, making chactl_inv redundant in the cache key.
        ram = self.memory.ram
        os_rom = self.memory.os_rom
        if os_rom is not None and OS_ROM_START <= chbase_page <= OS_ROM_END - 0x3FF:
            glyph_key = (chbase_page, glyph_row)
            if glyph_key not in self._glyph_cache:
                base = chbase_page - OS_ROM_START + glyph_row
                self._glyph_cache[glyph_key] = [os_rom[base + c * 8] for c in range(128)]
            glyph_src: list[int] | None = self._glyph_cache[glyph_key]
        else:
            glyph_src = None

        patterns = bytearray(columns)
        if glyph_src is not None:
            for i, c in enumerate(chars):
                q = glyph_src[c & 0x7F]
                if c >> 7:
                    q = 0 if chactl_inv else q ^ 0xFF
                patterns[i] = q
        else:
            for i, c in enumerate(chars):
                addr = (chbase_page + (c & 0x7F) * 8 + glyph_row) & 0xFFFF
                q = ram[addr]
                if c >> 7:
                    q = 0 if chactl_inv else q ^ 0xFF
                patterns[i] = q

        # ── Phase 3: Scanline output cache check ────────────────────────────────────
        # Key: raw colour registers + mode + pattern bytes. Using raw register values
        # (not colour_to_rgb output) defers the expensive colour computation until after
        # the cache miss is confirmed, making hits ~2-5 µs instead of ~20 µs.
        # The pattern bytes already encode glyph_row and chactl_inv, so they need not
        # appear separately in the key.
        wr = self.write_registers
        sc_key = (
            wr[_REG_COLPF0], wr[_REG_COLPF1], wr[_REG_COLPF2], wr[_REG_COLBK],
            line.mode, bytes(patterns),
        )
        cached_row = self._scanline_cache.get(sc_key)
        if cached_row is not None:
            self.framebuffer[row] = cached_row
            return

        # ── Phase 4: Colour computation (deferred to cache miss only) ───────────────
        if line.mode in {2, 3}:
            fg_color = _COLOR_TABLE[(wr[_REG_COLPF2] & 0xF0) | (wr[_REG_COLPF1] & 0x0E)]
            bg_color = _COLOR_TABLE[wr[_REG_COLPF2] & 0xFF]
        else:
            fg_color = _COLOR_TABLE[wr[_REG_COLPF1] & 0xFF]
            bg_color = _COLOR_TABLE[wr[_REG_COLBK] & 0xFF]
        if line.mode in {4, 5, 6, 7}:
            fg = _COLOR_TABLE[wr[_REG_COLPF2] & 0xFF]
            bg = _COLOR_TABLE[wr[_REG_COLPF0] & 0xFF]
        else:
            fg = fg_color
            bg = bg_color

        # Cross-scanline pixel table: precomputed for all 256 pattern bytes for this
        # (fg, bg, subpixel_count) combination. Built once and reused across all frames.
        table_key = (fg, bg, subpixel_count)
        pixel_table = self._pixel_table.get(table_key)
        if pixel_table is None:
            if subpixel_count == 1:
                pixel_table = [[fg if p & m else bg for m in _PIXEL_MASKS] for p in range(256)]
            else:
                pixel_table = [[c for m in _PIXEL_MASKS for c in (fg if p & m else bg,) * 2] for p in range(256)]
            self._pixel_table[table_key] = pixel_table

        # ── Phase 5: Pixel expansion ─────────────────────────────────────────────────
        # patterns bytearray already computed in Phase 2 — no second glyph read.
        out_row: list[int] = [bg_color] * DISPLAY_WIDTH
        col_start = 0
        if subpixel_count == 1:
            for q in patterns:
                out_row[col_start:col_start + 8] = pixel_table[q]
                col_start += 8
        else:
            for q in patterns:
                out_row[col_start:col_start + cell_width] = pixel_table[q]
                col_start += cell_width

        # ── Phase 6: Commit + cache store ───────────────────────────────────────────
        self.framebuffer[row] = out_row
        if len(self._scanline_cache) >= _SCANLINE_CACHE_MAX:
            self._scanline_cache.clear()
        self._scanline_cache[sc_key] = self.framebuffer[row].copy()

    def _render_bitmap_mode(self, line: DisplayListLine, *, row: int, vertical_offset: int = 0) -> None:
        mode_info = ANTIC_MODES[line.mode]
        row_block = vertical_offset // max(1, mode_info.scanlines_per_row)
        base_address = (line.screen_address + (row_block * mode_info.bytes_per_line)) & 0xFFFF
        data = [self.memory.read_byte(base_address + index) for index in range(mode_info.bytes_per_line)]
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

        if pixels:
            repeat = max(1, DISPLAY_WIDTH // max(1, len(pixels)))
            expanded = np.repeat(np.array(pixels, dtype=np.uint32), repeat)
            n = min(len(expanded), DISPLAY_WIDTH)
            self.framebuffer[row, :n] = expanded[:n]
            if n < DISPLAY_WIDTH:
                self.framebuffer[row, n:] = colors[0]

    def render_player(self, player: int, *, xpos: int, graphics: int, size: int, color: int) -> None:
        player_row = self.player_dma[player]
        if self._player_dirty[player]:
            player_row[:] = _ZERO_ROW
            self._player_dirty[player] = False
        if not graphics:
            return
        self._player_dirty[player] = True
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
        if self._missiles_dirty:
            for missile in range(4):
                self.missile_dma[missile][:] = _ZERO_ROW
            self._missiles_dirty = False
        if not (graphics & 0x0F):
            return
        self._missiles_dirty = True
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
        self._player_dirty[:] = [False, False, False, False]
        self._missiles_dirty = False

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
        src = self.framebuffer[row].copy()  # copy before in-place modification
        self.framebuffer[row, :offset] = bg
        self.framebuffer[row, offset:] = src[:DISPLAY_WIDTH - offset]

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
        self.framebuffer[row] = self.color_to_rgb(color_value)

    def _hires_luminance_color(self) -> int:
        pf2 = self.write_registers[int(GTIAWriteRegister.COLPF2)]
        pf1 = self.write_registers[int(GTIAWriteRegister.COLPF1)]
        return self.color_to_rgb((pf2 & 0xF0) | (pf1 & 0x0E))

    def _normalize(self, address: int) -> int:
        return GTIA_MIRROR_BASE + ((address - GTIA_MIRROR_BASE) & GTIA_MIRROR_MASK)
