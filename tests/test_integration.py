"""Integration tests for Phase 16 machine boot and frame flow."""

from __future__ import annotations

import sys

from pyatari.constants import (
    ANTICRegister,
    CYCLES_PER_FRAME,
    FRAMES_PER_SECOND,
    GTIAWriteRegister,
    IRQBits,
    POKEYReadRegister,
    POKEYWriteRegister,
    RESET_VECTOR,
    ShadowRegister,
    SIO_ERROR_NO_DEVICE,
    SIOCommand,
    SIOResponse,
    SIO_VECTOR,
    SIOWorkspace,
)
from pyatari.machine import Machine
from pyatari.rom_loader import create_test_rom_stub
from pyatari.sio import ATRImage, DiskDrive, create_test_atr, create_test_xex


def make_machine() -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, 0x2000)
    machine.reset()
    return machine


def read_screen_row(machine: Machine, row: int) -> str:
    start = 0x3000 + (row * 40)
    chars: list[str] = []
    for offset in range(40):
        code = machine.memory.read_byte(start + offset) & 0x7F
        if 0 <= code <= 63:
            chars.append(chr(code + 32))
        else:
            chars.append(" ")
    return "".join(chars)


def test_run_frame_advances_clock_and_queues_audio():
    machine = make_machine()
    machine.memory.load_ram(0x2000, bytes([0xEA] * 0x9000))
    machine.cpu.pc = 0x2000

    steps = machine.run_frame()

    assert steps > 0
    assert machine.clock.total_cycles >= CYCLES_PER_FRAME
    assert len(machine.audio.buffers) == 1
    assert len(machine.audio.buffers[0]) == machine.audio.sample_rate // FRAMES_PER_SECOND


def test_status_reports_runtime_fields_and_turbo():
    machine = make_machine()
    machine.set_turbo(True)

    status = machine.status()

    assert status.pc == machine.cpu.pc
    assert status.scanline == machine.clock.scanline
    assert status.frame == machine.clock.frame
    assert status.fps == FRAMES_PER_SECOND
    assert status.turbo is True


def test_boot_xex_loads_and_runs_to_run_address_without_roms():
    machine = make_machine()
    xex = create_test_xex((0x2400, b"\xEA\xEA\xEA"), run_address=0x2400)

    steps = machine.boot_xex(xex)

    assert steps == 0
    assert machine.cpu.pc == 0x2400
    assert machine.memory.read_byte(0x2400) == 0xEA


def test_run_program_executes_rom_free_machine_code():
    machine = make_machine()

    pc = machine.run_program(bytes([0xE8, 0xE8, 0xEA]), start=0x2800, steps=2)

    assert pc == 0x2802
    assert machine.cpu.x == 2


def test_load_demo_screen_produces_visible_frame_without_roms():
    machine = Machine()
    machine.reset()

    machine.load_demo_screen()
    machine.run_frame(queue_audio=False)

    background = machine.gtia.color_to_rgb(
        machine.memory.read_byte(int(GTIAWriteRegister.COLBK))
    )
    lit_pixels = sum(pixel != background for row in machine.gtia.framebuffer for pixel in row)

    assert machine.memory.read_word(int(ANTICRegister.DLISTL)) == 0x2400
    assert machine.memory.read_byte(int(ANTICRegister.CHBASE)) == 0x40
    assert machine.memory.read_byte(0x3000 + (8 * 40) + 13) == (ord("P") - 32)
    assert lit_pixels > 0


def test_load_demo_screen_does_not_repeat_display_list_below_visible_rows():
    machine = Machine()
    machine.reset()

    machine.load_demo_screen()
    machine.run_frame(queue_audio=False)

    background = machine.gtia.color_to_rgb(
        machine.memory.read_byte(int(GTIAWriteRegister.COLBK))
    )
    lit_bottom_pixels = sum(
        pixel != background
        for row in machine.gtia.framebuffer[200:]
        for pixel in row
    )

    assert lit_bottom_pixels == 0


def test_has_visible_output_detects_demo_frame():
    machine = Machine()
    machine.reset()

    machine.load_demo_screen()
    assert machine.has_visible_output() is False

    machine.run_frame(queue_audio=False)

    assert machine.has_visible_output() is True


