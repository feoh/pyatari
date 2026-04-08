"""Tests for the 6502 disassembler."""

from pyatari.disassembler import disassemble
from pyatari.memory import MemoryBus


def test_disassemble_immediate():
    memory = MemoryBus()
    memory.load_ram(0x8000, bytes([0xA9, 0x10]))

    text, size = disassemble(memory, 0x8000)

    assert text == "LDA #$10"
    assert size == 2


def test_disassemble_absolute_indexed():
    memory = MemoryBus()
    memory.load_ram(0x8000, bytes([0xBD, 0x34, 0x12]))

    text, size = disassemble(memory, 0x8000)

    assert text == "LDA $1234,X"
    assert size == 3


def test_disassemble_relative_branch_target():
    memory = MemoryBus()
    memory.load_ram(0x9000, bytes([0xD0, 0xFE]))

    text, size = disassemble(memory, 0x9000)

    assert text == "BNE $9000"
    assert size == 2


def test_disassemble_unknown_opcode_as_data_byte():
    memory = MemoryBus()
    memory.load_ram(0xA000, bytes([0x02]))

    text, size = disassemble(memory, 0xA000)

    assert text == ".DB $02"
    assert size == 1
