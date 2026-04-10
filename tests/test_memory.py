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
    XL_COMBINED_ROM_SIZE,
    create_test_rom_stub,
    find_self_test_rom,
    load_basic_rom,
    load_os_rom,
    load_self_test_rom,
    load_xl_rom_bundle,
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
    @staticmethod
    def _make_checksum_valid_os_self_test_pair() -> tuple[bytes, bytes]:
        os_data = bytearray(create_test_rom_stub(OS_ROM_SIZE, fill_byte=0x00))
        self_test_data = bytearray(create_test_rom_stub(SELF_TEST_ROM_SIZE, fill_byte=0x00))

        lower_sum = (
            sum(os_data[0x0002:0x1000])
            + sum(self_test_data)
            + sum(os_data[0x1800:0x2000])
        ) & 0xFFFF
        upper_sum = (
            sum(os_data[0x2000:0x3FF8])
            + sum(os_data[0x3FFA:0x4000])
        ) & 0xFFFF
        os_data[0] = lower_sum & 0xFF
        os_data[1] = (lower_sum >> 8) & 0xFF
        os_data[0x3FF8] = upper_sum & 0xFF
        os_data[0x3FF9] = (upper_sum >> 8) & 0xFF
        return (bytes(os_data), bytes(self_test_data))

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

    def test_load_xl_rom_bundle_accepts_os_only_dump(self, tmp_path: Path):
        rom_path = tmp_path / "atarixl.rom"
        rom_path.write_bytes(create_test_rom_stub(OS_ROM_SIZE))

        os_rom, self_test_rom = load_xl_rom_bundle(rom_path)

        assert os_rom.size == OS_ROM_SIZE
        assert self_test_rom is None

    def test_load_xl_rom_bundle_splits_leading_self_test_layout(self, tmp_path: Path):
        os_data, self_test_data = self._make_checksum_valid_os_self_test_pair()
        rom_path = tmp_path / "atarixl.rom"
        rom_path.write_bytes(self_test_data + os_data)

        os_rom, self_test_rom = load_xl_rom_bundle(rom_path)

        assert os_rom.data == os_data
        assert self_test_rom is not None
        assert self_test_rom.data == self_test_data

    def test_load_xl_rom_bundle_splits_trailing_self_test_layout(self, tmp_path: Path):
        os_data, self_test_data = self._make_checksum_valid_os_self_test_pair()
        rom_path = tmp_path / "atarixl.rom"
        rom_path.write_bytes(os_data + self_test_data)

        os_rom, self_test_rom = load_xl_rom_bundle(rom_path)

        assert os_rom.data == os_data
        assert self_test_rom is not None
        assert self_test_rom.data == self_test_data

    def test_load_xl_rom_bundle_rejects_unrecognized_combined_layout(self, tmp_path: Path):
        rom_path = tmp_path / "atarixl.rom"
        rom_path.write_bytes(create_test_rom_stub(XL_COMBINED_ROM_SIZE))

        with pytest.raises(ValueError, match="checksum layout is not recognized"):
            load_xl_rom_bundle(rom_path)

    def test_find_self_test_rom_prefers_known_candidate_names(self, tmp_path: Path):
        rom_path = tmp_path / "atarixl-selftest.rom"
        rom_path.write_bytes(create_test_rom_stub(SELF_TEST_ROM_SIZE))

        assert find_self_test_rom(tmp_path) == rom_path

    def test_find_self_test_rom_returns_none_when_absent(self, tmp_path: Path):
        assert find_self_test_rom(tmp_path) is None

    def test_stub_contains_deterministic_pattern(self):
        stub = create_test_rom_stub(32, fill_byte=0xEE)

        assert stub[:6] == bytes([0x00, 0x01, 0x02, 0x03, 0x04, 0x05])
        assert stub[-1] == 0xEE
        assert len(stub) == 32
