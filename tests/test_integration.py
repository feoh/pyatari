"""Integration tests for Phase 16 machine boot and frame flow."""

from __future__ import annotations

import sys

from pyatari.constants import (
    ANTICRegister,
    CYCLES_PER_FRAME,
    FRAMES_PER_SECOND,
    GTIAWriteRegister,
    RESET_VECTOR,
    ShadowRegister,
)
from pyatari.machine import BOOT_BASIC, BOOT_MEMO_PAD, Machine
from pyatari.rom_loader import create_test_rom_stub
from pyatari.sio import create_test_xex


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


def test_has_visible_output_detects_demo_frame():
    machine = Machine()
    machine.reset()

    machine.load_demo_screen()
    assert machine.has_visible_output() is False

    machine.run_frame(queue_audio=False)

    assert machine.has_visible_output() is True


def test_load_basic_screen_initializes_ready_prompt():
    machine = Machine()

    machine.load_basic_screen()

    row0 = read_screen_row(machine, 0)
    row2 = read_screen_row(machine, 2)

    assert machine.boot_mode == BOOT_BASIC
    assert "ATARI BASIC" in row0
    assert "READY" in row2


def test_basic_screen_print_command_writes_output_and_ready():
    machine = Machine()
    machine.load_basic_screen()

    for key in ['p', 'r', 'i', 'n', 't', 'space', '"', 'h', 'e', 'l', 'l', 'o', '"', 'return']:
        machine.press_key(key)

    row5 = read_screen_row(machine, 5)
    row6 = read_screen_row(machine, 6)

    assert "HELLO" in row5
    assert "READY" in row6


def test_basic_screen_accepts_parenthesized_print():
    machine = Machine()
    machine.load_basic_screen()

    for key in ['p', 'r', 'i', 'n', 't', '(', '"', 'h', 'e', 'l', 'l', 'o', 'space', 'w', 'o', 'r', 'l', 'd', '!', '"', ')', 'return']:
        machine.press_key(key)

    row5 = read_screen_row(machine, 5)

    assert "HELLO WORLD!" in row5


def test_basic_screen_can_run_print_goto_loop():
    machine = Machine()
    machine.load_basic_screen()

    program = ['1', '0', 'space', 'p', 'r', 'i', 'n', 't', 'space', '"', 'h', 'e', 'l', 'l', 'o', '"', 'space', ':', 'space', 'g', 'o', 't', 'o', 'space', '1', '0', 'return']
    for key in program:
        machine.press_key(key)
    for key in ['r', 'u', 'n', 'return']:
        machine.press_key(key)

    machine.run_frame(queue_audio=False)

    row7 = read_screen_row(machine, 7)

    assert machine.boot_running is True
    assert "HELLO" in row7


def test_basic_screen_preserves_numeric_input_codes():
    machine = Machine()
    machine.load_basic_screen()

    for key in ['1', '0', 'space', 'g', 'o', 't', 'o']:
        machine.press_key(key)

    row4 = read_screen_row(machine, 4)

    assert "10 GOTO" in row4


def test_basic_screen_list_displays_program_lines():
    machine = Machine()
    machine.load_basic_screen()

    for key in ['1', '0', 'space', 'p', 'r', 'i', 'n', 't', 'space', '"', 'h', 'i', '"', 'return']:
        machine.press_key(key)
    for key in ['2', '0', 'space', 'g', 'o', 't', 'o', 'space', '1', '0', 'return']:
        machine.press_key(key)
    for key in ['l', 'i', 's', 't', 'return']:
        machine.press_key(key)

    row9 = read_screen_row(machine, 9)
    row10 = read_screen_row(machine, 10)

    assert '10 PRINT "HI"' in row9
    assert "20 GOTO 10" in row10


def test_memo_pad_accepts_typed_text():
    machine = Machine()
    machine.load_memo_pad_screen()

    for key in ['h', 'i', 'space', 't', 'h', 'e', 'r', 'e', 'return', 'o', 'k']:
        machine.press_key(key)

    row4 = read_screen_row(machine, 4)
    row5 = read_screen_row(machine, 5)

    assert machine.boot_mode == BOOT_MEMO_PAD
    assert "HI THERE" in row4
    assert "OK" in row5


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
        ["pyatari", "--frames", "1", "--real-rom-boot", "--rom-dir", str(rom_dir)],
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
        ["pyatari", "--frames", "1", "--real-rom-boot", "--rom-dir", str(rom_dir)],
    )
    monkeypatch.setattr(
        Machine,
        "continue_without_self_test",
        lambda self, max_steps=800_000: True,
    )

    machine_module.main()

    output = capsys.readouterr().out
    assert "post-checksum warm-start fallback" in output