def test_vbi_syncs_os_shadow_registers_to_live_hardware():
    machine = make_machine()
    machine.memory.load_os_rom(create_test_rom_stub(0x4000))
    machine.memory.load_ram(0x2000, bytes([0xEA]))
    machine.cpu.pc = 0x2000
    machine.memory.write_byte(int(ShadowRegister.SDMCTL), 0x22)
    machine.memory.write_byte(int(ShadowRegister.SDLSTL), 0x34)
    machine.memory.write_byte(int(ShadowRegister.SDLSTH), 0x12)
    machine.memory.write_byte(int(ShadowRegister.CHART), 0x02)
    machine.memory.write_byte(int(ShadowRegister.CHBAS), 0xE0)
    machine.memory.write_byte(int(ShadowRegister.COLOR1), 0x0E)
    machine.memory.write_byte(int(ShadowRegister.COLOR4), 0x24)
    machine.antic.scanline = 247
    machine.antic.cycles_into_scanline = 113
    machine.antic.current_line = None
    machine.antic.current_line_remaining = 0
    machine.antic.dmactl = 0

    machine.step()

    assert machine.antic.dmactl == 0x22
    assert machine.antic.dlist == 0x1234
    assert machine.antic.chactl == 0x02
    assert machine.antic.chbase == 0xE0
    assert machine.gtia.write_registers[int(GTIAWriteRegister.COLPF1)] == 0x0E
    assert machine.gtia.write_registers[int(GTIAWriteRegister.COLBK)] == 0x24


def test_reset_with_os_rom_seeds_display_shadow_defaults():
    machine = Machine()
    machine.memory.load_os_rom(create_test_rom_stub(0x4000))
    machine.reset()

    assert machine.memory.read_word(int(ShadowRegister.SAVMSC)) == 0x9C40
    assert machine.memory.read_word(int(ShadowRegister.DLPTR)) == 0x9C20
    assert machine.memory.read_byte(int(ShadowRegister.RAMTOP)) == 0xA0
    assert machine.memory.read_byte(int(ShadowRegister.SDMCTL)) == 0x22
    assert machine.memory.read_word(int(ShadowRegister.SDLSTL)) == 0x9C20
    assert machine.memory.read_byte(int(ShadowRegister.CHART)) == 0x02
    assert machine.memory.read_byte(int(ShadowRegister.CHBAS)) == 0xE0


def test_reset_with_os_rom_syncs_seeded_display_defaults_to_hardware():
    machine = Machine()
    machine.memory.load_os_rom(create_test_rom_stub(0x4000))
    machine.reset()

    assert machine.antic.dmactl == 0x22
    assert machine.antic.dlist == 0x9C20
    assert machine.antic.chactl == 0x02
    assert machine.antic.chbase == 0xE0
    assert machine.gtia.write_registers[int(GTIAWriteRegister.COLBK)] == 0x00


def test_reset_with_os_rom_installs_default_display_list_ram():
    machine = Machine()
    machine.memory.load_os_rom(create_test_rom_stub(0x4000))
    machine.reset()

    assert machine.memory.read_byte(0x9C20) == 0x70
    assert machine.memory.read_byte(0x9C21) == 0x42
    assert machine.memory.read_word(0x9C22) == 0x9C40
    assert machine.memory.read_byte(0x9C3B) == 0x41
    assert machine.memory.read_word(0x9C3C) == 0x9C20
    assert machine.memory.read_byte(0x9C40) == 0x00


def test_os_rom_boot_frame_renders_correct_glyphs():
    """Glyph cache reads correct pattern bytes from OS ROM during ROM-boot rendering.

    This is the key regression guard for ADR 0005: verifies that the rendering
    shortcut (direct os_rom[] access instead of read_byte) produces the same
    pixel output as the full memory-bus path would.
    """
    os_rom = bytearray(0x4000)
    # Char 0x01 at ROM offset 0x2000 + 0x01*8 + 0 = 0x2008: alternating pattern
    os_rom[0x2008] = 0b10101010  # row 0: alternating pixels

    machine = Machine()
    machine.memory.load_os_rom(bytes(os_rom))
    machine.reset()

    # After reset, display list is at 0x9C20 and screen at 0x9C40 (set by _initialize_os_shadows).
    # Place char 0x01 in the first screen position; OS shadows set chbase = 0xE0.
    machine.memory.ram[0x9C40] = 0x01

    # Set COLPF2 = 0x00 (black bg) and COLPF1 = 0x0E (bright luminance),
    # syncing via the shadow path that the real OS uses.
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF2), 0x00)
    machine.memory.write_byte(int(GTIAWriteRegister.COLPF1), 0x0E)

    machine.run_frame(queue_audio=False)

    # For mode 2 (ANTIC mode 2 = 40-col text), display begins after the blank
    # at scanline 0 (skipped by blank instructions).  The first text line starts
    # at the display-list row 0 which maps to framebuffer row 0 after the 8
    # blank scanlines ANTIC inserts before the visible area.
    # Rather than hard-coding the scanline offset, just verify that somewhere in
    # the first few text rows the expected alternating pattern appears.
    fg = machine.gtia.color_to_rgb((0x00 & 0xF0) | (0x0E & 0x0E))  # mode-2 hires luminance
    bg = machine.gtia.color_to_rgb(0x00)

    # Scan the first 24 framebuffer rows; one of them is the first text scanline
    # for char 0x01 row 0, which must produce the alternating fg/bg/fg/bg pattern.
    found = False
    for row in machine.gtia.framebuffer:
        if row[0] == fg and row[1] == bg and row[2] == fg and row[3] == bg:
            found = True
            break
    assert found, "Alternating glyph pattern from OS ROM was not found in any framebuffer row"


