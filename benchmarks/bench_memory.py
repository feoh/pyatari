"""Memory bus read/write benchmarks."""

from __future__ import annotations

import pytest

from pyatari.constants import RESET_VECTOR
from pyatari.machine import Machine

# A plain RAM address with no handler registered
_RAM_ADDRESS = 0x0300
# Hardware register address (GTIA COLBK — in the 0xD000-0xD01F range)
_HW_READ_ADDRESS = 0xD01B   # GTIAReadRegister.CONSOL
_HW_WRITE_ADDRESS = 0xD01A  # GTIAWriteRegister.COLBK


@pytest.fixture
def mem_machine() -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.reset()
    return machine


def test_bench_memory_read_ram(benchmark: pytest.FixtureRequest, mem_machine: Machine) -> None:
    """read_byte() on a plain RAM address — no handler, no ROM overlay."""
    m = mem_machine
    benchmark(m.memory.read_byte, _RAM_ADDRESS)


def test_bench_memory_write_ram(benchmark: pytest.FixtureRequest, mem_machine: Machine) -> None:
    """write_byte() on a plain RAM address — direct bytearray write."""
    m = mem_machine
    benchmark(m.memory.write_byte, _RAM_ADDRESS, 0x42)


def test_bench_memory_read_hardware_register(
    benchmark: pytest.FixtureRequest, mem_machine: Machine
) -> None:
    """read_byte() on a hardware register — exercises dict-lookup dispatch."""
    m = mem_machine
    benchmark(m.memory.read_byte, _HW_READ_ADDRESS)


def test_bench_memory_write_hardware_register(
    benchmark: pytest.FixtureRequest, mem_machine: Machine
) -> None:
    """write_byte() on a hardware register — exercises dict-lookup dispatch + handler call."""
    m = mem_machine
    benchmark(m.memory.write_byte, _HW_WRITE_ADDRESS, 0x28)


def test_bench_memory_read_word(benchmark: pytest.FixtureRequest, mem_machine: Machine) -> None:
    """read_word() — two sequential read_byte() calls."""
    m = mem_machine
    benchmark(m.memory.read_word, _RAM_ADDRESS)
