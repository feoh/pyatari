"""Tests for Phase 15 input handling and fine scrolling."""

from pyatari.antic import DisplayListLine
from pyatari.constants import GTIAReadRegister, IRQBits, JoystickBits, RESET_VECTOR
from pyatari.gtia import GTIA
from pyatari.machine import Machine


def make_machine(program: bytes = bytes([0xEA]), start: int = 0x2000) -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, start)
    machine.memory.load_ram(start, program)
    machine.reset()
    machine.cpu.pc = start
    return machine


def test_keyboard_mapping_updates_kbcode():
    machine = make_machine()

    machine.press_key("a")

    assert machine.pokey.kbcode == 0x3F
    assert machine.pokey.irqst & int(IRQBits.KEYBOARD) == 0

    machine.release_key()

    assert machine.pokey.kbcode == 0xFF


def test_console_switches_are_active_low():
    machine = make_machine()

    machine.set_console_switches(start=True, select=False, option=True)

    assert machine.gtia.read_register(int(GTIAReadRegister.CONSOL)) == 0x02


def test_joystick_and_trigger_inputs_update_chips():
    machine = make_machine()

    machine.set_joystick(up=True, left=True)
    machine.set_trigger(True)

    porta = machine.pia.read_register(0xD300)
    trig0 = machine.gtia.read_register(int(GTIAReadRegister.TRIG0))

    assert porta & int(JoystickBits.STICK0_UP) == 0
    assert porta & int(JoystickBits.STICK0_LEFT) == 0
    assert trig0 == 0x00


def test_break_and_reset_queue_interrupts():
    machine = make_machine()
    machine.pokey.irqen = int(IRQBits.BREAK_KEY)

    machine.press_break()
    machine.press_reset()

    assert machine.pokey.irqst & int(IRQBits.BREAK_KEY) == 0
    assert machine.cpu.irq_pending is True
    assert machine.cpu.nmi_pending is True


def test_horizontal_fine_scroll_shifts_pixels():
    machine = make_machine()
    machine.gtia.write_register(0xD016, 0x0E)
    machine.gtia.write_register(0xD017, 0x2A)
    machine.memory.load_ram(0x3000, bytes([0b10000000]))
    line = DisplayListLine(
        instruction_address=0x2000,
        instruction=0x52,
        mode=2,
        scanlines=8,
        screen_address=0x3000,
        hscroll=True,
    )

    machine.gtia.render_scanline(line, row=0, antic_hscrol=3)

    bg = machine.gtia.color_to_rgb(machine.gtia.write_registers[0xD01A])
    fg = machine.gtia.color_to_rgb(machine.gtia.write_registers[0xD017])
    row = machine.gtia.framebuffer[0]
    assert row[0] == bg
    assert row[1] == bg
    assert row[2] == bg
    assert row[3] == fg


def test_vertical_fine_scroll_changes_glyph_row_source():
    gtia = GTIA(memory=make_machine().memory)
    gtia.write_register(0xD017, 0x3A)
    gtia.memory.load_ram(0x4000, bytes([0x00]))
    gtia.memory.write_byte(0x2000 + 2, 0x80)
    line = DisplayListLine(
        instruction_address=0x2100,
        instruction=0x22,
        mode=2,
        scanlines=8,
        screen_address=0x4000,
        vscroll=True,
    )

    gtia.render_scanline(line, row=0, antic_chbase=0x20, antic_vscrol=2)

    fg = gtia.color_to_rgb(gtia.write_registers[0xD017])
    assert gtia.framebuffer[0][0] == fg
