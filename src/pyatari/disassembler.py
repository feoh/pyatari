"""Simple 6502 disassembler."""

from __future__ import annotations

from pyatari.memory import MemoryBus
from pyatari.opcodes import AddressMode, OPCODES


def disassemble(memory: MemoryBus, addr: int) -> tuple[str, int]:
    opcode_byte = memory.read_byte(addr)
    opcode = OPCODES.get(opcode_byte)
    if opcode is None:
        return (f".DB ${opcode_byte:02X}", 1)

    if opcode.mode == AddressMode.IMPLIED:
        return (opcode.mnemonic, opcode.bytes)
    if opcode.mode == AddressMode.ACCUMULATOR:
        return (f"{opcode.mnemonic} A", opcode.bytes)

    op1 = memory.read_byte((addr + 1) & 0xFFFF)
    if opcode.mode == AddressMode.IMMEDIATE:
        return (f"{opcode.mnemonic} #${op1:02X}", opcode.bytes)
    if opcode.mode == AddressMode.ZERO_PAGE:
        return (f"{opcode.mnemonic} ${op1:02X}", opcode.bytes)
    if opcode.mode == AddressMode.ZERO_PAGE_X:
        return (f"{opcode.mnemonic} ${op1:02X},X", opcode.bytes)
    if opcode.mode == AddressMode.ZERO_PAGE_Y:
        return (f"{opcode.mnemonic} ${op1:02X},Y", opcode.bytes)
    if opcode.mode == AddressMode.INDEXED_INDIRECT:
        return (f"{opcode.mnemonic} (${op1:02X},X)", opcode.bytes)
    if opcode.mode == AddressMode.INDIRECT_INDEXED:
        return (f"{opcode.mnemonic} (${op1:02X}),Y", opcode.bytes)
    if opcode.mode == AddressMode.RELATIVE:
        offset = op1 - 0x100 if op1 & 0x80 else op1
        target = (addr + opcode.bytes + offset) & 0xFFFF
        return (f"{opcode.mnemonic} ${target:04X}", opcode.bytes)

    op2 = memory.read_byte((addr + 2) & 0xFFFF)
    operand = op1 | (op2 << 8)
    if opcode.mode == AddressMode.ABSOLUTE:
        return (f"{opcode.mnemonic} ${operand:04X}", opcode.bytes)
    if opcode.mode == AddressMode.ABSOLUTE_X:
        return (f"{opcode.mnemonic} ${operand:04X},X", opcode.bytes)
    if opcode.mode == AddressMode.ABSOLUTE_Y:
        return (f"{opcode.mnemonic} ${operand:04X},Y", opcode.bytes)
    if opcode.mode == AddressMode.INDIRECT:
        return (f"{opcode.mnemonic} (${operand:04X})", opcode.bytes)

    return (f".DB ${opcode_byte:02X}", 1)
