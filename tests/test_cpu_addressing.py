"""Tests for 6502 addressing mode resolution."""

from pyatari.addressing import resolve_address
from pyatari.cpu import CPU
from pyatari.memory import MemoryBus
from pyatari.opcodes import AddressMode


class TestAddressResolution:
    def make_cpu(self, pc: int = 0x2000, *, x: int = 0, y: int = 0) -> CPU:
        memory = MemoryBus()
        cpu = CPU(memory=memory, pc=pc, x=x, y=y)
        return cpu

    def test_immediate(self):
        cpu = self.make_cpu()
        cpu.memory.write_byte(0x2000, 0x44)

        result = resolve_address(cpu, AddressMode.IMMEDIATE)

        assert result.address == 0x2000
        assert cpu.pc == 0x2001

    def test_zero_page_x_wraps(self):
        cpu = self.make_cpu(x=0x20)
        cpu.memory.write_byte(0x2000, 0xF0)

        result = resolve_address(cpu, AddressMode.ZERO_PAGE_X)

        assert result.address == 0x10

    def test_relative_negative_offset(self):
        cpu = self.make_cpu(pc=0x3000)
        cpu.memory.write_byte(0x3000, 0xFC)  # -4

        result = resolve_address(cpu, AddressMode.RELATIVE)

        assert result.address == 0x2FFD

    def test_absolute_y_detects_page_cross(self):
        cpu = self.make_cpu(y=1)
        cpu.memory.write_byte(0x2000, 0xFF)
        cpu.memory.write_byte(0x2001, 0x12)

        result = resolve_address(cpu, AddressMode.ABSOLUTE_Y)

        assert result.address == 0x1300
        assert result.page_crossed is True

    def test_indirect_preserves_jmp_page_wrap_bug(self):
        cpu = self.make_cpu(pc=0x4000)
        cpu.memory.write_byte(0x4000, 0xFF)
        cpu.memory.write_byte(0x4001, 0x10)
        cpu.memory.write_byte(0x10FF, 0x34)
        cpu.memory.write_byte(0x1000, 0x12)

        result = resolve_address(cpu, AddressMode.INDIRECT)

        assert result.address == 0x1234

    def test_indexed_indirect(self):
        cpu = self.make_cpu(x=0x04)
        cpu.memory.write_byte(0x2000, 0x20)
        cpu.memory.write_byte(0x24, 0x78)
        cpu.memory.write_byte(0x25, 0x56)

        result = resolve_address(cpu, AddressMode.INDEXED_INDIRECT)

        assert result.address == 0x5678

    def test_indirect_indexed(self):
        cpu = self.make_cpu(y=0x10)
        cpu.memory.write_byte(0x2000, 0x80)
        cpu.memory.write_byte(0x80, 0x00)
        cpu.memory.write_byte(0x81, 0x20)

        result = resolve_address(cpu, AddressMode.INDIRECT_INDEXED)

        assert result.address == 0x2010
        assert result.page_crossed is False
