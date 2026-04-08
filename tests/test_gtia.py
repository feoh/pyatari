"""Tests for the GTIA core and initial display rendering."""

from __future__ import annotations

from pyatari.antic import DisplayListLine
from pyatari.constants import GTIAReadRegister, GTIAWriteRegister, RESET_VECTOR
from pyatari.display import DisplaySurface
from pyatari.gtia import DISPLAY_WIDTH, GTIA
from pyatari.machine import Machine
from pyatari.memory import MemoryBus


def test_gtia_write_and_read_registers_round_trip():
    gtia = GTIA(memory=MemoryBus())

    gtia.write_register(int(GTIAWriteRegister.COLPF1), 0x3A)

    assert gtia.read_register(int(GTIAWriteRegister.COLPF1)) == 0x3A


def test_hitclr_clears_collision_registers():
    gtia = GTIA(memory=MemoryBus())
    gtia.read_registers[int(GTIAReadRegister.P0PF)] = 0xFF

    gtia.write_register(int(GTIAWriteRegister.HITCLR), 0x00)

    assert gtia.read_register(int(GTIAReadRegister.P0PF)) == 0


def test_color_to_rgb_changes_with_input():
    gtia = GTIA(memory=MemoryBus())

    dark = gtia.color_to_rgb(0x00)
    bright = gtia.color_to_rgb(0x0E)
    different_hue = gtia.color_to_rgb(0xA0)

    assert dark != bright
    assert dark != different_hue


def test_render_scanline_mode_2_text_uses_charset_bits():
    memory = MemoryBus()
    gtia = GTIA(memory=memory)
    gtia.write_register(int(GTIAWriteRegister.COLPF1), 0x0E)
    gtia.write_register(int(GTIAWriteRegister.COLBK), 0x00)
    memory.write_byte(0x3000, 0x41)
    memory.write_byte(0x1608, 0b10000000)  # simplified glyph row for char $41

    line = DisplayListLine(instruction_address=0x2000, instruction=0x42, mode=2, scanlines=8, screen_address=0x3000)
    gtia.render_scanline(line, row=0, antic_chbase=0x14)

    assert gtia.framebuffer[0][0] == gtia.color_to_rgb(0x0E)
    assert gtia.framebuffer[0][1] == gtia.color_to_rgb(0x00)
    assert gtia.framebuffer[0][DISPLAY_WIDTH - 1] == gtia.color_to_rgb(0x00)


def test_display_surface_copies_gtia_framebuffer():
    gtia = GTIA(memory=MemoryBus())
    gtia.framebuffer[0][0] = 0x123456

    surface = DisplaySurface()
    frame = surface.frame_from_gtia(gtia)
    frame[0][0] = 0

    assert gtia.framebuffer[0][0] == 0x123456


def test_machine_installs_gtia_handlers_and_renders_visible_line():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.memory.load_ram(0x2000, bytes([0xEA] * 57))
    machine.memory.load_ram(0x2400, bytes([0x42, 0x00, 0x30]))
    machine.memory.write_byte(0x3000, 0x41)
    machine.memory.write_byte(0x1608, 0b10000000)
    machine.reset()
    machine.memory.write_byte(0xD403, 0x24)
    machine.memory.write_byte(0xD402, 0x00)
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF1), 0x0E)
    machine.memory.write_byte(int(GTIAWriteRegister.COLBK), 0x00)
    machine.memory.write_byte(0xD409, 0x14)
    machine.cpu.pc = 0x2000

    for _ in range(57):
        machine.step()

    assert machine.memory.read_byte(int(GTIAWriteRegister.COLPF1)) == 0x0E
    assert machine.gtia.framebuffer[0][0] == machine.gtia.color_to_rgb(0x0E)
