"""ROM loading helpers for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyatari.constants import BASIC_ROM_SIZE, OS_ROM_SIZE, SELF_TEST_END, SELF_TEST_START

SELF_TEST_ROM_SIZE = SELF_TEST_END - SELF_TEST_START + 1
XL_COMBINED_ROM_SIZE = OS_ROM_SIZE + SELF_TEST_ROM_SIZE
SELF_TEST_ROM_CANDIDATES = (
    "atarixlselftest.rom",
    "atarixl-selftest.rom",
    "atarixl_selftest.rom",
    "selftest.rom",
)


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


def load_xl_rom_bundle(path: str | Path) -> tuple[ROMImage, ROMImage | None]:
    """Load an XL OS ROM dump, optionally extracting a bundled self-test ROM.

    Supported layouts:
    - 16 KB OS-only dump
    - 18 KB combined dump with self-test + OS, in either contiguous order
    """
    rom_path = Path(path)
    data = rom_path.read_bytes()
    if len(data) == OS_ROM_SIZE:
        return (ROMImage(name="OS", path=rom_path, data=data), None)
    if len(data) != XL_COMBINED_ROM_SIZE:
        msg = (
            f"OS ROM must be {OS_ROM_SIZE} bytes or {XL_COMBINED_ROM_SIZE} bytes "
            f"with bundled self-test, got {len(data)}"
        )
        raise ValueError(msg)

    leading_self_test = data[:SELF_TEST_ROM_SIZE]
    trailing_os = data[SELF_TEST_ROM_SIZE:]
    if _is_valid_xl_rom_pair(trailing_os, leading_self_test):
        return (
            ROMImage(name="OS", path=rom_path, data=trailing_os),
            ROMImage(name="self-test", path=rom_path, data=leading_self_test),
        )

    leading_os = data[:OS_ROM_SIZE]
    trailing_self_test = data[OS_ROM_SIZE:]
    if _is_valid_xl_rom_pair(leading_os, trailing_self_test):
        return (
            ROMImage(name="OS", path=rom_path, data=leading_os),
            ROMImage(name="self-test", path=rom_path, data=trailing_self_test),
        )

    msg = "Combined XL ROM checksum layout is not recognized"
    raise ValueError(msg)


def find_self_test_rom(rom_dir: str | Path) -> Path | None:
    """Return the first matching self-test ROM path in ``rom_dir``."""
    directory = Path(rom_dir)
    for candidate in SELF_TEST_ROM_CANDIDATES:
        candidate_path = directory / candidate
        if candidate_path.exists():
            return candidate_path
    return None


def _is_valid_xl_rom_pair(os_data: bytes, self_test_data: bytes) -> bool:
    if len(os_data) != OS_ROM_SIZE or len(self_test_data) != SELF_TEST_ROM_SIZE:
        return False

    expected_lower = os_data[0] | (os_data[1] << 8)
    expected_upper = os_data[0x3FF8] | (os_data[0x3FF9] << 8)
    lower_sum = (
        sum(os_data[0x0002:0x1000])
        + sum(self_test_data)
        + sum(os_data[0x1800:0x2000])
    ) & 0xFFFF
    upper_sum = (
        sum(os_data[0x2000:0x3FF8])
        + sum(os_data[0x3FFA:0x4000])
    ) & 0xFFFF
    return lower_sum == expected_lower and upper_sum == expected_upper


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
