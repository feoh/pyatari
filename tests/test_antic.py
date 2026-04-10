"""Tests for the ANTIC core."""

from __future__ import annotations

from pyatari.antic import ANTIC
from pyatari.constants import (
    ANTICRegister,
    CYCLES_PER_SCANLINE,
    DL_DLI_BIT,
    DL_HSCROL_BIT,
    DL_LMS_BIT,
    DL_VSCROL_BIT,
    DMACTLBits,
    NMIBits,
    VBLANK_START_SCANLINE,
)
from pyatari.machine import Machine
from pyatari.memory import MemoryBus


def test_vcount_tracks_scanlines_divided_by_two():
    antic = ANTIC(memory=MemoryBus())

    antic.tick(CYCLES_PER_SCANLINE * 5)

    assert antic.read_register(ANTICRegister.VCOUNT) == 2


def test_fetch_display_list_line_parses_lms_and_mode_flags():
    memory = MemoryBus()
    antic = ANTIC(memory=memory)
    antic.display_list_pc = 0x2000
    memory.load_ram(0x2000, bytes([
        0x02 | DL_LMS_BIT | DL_DLI_BIT | DL_HSCROL_BIT | DL_VSCROL_BIT,
        0x34,
        0x12,
    ]))

    line = antic.fetch_next_display_list_line()

    assert line.mode == 0x02
    assert line.screen_address == 0x1234
    assert line.load_memory_scan is True
    assert line.dli is True
    assert line.hscroll is True
    assert line.vscroll is True


def test_fetch_display_list_line_handles_jump_and_jvb():
    memory = MemoryBus()
    antic = ANTIC(memory=memory)
    antic.display_list_pc = 0x2100
    memory.load_ram(0x2100, bytes([0x01, 0x78, 0x56, 0x41, 0x34, 0x12]))

    jmp = antic.fetch_next_display_list_line()
    assert jmp.jump_target == 0x5678
    assert jmp.wait_for_vblank is False
    assert antic.display_list_pc == 0x5678

    antic.display_list_pc = 0x2103
    jvb = antic.fetch_next_display_list_line()
    assert jvb.jump_target == 0x1234
    assert jvb.wait_for_vblank is True


def test_blank_instruction_scanline_count_is_decoded():
    antic = ANTIC(memory=MemoryBus())
    antic.display_list_pc = 0x2200
    antic.memory.load_ram(0x2200, bytes([0x30]))

    line = antic.fetch_next_display_list_line()

    assert line.mode is None
    assert line.scanlines == 4


def test_vbi_and_dli_set_nmist_bits():
    memory = MemoryBus()
    antic = ANTIC(memory=memory)
    antic.dmactl = 0x22  # enable DL DMA + normal playfield
    antic.nmien = int(NMIBits.DLI) | int(NMIBits.VBI)
    antic.display_list_pc = 0x2300
    memory.load_ram(0x2300, bytes([0x80, 0x40, 0x00, 0x20]))

    antic.step_scanline()
    assert antic.nmist & NMIBits.DLI

    antic.nmist = 0
    antic.scanline = VBLANK_START_SCANLINE - 1
    antic.current_line = None
    antic.current_line_remaining = 0
    antic.step_scanline()
    assert antic.nmist & NMIBits.VBI


def test_vbi_event_only_triggers_once_until_nmist_is_cleared():
    antic = ANTIC(memory=MemoryBus())
    antic.nmien = int(NMIBits.VBI)
    antic.scanline = VBLANK_START_SCANLINE - 1

    first_events = antic.tick(CYCLES_PER_SCANLINE)
    second_events = antic.tick(CYCLES_PER_SCANLINE)

    assert first_events.count("vbi") == 1
    assert "vbi" not in second_events


def test_enabling_nmien_with_latched_vbi_asserts_nmi_once():
    antic = ANTIC(memory=MemoryBus())
    antic.nmist = int(NMIBits.VBI)

    antic.write_register(int(ANTICRegister.NMIEN), int(NMIBits.VBI))

    assert antic.consume_nmi() is True
    assert antic.consume_nmi() is False


def test_wsync_request_is_consumed_by_machine_step():
    machine = Machine()
    machine.memory.write_word(0xFFFC, 0x2000)
    machine.memory.load_ram(0x2000, bytes([0xEA]))
    machine.reset()
    machine.memory.write_byte(0xD40A, 0x00)
    machine.cpu.pc = 0x2000
    machine.antic.cycles_into_scanline = 10

    machine.step()

    assert machine.antic.cycles_into_scanline == 2
    assert machine.clock.total_cycles == (CYCLES_PER_SCANLINE - 10) + 2


def test_machine_nmi_is_queued_from_antic_events():
    machine = Machine()
    machine.memory.write_word(0xFFFC, 0x2000)
    machine.memory.load_ram(0x2000, bytes([0xEA, 0xEA]))
    machine.reset()
    machine.cpu.pc = 0x2000
    machine.antic.dmactl = 0x22  # enable DL DMA
    machine.antic.nmien = int(NMIBits.DLI) | int(NMIBits.VBI)
    machine.antic.display_list_pc = 0x2400
    machine.memory.load_ram(0x2400, bytes([0x80]))
    machine.antic.cycles_into_scanline = CYCLES_PER_SCANLINE - 2

    machine.step()

    assert machine.cpu.nmi_pending is True


def test_machine_installs_antic_handlers():
    machine = Machine()

    machine.memory.write_byte(0xD402, 0x34)
    machine.memory.write_byte(0xD403, 0x12)
    machine.memory.write_byte(0xD40E, int(NMIBits.DLI | NMIBits.VBI))
    machine.memory.write_byte(0xD400, int(DMACTLBits.DL_DMA))

    assert machine.antic.dlist == 0x1234
    assert machine.memory.read_byte(0xD402) == 0x34
    assert machine.memory.read_byte(0xD40E) == int(NMIBits.DLI | NMIBits.VBI)
    assert machine.memory.read_byte(0xD400) == int(DMACTLBits.DL_DMA)
