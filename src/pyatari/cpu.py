"""MOS 6502C CPU scaffolding for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.addressing import AddressResult, resolve_address
from pyatari.constants import RESET_VECTOR
from pyatari.memory import MemoryBus
from pyatari.opcodes import AddressMode, OPCODES, Opcode


@dataclass(slots=True)
class StatusRegister:
    negative: bool = False
    overflow: bool = False
    reserved: bool = True
    break_flag: bool = False
    decimal: bool = False
    interrupt_disable: bool = False
    zero: bool = False
    carry: bool = False

    def to_byte(self) -> int:
        return (
            (int(self.negative) << 7)
            | (int(self.overflow) << 6)
            | (int(self.reserved) << 5)
            | (int(self.break_flag) << 4)
            | (int(self.decimal) << 3)
            | (int(self.interrupt_disable) << 2)
            | (int(self.zero) << 1)
            | int(self.carry)
        )

    @classmethod
    def from_byte(cls, value: int) -> "StatusRegister":
        return cls(
            negative=bool(value & 0x80),
            overflow=bool(value & 0x40),
            reserved=True,
            break_flag=bool(value & 0x10),
            decimal=bool(value & 0x08),
            interrupt_disable=bool(value & 0x04),
            zero=bool(value & 0x02),
            carry=bool(value & 0x01),
        )


@dataclass(slots=True)
class CPU:
    memory: MemoryBus
    a: int = 0
    x: int = 0
    y: int = 0
    sp: int = 0xFD
    pc: int = 0x0000
    status: StatusRegister = field(default_factory=StatusRegister)
    cycles: int = 0
    last_opcode: Opcode | None = None
    last_address: AddressResult | None = None

    def reset(self) -> None:
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.status = StatusRegister(interrupt_disable=True)
        self.pc = self.memory.read_word(RESET_VECTOR)
        self.cycles = 0
        self.last_opcode = None
        self.last_address = None

    def fetch(self) -> int:
        value = self.memory.read_byte(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def decode(self, opcode_byte: int) -> Opcode:
        try:
            return OPCODES[opcode_byte]
        except KeyError as exc:
            msg = f"Unknown or unofficial opcode: 0x{opcode_byte:02X}"
            raise ValueError(msg) from exc

    def step(self) -> Opcode:
        opcode_byte = self.fetch()
        opcode = self.decode(opcode_byte)
        self.last_opcode = opcode
        self.last_address = self._resolve_operand(opcode)
        self.cycles += opcode.cycles + (opcode.page_cross_cycles if self.last_address.page_crossed else 0)
        return opcode

    def _resolve_operand(self, opcode: Opcode) -> AddressResult:
        if opcode.mode in {AddressMode.IMPLIED, AddressMode.ACCUMULATOR}:
            return AddressResult(address=None)
        return resolve_address(self, opcode.mode)
