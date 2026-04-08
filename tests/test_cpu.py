"""Tests for CPU scaffolding."""

from pyatari.constants import RESET_VECTOR
from pyatari.cpu import CPU, StatusRegister
from pyatari.memory import MemoryBus


def test_status_round_trip():
    status = StatusRegister(
        negative=True,
        overflow=False,
        break_flag=True,
        decimal=True,
        interrupt_disable=False,
        zero=True,
        carry=False,
    )

    encoded = status.to_byte()
    decoded = StatusRegister.from_byte(encoded)

    assert decoded.negative is True
    assert decoded.break_flag is True
    assert decoded.decimal is True
    assert decoded.zero is True
    assert decoded.carry is False
    assert decoded.reserved is True


def test_reset_loads_reset_vector():
    memory = MemoryBus()
    memory.write_word(RESET_VECTOR, 0xC000)
    cpu = CPU(memory=memory)

    cpu.reset()

    assert cpu.pc == 0xC000
    assert cpu.sp == 0xFD
    assert cpu.status.interrupt_disable is True


def test_fetch_decode_and_step_tracks_opcode_and_cycles():
    memory = MemoryBus()
    memory.write_word(RESET_VECTOR, 0x8000)
    memory.load_ram(0x8000, bytes([0xA9, 0x42, 0xEA]))
    cpu = CPU(memory=memory)
    cpu.reset()

    opcode = cpu.step()

    assert opcode.mnemonic == "LDA"
    assert opcode.bytes == 2
    assert cpu.pc == 0x8002
    assert cpu.cycles == 2
    assert cpu.last_address is not None
    assert cpu.last_address.address == 0x8001
