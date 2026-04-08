"""Tests for the POKEY core."""

from __future__ import annotations

from pyatari.audio import AudioOutput
from pyatari.constants import IRQBits, POKEYReadRegister, POKEYWriteRegister, RESET_VECTOR
from pyatari.machine import Machine
from pyatari.memory import MemoryBus
from pyatari.pokey import POKEY


def test_timer_countdown_sets_irq_status_when_enabled():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(int(POKEYWriteRegister.AUDF1), 2)
    pokey.write_register(int(POKEYWriteRegister.IRQEN), int(IRQBits.TIMER1))
    pokey.write_register(int(POKEYWriteRegister.STIMER), 0)

    irq = pokey.tick(3)

    assert irq is True
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.TIMER1) == 0


def test_keyboard_code_and_irq_state_changes_on_press_and_release():
    pokey = POKEY(memory=MemoryBus())

    pokey.press_key(0x3F)
    assert pokey.read_register(int(POKEYReadRegister.KBCODE)) == 0x3F
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.KEYBOARD) == 0

    pokey.release_key()
    assert pokey.read_register(int(POKEYReadRegister.KBCODE)) == 0xFF
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.KEYBOARD)


def test_random_register_varies_between_reads():
    pokey = POKEY(memory=MemoryBus())

    first = pokey.read_register(int(POKEYReadRegister.RANDOM))
    second = pokey.read_register(int(POKEYReadRegister.RANDOM))

    assert first != second


def test_audctl_16bit_timer_pair_uses_combined_period():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(int(POKEYWriteRegister.AUDF1), 0x34)
    pokey.write_register(int(POKEYWriteRegister.AUDF2), 0x12)
    pokey.write_register(int(POKEYWriteRegister.AUDCTL), 0x10)
    pokey.write_register(int(POKEYWriteRegister.STIMER), 0)

    assert pokey.timers[0].reload_value == 0x1235


def test_channel_frequency_and_volume_reflect_registers():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(int(POKEYWriteRegister.AUDF1), 3)
    pokey.write_register(int(POKEYWriteRegister.AUDC1), 0x0F)

    assert pokey.channel_frequency(0) == 63_921.0 / 4
    assert pokey.channel_volume(0) == 1.0



def test_generate_samples_produces_square_wave_levels():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(int(POKEYWriteRegister.AUDF1), 0)
    pokey.write_register(int(POKEYWriteRegister.AUDC1), 0x0F)

    samples = pokey.generate_samples(8, sample_rate=4)

    assert len(samples) == 8
    assert max(samples) <= 1.0
    assert min(samples) >= -1.0
    assert any(sample > 0 for sample in samples)
    assert any(sample < 0 for sample in samples)



def test_audio_output_queues_samples_from_pokey():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(int(POKEYWriteRegister.AUDC1), 0x0F)
    audio = AudioOutput(sample_rate=8)

    samples = audio.queue_from_pokey(pokey, 4)

    assert len(samples) == 4
    assert audio.buffers[-1] == samples



def test_machine_installs_pokey_handlers_and_queues_irq():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.memory.load_ram(0x2000, bytes([0xEA] * 2))
    machine.reset()
    machine.cpu.pc = 0x2000
    machine.memory.write_byte(int(POKEYWriteRegister.AUDF1), 1)
    machine.memory.write_byte(int(POKEYWriteRegister.IRQEN), int(IRQBits.TIMER1))
    machine.memory.write_byte(int(POKEYWriteRegister.STIMER), 0)

    machine.step()

    assert machine.cpu.irq_pending is True
    assert machine.memory.read_byte(int(POKEYReadRegister.IRQST)) & int(IRQBits.TIMER1) == 0
