"""MOS 6502C CPU implementation for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.addressing import AddressResult, resolve_address
from pyatari.constants import IRQ_VECTOR, NMI_VECTOR, RESET_VECTOR
from pyatari.memory import MemoryBus
from pyatari.opcodes import AddressMode, OPCODES, Opcode

STACK_BASE = 0x0100


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
    irq_pending: bool = False
    nmi_pending: bool = False

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
        self.irq_pending = False
        self.nmi_pending = False

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
        if self.nmi_pending:
            self.nmi_pending = False
            return self._service_interrupt(NMI_VECTOR, break_flag=False, cycle_cost=7)

        if self.irq_pending and not self.status.interrupt_disable:
            self.irq_pending = False
            return self._service_interrupt(IRQ_VECTOR, break_flag=False, cycle_cost=7)

        opcode_byte = self.fetch()
        opcode = self.decode(opcode_byte)
        self.last_opcode = opcode
        self.last_address = self._resolve_operand(opcode)
        self._execute(opcode, self.last_address)
        self.cycles += opcode.cycles + (opcode.page_cross_cycles if self.last_address.page_crossed else 0)
        return opcode

    def _resolve_operand(self, opcode: Opcode) -> AddressResult:
        if opcode.mode in {AddressMode.IMPLIED, AddressMode.ACCUMULATOR}:
            return AddressResult(address=None)
        return resolve_address(self, opcode.mode)

    def _execute(self, opcode: Opcode, operand: AddressResult) -> None:
        mnemonic = opcode.mnemonic

        if mnemonic == "LDA":
            self.a = self._read_operand(opcode.mode, operand)
            self._update_nz(self.a)
        elif mnemonic == "LDX":
            self.x = self._read_operand(opcode.mode, operand)
            self._update_nz(self.x)
        elif mnemonic == "LDY":
            self.y = self._read_operand(opcode.mode, operand)
            self._update_nz(self.y)
        elif mnemonic == "STA":
            self._write_operand(opcode.mode, operand, self.a)
        elif mnemonic == "STX":
            self._write_operand(opcode.mode, operand, self.x)
        elif mnemonic == "STY":
            self._write_operand(opcode.mode, operand, self.y)
        elif mnemonic == "TAX":
            self.x = self.a
            self._update_nz(self.x)
        elif mnemonic == "TAY":
            self.y = self.a
            self._update_nz(self.y)
        elif mnemonic == "TXA":
            self.a = self.x
            self._update_nz(self.a)
        elif mnemonic == "TYA":
            self.a = self.y
            self._update_nz(self.a)
        elif mnemonic == "TSX":
            self.x = self.sp
            self._update_nz(self.x)
        elif mnemonic == "TXS":
            self.sp = self.x
        elif mnemonic == "PHA":
            self._push_byte(self.a)
        elif mnemonic == "PHP":
            self._push_byte(self.status.to_byte() | 0x10)
        elif mnemonic == "PLA":
            self.a = self._pop_byte()
            self._update_nz(self.a)
        elif mnemonic == "PLP":
            self.status = StatusRegister.from_byte(self._pop_byte())
        elif mnemonic in {"ORA", "AND", "EOR"}:
            value = self._read_operand(opcode.mode, operand)
            if mnemonic == "ORA":
                self.a |= value
            elif mnemonic == "AND":
                self.a &= value
            else:
                self.a ^= value
            self.a &= 0xFF
            self._update_nz(self.a)
        elif mnemonic == "ADC":
            self._adc(self._read_operand(opcode.mode, operand))
        elif mnemonic == "SBC":
            self._sbc(self._read_operand(opcode.mode, operand))
        elif mnemonic == "CMP":
            self._compare(self.a, self._read_operand(opcode.mode, operand))
        elif mnemonic == "CPX":
            self._compare(self.x, self._read_operand(opcode.mode, operand))
        elif mnemonic == "CPY":
            self._compare(self.y, self._read_operand(opcode.mode, operand))
        elif mnemonic == "INX":
            self.x = (self.x + 1) & 0xFF
            self._update_nz(self.x)
        elif mnemonic == "INY":
            self.y = (self.y + 1) & 0xFF
            self._update_nz(self.y)
        elif mnemonic == "DEX":
            self.x = (self.x - 1) & 0xFF
            self._update_nz(self.x)
        elif mnemonic == "DEY":
            self.y = (self.y - 1) & 0xFF
            self._update_nz(self.y)
        elif mnemonic == "INC":
            value = (self._read_operand(opcode.mode, operand) + 1) & 0xFF
            self._write_operand(opcode.mode, operand, value)
            self._update_nz(value)
        elif mnemonic == "DEC":
            value = (self._read_operand(opcode.mode, operand) - 1) & 0xFF
            self._write_operand(opcode.mode, operand, value)
            self._update_nz(value)
        elif mnemonic in {"ASL", "LSR", "ROL", "ROR"}:
            self._shift_rotate(mnemonic, opcode.mode, operand)
        elif mnemonic == "BIT":
            value = self._read_operand(opcode.mode, operand)
            self.status.zero = (self.a & value) == 0
            self.status.overflow = bool(value & 0x40)
            self.status.negative = bool(value & 0x80)
        elif mnemonic in {"BPL", "BMI", "BVC", "BVS", "BCC", "BCS", "BNE", "BEQ"}:
            self._branch(mnemonic, operand.address)
        elif mnemonic == "JMP":
            assert operand.address is not None
            self.pc = operand.address
        elif mnemonic == "JSR":
            assert operand.address is not None
            return_addr = (self.pc - 1) & 0xFFFF
            self._push_word(return_addr)
            self.pc = operand.address
        elif mnemonic == "RTS":
            self.pc = (self._pop_word() + 1) & 0xFFFF
        elif mnemonic == "RTI":
            self.status = StatusRegister.from_byte(self._pop_byte())
            self.pc = self._pop_word()
        elif mnemonic == "BRK":
            self._push_word((self.pc + 1) & 0xFFFF)
            self._push_byte(self.status.to_byte() | 0x10)
            self.status.interrupt_disable = True
            self.pc = self.memory.read_word(IRQ_VECTOR)
        elif mnemonic == "CLC":
            self.status.carry = False
        elif mnemonic == "SEC":
            self.status.carry = True
        elif mnemonic == "CLI":
            self.status.interrupt_disable = False
        elif mnemonic == "SEI":
            self.status.interrupt_disable = True
        elif mnemonic == "CLV":
            self.status.overflow = False
        elif mnemonic == "CLD":
            self.status.decimal = False
        elif mnemonic == "SED":
            self.status.decimal = True
        elif mnemonic == "NOP":
            return
        else:
            msg = f"Execution for opcode {mnemonic} is not implemented"
            raise NotImplementedError(msg)

    def _read_operand(self, mode: AddressMode, operand: AddressResult) -> int:
        if mode == AddressMode.ACCUMULATOR:
            return self.a
        if operand.address is None:
            msg = f"Mode {mode} does not have an addressable operand"
            raise ValueError(msg)
        return self.memory.read_byte(operand.address)

    def _write_operand(self, mode: AddressMode, operand: AddressResult, value: int) -> None:
        value &= 0xFF
        if mode == AddressMode.ACCUMULATOR:
            self.a = value
            return
        if operand.address is None:
            msg = f"Mode {mode} does not support writes"
            raise ValueError(msg)
        self.memory.write_byte(operand.address, value)

    def _update_nz(self, value: int) -> None:
        value &= 0xFF
        self.status.zero = value == 0
        self.status.negative = bool(value & 0x80)

    def _compare(self, register: int, value: int) -> None:
        result = (register - value) & 0x1FF
        self.status.carry = register >= value
        self.status.zero = (result & 0xFF) == 0
        self.status.negative = bool(result & 0x80)

    def _branch(self, mnemonic: str, target: int | None) -> None:
        assert target is not None
        should_branch = {
            "BPL": not self.status.negative,
            "BMI": self.status.negative,
            "BVC": not self.status.overflow,
            "BVS": self.status.overflow,
            "BCC": not self.status.carry,
            "BCS": self.status.carry,
            "BNE": not self.status.zero,
            "BEQ": self.status.zero,
        }[mnemonic]
        if should_branch:
            self.pc = target

    def _shift_rotate(self, mnemonic: str, mode: AddressMode, operand: AddressResult) -> None:
        value = self.a if mode == AddressMode.ACCUMULATOR else self._read_operand(mode, operand)
        carry_in = 1 if self.status.carry else 0

        if mnemonic == "ASL":
            self.status.carry = bool(value & 0x80)
            result = (value << 1) & 0xFF
        elif mnemonic == "LSR":
            self.status.carry = bool(value & 0x01)
            result = (value >> 1) & 0xFF
        elif mnemonic == "ROL":
            self.status.carry = bool(value & 0x80)
            result = ((value << 1) | carry_in) & 0xFF
        else:  # ROR
            self.status.carry = bool(value & 0x01)
            result = ((value >> 1) | (carry_in << 7)) & 0xFF

        self._write_operand(mode, operand, result)
        self._update_nz(result)

    def _adc(self, value: int) -> None:
        carry_in = 1 if self.status.carry else 0
        original_a = self.a
        binary_sum = original_a + value + carry_in

        if self.status.decimal:
            low = (original_a & 0x0F) + (value & 0x0F) + carry_in
            carry_low = 0
            if low > 9:
                low += 6
                carry_low = 1
            high = (original_a >> 4) + (value >> 4) + carry_low
            if high > 9:
                high += 6
            result = ((high << 4) | (low & 0x0F)) & 0xFF
            self.status.carry = high > 15
        else:
            result = binary_sum & 0xFF
            self.status.carry = binary_sum > 0xFF

        self.status.overflow = (~(original_a ^ value) & (original_a ^ (binary_sum & 0xFF)) & 0x80) != 0
        self.a = result
        self._update_nz(self.a)

    def _sbc(self, value: int) -> None:
        carry_in = 1 if self.status.carry else 0
        original_a = self.a
        binary_diff = original_a - value - (1 - carry_in)
        result = binary_diff & 0xFF

        if self.status.decimal:
            low = (original_a & 0x0F) - (value & 0x0F) - (1 - carry_in)
            borrow = 0
            if low < 0:
                low -= 6
                borrow = 1
            high = (original_a >> 4) - (value >> 4) - borrow
            if high < 0:
                high -= 6
            result = ((high << 4) | (low & 0x0F)) & 0xFF

        self.status.carry = binary_diff >= 0
        self.status.overflow = ((original_a ^ value) & (original_a ^ result) & 0x80) != 0
        self.a = result
        self._update_nz(self.a)

    def irq(self) -> None:
        self.irq_pending = True

    def nmi(self) -> None:
        self.nmi_pending = True

    def _service_interrupt(self, vector: int, *, break_flag: bool, cycle_cost: int) -> Opcode:
        self._push_word(self.pc)
        flags = self.status.to_byte() & ~0x10
        if break_flag:
            flags |= 0x10
        self._push_byte(flags)
        self.status.interrupt_disable = True
        self.pc = self.memory.read_word(vector)
        interrupt_opcode = Opcode(0x00, "INT", AddressMode.IMPLIED, 1, cycle_cost)
        self.last_opcode = interrupt_opcode
        self.last_address = AddressResult(address=None)
        self.cycles += cycle_cost
        return interrupt_opcode

    def _push_byte(self, value: int) -> None:
        self.memory.write_byte(STACK_BASE + self.sp, value & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def _pop_byte(self) -> int:
        self.sp = (self.sp + 1) & 0xFF
        return self.memory.read_byte(STACK_BASE + self.sp)

    def _push_word(self, value: int) -> None:
        self._push_byte((value >> 8) & 0xFF)
        self._push_byte(value & 0xFF)

    def _pop_word(self) -> int:
        low = self._pop_byte()
        high = self._pop_byte()
        return low | (high << 8)
