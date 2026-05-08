"""Shared fixtures for pyatari benchmarks."""

from __future__ import annotations

import pytest

from pyatari.constants import RESET_VECTOR
from pyatari.machine import Machine


@pytest.fixture
def bare_machine() -> Machine:
    """ROM-free machine filled with NOPs, PC at 0x2000."""
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.reset()
    machine.memory.load_ram(0x2000, bytes([0xEA] * 0x8000))
    machine.cpu.pc = 0x2000
    return machine


@pytest.fixture
def demo_machine() -> Machine:
    """Machine with demo screen loaded and one frame pre-rendered."""
    machine = Machine()
    machine.reset()
    machine.load_demo_screen()
    machine.run_frame(queue_audio=False)
    return machine