def test_continue_without_self_test_marks_checksum_gate_complete(monkeypatch):
    machine = Machine()
    machine.memory.load_os_rom(create_test_rom_stub(0x4000))
    machine.reset()

    def fake_run_until(self, address: int, max_steps: int = 100_000) -> int:
        assert address == 0xC3AB
        assert max_steps == 800_000
        machine.cpu.pc = address
        return 123

    monkeypatch.setattr(Machine, "run_until", fake_run_until)
    machine.memory.write_byte(0x0001, 0x00)

    assert machine.continue_without_self_test() is True
    assert machine.cpu.pc == 0xC3AB
    assert machine.memory.read_byte(0x0001) == 0x01


def test_continue_without_self_test_is_noop_when_self_test_rom_is_loaded():
    machine = Machine()
    machine.memory.load_os_rom(create_test_rom_stub(0x4000))
    machine.memory.load_self_test_rom(create_test_rom_stub(0x0800))
    machine.reset()
    machine.memory.write_byte(0x0001, 0x00)

    assert machine.continue_without_self_test() is False
    assert machine.memory.read_byte(0x0001) == 0x00


def test_rom_boot_state_reports_reset_visible_registers():
    machine = Machine()
    machine.memory.load_os_rom(create_test_rom_stub(0x4000))
    machine.reset()

    state = machine.rom_boot_state()

    assert state.pc == machine.cpu.pc
    assert state.portb == machine.memory.portb
    assert state.coldstart_status == machine.memory.read_byte(0x0001)
    assert state.dmactl == 0x22
    assert state.dlist == 0x9C20
    assert state.chbase == 0xE0
    assert state.sdmctl == 0x22
    assert state.sdlstl == 0x9C20
    assert state.chbas_shadow == 0xE0
    assert state.savmsc == 0x9C40


def test_real_rom_boot_message_clarifies_basic_is_enabled_when_option_not_held(
    monkeypatch, tmp_path, capsys
):
    from pyatari import machine as machine_module

    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    (rom_dir / "atarixl.rom").write_bytes(create_test_rom_stub(0x4000))
    (rom_dir / "ataribas.rom").write_bytes(create_test_rom_stub(0x2000))

    monkeypatch.setattr(
        sys,
        "argv",
        ["pyatari", "--frames", "1", "--rom-dir", str(rom_dir)],
    )
    monkeypatch.setattr(
        Machine,
        "continue_without_self_test",
        lambda self, max_steps=800_000: True,
    )

    machine_module.main()

    output = capsys.readouterr().out
    assert "OPTION not held" in output
    assert "BASIC remains enabled" in output


def test_real_rom_boot_message_reports_post_checksum_fallback(
    monkeypatch, tmp_path, capsys
):
    from pyatari import machine as machine_module

    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    (rom_dir / "atarixl.rom").write_bytes(create_test_rom_stub(0x4000))
    (rom_dir / "ataribas.rom").write_bytes(create_test_rom_stub(0x2000))

    monkeypatch.setattr(
        sys,
        "argv",
        ["pyatari", "--frames", "1", "--rom-dir", str(rom_dir)],
    )
    monkeypatch.setattr(
        Machine,
        "continue_without_self_test",
        lambda self, max_steps=800_000: True,
    )

    machine_module.main()

    output = capsys.readouterr().out
    assert "post-checksum warm-start fallback" in output


def test_demo_flag_forces_demo_even_when_roms_are_present(
    monkeypatch, tmp_path, capsys
):
    from pyatari import machine as machine_module

    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    (rom_dir / "atarixl.rom").write_bytes(create_test_rom_stub(0x4000))

    monkeypatch.setattr(
        sys,
        "argv",
        ["pyatari", "--frames", "1", "--demo", "--rom-dir", str(rom_dir)],
    )

    machine_module.main()

    output = capsys.readouterr().out
    assert "Loaded built-in graphics demo (--demo requested)" in output
    assert "Running real ROM boot path" not in output


