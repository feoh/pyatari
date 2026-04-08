"""Tests for the Atari PIA implementation."""

from __future__ import annotations

from pyatari.constants import JoystickBits, PIARegister, PORTBBits
from pyatari.machine import Machine
from pyatari.memory import MemoryBus
from pyatari.pia import DDR_ACCESS_BIT, PIA


def test_porta_ddr_and_data_selection():
    pia = PIA(memory=MemoryBus())

    pia.write_register(PIARegister.PACTL, 0x00)
    pia.write_register(PIARegister.PORTA, 0x0F)
    assert pia.porta_ddr == 0x0F
    assert pia.read_register(PIARegister.PORTA) == 0x0F

    pia.write_register(PIARegister.PACTL, DDR_ACCESS_BIT)
    pia.write_register(PIARegister.PORTA, 0x05)
    assert pia.porta_output == 0x05
    assert pia.read_register(PIARegister.PORTA) == 0xF5


def test_joystick_bits_are_active_low_on_porta():
    pia = PIA(memory=MemoryBus())

    pia.press_joystick(JoystickBits.STICK0_UP, JoystickBits.STICK1_LEFT)

    value = pia.read_register(PIARegister.PORTA)
    assert value & JoystickBits.STICK0_UP == 0
    assert value & JoystickBits.STICK1_LEFT == 0
    assert value & JoystickBits.STICK0_DOWN

    pia.release_joystick(JoystickBits.STICK0_UP, JoystickBits.STICK1_LEFT)
    assert pia.read_register(PIARegister.PORTA) == 0xFF


def test_portb_writes_update_memory_bank_config():
    memory = MemoryBus()
    pia = PIA(memory=memory)

    pia.write_register(PIARegister.PORTB, int(PORTBBits.OS_ROM_ENABLE | PORTBBits.SELF_TEST_ENABLE))

    assert memory.portb == int(PORTBBits.OS_ROM_ENABLE | PORTBBits.SELF_TEST_ENABLE)


def test_pia_registers_are_mirrored_every_four_bytes():
    memory = MemoryBus()
    pia = PIA(memory=memory)
    pia.install()

    memory.write_byte(0xD301, 0x00)
    memory.write_byte(0xD304, 0xAA)

    assert pia.porta_ddr == 0xAA
    assert memory.read_byte(0xD308) == 0xAA


def test_machine_installs_pia_handlers():
    machine = Machine()

    machine.memory.write_byte(0xD301, 0x00)
    machine.memory.write_byte(0xD300, 0xF0)

    assert machine.pia.porta_ddr == 0xF0
