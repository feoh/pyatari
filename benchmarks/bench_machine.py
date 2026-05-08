"""Full-machine and frame-level benchmarks."""

from __future__ import annotations

import pytest

from pyatari.constants import RESET_VECTOR
from pyatari.machine import Machine


@pytest.fixture
def frame_machine() -> Machine:
    """ROM-free machine filled with NOPs, configured for frame benchmarks."""
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.reset()
    machine.memory.load_ram(0x2000, bytes([0xEA] * 0x8000))
    machine.cpu.pc = 0x2000
    return machine


@pytest.fixture
def demo_frame_machine() -> Machine:
    """Machine with demo screen, used for realistic rendering benchmarks."""
    machine = Machine()
    machine.reset()
    machine.load_demo_screen()
    return machine


def test_bench_machine_step(benchmark: pytest.FixtureRequest, frame_machine: Machine) -> None:
    """machine.step() — full instruction cycle: CPU + ANTIC tick + POKEY tick + rendering."""
    benchmark(frame_machine.step)


def test_bench_machine_run_frame(
    benchmark: pytest.FixtureRequest, frame_machine: Machine
) -> None:
    """run_frame(queue_audio=False) — headline throughput benchmark.

    OPS value = frames/second the emulator can sustain.
    Real-time target is 60 FPS (one frame every ~16.7ms).
    """
    m = frame_machine

    def run() -> None:
        m.clock.reset()
        m.cpu.pc = 0x2000
        m.run_frame(queue_audio=False)

    benchmark(run)


def test_bench_machine_run_frame_with_audio(
    benchmark: pytest.FixtureRequest, frame_machine: Machine
) -> None:
    """run_frame(queue_audio=True) — measures audio sample generation overhead."""
    m = frame_machine

    def run() -> None:
        m.clock.reset()
        m.cpu.pc = 0x2000
        m.audio.buffers.clear()
        m.run_frame(queue_audio=True)

    benchmark(run)


def test_bench_machine_run_frame_demo(
    benchmark: pytest.FixtureRequest, demo_frame_machine: Machine
) -> None:
    """run_frame() with demo screen active — realistic frame including text rendering."""
    m = demo_frame_machine

    def run() -> None:
        m.clock.reset()
        m.cpu.pc = 0x2000
        m.run_frame(queue_audio=False)

    benchmark(run)


def test_bench_machine_10_frames(
    benchmark: pytest.FixtureRequest, frame_machine: Machine
) -> None:
    """10 consecutive frames — amortizes per-frame setup cost, measures sustained throughput."""
    m = frame_machine

    def run() -> None:
        m.clock.reset()
        m.cpu.pc = 0x2000
        for _ in range(10):
            m.run_frame(queue_audio=False)

    benchmark(run)
