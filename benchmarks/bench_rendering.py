"""ANTIC/GTIA rendering pipeline benchmarks."""

from __future__ import annotations

import pytest

from pyatari.antic import DisplayListLine
from pyatari.constants import CYCLES_PER_SCANLINE, GTIAWriteRegister, RESET_VECTOR
from pyatari.gtia import DISPLAY_HEIGHT
from pyatari.machine import Machine

_SCREEN_ADDRESS = 0x3000
_CHARSET_ADDRESS = 0x4000


def _text_mode_line() -> DisplayListLine:
    return DisplayListLine(
        instruction_address=0x2400,
        instruction=0x02,
        mode=2,  # ANTIC mode 2: 40-column text
        scanlines=8,
        screen_address=_SCREEN_ADDRESS,
    )


def _bitmap_mode_line() -> DisplayListLine:
    return DisplayListLine(
        instruction_address=0x2400,
        instruction=0x0F,
        mode=15,  # ANTIC mode 15: 320-pixel hi-res bitmap
        scanlines=1,
        screen_address=_SCREEN_ADDRESS,
    )


@pytest.fixture
def render_machine() -> Machine:
    """Machine with demo screen loaded, ready for direct render_scanline calls."""
    machine = Machine()
    machine.reset()
    machine.load_demo_screen()
    # One warmup frame so the framebuffer is fully initialized
    machine.run_frame(queue_audio=False)
    return machine


@pytest.fixture
def bare_render_machine() -> Machine:
    """Minimal machine set up for raw render_scanline benchmarks."""
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.reset()
    machine.memory.load_ram(0x2000, bytes([0xEA] * 0x8000))
    # Put a screenful of 'A' characters (screen code 33) at 0x3000
    machine.memory.load_ram(_SCREEN_ADDRESS, bytes([33] * 40 * 25))
    # Put a simple checkerboard pattern in bitmap memory
    machine.memory.load_ram(_SCREEN_ADDRESS, bytes([0xAA, 0x55] * 500))
    # Minimal GTIA color registers for a visible image
    machine.memory.write_byte(int(GTIAWriteRegister.COLBK), 0x00)
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF0), 0x28)
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF1), 0x0E)
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF2), 0x58)
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF3), 0xC6)
    machine.antic.chbase = _CHARSET_ADDRESS >> 8
    return machine


def test_bench_gtia_color_to_rgb(benchmark: pytest.FixtureRequest, render_machine: Machine) -> None:
    """color_to_rgb() — called per-pixel; uses sqrt() internally."""
    benchmark(render_machine.gtia.color_to_rgb, 0x28)


def test_bench_gtia_render_scanline_text(
    benchmark: pytest.FixtureRequest, bare_render_machine: Machine
) -> None:
    """render_scanline() in text mode 2 — 40-column character rendering."""
    m = bare_render_machine
    line = _text_mode_line()
    benchmark(
        m.gtia.render_scanline,
        line,
        row=10,
        antic_chbase=_CHARSET_ADDRESS >> 8,
    )


def test_bench_gtia_render_scanline_bitmap(
    benchmark: pytest.FixtureRequest, bare_render_machine: Machine
) -> None:
    """render_scanline() in bitmap mode 15 — 320-pixel hi-res."""
    m = bare_render_machine
    line = _bitmap_mode_line()
    benchmark(
        m.gtia.render_scanline,
        line,
        row=10,
    )


def test_bench_gtia_render_full_frame(
    benchmark: pytest.FixtureRequest, bare_render_machine: Machine
) -> None:
    """All 240 visible scanlines rendered in text mode — full frame render cost."""
    m = bare_render_machine
    line = _text_mode_line()
    chbase = _CHARSET_ADDRESS >> 8

    def render_frame() -> None:
        for row in range(DISPLAY_HEIGHT):
            m.gtia.render_scanline(line, row=row, antic_chbase=chbase)

    benchmark(render_frame)


def test_bench_antic_tick_one_cycle(
    benchmark: pytest.FixtureRequest, render_machine: Machine
) -> None:
    """antic.tick(1) — per-cycle overhead: the inner loop in every machine.step()."""
    benchmark(render_machine.antic.tick, 1)


def test_bench_antic_tick_scanline(
    benchmark: pytest.FixtureRequest, render_machine: Machine
) -> None:
    """antic.tick(114) — one full scanline's worth of ANTIC ticks."""
    benchmark(render_machine.antic.tick, CYCLES_PER_SCANLINE)
