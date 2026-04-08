"""SIO bus, ATR disk support, and XEX loading for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pyatari.constants import OSVector, SIOCommand, SECTOR_SIZE_DOUBLE, SECTOR_SIZE_SINGLE
from pyatari.memory import MemoryBus

ATR_HEADER_SIZE = 16
ATR_MAGIC = 0x0296


@dataclass(slots=True)
class ATRImage:
    sector_size: int
    sectors: list[bytes]

    @classmethod
    def from_bytes(cls, data: bytes) -> "ATRImage":
        if len(data) < ATR_HEADER_SIZE:
            msg = "ATR image too small"
            raise ValueError(msg)

        magic = int.from_bytes(data[0:2], "little")
        if magic != ATR_MAGIC:
            msg = "Invalid ATR magic"
            raise ValueError(msg)

        sector_size = int.from_bytes(data[4:6], "little") or SECTOR_SIZE_SINGLE
        payload = data[ATR_HEADER_SIZE:]
        if len(payload) % sector_size != 0:
            msg = "ATR payload is not an even multiple of sector size"
            raise ValueError(msg)

        sectors = [payload[offset:offset + sector_size] for offset in range(0, len(payload), sector_size)]
        return cls(sector_size=sector_size, sectors=sectors)

    @classmethod
    def from_path(cls, path: str | Path) -> "ATRImage":
        return cls.from_bytes(Path(path).read_bytes())

    @property
    def sector_count(self) -> int:
        return len(self.sectors)

    def read_sector(self, sector_number: int) -> bytes:
        if sector_number < 1 or sector_number > self.sector_count:
            msg = f"Sector out of range: {sector_number}"
            raise IndexError(msg)
        return self.sectors[sector_number - 1]

    def write_sector(self, sector_number: int, data: bytes) -> None:
        if len(data) != self.sector_size:
            msg = f"Sector data must be exactly {self.sector_size} bytes"
            raise ValueError(msg)
        if sector_number < 1 or sector_number > self.sector_count:
            msg = f"Sector out of range: {sector_number}"
            raise IndexError(msg)
        self.sectors[sector_number - 1] = bytes(data)


@dataclass(slots=True)
class DiskDrive:
    image: ATRImage
    write_enabled: bool = True

    def status(self) -> bytes:
        sector_size_flag = 0x20 if self.image.sector_size == SECTOR_SIZE_DOUBLE else 0x00
        write_flag = 0x00 if self.write_enabled else 0x80
        return bytes([sector_size_flag | write_flag, self.image.sector_count & 0xFF, self.image.sector_size & 0xFF, self.image.sector_size >> 8])

    def read_sector(self, sector_number: int) -> bytes:
        return self.image.read_sector(sector_number)

    def write_sector(self, sector_number: int, data: bytes, *, verify: bool = True) -> None:
        if not self.write_enabled:
            msg = "Disk is write protected"
            raise PermissionError(msg)
        self.image.write_sector(sector_number, data)
        if verify and self.image.read_sector(sector_number) != data:
            msg = "Sector verify failed"
            raise IOError(msg)

    def boot_sectors(self, count: int = 3) -> bytes:
        chunks = [self.read_sector(sector)[:SECTOR_SIZE_SINGLE] for sector in range(1, min(count, self.image.sector_count) + 1)]
        return b"".join(chunks)


@dataclass(slots=True)
class SIOBus:
    devices: dict[int, DiskDrive] = field(default_factory=dict)

    def attach_disk(self, device_id: int, drive: DiskDrive) -> None:
        self.devices[device_id] = drive

    def send_command(self, device_id: int, command: int, *, sector: int | None = None, data: bytes | None = None) -> bytes:
        if device_id not in self.devices:
            msg = f"No SIO device attached at {device_id:#04x}"
            raise KeyError(msg)
        drive = self.devices[device_id]
        command = int(command)
        if command == int(SIOCommand.STATUS):
            return drive.status()
        if command == int(SIOCommand.READ_SECTOR):
            if sector is None:
                msg = "READ_SECTOR requires a sector number"
                raise ValueError(msg)
            return drive.read_sector(sector)
        if command in {int(SIOCommand.WRITE_SECTOR), int(SIOCommand.PUT_SECTOR)}:
            if sector is None or data is None:
                msg = "Write commands require sector number and data"
                raise ValueError(msg)
            drive.write_sector(sector, data, verify=command == int(SIOCommand.WRITE_SECTOR))
            return b"A"
        msg = f"Unsupported SIO command {command:#04x}"
        raise ValueError(msg)


@dataclass(slots=True)
class XEXSegment:
    start: int
    end: int
    data: bytes


@dataclass(slots=True)
class XEXImage:
    segments: list[XEXSegment]
    run_address: int | None = None
    init_address: int | None = None

    @classmethod
    def from_bytes(cls, data: bytes) -> "XEXImage":
        offset = 0
        segments: list[XEXSegment] = []
        run_address: int | None = None
        init_address: int | None = None

        if len(data) >= 2 and int.from_bytes(data[:2], "little") == 0xFFFF:
            offset = 2

        while offset + 4 <= len(data):
            start = int.from_bytes(data[offset:offset + 2], "little")
            end = int.from_bytes(data[offset + 2:offset + 4], "little")
            offset += 4
            length = end - start + 1
            if length < 0 or offset + length > len(data):
                msg = "Malformed XEX segment"
                raise ValueError(msg)
            payload = data[offset:offset + length]
            offset += length
            if start == int(OSVector.RUNAD) and length >= 2:
                run_address = int.from_bytes(payload[:2], "little")
            elif start == int(OSVector.INITAD) and length >= 2:
                init_address = int.from_bytes(payload[:2], "little")
            else:
                segments.append(XEXSegment(start=start, end=end, data=payload))

        return cls(segments=segments, run_address=run_address, init_address=init_address)

    @classmethod
    def from_path(cls, path: str | Path) -> "XEXImage":
        return cls.from_bytes(Path(path).read_bytes())

    def load_into(self, memory: MemoryBus) -> None:
        for segment in self.segments:
            memory.load_ram(segment.start, segment.data)
        if self.run_address is not None:
            memory.write_word(int(OSVector.RUNAD), self.run_address)
        if self.init_address is not None:
            memory.write_word(int(OSVector.INITAD), self.init_address)


def create_test_atr(sectors: list[bytes], *, sector_size: int = SECTOR_SIZE_SINGLE) -> bytes:
    normalized = [sector.ljust(sector_size, b"\x00")[:sector_size] for sector in sectors]
    paragraph_count = ((len(normalized) * sector_size) + 15) // 16
    header = bytearray(ATR_HEADER_SIZE)
    header[0:2] = ATR_MAGIC.to_bytes(2, "little")
    header[2:4] = paragraph_count.to_bytes(2, "little")
    header[4:6] = sector_size.to_bytes(2, "little")
    return bytes(header) + b"".join(normalized)


def create_test_xex(*segments: tuple[int, bytes], run_address: int | None = None, init_address: int | None = None) -> bytes:
    chunks = [b"\xFF\xFF"]
    for start, payload in segments:
        end = start + len(payload) - 1
        chunks.append(start.to_bytes(2, "little"))
        chunks.append(end.to_bytes(2, "little"))
        chunks.append(payload)
    if run_address is not None:
        chunks.append(int(OSVector.RUNAD).to_bytes(2, "little"))
        chunks.append((int(OSVector.RUNAD) + 1).to_bytes(2, "little"))
        chunks.append(run_address.to_bytes(2, "little"))
    if init_address is not None:
        chunks.append(int(OSVector.INITAD).to_bytes(2, "little"))
        chunks.append((int(OSVector.INITAD) + 1).to_bytes(2, "little"))
        chunks.append(init_address.to_bytes(2, "little"))
    return b"".join(chunks)
