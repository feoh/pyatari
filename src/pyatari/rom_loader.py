"""ROM loading helpers for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyatari.constants import BASIC_ROM_SIZE, OS_ROM_SIZE, SELF_TEST_END, SELF_TEST_START

SELF_TEST_ROM_SIZE = SELF_TEST_END - SELF_TEST_START + 1


@dataclass(frozen=True, slots=True)
class ROMImage:
    """A loaded ROM image with basic metadata."""

    name: str
    path: Path
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)


def load_rom(path: str | Path, *, expected_size: int, name: str) -> ROMImage:
    """Load a ROM from disk and validate its exact size."""
    rom_path = Path(path)
    data = rom_path.read_bytes()
    if len(data) != expected_size:
        msg = f"{name} ROM must be {expected_size} bytes, got {len(data)}"
        raise ValueError(msg)
    return ROMImage(name=name, path=rom_path, data=data)


def load_os_rom(path: str | Path) -> ROMImage:
    return load_rom(path, expected_size=OS_ROM_SIZE, name="OS")


def load_basic_rom(path: str | Path) -> ROMImage:
    return load_rom(path, expected_size=BASIC_ROM_SIZE, name="BASIC")


def load_self_test_rom(path: str | Path) -> ROMImage:
    return load_rom(path, expected_size=SELF_TEST_ROM_SIZE, name="self-test")


def create_test_rom_stub(size: int, *, fill_byte: int = 0xFF) -> bytes:
    """Create a deterministic ROM stub for tests.

    The stub is mostly filled with ``fill_byte`` but has a small ascending
    pattern at the front so tests can easily verify that the right overlay is
    visible.
    """
    if not 0 <= fill_byte <= 0xFF:
        msg = "fill_byte must fit in one byte"
        raise ValueError(msg)
    if size <= 0:
        msg = "size must be positive"
        raise ValueError(msg)

    data = bytearray([fill_byte] * size)
    for index in range(min(16, size)):
        data[index] = index
    return bytes(data)
