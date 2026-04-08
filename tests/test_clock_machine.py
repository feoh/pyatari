"""Tests for the master clock and initial machine integration."""

from __future__ import annotations

from pyatari.clock import MasterClock
from pyatari.constants import CYCLES_PER_FRAME, CYCLES_PER_SCANLINE, IRQ_VECTOR, NMI_VECTOR, RESET_VECTOR, VBLANK_START_SCANLINE
from pyatari.machine import Machine


def test_master_clock_tracks_scanlines_frames_and_vblank():
    clock = MasterClock()

    clock.tick(CYCLES_PER_SCANLINE - 1)
    assert clock.scanline == 0
    assert clock.cycle_in_scanline == CYCLES_PER_SCANLINE - 1
    assert not clock.in_vblank

    clock.tick(1)
    assert clock.scanline == 1
    assert clock.cycle_in_scanline == 0

    clock.tick(CYCLES_PER_SCANLINE * (VBLANK_START_SCANLINE - 1))
    assert clock.scanline == VBLANK_START_SCANLINE
    assert clock.in_vblank

    remaining = CYCLES_PER_FRAME - clock.cycle_in_frame
    clock.tick(remaining)
    assert clock.frame == 1
    assert clock.scanline == 0
    assert clock.cycle_in_scanline == 0
    assert not clock.in_vblank


def test_machine_reset_loads_reset_vector():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x1234)

    machine.reset()

    assert machine.cpu.pc == 0x1234
    assert machine.clock.total_cycles == 0


def test_cpu_nmi_pushes_pc_and_jumps_to_vector():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.memory.write_word(NMI_VECTOR, 0x3456)
    machine.reset()
    machine.cpu.pc = 0x2345

    machine.cpu.nmi()
    opcode = machine.step()

    assert opcode.mnemonic == "INT"
    assert machine.cpu.pc == 0x3456
    assert machine.cpu.status.interrupt_disable is True
    assert machine.cpu.sp == 0xFA
    assert machine.memory.read_byte(0x01FD) == 0x23
    assert machine.memory.read_byte(0x01FC) == 0x45
    assert machine.memory.read_byte(0x01FB) & 0x10 == 0
    assert machine.clock.total_cycles == 7


def test_cpu_irq_respects_mask_and_jumps_when_enabled():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.memory.write_word(IRQ_VECTOR, 0x4567)
    machine.memory.load_ram(0x2000, bytes([0xEA]))  # NOP
    machine.reset()
    machine.cpu.pc = 0x2000

    machine.cpu.status.interrupt_disable = True
    machine.cpu.irq()
    machine.step()
    assert machine.cpu.pc == 0x2001

    machine.cpu.pc = 0x2000
    machine.cpu.status.interrupt_disable = False
    machine.cpu.irq()
    opcode = machine.step()

    assert opcode.mnemonic == "INT"
    assert machine.cpu.pc == 0x4567
    assert machine.clock.total_cycles == 9  # NOP (2) + IRQ (7)


def test_machine_run_until_and_run_frame():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x3000)
    machine.memory.load_ram(0x3000, bytes([0xEA, 0xEA, 0xEA]))
    machine.reset()

    steps = machine.run_until(0x3002)
    assert steps == 2
    assert machine.cpu.pc == 0x3002
    assert machine.clock.total_cycles == 4

    machine.memory.load_ram(0x3002, bytes([0xEA] * 0x8000))
    frame_steps = machine.run_frame()
    assert frame_steps > 0
    assert machine.clock.total_cycles >= CYCLES_PER_FRAME
