"""Tests for the PyAtari debugger."""

from __future__ import annotations

from pyatari.debugger import Debugger
from pyatari.machine import Machine
from pyatari.constants import RESET_VECTOR


def make_machine(program: bytes, start: int = 0x2000) -> Machine:
    machine = Machine()
    machine.memory.write_word(RESET_VECTOR, start)
    machine.memory.load_ram(start, program)
    machine.reset()
    machine.cpu.pc = start
    return machine


def test_step_advances_pc_and_records_history():
    debugger = Debugger(make_machine(bytes([0xEA, 0xEA])))

    entry = debugger.step()

    assert entry.pc == 0x2000
    assert entry.text == "NOP"
    assert debugger.machine.cpu.pc == 0x2001
    assert len(debugger.history) == 1


def test_breakpoint_stops_continue_execution():
    debugger = Debugger(make_machine(bytes([0xEA, 0xEA, 0xEA])))
    debugger.add_breakpoint(0x2002)

    reason = debugger.continue_execution()

    assert reason == "breakpoint at $2002"
    assert debugger.machine.cpu.pc == 0x2002


def test_watchpoint_triggers_on_memory_write():
    debugger = Debugger(make_machine(bytes([0xA9, 0x42, 0x8D, 0x00, 0x30])))
    debugger.add_watchpoint(0x3000)

    debugger.step()  # LDA
    reason = debugger.continue_execution()

    assert reason == "watchpoint at $3000"
    assert debugger.machine.memory.read_byte(0x3000) == 0x42


def test_disassembly_and_memory_dump_are_readable():
    debugger = Debugger(make_machine(bytes([0xA9, 0x10, 0xEA])))

    lines = debugger.disassembly(lines=2)
    dump = debugger.memory_dump(0x2000, length=3)

    assert lines[0] == "=> 2000: LDA #$10"
    assert lines[1] == "   2002: NOP"
    assert "2000:" in dump


def test_chip_state_reports_major_subsystems():
    debugger = Debugger(make_machine(bytes([0xEA])))

    state = debugger.chip_state()

    assert set(state) == {"antic", "gtia", "pokey", "pia"}
    assert "scanline" in state["antic"]
    assert "irqst" in state["pokey"]
