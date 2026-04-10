"""Tests for the POKEY core."""

from __future__ import annotations

from pyatari.audio import AudioOutput
from pyatari.constants import (
    AUDCTLBits,
    IRQBits,
    POKEYReadRegister,
    POKEYWriteRegister,
    RESET_VECTOR,
    SKCTLBits,
    SKSTATBits,
)
from pyatari.machine import Machine
from pyatari.memory import MemoryBus
from pyatari.pokey import (
    CPU_CYCLES_PER_SERIAL_BYTE,
    CPU_CYCLES_PER_POKEY_15KHZ_TICK,
    CPU_CYCLES_PER_POKEY_64KHZ_TICK,
    POKEY,
)


def test_timer_countdown_sets_irq_status_when_enabled():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(int(POKEYWriteRegister.AUDF1), 2)
    pokey.write_register(int(POKEYWriteRegister.IRQEN), int(IRQBits.TIMER1))
    pokey.write_register(int(POKEYWriteRegister.STIMER), 0)

    irq = pokey.tick(3 * CPU_CYCLES_PER_POKEY_64KHZ_TICK)

    assert irq is True
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.TIMER1) == 0


def test_keyboard_code_and_irq_state_changes_on_press_and_release():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(
        int(POKEYWriteRegister.SKCTL),
        int(SKCTLBits.KEYBOARD_SCAN | SKCTLBits.KEYBOARD_DEBOUNCE),
    )

    assert pokey.press_key(0x3F) is False
    assert pokey.read_register(int(POKEYReadRegister.KBCODE)) == 0x3F
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.KEYBOARD) == 0
    assert pokey.read_register(int(POKEYReadRegister.SKSTAT)) & int(SKSTATBits.KEY_DOWN) == 0

    pokey.release_key()
    assert pokey.read_register(int(POKEYReadRegister.KBCODE)) == 0x3F
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.KEYBOARD)
    assert pokey.read_register(int(POKEYReadRegister.SKSTAT)) & int(SKSTATBits.KEY_DOWN)


def test_keyboard_scan_must_be_enabled_to_report_keypress():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(int(POKEYWriteRegister.IRQEN), int(IRQBits.KEYBOARD))

    assert pokey.press_key(0x3F) is False
    assert pokey.read_register(int(POKEYReadRegister.KBCODE)) == 0xFF
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.KEYBOARD)
    assert pokey.read_register(int(POKEYReadRegister.SKSTAT)) & int(SKSTATBits.KEY_DOWN)


def test_keyboard_press_requests_irq_when_enabled():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(
        int(POKEYWriteRegister.SKCTL),
        int(SKCTLBits.KEYBOARD_SCAN | SKCTLBits.KEYBOARD_DEBOUNCE),
    )
    pokey.write_register(int(POKEYWriteRegister.IRQEN), int(IRQBits.KEYBOARD))

    assert pokey.press_key(0x3F) is True


def test_serial_output_schedules_need_irq_before_done_irq():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(
        int(POKEYWriteRegister.IRQEN),
        int(IRQBits.SERIAL_OUT_NEED),
    )
    pokey.write_register(int(POKEYWriteRegister.SEROUT), 0x55)

    irq = pokey.tick(CPU_CYCLES_PER_SERIAL_BYTE)

    assert irq is True
    irqst = pokey.read_register(int(POKEYReadRegister.IRQST))
    assert irqst & int(IRQBits.SERIAL_OUT_NEED) == 0
    assert irqst & int(IRQBits.SERIAL_OUT_DONE)

    pokey.write_register(
        int(POKEYWriteRegister.IRQEN),
        int(IRQBits.SERIAL_OUT_DONE),
    )
    irq = pokey.tick(CPU_CYCLES_PER_SERIAL_BYTE)

    assert irq is True
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.SERIAL_OUT_DONE) == 0


def test_queue_serial_input_sets_serin_skstat_and_irq():
    pokey = POKEY(memory=MemoryBus())
    pokey.write_register(
        int(POKEYWriteRegister.IRQEN),
        int(IRQBits.SERIAL_IN_DONE),
    )
    pokey.queue_serial_input(0x41, skstat=0x00)

    irq = pokey.tick(CPU_CYCLES_PER_SERIAL_BYTE)

    assert irq is True
    assert pokey.read_register(int(POKEYReadRegister.SERIN)) == 0x41
    assert pokey.read_register(int(POKEYReadRegister.SKSTAT)) == 0x00
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.SERIAL_IN_DONE) == 0


def test_serial_input_event_latches_until_irq_is_enabled():
    pokey = POKEY(memory=MemoryBus())
    pokey.queue_serial_input(0x41, skstat=0x00)

    irq = pokey.tick(CPU_CYCLES_PER_SERIAL_BYTE)

    assert irq is False
    assert len(pokey.serial_events) == 1
    assert pokey.read_register(int(POKEYReadRegister.SERIN)) == 0x00
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.SERIAL_IN_DONE)

    pokey.write_register(
        int(POKEYWriteRegister.IRQEN),
        int(IRQBits.SERIAL_IN_DONE),
    )
    irq = pokey.tick(1)

    assert irq is True
    assert pokey.read_register(int(POKEYReadRegister.SERIN)) == 0x41
    assert pokey.read_register(int(POKEYReadRegister.SKSTAT)) == 0x00
    assert pokey.read_register(int(POKEYReadRegister.IRQST)) & int(IRQBits.SERIAL_IN_DONE) == 0
    assert pokey.serial_events == []


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


def test_timer_clock_divider_uses_15khz_and_179mhz_modes():
    pokey = POKEY(memory=MemoryBus())

    pokey.write_register(int(POKEYWriteRegister.AUDCTL), int(AUDCTLBits.CLOCK_15KHZ))
    assert pokey._timer_clock_divider(0) == CPU_CYCLES_PER_POKEY_15KHZ_TICK

    pokey.write_register(int(POKEYWriteRegister.AUDCTL), int(AUDCTLBits.CH1_179MHZ))
    assert pokey._timer_clock_divider(0) == 1


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

    for _ in range(40):
        machine.step()
        if machine.cpu.irq_pending:
            break

    assert machine.cpu.irq_pending is True
    assert machine.memory.read_byte(int(POKEYReadRegister.IRQST)) & int(IRQBits.TIMER1) == 0


def test_machine_queues_irq_for_serial_output_events():
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.memory.load_ram(0x2000, bytes([0xEA] * 8))
    machine.reset()
    machine.cpu.pc = 0x2000
    machine.memory.write_byte(
        int(POKEYWriteRegister.IRQEN),
        int(IRQBits.SERIAL_OUT_NEED | IRQBits.SERIAL_OUT_DONE),
    )
    machine.memory.write_byte(int(POKEYWriteRegister.SEROUT), 0x55)

    for _ in range(160):
        machine.step()
        if machine.cpu.irq_pending:
            break

    assert machine.cpu.irq_pending is True
