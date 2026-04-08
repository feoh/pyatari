"""Interactive debugger helpers for PyAtari."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from pyatari.disassembler import disassemble
from pyatari.machine import Machine


@dataclass(slots=True)
class RegisterSnapshot:
    pc: int
    a: int
    x: int
    y: int
    sp: int
    status: int
    cycles: int


@dataclass(slots=True)
class TraceEntry:
    pc: int
    text: str
    cycles: int


@dataclass(slots=True)
class Debugger:
    machine: Machine
    breakpoints: set[int] = field(default_factory=set)
    watchpoints: set[int] = field(default_factory=set)
    history_limit: int = 128
    history: deque[TraceEntry] = field(default_factory=lambda: deque(maxlen=128))
    last_stop_reason: str | None = None

    def __post_init__(self) -> None:
        self.history = deque(maxlen=self.history_limit)

    def snapshot_registers(self) -> RegisterSnapshot:
        cpu = self.machine.cpu
        return RegisterSnapshot(
            pc=cpu.pc,
            a=cpu.a,
            x=cpu.x,
            y=cpu.y,
            sp=cpu.sp,
            status=cpu.status.to_byte(),
            cycles=cpu.cycles,
        )

    def step(self) -> TraceEntry:
        entry = self._trace_current_instruction()
        touched = self._watched_write_addresses()
        self.machine.step()
        self.history.append(entry)
        self.last_stop_reason = None
        if self.machine.cpu.pc in self.breakpoints:
            self.last_stop_reason = f"breakpoint at ${self.machine.cpu.pc:04X}"
        elif touched & self.watchpoints:
            address = min(touched & self.watchpoints)
            self.last_stop_reason = f"watchpoint at ${address:04X}"
        return entry

    def continue_execution(self, max_steps: int = 100_000) -> str:
        for _ in range(max_steps):
            self.step()
            if self.last_stop_reason is not None:
                return self.last_stop_reason
        self.last_stop_reason = "max steps reached"
        return self.last_stop_reason

    def add_breakpoint(self, address: int) -> None:
        self.breakpoints.add(address & 0xFFFF)

    def remove_breakpoint(self, address: int) -> None:
        self.breakpoints.discard(address & 0xFFFF)

    def add_watchpoint(self, address: int) -> None:
        self.watchpoints.add(address & 0xFFFF)

    def remove_watchpoint(self, address: int) -> None:
        self.watchpoints.discard(address & 0xFFFF)

    def disassembly(self, start: int | None = None, lines: int = 8) -> list[str]:
        pc = self.machine.cpu.pc if start is None else (start & 0xFFFF)
        output: list[str] = []
        current = pc
        for _ in range(lines):
            text, size = disassemble(self.machine.memory, current)
            marker = "=>" if current == self.machine.cpu.pc else "  "
            output.append(f"{marker} {current:04X}: {text}")
            current = (current + size) & 0xFFFF
        return output

    def memory_dump(self, start: int, length: int = 16) -> str:
        return self.machine.memory.hex_dump(start, length)

    def chip_state(self) -> dict[str, dict[str, int]]:
        return {
            "antic": {
                "scanline": self.machine.antic.scanline,
                "vcount": self.machine.antic.read_register(0xD40B),
            },
            "gtia": {
                "prior": self.machine.gtia.write_registers.get(0xD01B, 0),
                "gractl": self.machine.gtia.write_registers.get(0xD01D, 0),
            },
            "pokey": {
                "irqen": self.machine.pokey.irqen,
                "irqst": self.machine.pokey.irqst,
            },
            "pia": {
                "porta": self.machine.pia.read_register(0xD300),
                "portb": self.machine.pia.read_register(0xD302),
            },
        }

    def _trace_current_instruction(self) -> TraceEntry:
        pc = self.machine.cpu.pc
        text, _ = disassemble(self.machine.memory, pc)
        return TraceEntry(pc=pc, text=text, cycles=self.machine.cpu.cycles)

    def _watched_write_addresses(self) -> set[int]:
        opcode = self.machine.memory.read_byte(self.machine.cpu.pc)
        if opcode in {0x8D, 0x8E, 0x8C, 0xEE, 0xCE}:  # STA/STX/STY/INC/DEC abs
            low = self.machine.memory.read_byte((self.machine.cpu.pc + 1) & 0xFFFF)
            high = self.machine.memory.read_byte((self.machine.cpu.pc + 2) & 0xFFFF)
            return {low | (high << 8)}
        if opcode in {0x85, 0x86, 0x84, 0xE6, 0xC6}:  # zp writes
            return {self.machine.memory.read_byte((self.machine.cpu.pc + 1) & 0xFFFF)}
        return set()
