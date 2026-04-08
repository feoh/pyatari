"""Integration harness for Klaus Dormann's 6502 functional test."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyatari.cpu import CPU, StatusRegister
from pyatari.memory import MemoryBus

KLAUS_START_PC = 0x0400
KLAUS_SUCCESS_PC = 0x3469
KLAUS_MAX_STEPS = 35_000_000
KLAUS_ROM = Path(__file__).parent / "roms" / "6502_functional_test.bin"


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("PYATARI_RUN_KLAUS") != "1",
    reason="Set PYATARI_RUN_KLAUS=1 to run the Klaus 6502 functional suite",
)
def test_klaus_dormann_functional_suite_reaches_success_loop():
    memory = MemoryBus()
    memory.load_ram(0x0000, KLAUS_ROM.read_bytes())

    cpu = CPU(memory=memory)
    cpu.pc = KLAUS_START_PC
    cpu.sp = 0xFD
    cpu.status = StatusRegister(reserved=True)

    previous_pc: int | None = None
    repeated_pc = 0

    for _ in range(KLAUS_MAX_STEPS):
        if cpu.pc == KLAUS_SUCCESS_PC:
            return

        if cpu.pc == previous_pc:
            repeated_pc += 1
        else:
            previous_pc = cpu.pc
            repeated_pc = 0

        if repeated_pc > 1000:
            pytest.fail(f"CPU appears trapped in a self-loop at PC={cpu.pc:#06x}")

        cpu.step()

    pytest.fail(
        "Klaus functional test did not reach the success loop within "
        f"{KLAUS_MAX_STEPS:,} instructions; last PC={cpu.pc:#06x}"
    )
