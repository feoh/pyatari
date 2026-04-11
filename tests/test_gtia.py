"""Tests for the GTIA core and initial display rendering."""

from __future__ import annotations

from pyatari.antic import DisplayListLine
from pyatari.constants import CHACTLBits, GTIAReadRegister, GTIAWriteRegister, PORTBBits, RESET_VECTOR
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


def test_hitclr_preserves_input_registers():
    gtia = GTIA(memory=MemoryBus())
    gtia.set_console_switch(start=True)

    gtia.write_register(int(GTIAWriteRegister.HITCLR), 0x00)

    assert gtia.read_register(int(GTIAReadRegister.CONSOL)) == 0x06
    assert gtia.read_register(int(GTIAReadRegister.PAL)) == 0x01


def test_trig3_reflects_basic_rom_enable_flag():
    memory = MemoryBus()
    gtia = GTIA(memory=memory)

    assert gtia.read_register(int(GTIAReadRegister.TRIG3)) == 0x01

    memory.update_bank_config(memory.portb & ~int(PORTBBits.BASIC_ROM_ENABLE))

    assert gtia.read_register(int(GTIAReadRegister.TRIG3)) == 0x00


def test_color_to_rgb_changes_with_input():
    gtia = GTIA(memory=MemoryBus())

    dark = gtia.color_to_rgb(0x00)
    bright = gtia.color_to_rgb(0x0E)
    different_hue = gtia.color_to_rgb(0xAE)

    assert dark != bright
    assert dark != different_hue
    assert gtia.color_to_rgb(0x94) == gtia.color_to_rgb(0x95)


def test_color_to_rgb_maps_basic_blue_distinctly_from_black():
    gtia = GTIA(memory=MemoryBus())

    assert gtia.color_to_rgb(0x00) == 0x000000
    assert gtia.color_to_rgb(0x94) == 0x005088
    assert gtia.color_to_rgb(0x9A) == 0x007ED7


def test_render_scanline_mode_2_text_uses_hires_playfield_colors():
    memory = MemoryBus()
    gtia = GTIA(memory=memory)
    gtia.write_register(int(GTIAWriteRegister.COLPF1), 0xCA)
    gtia.write_register(int(GTIAWriteRegister.COLPF2), 0x94)
    memory.write_byte(0x3000, 0x41)
    memory.write_byte(0x1608, 0b10000000)  # simplified glyph row for char $41

    line = DisplayListLine(instruction_address=0x2000, instruction=0x42, mode=2, scanlines=8, screen_address=0x3000)
    gtia.render_scanline(line, row=0, antic_chbase=0x14)

    assert gtia.framebuffer[0][0] == gtia.color_to_rgb(0x9A)
    assert gtia.framebuffer[0][1] == gtia.color_to_rgb(0x94)
    assert gtia.framebuffer[0][DISPLAY_WIDTH - 1] == gtia.color_to_rgb(0x94)


def test_display_surface_copies_gtia_framebuffer():
    gtia = GTIA(memory=MemoryBus())
    gtia.framebuffer[0][0] = 0x123456

    surface = DisplaySurface()
    frame = surface.frame_from_gtia(gtia)
    frame[0][0] = 0

    assert gtia.framebuffer[0][0] == 0x123456


def test_render_scanline_inverse_text_uses_chactl():
    memory = MemoryBus()
    gtia = GTIA(memory=memory)
    gtia.write_register(int(GTIAWriteRegister.COLPF1), 0xCA)
    gtia.write_register(int(GTIAWriteRegister.COLPF2), 0x94)
    memory.write_byte(0x3000, 0xC1)
    memory.write_byte(0x1608, 0b10000000)

    line = DisplayListLine(instruction_address=0x2000, instruction=0x42, mode=2, scanlines=8, screen_address=0x3000)
    gtia.render_scanline(line, row=0, antic_chbase=0x14, antic_chactl=0)
    assert gtia.framebuffer[0][0] == gtia.color_to_rgb(0x94)
    assert gtia.framebuffer[0][1] == gtia.color_to_rgb(0x9A)

    gtia.render_scanline(line, row=1, antic_chbase=0x14, antic_chactl=int(CHACTLBits.INVERSE))
    assert gtia.framebuffer[1][0] == gtia.color_to_rgb(0x94)
    assert gtia.framebuffer[1][1] == gtia.color_to_rgb(0x94)



