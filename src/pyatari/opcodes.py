"""6502 opcode metadata.

This module defines the official MOS 6502 instruction set used by the Atari's
6502C CPU. It deliberately focuses on readable metadata rather than clever
compression.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AddressMode(str, Enum):
    IMPLIED = "implied"
    ACCUMULATOR = "accumulator"
    IMMEDIATE = "immediate"
    ZERO_PAGE = "zero_page"
    ZERO_PAGE_X = "zero_page_x"
    ZERO_PAGE_Y = "zero_page_y"
    RELATIVE = "relative"
    ABSOLUTE = "absolute"
    ABSOLUTE_X = "absolute_x"
    ABSOLUTE_Y = "absolute_y"
    INDIRECT = "indirect"
    INDEXED_INDIRECT = "indexed_indirect"
    INDIRECT_INDEXED = "indirect_indexed"


MODE_BYTES: dict[AddressMode, int] = {
    AddressMode.IMPLIED: 1,
    AddressMode.ACCUMULATOR: 1,
    AddressMode.IMMEDIATE: 2,
    AddressMode.ZERO_PAGE: 2,
    AddressMode.ZERO_PAGE_X: 2,
    AddressMode.ZERO_PAGE_Y: 2,
    AddressMode.RELATIVE: 2,
    AddressMode.ABSOLUTE: 3,
    AddressMode.ABSOLUTE_X: 3,
    AddressMode.ABSOLUTE_Y: 3,
    AddressMode.INDIRECT: 3,
    AddressMode.INDEXED_INDIRECT: 2,
    AddressMode.INDIRECT_INDEXED: 2,
}


@dataclass(frozen=True, slots=True)
class Opcode:
    code: int
    mnemonic: str
    mode: AddressMode
    bytes: int
    cycles: int
    page_cross_cycles: int = 0


OPCODES: dict[int, Opcode] = {}


def _add(
    code: int,
    mnemonic: str,
    mode: AddressMode,
    cycles: int,
    page_cross_cycles: int = 0,
) -> None:
    OPCODES[code] = Opcode(
        code=code,
        mnemonic=mnemonic,
        mode=mode,
        bytes=MODE_BYTES[mode],
        cycles=cycles,
        page_cross_cycles=page_cross_cycles,
    )


# Load/store
for code, mode, cycles, extra in [
    (0xA9, AddressMode.IMMEDIATE, 2, 0),
    (0xA5, AddressMode.ZERO_PAGE, 3, 0),
    (0xB5, AddressMode.ZERO_PAGE_X, 4, 0),
    (0xAD, AddressMode.ABSOLUTE, 4, 0),
    (0xBD, AddressMode.ABSOLUTE_X, 4, 1),
    (0xB9, AddressMode.ABSOLUTE_Y, 4, 1),
    (0xA1, AddressMode.INDEXED_INDIRECT, 6, 0),
    (0xB1, AddressMode.INDIRECT_INDEXED, 5, 1),
]:
    _add(code, "LDA", mode, cycles, extra)
for code, mode, cycles, extra in [
    (0xA2, AddressMode.IMMEDIATE, 2, 0),
    (0xA6, AddressMode.ZERO_PAGE, 3, 0),
    (0xB6, AddressMode.ZERO_PAGE_Y, 4, 0),
    (0xAE, AddressMode.ABSOLUTE, 4, 0),
    (0xBE, AddressMode.ABSOLUTE_Y, 4, 1),
]:
    _add(code, "LDX", mode, cycles, extra)
for code, mode, cycles, extra in [
    (0xA0, AddressMode.IMMEDIATE, 2, 0),
    (0xA4, AddressMode.ZERO_PAGE, 3, 0),
    (0xB4, AddressMode.ZERO_PAGE_X, 4, 0),
    (0xAC, AddressMode.ABSOLUTE, 4, 0),
    (0xBC, AddressMode.ABSOLUTE_X, 4, 1),
]:
    _add(code, "LDY", mode, cycles, extra)
for code, mode, cycles in [
    (0x85, AddressMode.ZERO_PAGE, 3),
    (0x95, AddressMode.ZERO_PAGE_X, 4),
    (0x8D, AddressMode.ABSOLUTE, 4),
    (0x9D, AddressMode.ABSOLUTE_X, 5),
    (0x99, AddressMode.ABSOLUTE_Y, 5),
    (0x81, AddressMode.INDEXED_INDIRECT, 6),
    (0x91, AddressMode.INDIRECT_INDEXED, 6),
]:
    _add(code, "STA", mode, cycles)
for code, mode, cycles in [
    (0x86, AddressMode.ZERO_PAGE, 3),
    (0x96, AddressMode.ZERO_PAGE_Y, 4),
    (0x8E, AddressMode.ABSOLUTE, 4),
]:
    _add(code, "STX", mode, cycles)
for code, mode, cycles in [
    (0x84, AddressMode.ZERO_PAGE, 3),
    (0x94, AddressMode.ZERO_PAGE_X, 4),
    (0x8C, AddressMode.ABSOLUTE, 4),
]:
    _add(code, "STY", mode, cycles)

# Transfers
for code, mnemonic in [
    (0xAA, "TAX"), (0xA8, "TAY"), (0x8A, "TXA"), (0x98, "TYA"),
    (0xBA, "TSX"), (0x9A, "TXS"),
]:
    _add(code, mnemonic, AddressMode.IMPLIED, 2)

# Stack
for code, mnemonic, cycles in [
    (0x48, "PHA", 3), (0x08, "PHP", 3), (0x68, "PLA", 4), (0x28, "PLP", 4)
]:
    _add(code, mnemonic, AddressMode.IMPLIED, cycles)

# Logic/arithmetic families
for mnemonic, entries in {
    "ORA": [
        (0x09, AddressMode.IMMEDIATE, 2, 0), (0x05, AddressMode.ZERO_PAGE, 3, 0),
        (0x15, AddressMode.ZERO_PAGE_X, 4, 0), (0x0D, AddressMode.ABSOLUTE, 4, 0),
        (0x1D, AddressMode.ABSOLUTE_X, 4, 1), (0x19, AddressMode.ABSOLUTE_Y, 4, 1),
        (0x01, AddressMode.INDEXED_INDIRECT, 6, 0), (0x11, AddressMode.INDIRECT_INDEXED, 5, 1),
    ],
    "AND": [
        (0x29, AddressMode.IMMEDIATE, 2, 0), (0x25, AddressMode.ZERO_PAGE, 3, 0),
        (0x35, AddressMode.ZERO_PAGE_X, 4, 0), (0x2D, AddressMode.ABSOLUTE, 4, 0),
        (0x3D, AddressMode.ABSOLUTE_X, 4, 1), (0x39, AddressMode.ABSOLUTE_Y, 4, 1),
        (0x21, AddressMode.INDEXED_INDIRECT, 6, 0), (0x31, AddressMode.INDIRECT_INDEXED, 5, 1),
    ],
    "EOR": [
        (0x49, AddressMode.IMMEDIATE, 2, 0), (0x45, AddressMode.ZERO_PAGE, 3, 0),
        (0x55, AddressMode.ZERO_PAGE_X, 4, 0), (0x4D, AddressMode.ABSOLUTE, 4, 0),
        (0x5D, AddressMode.ABSOLUTE_X, 4, 1), (0x59, AddressMode.ABSOLUTE_Y, 4, 1),
        (0x41, AddressMode.INDEXED_INDIRECT, 6, 0), (0x51, AddressMode.INDIRECT_INDEXED, 5, 1),
    ],
    "ADC": [
        (0x69, AddressMode.IMMEDIATE, 2, 0), (0x65, AddressMode.ZERO_PAGE, 3, 0),
        (0x75, AddressMode.ZERO_PAGE_X, 4, 0), (0x6D, AddressMode.ABSOLUTE, 4, 0),
        (0x7D, AddressMode.ABSOLUTE_X, 4, 1), (0x79, AddressMode.ABSOLUTE_Y, 4, 1),
        (0x61, AddressMode.INDEXED_INDIRECT, 6, 0), (0x71, AddressMode.INDIRECT_INDEXED, 5, 1),
    ],
    "SBC": [
        (0xE9, AddressMode.IMMEDIATE, 2, 0), (0xE5, AddressMode.ZERO_PAGE, 3, 0),
        (0xF5, AddressMode.ZERO_PAGE_X, 4, 0), (0xED, AddressMode.ABSOLUTE, 4, 0),
        (0xFD, AddressMode.ABSOLUTE_X, 4, 1), (0xF9, AddressMode.ABSOLUTE_Y, 4, 1),
        (0xE1, AddressMode.INDEXED_INDIRECT, 6, 0), (0xF1, AddressMode.INDIRECT_INDEXED, 5, 1),
    ],
    "CMP": [
        (0xC9, AddressMode.IMMEDIATE, 2, 0), (0xC5, AddressMode.ZERO_PAGE, 3, 0),
        (0xD5, AddressMode.ZERO_PAGE_X, 4, 0), (0xCD, AddressMode.ABSOLUTE, 4, 0),
        (0xDD, AddressMode.ABSOLUTE_X, 4, 1), (0xD9, AddressMode.ABSOLUTE_Y, 4, 1),
        (0xC1, AddressMode.INDEXED_INDIRECT, 6, 0), (0xD1, AddressMode.INDIRECT_INDEXED, 5, 1),
    ],
}.items():
    for code, mode, cycles, extra in entries:
        _add(code, mnemonic, mode, cycles, extra)
for code, mode, cycles in [
    (0xE0, AddressMode.IMMEDIATE, 2), (0xE4, AddressMode.ZERO_PAGE, 3), (0xEC, AddressMode.ABSOLUTE, 4)
]:
    _add(code, "CPX", mode, cycles)
for code, mode, cycles in [
    (0xC0, AddressMode.IMMEDIATE, 2), (0xC4, AddressMode.ZERO_PAGE, 3), (0xCC, AddressMode.ABSOLUTE, 4)
]:
    _add(code, "CPY", mode, cycles)

# INC/DEC
for code, mnemonic in [(0xE8, "INX"), (0xC8, "INY"), (0xCA, "DEX"), (0x88, "DEY")]:
    _add(code, mnemonic, AddressMode.IMPLIED, 2)
for code, mode, cycles in [
    (0xE6, AddressMode.ZERO_PAGE, 5), (0xF6, AddressMode.ZERO_PAGE_X, 6),
    (0xEE, AddressMode.ABSOLUTE, 6), (0xFE, AddressMode.ABSOLUTE_X, 7)
]:
    _add(code, "INC", mode, cycles)
for code, mode, cycles in [
    (0xC6, AddressMode.ZERO_PAGE, 5), (0xD6, AddressMode.ZERO_PAGE_X, 6),
    (0xCE, AddressMode.ABSOLUTE, 6), (0xDE, AddressMode.ABSOLUTE_X, 7)
]:
    _add(code, "DEC", mode, cycles)

# Shifts/rotates
for mnemonic, acc_code, entries in [
    ("ASL", 0x0A, [(0x06, AddressMode.ZERO_PAGE, 5), (0x16, AddressMode.ZERO_PAGE_X, 6), (0x0E, AddressMode.ABSOLUTE, 6), (0x1E, AddressMode.ABSOLUTE_X, 7)]),
    ("LSR", 0x4A, [(0x46, AddressMode.ZERO_PAGE, 5), (0x56, AddressMode.ZERO_PAGE_X, 6), (0x4E, AddressMode.ABSOLUTE, 6), (0x5E, AddressMode.ABSOLUTE_X, 7)]),
    ("ROL", 0x2A, [(0x26, AddressMode.ZERO_PAGE, 5), (0x36, AddressMode.ZERO_PAGE_X, 6), (0x2E, AddressMode.ABSOLUTE, 6), (0x3E, AddressMode.ABSOLUTE_X, 7)]),
    ("ROR", 0x6A, [(0x66, AddressMode.ZERO_PAGE, 5), (0x76, AddressMode.ZERO_PAGE_X, 6), (0x6E, AddressMode.ABSOLUTE, 6), (0x7E, AddressMode.ABSOLUTE_X, 7)]),
]:
    _add(acc_code, mnemonic, AddressMode.ACCUMULATOR, 2)
    for code, mode, cycles in entries:
        _add(code, mnemonic, mode, cycles)

# BIT
for code, mode, cycles in [(0x24, AddressMode.ZERO_PAGE, 3), (0x2C, AddressMode.ABSOLUTE, 4)]:
    _add(code, "BIT", mode, cycles)

# Branches
for code, mnemonic in [
    (0x10, "BPL"), (0x30, "BMI"), (0x50, "BVC"), (0x70, "BVS"),
    (0x90, "BCC"), (0xB0, "BCS"), (0xD0, "BNE"), (0xF0, "BEQ"),
]:
    _add(code, mnemonic, AddressMode.RELATIVE, 2, 2)

# Jumps/subroutines
_add(0x4C, "JMP", AddressMode.ABSOLUTE, 3)
_add(0x6C, "JMP", AddressMode.INDIRECT, 5)
_add(0x20, "JSR", AddressMode.ABSOLUTE, 6)
_add(0x60, "RTS", AddressMode.IMPLIED, 6)
_add(0x40, "RTI", AddressMode.IMPLIED, 6)
_add(0x00, "BRK", AddressMode.IMPLIED, 7)

# Flags / nop
for code, mnemonic in [
    (0x18, "CLC"), (0x38, "SEC"), (0x58, "CLI"), (0x78, "SEI"),
    (0xB8, "CLV"), (0xD8, "CLD"), (0xF8, "SED"), (0xEA, "NOP")
]:
    _add(code, mnemonic, AddressMode.IMPLIED, 2)

# Misc
for code, mode, cycles in [
    (0xC6, AddressMode.ZERO_PAGE, 5),
]:
    pass

# STY/STX/LDY/LDX already done; remaining misc official opcodes:
for code, mode, cycles in [
    (0xC6, AddressMode.ZERO_PAGE, 5),
]:
    pass

# Official singletons not covered above.
for code, mnemonic, mode, cycles in [
    (0x24, "BIT", AddressMode.ZERO_PAGE, 3),
    (0x2C, "BIT", AddressMode.ABSOLUTE, 4),
]:
    OPCODES[code] = Opcode(code, mnemonic, mode, MODE_BYTES[mode], cycles, 0)

# Complements still missing from official set.
for code, mnemonic, mode, cycles, extra in [
    (0xE6, "INC", AddressMode.ZERO_PAGE, 5, 0),
    (0xF6, "INC", AddressMode.ZERO_PAGE_X, 6, 0),
    (0xEE, "INC", AddressMode.ABSOLUTE, 6, 0),
    (0xFE, "INC", AddressMode.ABSOLUTE_X, 7, 0),
    (0xC6, "DEC", AddressMode.ZERO_PAGE, 5, 0),
    (0xD6, "DEC", AddressMode.ZERO_PAGE_X, 6, 0),
    (0xCE, "DEC", AddressMode.ABSOLUTE, 6, 0),
    (0xDE, "DEC", AddressMode.ABSOLUTE_X, 7, 0),
]:
    OPCODES[code] = Opcode(code, mnemonic, mode, MODE_BYTES[mode], cycles, extra)

# Ensure remaining official opcodes are registered.
for code, mnemonic, mode, cycles, extra in [
    (0xC1, "CMP", AddressMode.INDEXED_INDIRECT, 6, 0), (0xD1, "CMP", AddressMode.INDIRECT_INDEXED, 5, 1),
    (0xE1, "SBC", AddressMode.INDEXED_INDIRECT, 6, 0), (0xF1, "SBC", AddressMode.INDIRECT_INDEXED, 5, 1),
    (0x81, "STA", AddressMode.INDEXED_INDIRECT, 6, 0), (0x91, "STA", AddressMode.INDIRECT_INDEXED, 6, 0),
]:
    OPCODES[code] = Opcode(code, mnemonic, mode, MODE_BYTES[mode], cycles, extra)

# Common undocumented opcodes used by real software.
for code, mnemonic, mode, cycles, extra in [
    # LAX
    (0xA7, "LAX", AddressMode.ZERO_PAGE, 3, 0),
    (0xB7, "LAX", AddressMode.ZERO_PAGE_Y, 4, 0),
    (0xAF, "LAX", AddressMode.ABSOLUTE, 4, 0),
    (0xBF, "LAX", AddressMode.ABSOLUTE_Y, 4, 1),
    (0xA3, "LAX", AddressMode.INDEXED_INDIRECT, 6, 0),
    (0xB3, "LAX", AddressMode.INDIRECT_INDEXED, 5, 1),
    # SAX
    (0x87, "SAX", AddressMode.ZERO_PAGE, 3, 0),
    (0x97, "SAX", AddressMode.ZERO_PAGE_Y, 4, 0),
    (0x8F, "SAX", AddressMode.ABSOLUTE, 4, 0),
    (0x83, "SAX", AddressMode.INDEXED_INDIRECT, 6, 0),
    # DCP
    (0xC7, "DCP", AddressMode.ZERO_PAGE, 5, 0),
    (0xD7, "DCP", AddressMode.ZERO_PAGE_X, 6, 0),
    (0xCF, "DCP", AddressMode.ABSOLUTE, 6, 0),
    (0xDF, "DCP", AddressMode.ABSOLUTE_X, 7, 0),
    (0xDB, "DCP", AddressMode.ABSOLUTE_Y, 7, 0),
    (0xC3, "DCP", AddressMode.INDEXED_INDIRECT, 8, 0),
    (0xD3, "DCP", AddressMode.INDIRECT_INDEXED, 8, 0),
    # ISB/ISC
    (0xE7, "ISB", AddressMode.ZERO_PAGE, 5, 0),
    (0xF7, "ISB", AddressMode.ZERO_PAGE_X, 6, 0),
    (0xEF, "ISB", AddressMode.ABSOLUTE, 6, 0),
    (0xFF, "ISB", AddressMode.ABSOLUTE_X, 7, 0),
    (0xFB, "ISB", AddressMode.ABSOLUTE_Y, 7, 0),
    (0xE3, "ISB", AddressMode.INDEXED_INDIRECT, 8, 0),
    (0xF3, "ISB", AddressMode.INDIRECT_INDEXED, 8, 0),
    # SLO
    (0x07, "SLO", AddressMode.ZERO_PAGE, 5, 0),
    (0x17, "SLO", AddressMode.ZERO_PAGE_X, 6, 0),
    (0x0F, "SLO", AddressMode.ABSOLUTE, 6, 0),
    (0x1F, "SLO", AddressMode.ABSOLUTE_X, 7, 0),
    (0x1B, "SLO", AddressMode.ABSOLUTE_Y, 7, 0),
    (0x03, "SLO", AddressMode.INDEXED_INDIRECT, 8, 0),
    (0x13, "SLO", AddressMode.INDIRECT_INDEXED, 8, 0),
    # RLA
    (0x27, "RLA", AddressMode.ZERO_PAGE, 5, 0),
    (0x37, "RLA", AddressMode.ZERO_PAGE_X, 6, 0),
    (0x2F, "RLA", AddressMode.ABSOLUTE, 6, 0),
    (0x3F, "RLA", AddressMode.ABSOLUTE_X, 7, 0),
    (0x3B, "RLA", AddressMode.ABSOLUTE_Y, 7, 0),
    (0x23, "RLA", AddressMode.INDEXED_INDIRECT, 8, 0),
    (0x33, "RLA", AddressMode.INDIRECT_INDEXED, 8, 0),
    # SRE
    (0x47, "SRE", AddressMode.ZERO_PAGE, 5, 0),
    (0x57, "SRE", AddressMode.ZERO_PAGE_X, 6, 0),
    (0x4F, "SRE", AddressMode.ABSOLUTE, 6, 0),
    (0x5F, "SRE", AddressMode.ABSOLUTE_X, 7, 0),
    (0x5B, "SRE", AddressMode.ABSOLUTE_Y, 7, 0),
    (0x43, "SRE", AddressMode.INDEXED_INDIRECT, 8, 0),
    (0x53, "SRE", AddressMode.INDIRECT_INDEXED, 8, 0),
    # RRA
    (0x67, "RRA", AddressMode.ZERO_PAGE, 5, 0),
    (0x77, "RRA", AddressMode.ZERO_PAGE_X, 6, 0),
    (0x6F, "RRA", AddressMode.ABSOLUTE, 6, 0),
    (0x7F, "RRA", AddressMode.ABSOLUTE_X, 7, 0),
    (0x7B, "RRA", AddressMode.ABSOLUTE_Y, 7, 0),
    (0x63, "RRA", AddressMode.INDEXED_INDIRECT, 8, 0),
    (0x73, "RRA", AddressMode.INDIRECT_INDEXED, 8, 0),
]:
    OPCODES[code] = Opcode(code, mnemonic, mode, MODE_BYTES[mode], cycles, extra)

# Sanity: official 6502 has 151 opcodes, plus 52 common undocumented opcodes here.
assert len(OPCODES) == 203, f"Expected 203 opcodes, found {len(OPCODES)}"
