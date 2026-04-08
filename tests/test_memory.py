"""Tests for the Atari memory subsystem."""

from pathlib import Path

import pytest

from pyatari.constants import (
    BASIC_ROM_SIZE,
    BASIC_ROM_START,
    OS_ROM_SIZE,
    OS_ROM_START,
    PORTBBits,
    SELF_TEST_START,
)
from pyatari.memory import MemoryBus
from pyatari.rom_loader import (
    SELF_TEST_ROM_SIZE,
    create_test_rom_stub,
    load_basic_rom,
    load_os_rom,
    load_self_test_rom,
)


class TestMemoryBus:
    def test_ram_read_write(self):
        bus = MemoryBus()

        bus.write_byte(0x1234, 0xAB)

        assert bus.read_byte(0x1234) == 0xAB

    def test_read_word_and_write_word(self):
        bus = MemoryBus()

        bus.write_word(0x2000, 0xBEEF)

        assert bus.read_word(0x2000) == 0xBEEF
        assert bus.read_byte(0x2000) == 0xEF
        assert bus.read_byte(0x2001) == 0xBE

    def test_basic_rom_is_read_only_when_enabled(self):
        bus = MemoryBus()
        rom = bytes([0xAA] * BASIC_ROM_SIZE)
        bus.load_basic_rom(rom)

        bus.write_byte(BASIC_ROM_START, 0x55)

        assert bus.read_byte(BASIC_ROM_START) == 0xAA

    def test_basic_rom_can_be_banked_out_to_reveal_ram(self):
        bus = MemoryBus()
        bus.load_basic_rom(bytes([0xAA] * BASIC_ROM_SIZE))
        bus.ram[BASIC_ROM_START] = 0x11

        bus.update_bank_config(bus.portb & ~PORTBBits.BASIC_ROM_ENABLE)

        bus.write_byte(BASIC_ROM_START, 0x55)

        assert bus.read_byte(BASIC_ROM_START) == 0x55

    def test_os_rom_overlay_and_underlying_ram(self):
        bus = MemoryBus()
        bus.load_os_rom(bytes([0xCC] * OS_ROM_SIZE))
        bus.ram[OS_ROM_START] = 0x33

        assert bus.read_byte(OS_ROM_START) == 0xCC

        bus.update_bank_config(bus.portb & ~PORTBBits.OS_ROM_ENABLE)

        assert bus.read_byte(OS_ROM_START) == 0x33

    def test_self_test_overlay_uses_inverse_portb_bit(self):
        bus = MemoryBus()
        bus.load_self_test_rom(bytes([0x77] * SELF_TEST_ROM_SIZE))
        bus.ram[SELF_TEST_START] = 0x22

        assert bus.read_byte(SELF_TEST_START) == 0x22

        bus.update_bank_config(bus.portb & ~PORTBBits.SELF_TEST_ENABLE)

        assert bus.read_byte(SELF_TEST_START) == 0x77

    def test_register_dispatch_handlers_take_priority(self):
        bus = MemoryBus()

        writes: list[tuple[int, int]] = []

        def read_handler(address: int) -> int:
            return 0x5A if address == 0xD200 else 0

        def write_handler(address: int, value: int) -> None:
            writes.append((address, value))

        bus.register_read_handler(0xD200, 0xD20F, read_handler)
        bus.register_write_handler(0xD200, 0xD20F, write_handler)

        bus.write_byte(0xD200, 0x99)

        assert writes == [(0xD200, 0x99)]
        assert bus.read_byte(0xD200) == 0x5A

    def test_hex_dump_shows_hex_and_ascii(self):
        bus = MemoryBus()
        bus.load_ram(0x0200, b"ABC\x00xyz")

        dump = bus.hex_dump(0x0200, length=7)

        assert "0200:" in dump
        assert "41 42 43 00 78 79 7A" in dump
        assert "ABC.xyz" in dump


class TestROMLoader:
    def test_load_basic_rom_validates_size(self, tmp_path: Path):
        rom_path = tmp_path / "ataribas.rom"
        rom_path.write_bytes(create_test_rom_stub(BASIC_ROM_SIZE))

        rom = load_basic_rom(rom_path)

        assert rom.name == "BASIC"
        assert rom.size == BASIC_ROM_SIZE

    def test_load_os_rom_raises_for_wrong_size(self, tmp_path: Path):
        rom_path = tmp_path / "atarixl.rom"
        rom_path.write_bytes(b"bad")

        with pytest.raises(ValueError, match="OS ROM must be"):
            load_os_rom(rom_path)

    def test_load_self_test_rom(self, tmp_path: Path):
        rom_path = tmp_path / "selftest.rom"
        rom_path.write_bytes(create_test_rom_stub(SELF_TEST_ROM_SIZE, fill_byte=0xAA))

        rom = load_self_test_rom(rom_path)

        assert rom.size == SELF_TEST_ROM_SIZE
        assert rom.data[:4] == bytes([0x00, 0x01, 0x02, 0x03])

    def test_stub_contains_deterministic_pattern(self):
        stub = create_test_rom_stub(32, fill_byte=0xEE)

        assert stub[:6] == bytes([0x00, 0x01, 0x02, 0x03, 0x04, 0x05])
        assert stub[-1] == 0xEE
        assert len(stub) == 32