def test_render_scanline_mode_6_double_width_and_chbase_switching():
    memory = MemoryBus()
    gtia = GTIA(memory=memory)
    gtia.write_register(int(GTIAWriteRegister.COLPF2), 0x2E)
    gtia.write_register(int(GTIAWriteRegister.COLPF0), 0x00)
    memory.write_byte(0x3100, 0x41)
    memory.write_byte(0x1608, 0b10000000)
    memory.write_byte(0x2609, 0b01000000)

    line = DisplayListLine(instruction_address=0x2000, instruction=0x46, mode=6, scanlines=8, screen_address=0x3100)
    gtia.render_scanline(line, row=0, antic_chbase=0x14)
    first_base = gtia.framebuffer[0][0]
    second_base = gtia.framebuffer[0][2]

    gtia.render_scanline(line, row=1, antic_chbase=0x24)

    assert first_base == gtia.color_to_rgb(0x2E)
    assert second_base == gtia.color_to_rgb(0x00)
    assert gtia.framebuffer[1][0] == gtia.color_to_rgb(0x00)
    assert gtia.framebuffer[1][2] == gtia.color_to_rgb(0x2E)



def test_render_scanline_bitmap_mode_8_uses_playfield_colors():
    memory = MemoryBus()
    gtia = GTIA(memory=memory)
    gtia.write_register(int(GTIAWriteRegister.COLBK), 0x00)
    gtia.write_register(int(GTIAWriteRegister.COLPF0), 0x12)
    gtia.write_register(int(GTIAWriteRegister.COLPF1), 0x24)
    gtia.write_register(int(GTIAWriteRegister.COLPF2), 0x36)
    memory.write_byte(0x3200, 0b00011011)

    line = DisplayListLine(instruction_address=0x2000, instruction=0x48, mode=8, scanlines=8, screen_address=0x3200)
    gtia.render_scanline(line, row=0)

    assert gtia.framebuffer[0][0] == gtia.color_to_rgb(0x00)
    assert gtia.framebuffer[0][9] == gtia.color_to_rgb(0x12)
    assert gtia.framebuffer[0][18] == gtia.color_to_rgb(0x24)
    assert gtia.framebuffer[0][27] == gtia.color_to_rgb(0x36)


def test_render_scanline_bitmap_mode_15_uses_hires_playfield_colors():
    memory = MemoryBus()
    gtia = GTIA(memory=memory)
    gtia.write_register(int(GTIAWriteRegister.COLPF1), 0xCA)
    gtia.write_register(int(GTIAWriteRegister.COLPF2), 0x94)
    memory.write_byte(0x3200, 0b10000000)

    line = DisplayListLine(instruction_address=0x2000, instruction=0x4F, mode=15, scanlines=1, screen_address=0x3200)
    gtia.render_scanline(line, row=0)

    assert gtia.framebuffer[0][0] == gtia.color_to_rgb(0x9A)
    assert gtia.framebuffer[0][1] == gtia.color_to_rgb(0x94)



def test_player_rendering_respects_position_and_size():
    gtia = GTIA(memory=MemoryBus())
    gtia.render_player(0, xpos=10, graphics=0b10000000, size=1, color=0x2E)

    assert gtia.player_dma[0][10] == gtia.color_to_rgb(0x2E)
    assert gtia.player_dma[0][11] == gtia.color_to_rgb(0x2E)
    assert gtia.player_dma[0][12] == 0



def test_missile_rendering_and_collision_registers():
    gtia = GTIA(memory=MemoryBus())
    gtia.write_register(int(GTIAWriteRegister.COLBK), 0x00)
    gtia._fill_row(0, 0x12)
    gtia.render_missiles(xpos=[4, 0, 0, 0], graphics=0b0001, size_mask=0, color=0x3A)
    gtia._overlay_player_missile_graphics(0)

    assert gtia.framebuffer[0][4] == gtia.color_to_rgb(0x3A)
    assert gtia.read_register(int(GTIAReadRegister.M0PF)) == 0x0F



def test_machine_installs_gtia_handlers_and_renders_visible_line():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.memory.load_ram(0x2000, bytes([0xEA] * 57))
    machine.memory.load_ram(0x2400, bytes([0x42, 0x00, 0x30]))
    machine.memory.write_byte(0x3000, 0x41)
    machine.memory.write_byte(0x1608, 0b10000000)
    machine.reset()
    machine.memory.write_byte(0xD400, 0x22)  # enable DL DMA + normal playfield
    machine.memory.write_byte(0xD403, 0x24)
    machine.memory.write_byte(0xD402, 0x00)
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF1), 0x0E)
    machine.memory.write_byte(int(GTIAWriteRegister.COLBK), 0x00)
    machine.memory.write_byte(0xD409, 0x14)
    machine.memory.write_byte(0xD000, 8)
    machine.memory.write_byte(0xD00D, 0b10000000)
    machine.memory.write_byte(0xD008, 0)
    machine.memory.write_byte(0xD012, 0x3A)
    machine.cpu.pc = 0x2000

    for _ in range(57):
        machine.step()

    assert machine.memory.read_byte(int(GTIAWriteRegister.COLPF1)) == 0x0E
    assert machine.gtia.framebuffer[0][0] == machine.gtia.color_to_rgb(0x0E)
    assert machine.gtia.framebuffer[0][8] == machine.gtia.color_to_rgb(0x3A)
