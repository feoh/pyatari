"""Tests for the POKEY core."""

from __future__ import annotations

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
