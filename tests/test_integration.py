"""Integration tests for Phase 16 machine boot and frame flow."""

from __future__ import annotations

from pyatari.constants import CYCLES_PER_FRAME, FRAMES_PER_SECOND, RESET_VECTOR
from pyatari.machine import Machine
from pyatari.sio import create_test_xex


def make_machine() -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.reset()
    return machine


def test_run_frame_advances_clock_and_queues_audio():
    machine = make_machine()
    machine.memory.load_ram(0x2000, bytes([0xEA] * 0x9000))
    machine.cpu.pc = 0x2000

    steps = machine.run_frame()

    assert steps > 0
    assert machine.clock.total_cycles >= CYCLES_PER_FRAME
    assert len(machine.audio.buffers) == 1
    assert len(machine.audio.buffers[0]) == machine.audio.sample_rate // FRAMES_PER_SECOND


def test_status_reports_runtime_fields_and_turbo():
    machine = make_machine()
    machine.set_turbo(True)

    status = machine.status()

    assert status.pc == machine.cpu.pc
    assert status.scanline == machine.clock.scanline
    assert status.frame == machine.clock.frame
    assert status.fps == FRAMES_PER_SECOND
    assert status.turbo is True


def test_boot_xex_loads_and_runs_to_run_address_without_roms():
    machine = make_machine()
    xex = create_test_xex((0x2400, b"\xEA\xEA\xEA"), run_address=0x2400)

    steps = machine.boot_xex(xex)

    assert steps == 0
    assert machine.cpu.pc == 0x2400
    assert machine.memory.read_byte(0x2400) == 0xEA


def test_run_program_executes_rom_free_machine_code():
    machine = make_machine()

    pc = machine.run_program(bytes([0xE8, 0xE8, 0xEA]), start=0x2800, steps=2)

    assert pc == 0x2802
    assert machine.cpu.x == 2
