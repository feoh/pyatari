"""6502 addressing mode helpers."""

from __future__ import annotations

from dataclasses import dataclass

from pyatari.opcodes import AddressMode


@dataclass(frozen=True, slots=True)
class AddressResult:
    address: int | None
    page_crossed: bool = False


def resolve_address(cpu: object, mode: AddressMode) -> AddressResult:
    """Resolve an effective address for the current instruction.

    The CPU is expected to expose ``pc``, ``x``, ``y``, and ``memory`` with a
    ``read_byte`` method. The program counter is advanced past operand bytes.
    """
    memory = cpu.memory

    if mode in {AddressMode.IMPLIED, AddressMode.ACCUMULATOR}:
        return AddressResult(address=None)

    if mode == AddressMode.IMMEDIATE:
        address = cpu.pc
        cpu.pc = (cpu.pc + 1) & 0xFFFF
        return AddressResult(address=address)

    if mode == AddressMode.ZERO_PAGE:
        address = memory.read_byte(cpu.pc)
        cpu.pc = (cpu.pc + 1) & 0xFFFF
        return AddressResult(address=address)

    if mode == AddressMode.ZERO_PAGE_X:
        base = memory.read_byte(cpu.pc)
        cpu.pc = (cpu.pc + 1) & 0xFFFF
        return AddressResult(address=(base + cpu.x) & 0xFF)

    if mode == AddressMode.ZERO_PAGE_Y:
        base = memory.read_byte(cpu.pc)
        cpu.pc = (cpu.pc + 1) & 0xFFFF
        return AddressResult(address=(base + cpu.y) & 0xFF)

    if mode == AddressMode.RELATIVE:
        offset = memory.read_byte(cpu.pc)
        cpu.pc = (cpu.pc + 1) & 0xFFFF
        if offset & 0x80:
            offset -= 0x100
        return AddressResult(address=(cpu.pc + offset) & 0xFFFF)

    if mode == AddressMode.INDEXED_INDIRECT:
        zp_base = memory.read_byte(cpu.pc)
        cpu.pc = (cpu.pc + 1) & 0xFFFF
        pointer = (zp_base + cpu.x) & 0xFF
        low = memory.read_byte(pointer)
        high = memory.read_byte((pointer + 1) & 0xFF)
        return AddressResult(address=low | (high << 8))

    if mode == AddressMode.INDIRECT_INDEXED:
        pointer = memory.read_byte(cpu.pc)
        cpu.pc = (cpu.pc + 1) & 0xFFFF
        low = memory.read_byte(pointer)
        high = memory.read_byte((pointer + 1) & 0xFF)
        base_addr = low | (high << 8)
        address = (base_addr + cpu.y) & 0xFFFF
        return AddressResult(
            address=address,
            page_crossed=(base_addr & 0xFF00) != (address & 0xFF00),
        )

    low = memory.read_byte(cpu.pc)
    high = memory.read_byte((cpu.pc + 1) & 0xFFFF)
    cpu.pc = (cpu.pc + 2) & 0xFFFF
    base = low | (high << 8)

    if mode == AddressMode.ABSOLUTE:
        return AddressResult(address=base)

    if mode == AddressMode.ABSOLUTE_X:
        address = (base + cpu.x) & 0xFFFF
        return AddressResult(
            address=address,
            page_crossed=(base & 0xFF00) != (address & 0xFF00),
        )

    if mode == AddressMode.ABSOLUTE_Y:
        address = (base + cpu.y) & 0xFFFF
        return AddressResult(
            address=address,
            page_crossed=(base & 0xFF00) != (address & 0xFF00),
        )

    if mode == AddressMode.INDIRECT:
        low = memory.read_byte(base)
        high = memory.read_byte((base & 0xFF00) | ((base + 1) & 0x00FF))
        return AddressResult(address=low | (high << 8))

    msg = f"Unsupported address mode: {mode}"
    raise ValueError(msg)
