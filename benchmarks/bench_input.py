"""User input pipeline benchmarks."""

from __future__ import annotations

import pytest

from pyatari.constants import FRAMES_PER_SECOND, RESET_VECTOR
from pyatari.machine import Machine

_SAMPLES_PER_FRAME = 44_100 // FRAMES_PER_SECOND


@pytest.fixture
def input_machine() -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.reset()
    machine.memory.load_ram(0x2000, bytes([0xEA] * 0x8000))
    machine.cpu.pc = 0x2000
    return machine


def test_bench_press_key_a(benchmark: pytest.FixtureRequest, input_machine: Machine) -> None:
    """machine.press_key('a') — full path: Machine → KEYCODE_MAP lookup → POKEY register update."""
    benchmark(input_machine.press_key, "a")


def test_bench_release_key(benchmark: pytest.FixtureRequest, input_machine: Machine) -> None:
    """machine.release_key() — restores POKEY KBCODE/SKSTAT, clears key-down state."""
    benchmark(input_machine.release_key)


def test_bench_set_joystick_direction(
    benchmark: pytest.FixtureRequest, input_machine: Machine
) -> None:
    """machine.set_joystick(up=True) — bit-mask update through PIA joystick state."""
    benchmark(input_machine.set_joystick, up=True)


def test_bench_set_joystick_neutral(
    benchmark: pytest.FixtureRequest, input_machine: Machine
) -> None:
    """machine.set_joystick() with no direction — idle joystick poll cost."""
    benchmark(input_machine.set_joystick)


def test_bench_set_trigger(benchmark: pytest.FixtureRequest, input_machine: Machine) -> None:
    """machine.set_trigger(True) — fire button path through GTIA trigger register."""
    benchmark(input_machine.set_trigger, True)


def test_bench_pokey_tick_scanline(
    benchmark: pytest.FixtureRequest, input_machine: Machine
) -> None:
    """pokey.tick(114) — one scanline of timer advancement, IRQ evaluation, serial events."""
    benchmark(input_machine.pokey.tick, 114)


def test_bench_pokey_generate_samples(
    benchmark: pytest.FixtureRequest, input_machine: Machine
) -> None:
    """pokey.generate_samples(735) — one frame of 44.1kHz audio synthesis (all 4 channels)."""
    benchmark(input_machine.pokey.generate_samples, _SAMPLES_PER_FRAME)
