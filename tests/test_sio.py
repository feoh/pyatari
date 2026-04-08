"""Tests for SIO, ATR, and XEX support."""

from __future__ import annotations

from pyatari.constants import OSVector, SIOCommand, SIODeviceID
from pyatari.machine import Machine
from pyatari.memory import MemoryBus
from pyatari.sio import ATRImage, DiskDrive, SIOBus, XEXImage, create_test_atr, create_test_xex


def test_atr_parsing_and_sector_reads():
    atr_bytes = create_test_atr([b"ABC", b"DEF"])

    image = ATRImage.from_bytes(atr_bytes)

    assert image.sector_count == 2
    assert image.read_sector(1)[:3] == b"ABC"
    assert image.read_sector(2)[:3] == b"DEF"


def test_disk_drive_status_and_write_round_trip():
    image = ATRImage.from_bytes(create_test_atr([b"A" * 128]))
    drive = DiskDrive(image=image)

    status = drive.status()
    drive.write_sector(1, b"B" * 128)

    assert status[2] == 128
    assert drive.read_sector(1) == b"B" * 128


def test_sio_bus_command_protocol():
    drive = DiskDrive(image=ATRImage.from_bytes(create_test_atr([b"HELLO", b"WORLD"])))
    sio = SIOBus()
    sio.attach_disk(int(SIODeviceID.DISK_1), drive)

    status = sio.send_command(int(SIODeviceID.DISK_1), int(SIOCommand.STATUS))
    sector = sio.send_command(int(SIODeviceID.DISK_1), int(SIOCommand.READ_SECTOR), sector=2)

    assert status[1] == 2
    assert sector[:5] == b"WORLD"


def test_xex_loader_maps_segments_and_vectors_into_memory():
    xex = XEXImage.from_bytes(
        create_test_xex((0x2000, b"\xA9\x42"), run_address=0x2000, init_address=0x2100)
    )
    memory = MemoryBus()

    xex.load_into(memory)

    assert memory.read_byte(0x2000) == 0xA9
    assert memory.read_byte(0x2001) == 0x42
    assert memory.read_word(int(OSVector.RUNAD)) == 0x2000
    assert memory.read_word(int(OSVector.INITAD)) == 0x2100


def test_machine_can_load_xex_and_set_pc():
    machine = Machine()
    image = machine.load_xex(create_test_xex((0x2400, b"\xEA\xEA"), run_address=0x2400))

    assert image.run_address == 0x2400
    assert machine.cpu.pc == 0x2400
    assert machine.memory.read_byte(0x2400) == 0xEA


def test_boot_sectors_expose_first_three_disk_sectors():
    sectors = [bytes([index]) * 128 for index in range(1, 5)]
    drive = DiskDrive(image=ATRImage.from_bytes(create_test_atr(sectors)))

    boot = drive.boot_sectors()

    assert len(boot) == 128 * 3
    assert boot[:3] == b"\x01\x01\x01"
    assert boot[128:131] == b"\x02\x02\x02"