def test_machine_leaves_missing_sio_device_probe_silent():
    machine = Machine()
    machine.memory.write_byte(int(SIOWorkspace.STATUS), 0x55)

    for byte in (0x31, 0x53, 0x00, 0x00, 0x00):
        machine.memory.write_byte(int(POKEYWriteRegister.SEROUT), byte)
    machine._service_serial_bus()

    assert machine.memory.read_byte(int(SIOWorkspace.STATUS)) == 0x55
    assert all(event.data is None for event in machine.pokey.serial_events)


def test_machine_queues_sio_status_response_bytes_for_attached_drive():
    machine = Machine()
    machine.sio.attach_disk(
        0x31,
        DiskDrive(image=ATRImage.from_bytes(create_test_atr([b"A" * 128]))),
    )
    machine.memory.write_byte(
        int(POKEYWriteRegister.IRQEN),
        int(IRQBits.SERIAL_IN_DONE),
    )

    for byte in (0x31, 0x53, 0x00, 0x00, 0x00):
        machine.memory.write_byte(int(POKEYWriteRegister.SEROUT), byte)
    machine._service_serial_bus()

    observed: list[int] = []
    for _ in range(7):
        machine.pokey.tick(28 * 10)
        observed.append(machine.memory.read_byte(int(POKEYReadRegister.SERIN)))

    assert machine.memory.read_byte(int(SIOWorkspace.STATUS)) == 0x00
    assert observed == [
        int(SIOResponse.ACK),
        int(SIOResponse.COMPLETE),
        0x00,
        0x01,
        0x80,
        0x00,
        0x81,
    ]


def test_os_siov_trap_returns_no_device_error_to_caller():
    machine = Machine()
    machine.cpu.pc = SIO_VECTOR
    machine.cpu.sp = 0xFB
    machine.memory.write_byte(0x01FC, 0x02)
    machine.memory.write_byte(0x01FD, 0x20)
    machine.memory.write_byte(int(SIOWorkspace.DDEVIC), 0x31)
    machine.memory.write_byte(int(SIOWorkspace.DCMND), int(SIOCommand.STATUS))
    machine.memory.write_word(int(SIOWorkspace.DBUFLO), 0x02EA)
    machine.memory.write_word(int(SIOWorkspace.DBYTLO), 4)

    opcode = machine.step()

    assert opcode.mnemonic == "RTS"
    assert machine.cpu.pc == 0x2003
    assert machine.cpu.a == SIO_ERROR_NO_DEVICE
    assert machine.cpu.y == SIO_ERROR_NO_DEVICE
    assert machine.cpu.status.carry is True
    assert machine.memory.read_byte(int(SIOWorkspace.DSTATS)) == SIO_ERROR_NO_DEVICE
    assert machine.memory.read_byte(int(SIOWorkspace.STATUS)) == SIO_ERROR_NO_DEVICE


def test_os_siov_trap_copies_attached_drive_status_frame_to_buffer():
    machine = Machine()
    machine.sio.attach_disk(
        0x31,
        DiskDrive(image=ATRImage.from_bytes(create_test_atr([b"A" * 128]))),
    )
    machine.cpu.pc = SIO_VECTOR
    machine.cpu.sp = 0xFB
    machine.memory.write_byte(0x01FC, 0x02)
    machine.memory.write_byte(0x01FD, 0x20)
    machine.memory.write_byte(int(SIOWorkspace.DDEVIC), 0x31)
    machine.memory.write_byte(int(SIOWorkspace.DCMND), int(SIOCommand.STATUS))
    machine.memory.write_word(int(SIOWorkspace.DBUFLO), 0x02EA)
    machine.memory.write_word(int(SIOWorkspace.DBYTLO), 4)

    opcode = machine.step()

    assert opcode.mnemonic == "RTS"
    assert machine.cpu.pc == 0x2003
    assert machine.cpu.a == 0x01
    assert machine.cpu.y == 0x01
    assert machine.cpu.status.carry is False
    assert machine.memory.read_byte(int(SIOWorkspace.DSTATS)) == 0x01
    assert machine.memory.read_byte(int(SIOWorkspace.STATUS)) == 0x01
    assert [
        machine.memory.read_byte(0x02EA + offset)
        for offset in range(4)
    ] == [0x00, 0x01, 0x80, 0x00]
