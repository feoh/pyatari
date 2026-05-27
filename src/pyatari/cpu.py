"""MOS 6502C CPU implementation for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.addressing import AddressResult, resolve_address
from pyatari.constants import IRQ_VECTOR, NMI_VECTOR, RESET_VECTOR
from pyatari.memory import MemoryBus
from pyatari.opcodes import AddressMode, OPCODES, Opcode

STACK_BASE = 0x0100

# Instructions with no operand always produce the same AddressResult.
# Allocating one shared instance avoids a dataclass construction per instruction.
_IMPLIED_OPERAND = AddressResult(address=None)
_NO_OPERAND_MODES = frozenset({AddressMode.IMPLIED, AddressMode.ACCUMULATOR})

# Processor status register bit masks (NV1BDIZC layout)
_P_N = 0x80  # Negative
_P_V = 0x40  # Overflow
_P_R = 0x20  # Reserved (always 1)
_P_B = 0x10  # Break
_P_D = 0x08  # Decimal
_P_I = 0x04  # Interrupt Disable
_P_Z = 0x02  # Zero
_P_C = 0x01  # Carry


@dataclass(slots=True)
class StatusRegister:
    """Standalone (detached) status register — used for construction and serialization.

    When obtained via ``CPU.status``, a ``_StatusProxy`` is returned instead.
    That proxy writes flag changes immediately back to ``CPU.p``.  Standalone
    ``StatusRegister`` objects are still used for:
      - direct construction in tests: ``StatusRegister(carry=True)``
      - the ``CPU.status`` setter: ``cpu.status = StatusRegister(...)``
      - ``to_byte()`` / ``from_byte()`` serialization
    """

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


class _StatusProxy:
    """A live proxy that reads/writes individual flags directly on ``CPU.p``.

    Returned by ``CPU.status`` so that code like ``cpu.status.carry = True``
    continues to work correctly after the internal representation was changed
    from a ``StatusRegister`` dataclass field to a packed integer ``p``.

    All attribute reads/writes are forwarded to bit operations on the owning
    CPU's ``p`` field.  ``to_byte()`` and ``from_byte()`` delegate to
    ``StatusRegister`` so existing serialization code keeps working.
    """

    __slots__ = ("_cpu",)

    def __init__(self, cpu: object) -> None:
        object.__setattr__(self, "_cpu", cpu)

    # ---- read ----

    @property  # type: ignore[misc]
    def negative(self) -> bool:
        return bool(object.__getattribute__(self, "_cpu").p & _P_N)

    @property  # type: ignore[misc]
    def overflow(self) -> bool:
        return bool(object.__getattribute__(self, "_cpu").p & _P_V)

    @property  # type: ignore[misc]
    def reserved(self) -> bool:
        return True  # always 1 on the 6502

    @property  # type: ignore[misc]
    def break_flag(self) -> bool:
        return bool(object.__getattribute__(self, "_cpu").p & _P_B)

    @property  # type: ignore[misc]
    def decimal(self) -> bool:
        return bool(object.__getattribute__(self, "_cpu").p & _P_D)

    @property  # type: ignore[misc]
    def interrupt_disable(self) -> bool:
        return bool(object.__getattribute__(self, "_cpu").p & _P_I)

    @property  # type: ignore[misc]
    def zero(self) -> bool:
        return bool(object.__getattribute__(self, "_cpu").p & _P_Z)

    @property  # type: ignore[misc]
    def carry(self) -> bool:
        return bool(object.__getattribute__(self, "_cpu").p & _P_C)

    # ---- write ----

    @negative.setter  # type: ignore[misc]
    def negative(self, value: bool) -> None:
        cpu = object.__getattribute__(self, "_cpu")
        if value:
            cpu.p |= _P_N
        else:
            cpu.p &= ~_P_N & 0xFF

    @overflow.setter  # type: ignore[misc]
    def overflow(self, value: bool) -> None:
        cpu = object.__getattribute__(self, "_cpu")
        if value:
            cpu.p |= _P_V
        else:
            cpu.p &= ~_P_V & 0xFF

    @break_flag.setter  # type: ignore[misc]
    def break_flag(self, value: bool) -> None:
        cpu = object.__getattribute__(self, "_cpu")
        if value:
            cpu.p |= _P_B
        else:
            cpu.p &= ~_P_B & 0xFF

    @decimal.setter  # type: ignore[misc]
    def decimal(self, value: bool) -> None:
        cpu = object.__getattribute__(self, "_cpu")
        if value:
            cpu.p |= _P_D
        else:
            cpu.p &= ~_P_D & 0xFF

    @interrupt_disable.setter  # type: ignore[misc]
    def interrupt_disable(self, value: bool) -> None:
        cpu = object.__getattribute__(self, "_cpu")
        if value:
            cpu.p |= _P_I
        else:
            cpu.p &= ~_P_I & 0xFF

    @zero.setter  # type: ignore[misc]
    def zero(self, value: bool) -> None:
        cpu = object.__getattribute__(self, "_cpu")
        if value:
            cpu.p |= _P_Z
        else:
            cpu.p &= ~_P_Z & 0xFF

    @carry.setter  # type: ignore[misc]
    def carry(self, value: bool) -> None:
        cpu = object.__getattribute__(self, "_cpu")
        if value:
            cpu.p |= _P_C
        else:
            cpu.p &= ~_P_C & 0xFF

    # ---- serialization compat ----

    def to_byte(self) -> int:
        return object.__getattribute__(self, "_cpu").p

    @staticmethod
    def from_byte(value: int) -> "StatusRegister":
        return StatusRegister.from_byte(value)


# ---------------------------------------------------------------------------
# Two-class design: slots=True dataclass base + property-bearing subclass.
# Python does not allow properties on a slots=True dataclass directly, so we
# split into _CPUBase (all primitive fields) and CPU (adds the `status`
# property as a compatibility shim for external code that still reads/writes
# individual flag attributes like cpu.status.carry = True).
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _CPUBase:
    memory: MemoryBus
    a: int = 0
    x: int = 0
    y: int = 0
    sp: int = 0xFD
    pc: int = 0x0000
    p: int = _P_R           # packed status byte: NV1BDIZC, reserved always 1
    cycles: int = 0
    last_opcode: object = None
    last_address: object = None
    irq_pending: bool = False
    nmi_pending: bool = False
    _dispatch: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        pass  # CPU subclass overrides this


class CPU(_CPUBase):
    """MOS 6502C CPU with packed status register and dispatch-table execution."""

    __slots__ = ()

    def __post_init__(self) -> None:
        # Build per-mnemonic dispatch table at construction time so _execute
        # is a single dict lookup instead of a 60+ if/elif chain.
        self._dispatch = {
            "ADC": self._exec_adc,
            "AND": self._exec_and,
            "ASL": self._exec_asl,
            "BCC": self._exec_bcc,
            "BCS": self._exec_bcs,
            "BEQ": self._exec_beq,
            "BIT": self._exec_bit,
            "BMI": self._exec_bmi,
            "BNE": self._exec_bne,
            "BPL": self._exec_bpl,
            "BRK": self._exec_brk,
            "BVC": self._exec_bvc,
            "BVS": self._exec_bvs,
            "CLC": self._exec_clc,
            "CLD": self._exec_cld,
            "CLI": self._exec_cli,
            "CLV": self._exec_clv,
            "CMP": self._exec_cmp,
            "CPX": self._exec_cpx,
            "CPY": self._exec_cpy,
            "DCP": self._exec_dcp,
            "DEC": self._exec_dec,
            "DEX": self._exec_dex,
            "DEY": self._exec_dey,
            "EOR": self._exec_eor,
            "INC": self._exec_inc,
            "INX": self._exec_inx,
            "INY": self._exec_iny,
            "ISB": self._exec_isb,
            "JMP": self._exec_jmp,
            "JSR": self._exec_jsr,
            "LAX": self._exec_lax,
            "LDA": self._exec_lda,
            "LDX": self._exec_ldx,
            "LDY": self._exec_ldy,
            "LSR": self._exec_lsr,
            "NOP": self._exec_nop,
            "ORA": self._exec_ora,
            "PHA": self._exec_pha,
            "PHP": self._exec_php,
            "PLA": self._exec_pla,
            "PLP": self._exec_plp,
            "RLA": self._exec_rla,
            "ROL": self._exec_rol,
            "ROR": self._exec_ror,
            "RRA": self._exec_rra,
            "RTI": self._exec_rti,
            "RTS": self._exec_rts,
            "SAX": self._exec_sax,
            "SBC": self._exec_sbc,
            "SEC": self._exec_sec,
            "SED": self._exec_sed,
            "SEI": self._exec_sei,
            "SLO": self._exec_slo,
            "SRE": self._exec_sre,
            "STA": self._exec_sta,
            "STX": self._exec_stx,
            "STY": self._exec_sty,
            "TAX": self._exec_tax,
            "TAY": self._exec_tay,
            "TSX": self._exec_tsx,
            "TXA": self._exec_txa,
            "TXS": self._exec_txs,
            "TYA": self._exec_tya,
        }

    # ------------------------------------------------------------------
    # status property: compatibility shim for external code that reads or
    # writes individual flag attributes (e.g. cpu.status.carry = True).
    # Internally all flag operations work directly on self.p (int).
    # ------------------------------------------------------------------

    @property
    def status(self) -> _StatusProxy:
        """Return a live proxy that reads/writes flags directly on self.p.

        This means ``cpu.status.carry = True`` is equivalent to
        ``cpu.p |= _P_C``, maintaining full backward compatibility with all
        code that mutates individual status flags through the property.
        """
        return _StatusProxy(self)

    @status.setter
    def status(self, value: StatusRegister) -> None:
        self.p = value.to_byte() | _P_R

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.p = _P_R | _P_I  # 0x24 — reserved always set, interrupts disabled
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

        if self.irq_pending and not (self.p & _P_I):
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
        if opcode.mode in _NO_OPERAND_MODES:
            return _IMPLIED_OPERAND
        return resolve_address(self, opcode.mode)

    def run_steps(self, n: int) -> list[Opcode]:
        return [self.step() for _ in range(n)]

    def run_until(self, address: int, max_steps: int = 100_000) -> int:
        address &= 0xFFFF
        if self.pc == address:
            return 0
        for executed in range(1, max_steps + 1):
            self.step()
            if self.pc == address:
                return executed
        msg = f"CPU did not reach address {address:#06x} within {max_steps} steps"
        raise TimeoutError(msg)

    def irq(self) -> None:
        self.irq_pending = True

    def nmi(self) -> None:
        self.nmi_pending = True

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _execute(self, opcode: Opcode, operand: AddressResult) -> None:
        self._dispatch[opcode.mnemonic](opcode, operand)

    # ------------------------------------------------------------------
    # Operand helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Flag helpers — all operate on self.p (int) directly
    # ------------------------------------------------------------------

    def _update_nz(self, value: int) -> None:
        # 0x7D = ~(_P_N | _P_Z) = 0b01111101; clears bits 7 and 1, keeps all others.
        value &= 0xFF
        self.p = (self.p & 0x7D) | (value & 0x80) | (0x02 if value == 0 else 0)

    def _compare(self, register: int, value: int) -> None:
        result = (register - value) & 0x1FF
        rb = result & 0xFF
        # 0x7C = ~(_P_N | _P_Z | _P_C); clears N, Z, C; keeps V, R, B, D, I.
        self.p = (
            (self.p & 0x7C)
            | (rb & 0x80)
            | (0x02 if rb == 0 else 0)
            | (0x01 if register >= value else 0)
        )

    # ------------------------------------------------------------------
    # Stack helpers — bypass the full memory dispatch because the stack
    # page (0x0100-0x01FF) is always plain RAM with no registered handlers.
    # ------------------------------------------------------------------

    def _push_byte(self, value: int) -> None:
        self.memory.ram[STACK_BASE + self.sp] = value & 0xFF
        self.sp = (self.sp - 1) & 0xFF

    def _pop_byte(self) -> int:
        self.sp = (self.sp + 1) & 0xFF
        return self.memory.ram[STACK_BASE + self.sp]

    def _push_word(self, value: int) -> None:
        self._push_byte((value >> 8) & 0xFF)
        self._push_byte(value & 0xFF)

    def _pop_word(self) -> int:
        low = self._pop_byte()
        high = self._pop_byte()
        return low | (high << 8)

    # ------------------------------------------------------------------
    # Interrupt service
    # ------------------------------------------------------------------

    def _service_interrupt(self, vector: int, *, break_flag: bool, cycle_cost: int) -> Opcode:
        self._push_word(self.pc)
        flags = self.p & ~_P_B
        if break_flag:
            flags |= _P_B
        self._push_byte(flags)
        self.p |= _P_I
        self.pc = self.memory.read_word(vector)
        interrupt_opcode = Opcode(0x00, "INT", AddressMode.IMPLIED, 1, cycle_cost)
        self.last_opcode = interrupt_opcode
        self.last_address = AddressResult(address=None)
        self.cycles += cycle_cost
        return interrupt_opcode

    # ------------------------------------------------------------------
    # ADC / SBC arithmetic helpers
    # ------------------------------------------------------------------

    def _adc(self, value: int) -> None:
        carry_in = self.p & _P_C  # already 0 or 1
        original_a = self.a
        binary_sum = original_a + value + carry_in

        if self.p & _P_D:
            low = (original_a & 0x0F) + (value & 0x0F) + carry_in
            carry_low = 0
            if low > 9:
                low += 6
                carry_low = 1
            high = (original_a >> 4) + (value >> 4) + carry_low
            if high > 9:
                high += 6
            result = ((high << 4) | (low & 0x0F)) & 0xFF
            new_carry = 0x01 if high > 15 else 0
        else:
            result = binary_sum & 0xFF
            new_carry = 0x01 if binary_sum > 0xFF else 0

        overflow = 0x40 if (~(original_a ^ value) & (original_a ^ (binary_sum & 0xFF)) & 0x80) != 0 else 0
        self.a = result
        # 0x3C = ~(_P_N | _P_V | _P_Z | _P_C) — keeps R, B, D, I
        self.p = (self.p & 0x3C) | new_carry | overflow | (result & 0x80) | (0x02 if result == 0 else 0)

    def _sbc(self, value: int) -> None:
        carry_in = self.p & _P_C  # already 0 or 1
        original_a = self.a
        binary_diff = original_a - value - (1 - carry_in)
        result = binary_diff & 0xFF

        if self.p & _P_D:
            low = (original_a & 0x0F) - (value & 0x0F) - (1 - carry_in)
            borrow = 0
            if low < 0:
                low -= 6
                borrow = 1
            high = (original_a >> 4) - (value >> 4) - borrow
            if high < 0:
                high -= 6
            result = ((high << 4) | (low & 0x0F)) & 0xFF

        new_carry = 0x01 if binary_diff >= 0 else 0
        overflow = 0x40 if ((original_a ^ value) & (original_a ^ result) & 0x80) != 0 else 0
        self.a = result
        # 0x3C = ~(_P_N | _P_V | _P_Z | _P_C) — keeps R, B, D, I
        self.p = (self.p & 0x3C) | new_carry | overflow | (result & 0x80) | (0x02 if result == 0 else 0)

    # ------------------------------------------------------------------
    # Per-mnemonic handlers
    # Each takes (self, opcode: Opcode, operand: AddressResult) -> None
    # ------------------------------------------------------------------

    # -- Loads --

    def _exec_lda(self, opcode: Opcode, operand: AddressResult) -> None:
        self.a = self._read_operand(opcode.mode, operand)
        v = self.a
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_ldx(self, opcode: Opcode, operand: AddressResult) -> None:
        self.x = self._read_operand(opcode.mode, operand)
        v = self.x
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_ldy(self, opcode: Opcode, operand: AddressResult) -> None:
        self.y = self._read_operand(opcode.mode, operand)
        v = self.y
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_lax(self, opcode: Opcode, operand: AddressResult) -> None:
        v = self._read_operand(opcode.mode, operand)
        self.a = v
        self.x = v
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    # -- Stores --

    def _exec_sta(self, opcode: Opcode, operand: AddressResult) -> None:
        self._write_operand(opcode.mode, operand, self.a)

    def _exec_stx(self, opcode: Opcode, operand: AddressResult) -> None:
        self._write_operand(opcode.mode, operand, self.x)

    def _exec_sty(self, opcode: Opcode, operand: AddressResult) -> None:
        self._write_operand(opcode.mode, operand, self.y)

    def _exec_sax(self, opcode: Opcode, operand: AddressResult) -> None:
        self._write_operand(opcode.mode, operand, self.a & self.x)

    # -- Register transfers --

    def _exec_tax(self, opcode: Opcode, operand: AddressResult) -> None:
        self.x = self.a
        v = self.x
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_tay(self, opcode: Opcode, operand: AddressResult) -> None:
        self.y = self.a
        v = self.y
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_txa(self, opcode: Opcode, operand: AddressResult) -> None:
        self.a = self.x
        v = self.a
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_tya(self, opcode: Opcode, operand: AddressResult) -> None:
        self.a = self.y
        v = self.a
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_tsx(self, opcode: Opcode, operand: AddressResult) -> None:
        self.x = self.sp
        v = self.x
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_txs(self, opcode: Opcode, operand: AddressResult) -> None:
        self.sp = self.x  # TXS does not affect flags

    # -- Stack --

    def _exec_pha(self, opcode: Opcode, operand: AddressResult) -> None:
        self._push_byte(self.a)

    def _exec_php(self, opcode: Opcode, operand: AddressResult) -> None:
        # B flag is always set when status is pushed to the stack
        self._push_byte(self.p | _P_B)

    def _exec_pla(self, opcode: Opcode, operand: AddressResult) -> None:
        self.a = self._pop_byte()
        v = self.a
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_plp(self, opcode: Opcode, operand: AddressResult) -> None:
        # B flag is cleared when pulled from stack; reserved bit always stays 1
        self.p = (self._pop_byte() & ~_P_B) | _P_R

    # -- Logical --

    def _exec_ora(self, opcode: Opcode, operand: AddressResult) -> None:
        self.a = (self.a | self._read_operand(opcode.mode, operand)) & 0xFF
        v = self.a
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_and(self, opcode: Opcode, operand: AddressResult) -> None:
        self.a = (self.a & self._read_operand(opcode.mode, operand)) & 0xFF
        v = self.a
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_eor(self, opcode: Opcode, operand: AddressResult) -> None:
        self.a = (self.a ^ self._read_operand(opcode.mode, operand)) & 0xFF
        v = self.a
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    # -- Arithmetic --

    def _exec_adc(self, opcode: Opcode, operand: AddressResult) -> None:
        self._adc(self._read_operand(opcode.mode, operand))

    def _exec_sbc(self, opcode: Opcode, operand: AddressResult) -> None:
        self._sbc(self._read_operand(opcode.mode, operand))

    # -- Compare --

    def _exec_cmp(self, opcode: Opcode, operand: AddressResult) -> None:
        self._compare(self.a, self._read_operand(opcode.mode, operand))

    def _exec_cpx(self, opcode: Opcode, operand: AddressResult) -> None:
        self._compare(self.x, self._read_operand(opcode.mode, operand))

    def _exec_cpy(self, opcode: Opcode, operand: AddressResult) -> None:
        self._compare(self.y, self._read_operand(opcode.mode, operand))

    # -- Increment / Decrement --

    def _exec_inx(self, opcode: Opcode, operand: AddressResult) -> None:
        self.x = (self.x + 1) & 0xFF
        v = self.x
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_iny(self, opcode: Opcode, operand: AddressResult) -> None:
        self.y = (self.y + 1) & 0xFF
        v = self.y
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_dex(self, opcode: Opcode, operand: AddressResult) -> None:
        self.x = (self.x - 1) & 0xFF
        v = self.x
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_dey(self, opcode: Opcode, operand: AddressResult) -> None:
        self.y = (self.y - 1) & 0xFF
        v = self.y
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_inc(self, opcode: Opcode, operand: AddressResult) -> None:
        v = (self._read_operand(opcode.mode, operand) + 1) & 0xFF
        self._write_operand(opcode.mode, operand, v)
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_dec(self, opcode: Opcode, operand: AddressResult) -> None:
        v = (self._read_operand(opcode.mode, operand) - 1) & 0xFF
        self._write_operand(opcode.mode, operand, v)
        self.p = (self.p & 0x7D) | (v & 0x80) | (0x02 if v == 0 else 0)

    # -- Undocumented combined ops --

    def _exec_dcp(self, opcode: Opcode, operand: AddressResult) -> None:
        # DEC memory, then CMP A with result
        v = (self._read_operand(opcode.mode, operand) - 1) & 0xFF
        self._write_operand(opcode.mode, operand, v)
        self._compare(self.a, v)

    def _exec_isb(self, opcode: Opcode, operand: AddressResult) -> None:
        # INC memory, then SBC A with result
        v = (self._read_operand(opcode.mode, operand) + 1) & 0xFF
        self._write_operand(opcode.mode, operand, v)
        self._sbc(v)

    # -- BIT test --

    def _exec_bit(self, opcode: Opcode, operand: AddressResult) -> None:
        value = self._read_operand(opcode.mode, operand)
        # N = bit 7 of memory, V = bit 6 of memory, Z = (A & M) == 0
        # 0x3D = ~(_P_N | _P_V | _P_Z); 0xC0 picks up bits 7+6 from value
        self.p = (self.p & 0x3D) | (value & 0xC0) | (0x02 if (self.a & value) == 0 else 0)

    # -- Shifts and rotates --

    def _exec_asl(self, opcode: Opcode, operand: AddressResult) -> None:
        value = self.a if opcode.mode == AddressMode.ACCUMULATOR else self._read_operand(opcode.mode, operand)
        new_carry = (value >> 7) & 1
        result = (value << 1) & 0xFF
        self._write_operand(opcode.mode, operand, result)
        # 0x7C = ~(_P_N | _P_Z | _P_C)
        self.p = (self.p & 0x7C) | new_carry | (result & 0x80) | (0x02 if result == 0 else 0)

    def _exec_lsr(self, opcode: Opcode, operand: AddressResult) -> None:
        value = self.a if opcode.mode == AddressMode.ACCUMULATOR else self._read_operand(opcode.mode, operand)
        new_carry = value & 1
        result = (value >> 1) & 0xFF
        self._write_operand(opcode.mode, operand, result)
        # 0x7C = ~(_P_N | _P_Z | _P_C); result of LSR always has N=0
        self.p = (self.p & 0x7C) | new_carry | (0x02 if result == 0 else 0)

    def _exec_rol(self, opcode: Opcode, operand: AddressResult) -> None:
        value = self.a if opcode.mode == AddressMode.ACCUMULATOR else self._read_operand(opcode.mode, operand)
        carry_in = self.p & _P_C
        new_carry = (value >> 7) & 1
        result = ((value << 1) | carry_in) & 0xFF
        self._write_operand(opcode.mode, operand, result)
        self.p = (self.p & 0x7C) | new_carry | (result & 0x80) | (0x02 if result == 0 else 0)

    def _exec_ror(self, opcode: Opcode, operand: AddressResult) -> None:
        value = self.a if opcode.mode == AddressMode.ACCUMULATOR else self._read_operand(opcode.mode, operand)
        carry_in = self.p & _P_C
        new_carry = value & 1
        result = ((value >> 1) | (carry_in << 7)) & 0xFF
        self._write_operand(opcode.mode, operand, result)
        self.p = (self.p & 0x7C) | new_carry | (result & 0x80) | (0x02 if result == 0 else 0)

    # -- Composite (undocumented) shift+logic ops --

    def _exec_slo(self, opcode: Opcode, operand: AddressResult) -> None:
        # ASL memory, then ORA A
        value = self._read_operand(opcode.mode, operand)
        new_carry = (value >> 7) & 1
        shifted = (value << 1) & 0xFF
        self._write_operand(opcode.mode, operand, shifted)
        self.a = (self.a | shifted) & 0xFF
        v = self.a
        self.p = (self.p & 0x7C) | new_carry | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_rla(self, opcode: Opcode, operand: AddressResult) -> None:
        # ROL memory, then AND A
        value = self._read_operand(opcode.mode, operand)
        carry_in = self.p & _P_C
        new_carry = (value >> 7) & 1
        rotated = ((value << 1) | carry_in) & 0xFF
        self._write_operand(opcode.mode, operand, rotated)
        self.a = (self.a & rotated) & 0xFF
        v = self.a
        self.p = (self.p & 0x7C) | new_carry | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_sre(self, opcode: Opcode, operand: AddressResult) -> None:
        # LSR memory, then EOR A
        value = self._read_operand(opcode.mode, operand)
        new_carry = value & 1
        shifted = (value >> 1) & 0xFF
        self._write_operand(opcode.mode, operand, shifted)
        self.a = (self.a ^ shifted) & 0xFF
        v = self.a
        # LSR output always has N=0; use 0x7C to clear N,Z,C then recompute
        self.p = (self.p & 0x7C) | new_carry | (v & 0x80) | (0x02 if v == 0 else 0)

    def _exec_rra(self, opcode: Opcode, operand: AddressResult) -> None:
        # ROR memory, then ADC A
        value = self._read_operand(opcode.mode, operand)
        carry_in = self.p & _P_C
        new_carry = value & 1
        rotated = ((value >> 1) | (carry_in << 7)) & 0xFF
        self._write_operand(opcode.mode, operand, rotated)
        # Temporarily install the new carry so _adc sees the correct carry-in
        self.p = (self.p & 0xFE) | new_carry
        self._adc(rotated)

    # -- Branches --
    # Each branch has its own handler to avoid a dict lookup inside the method.

    def _exec_bpl(self, opcode: Opcode, operand: AddressResult) -> None:
        if not (self.p & _P_N):
            self.pc = operand.address  # type: ignore[assignment]

    def _exec_bmi(self, opcode: Opcode, operand: AddressResult) -> None:
        if self.p & _P_N:
            self.pc = operand.address  # type: ignore[assignment]

    def _exec_bvc(self, opcode: Opcode, operand: AddressResult) -> None:
        if not (self.p & _P_V):
            self.pc = operand.address  # type: ignore[assignment]

    def _exec_bvs(self, opcode: Opcode, operand: AddressResult) -> None:
        if self.p & _P_V:
            self.pc = operand.address  # type: ignore[assignment]

    def _exec_bcc(self, opcode: Opcode, operand: AddressResult) -> None:
        if not (self.p & _P_C):
            self.pc = operand.address  # type: ignore[assignment]

    def _exec_bcs(self, opcode: Opcode, operand: AddressResult) -> None:
        if self.p & _P_C:
            self.pc = operand.address  # type: ignore[assignment]

    def _exec_bne(self, opcode: Opcode, operand: AddressResult) -> None:
        if not (self.p & _P_Z):
            self.pc = operand.address  # type: ignore[assignment]

    def _exec_beq(self, opcode: Opcode, operand: AddressResult) -> None:
        if self.p & _P_Z:
            self.pc = operand.address  # type: ignore[assignment]

    # -- Jumps --

    def _exec_jmp(self, opcode: Opcode, operand: AddressResult) -> None:
        assert operand.address is not None
        self.pc = operand.address

    def _exec_jsr(self, opcode: Opcode, operand: AddressResult) -> None:
        assert operand.address is not None
        self._push_word((self.pc - 1) & 0xFFFF)
        self.pc = operand.address

    def _exec_rts(self, opcode: Opcode, operand: AddressResult) -> None:
        self.pc = (self._pop_word() + 1) & 0xFFFF

    def _exec_rti(self, opcode: Opcode, operand: AddressResult) -> None:
        # B flag cleared on pull; reserved bit always 1
        self.p = (self._pop_byte() & ~_P_B) | _P_R
        self.pc = self._pop_word()

    def _exec_brk(self, opcode: Opcode, operand: AddressResult) -> None:
        self._push_word((self.pc + 1) & 0xFFFF)
        self._push_byte(self.p | _P_B)
        self.p |= _P_I
        self.pc = self.memory.read_word(IRQ_VECTOR)

    # -- Flag operations (one handler per flag for zero-overhead dispatch) --

    def _exec_clc(self, opcode: Opcode, operand: AddressResult) -> None:
        self.p &= 0xFE  # ~_P_C

    def _exec_sec(self, opcode: Opcode, operand: AddressResult) -> None:
        self.p |= _P_C

    def _exec_cli(self, opcode: Opcode, operand: AddressResult) -> None:
        self.p &= 0xFB  # ~_P_I

    def _exec_sei(self, opcode: Opcode, operand: AddressResult) -> None:
        self.p |= _P_I

    def _exec_clv(self, opcode: Opcode, operand: AddressResult) -> None:
        self.p &= 0xBF  # ~_P_V

    def _exec_cld(self, opcode: Opcode, operand: AddressResult) -> None:
        self.p &= 0xF7  # ~_P_D

    def _exec_sed(self, opcode: Opcode, operand: AddressResult) -> None:
        self.p |= _P_D

    # -- NOP --

    def _exec_nop(self, opcode: Opcode, operand: AddressResult) -> None:
        pass
