"""Memory subsystem for the Atari 800XL.

This module models the machine's 64KB address space, including RAM, ROM
overlays, hardware register dispatch, and the memory banking controlled by PIA
PORTB. The implementation favors clarity over micro-optimizations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pyatari.constants import (
    BASIC_ROM_END,
    BASIC_ROM_START,
    OS_ROM_END,
    OS_ROM_LOWER_END,
    OS_ROM_LOWER_START,
    OS_ROM_START,
    OS_ROM_UPPER_END,
    OS_ROM_UPPER_START,
    PORTBBits,
    SELF_TEST_END,
    SELF_TEST_START,
)

ReadHandler = Callable[[int], int]
WriteHandler = Callable[[int, int], None]


@dataclass(slots=True)
class MemoryRegion:
    """A contiguous memory region mapped into the bus."""

    start: int
    end: int
    name: str
    read_only: bool = False
    storage: bytearray = field(default_factory=bytearray)

    def contains(self, address: int) -> bool:
        return self.start <= address <= self.end

    def read(self, address: int) -> int:
        return self.storage[address - self.start]

    def write(self, address: int, value: int) -> None:
        if self.read_only:
            return
        self.storage[address - self.start] = value & 0xFF


class MemoryBus:
    """Model the Atari 800XL 64KB CPU-visible address space."""

    def __init__(self) -> None:
        self.ram = bytearray(0x10000)
        self.basic_rom: bytes | None = None
        self.os_rom: bytes | None = None
        self.self_test_rom: bytes | None = None

        self.portb = int(
            PORTBBits.OS_ROM_ENABLE
            | PORTBBits.BASIC_ROM_ENABLE
            | PORTBBits.SELF_TEST_ENABLE
        )

        self._read_handlers: dict[int, ReadHandler] = {}
        self._write_handlers: dict[int, WriteHandler] = {}

    def reset(self) -> None:
        """Clear RAM, preserving currently loaded ROM images."""
        self.ram = bytearray(0x10000)

    def load_basic_rom(self, rom_data: bytes) -> None:
        if len(rom_data) != BASIC_ROM_END - BASIC_ROM_START + 1:
            msg = "BASIC ROM must be exactly 8192 bytes"
            raise ValueError(msg)
        self.basic_rom = bytes(rom_data)

    def load_os_rom(self, rom_data: bytes) -> None:
        if len(rom_data) != OS_ROM_END - OS_ROM_START + 1:
            msg = "OS ROM must be exactly 16384 bytes"
            raise ValueError(msg)
        self.os_rom = bytes(rom_data)

    def load_self_test_rom(self, rom_data: bytes) -> None:
        expected = SELF_TEST_END - SELF_TEST_START + 1
        if len(rom_data) != expected:
            msg = f"Self-test ROM must be exactly {expected} bytes"
            raise ValueError(msg)
        self.self_test_rom = bytes(rom_data)

    def register_read_handler(self, start: int, end: int, handler: ReadHandler) -> None:
        for address in range(start, end + 1):
            self._read_handlers[address] = handler

    def register_write_handler(self, start: int, end: int, handler: WriteHandler) -> None:
        for address in range(start, end + 1):
            self._write_handlers[address] = handler

    def unregister_read_handler(self, start: int, end: int) -> None:
        for address in range(start, end + 1):
            self._read_handlers.pop(address, None)

    def unregister_write_handler(self, start: int, end: int) -> None:
        for address in range(start, end + 1):
            self._write_handlers.pop(address, None)

    def update_bank_config(self, portb_value: int) -> None:
        self.portb = portb_value & 0xFF

    def read_byte(self, address: int) -> int:
        address &= 0xFFFF

        if address in self._read_handlers:
            return self._read_handlers[address](address) & 0xFF

        rom_value = self._read_rom_overlay(address)
        if rom_value is not None:
            return rom_value

        return self.ram[address]

    def write_byte(self, address: int, value: int) -> None:
        address &= 0xFFFF
        value &= 0xFF

        if address in self._write_handlers:
            self._write_handlers[address](address, value)
            return

        if self._is_rom_address(address):
            return

        self.ram[address] = value

    def read_word(self, address: int) -> int:
        low = self.read_byte(address)
        high = self.read_byte((address + 1) & 0xFFFF)
        return low | (high << 8)

    def write_word(self, address: int, value: int) -> None:
        self.write_byte(address, value & 0xFF)
        self.write_byte((address + 1) & 0xFFFF, (value >> 8) & 0xFF)

    def load_ram(self, start: int, data: bytes) -> None:
        end = start + len(data)
        if not 0 <= start <= 0xFFFF or end > 0x10000:
            msg = "RAM load exceeds address space"
            raise ValueError(msg)
        self.ram[start:end] = data

    def hex_dump(self, start: int, length: int = 16) -> str:
        start &= 0xFFFF
        if length <= 0:
            return ""

        lines: list[str] = []
        for offset in range(0, length, 16):
            line_start = (start + offset) & 0xFFFF
            chunk = [self.read_byte((line_start + i) & 0xFFFF) for i in range(min(16, length - offset))]
            hex_bytes = " ".join(f"{byte:02X}" for byte in chunk)
            ascii_bytes = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in chunk)
            lines.append(f"{line_start:04X}: {hex_bytes:<47}  {ascii_bytes}")
        return "\n".join(lines)

    def _read_rom_overlay(self, address: int) -> int | None:
        # Below the self-test ROM ($5000) no ROM region exists, so skip all checks.
        if address < SELF_TEST_START:
            return None

        if BASIC_ROM_START <= address <= BASIC_ROM_END and self._basic_rom_enabled():
            if self.basic_rom is not None:
                return self.basic_rom[address - BASIC_ROM_START]

        if SELF_TEST_START <= address <= SELF_TEST_END and self._self_test_enabled():
            if self.self_test_rom is not None:
                return self.self_test_rom[address - SELF_TEST_START]

        if self._os_rom_enabled() and self.os_rom is not None:
            if OS_ROM_LOWER_START <= address <= OS_ROM_LOWER_END:
                return self.os_rom[address - OS_ROM_START]
            if OS_ROM_UPPER_START <= address <= OS_ROM_UPPER_END:
                return self.os_rom[address - OS_ROM_START]

        return None

    def _is_rom_address(self, address: int) -> bool:
        if BASIC_ROM_START <= address <= BASIC_ROM_END and self._basic_rom_enabled():
            return self.basic_rom is not None

        if SELF_TEST_START <= address <= SELF_TEST_END and self._self_test_enabled():
            return self.self_test_rom is not None

        if self._os_rom_enabled() and self.os_rom is not None:
            if OS_ROM_LOWER_START <= address <= OS_ROM_LOWER_END:
                return True
            if OS_ROM_UPPER_START <= address <= OS_ROM_UPPER_END:
                return True

        return False

    def _basic_rom_enabled(self) -> bool:
        return bool(self.portb & PORTBBits.BASIC_ROM_ENABLE)

    def _os_rom_enabled(self) -> bool:
        return bool(self.portb & PORTBBits.OS_ROM_ENABLE)

    def _self_test_enabled(self) -> bool:
        return not bool(self.portb & PORTBBits.SELF_TEST_ENABLE)
