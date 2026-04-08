"""Tests for optional Phase 17 peripherals."""

from __future__ import annotations

import pytest

from pyatari.constants import GTIAReadRegister, JoystickBits, POKEYReadRegister
from pyatari.machine import Machine
from pyatari.peripherals import CassetteDeck, PrinterDevice


def test_second_joystick_and_trigger_are_exposed():
    machine = Machine()

    machine.set_joystick(down=True, right=True, port=1)
    machine.set_trigger(True, port=1)

    porta = machine.pia.read_register(0xD300)
    trig1 = machine.gtia.read_register(int(GTIAReadRegister.TRIG1))

    assert porta & int(JoystickBits.STICK1_DOWN) == 0
    assert porta & int(JoystickBits.STICK1_RIGHT) == 0
    assert trig1 == 0x00


def test_paddle_values_flow_through_pokey_registers():
    machine = Machine()

    machine.set_paddle(3, 17)

    assert machine.pokey.read_register(int(POKEYReadRegister.POT3)) == 17


def test_paddle_range_is_validated():
    machine = Machine()

    with pytest.raises(ValueError):
        machine.set_paddle(8, 10)

    with pytest.raises(ValueError):
        machine.set_paddle(0, 999)


def test_cassette_deck_reads_and_rewinds():
    deck = CassetteDeck()
    deck.load_tape(b"HELLOWORLD")

    assert deck.read_block(5) == b"HELLO"
    assert deck.read_block(5) == b"WORLD"
    deck.rewind()
    assert deck.read_block(5) == b"HELLO"


def test_machine_cassette_helpers_delegate_to_deck():
    machine = Machine()
    machine.load_cassette(b"ABCDEF")

    assert machine.read_cassette_block(3) == b"ABC"
    assert machine.read_cassette_block(3) == b"DEF"


def test_printer_device_collects_output():
    printer = PrinterDevice()
    printer.write("HELLO")
    printer.write(" WORLD")

    assert printer.output == ["HELLO", " WORLD"]
    printer.clear()
    assert printer.output == []


def test_machine_printer_helper_writes_output():
    machine = Machine()
    machine.printer_write("LIST\n")

    assert machine.printer.output == ["LIST\n"]
