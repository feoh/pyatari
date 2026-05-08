"""CPU instruction execution benchmarks."""

from __future__ import annotations

import pytest

from pyatari.constants import RESET_VECTOR
from pyatari.machine import Machine


def _machine_with_program(program: bytes, *, start: int = 0x2000) -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, start)
    machine.reset()
    # Pad with NOPs so execution never falls off the end during benchmarking
    machine.memory.load_ram(start, program + bytes([0xEA] * 0x7000))
    machine.cpu.pc = start
    return machine


@pytest.fixture
def nop_machine() -> Machine:
    # 0xEA = NOP
    return _machine_with_program(bytes([0xEA]))


@pytest.fixture
def lda_imm_machine() -> Machine:
    # LDA #$42
    return _machine_with_program(bytes([0xA9, 0x42]))


@pytest.fixture
def sta_zp_machine() -> Machine:
    # STA $10
    return _machine_with_program(bytes([0x85, 0x10]))


@pytest.fixture
def branch_taken_machine() -> Machine:
    # CLC; BCC -2 (backward branch, same page, always taken → tight loop)
    # $18 = CLC, $90 = BCC, $FE = -2 offset
    return _machine_with_program(bytes([0x18, 0x90, 0xFE]))


@pytest.fixture
def jmp_machine() -> Machine:
    # JMP $2000 (jump back to self)
    return _machine_with_program(bytes([0x4C, 0x00, 0x20]))


@pytest.fixture
def bulk_machine() -> Machine:
    return _machine_with_program(bytes([0xEA] * 0x7000))


def test_bench_cpu_step_nop(benchmark: pytest.FixtureRequest, nop_machine: Machine) -> None:
    """Baseline: single NOP instruction — measures raw step() dispatch overhead."""
    m = nop_machine
    benchmark(m.cpu.step)


def test_bench_cpu_step_lda_immediate(
    benchmark: pytest.FixtureRequest, lda_imm_machine: Machine
) -> None:
    """LDA #imm — load immediate: fetch + decode + execute + cycle update."""
    m = lda_imm_machine
    benchmark(m.cpu.step)


def test_bench_cpu_step_sta_zeropage(
    benchmark: pytest.FixtureRequest, sta_zp_machine: Machine
) -> None:
    """STA $zp — zero page write: measures memory write path cost."""
    m = sta_zp_machine
    benchmark(m.cpu.step)


def test_bench_cpu_step_branch_taken(
    benchmark: pytest.FixtureRequest, branch_taken_machine: Machine
) -> None:
    """BCC taken (same page) — measures branch resolution cost."""
    m = branch_taken_machine
    benchmark(m.cpu.step)


def test_bench_cpu_step_jmp_absolute(
    benchmark: pytest.FixtureRequest, jmp_machine: Machine
) -> None:
    """JMP abs — absolute jump: measures 3-byte decode + PC update."""
    m = jmp_machine
    benchmark(m.cpu.step)


def test_bench_cpu_1000_steps(benchmark: pytest.FixtureRequest, bulk_machine: Machine) -> None:
    """1000 consecutive NOPs — bulk throughput, measures per-step overhead at scale."""
    m = bulk_machine

    def run() -> None:
        m.cpu.pc = 0x2000
        m.run_steps(1000)

    benchmark(run)
