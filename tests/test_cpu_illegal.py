"""Tests for common undocumented 6502 opcodes."""

from __future__ import annotations

from pyatari.constants import RESET_VECTOR
from pyatari.machine import Machine


def make_machine(program: bytes, start: int = 0x2000) -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, start)
    machine.memory.load_ram(start, program)
    machine.reset()
    machine.cpu.pc = start
    return machine


def test_lax_loads_a_and_x_together():
    machine = make_machine(bytes([0xA7, 0x10]))
    machine.memory.write_byte(0x0010, 0x42)

    machine.step()

    assert machine.cpu.a == 0x42
    assert machine.cpu.x == 0x42


def test_sax_stores_a_and_x_and_masked_together():
    machine = make_machine(bytes([0x87, 0x20]))
    machine.cpu.a = 0xCC
    machine.cpu.x = 0xAA

    machine.step()

    assert machine.memory.read_byte(0x0020) == 0x88


def test_dcp_decrements_memory_then_compares_against_a():
    machine = make_machine(bytes([0xC7, 0x30]))
    machine.cpu.a = 0x20
    machine.memory.write_byte(0x0030, 0x20)

    machine.step()

    assert machine.memory.read_byte(0x0030) == 0x1F
    assert machine.cpu.status.carry is True
    assert machine.cpu.status.zero is False


def test_isb_increments_memory_then_subtracts_from_a():
    machine = make_machine(bytes([0xE7, 0x40]))
    machine.cpu.a = 0x20
    machine.cpu.status.carry = True
    machine.memory.write_byte(0x0040, 0x05)

    machine.step()

    assert machine.memory.read_byte(0x0040) == 0x06
    assert machine.cpu.a == 0x1A


def test_slo_shifts_then_ors_into_a():
    machine = make_machine(bytes([0x07, 0x50]))
    machine.cpu.a = 0x01
    machine.memory.write_byte(0x0050, 0x81)

    machine.step()

    assert machine.memory.read_byte(0x0050) == 0x02
    assert machine.cpu.a == 0x03
    assert machine.cpu.status.carry is True


def test_rla_rotates_then_ands_into_a():
    machine = make_machine(bytes([0x27, 0x60]))
    machine.cpu.a = 0xF0
    machine.cpu.status.carry = True
    machine.memory.write_byte(0x0060, 0x80)

    machine.step()

    assert machine.memory.read_byte(0x0060) == 0x01
    assert machine.cpu.a == 0x00
    assert machine.cpu.status.zero is True


def test_sre_shifts_then_xors_into_a():
    machine = make_machine(bytes([0x47, 0x70]))
    machine.cpu.a = 0x0F
    machine.memory.write_byte(0x0070, 0x03)

    machine.step()

    assert machine.memory.read_byte(0x0070) == 0x01
    assert machine.cpu.a == 0x0E
    assert machine.cpu.status.carry is True


def test_rra_rotates_then_adds_into_a():
    machine = make_machine(bytes([0x67, 0x80]))
    machine.cpu.a = 0x10
    machine.cpu.status.carry = False
    machine.memory.write_byte(0x0080, 0x02)

    machine.step()

    assert machine.memory.read_byte(0x0080) == 0x01
    assert machine.cpu.a == 0x11
    assert machine.cpu.status.carry is False
