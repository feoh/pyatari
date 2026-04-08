"""Focused instruction execution tests for the 6502 core."""

from pyatari.constants import IRQ_VECTOR, RESET_VECTOR
from pyatari.cpu import CPU
from pyatari.memory import MemoryBus


def make_cpu(program: bytes, start: int = 0x8000) -> CPU:
    memory = MemoryBus()
    memory.write_word(RESET_VECTOR, start)
    memory.load_ram(start, program)
    cpu = CPU(memory=memory)
    cpu.reset()
    return cpu


def test_lda_adc_sta_path():
    cpu = make_cpu(bytes([
        0xA9, 0x10,  # LDA #$10
        0x69, 0x05,  # ADC #$05
        0x8D, 0x00, 0x20,  # STA $2000
    ]))

    cpu.step()
    cpu.step()
    cpu.step()

    assert cpu.a == 0x15
    assert cpu.memory.read_byte(0x2000) == 0x15


def test_jsr_and_rts():
    cpu = make_cpu(bytes([
        0x20, 0x06, 0x80,  # JSR $8006
        0xA9, 0x01,        # LDA #$01
        0xEA,              # NOP
        0xA9, 0x42,        # LDA #$42
        0x60,              # RTS
    ]))

    cpu.step()  # JSR
    cpu.step()  # subroutine LDA
    cpu.step()  # RTS
    cpu.step()  # caller LDA

    assert cpu.a == 0x01
    assert cpu.pc == 0x8005


def test_branch_taken_and_not_taken():
    cpu = make_cpu(bytes([
        0xA9, 0x00,  # LDA #$00 sets zero
        0xF0, 0x02,  # BEQ +2
        0xA9, 0x01,  # skipped
        0xA9, 0x02,  # executed
        0xD0, 0x02,  # BNE +2
        0xA9, 0x03,  # skipped
        0xEA,        # target
    ]))

    for _ in range(5):
        cpu.step()

    assert cpu.a == 0x02
    assert cpu.pc == 0x800D


def test_jmp_indirect_page_wrap_bug():
    memory = MemoryBus()
    memory.write_word(RESET_VECTOR, 0x8000)
    memory.load_ram(0x8000, bytes([0x6C, 0xFF, 0x10]))
    memory.write_byte(0x10FF, 0x34)
    memory.write_byte(0x1000, 0x12)
    cpu = CPU(memory=memory)
    cpu.reset()

    cpu.step()

    assert cpu.pc == 0x1234


def test_brk_pushes_state_and_uses_irq_vector():
    memory = MemoryBus()
    memory.write_word(RESET_VECTOR, 0x8000)
    memory.write_word(IRQ_VECTOR, 0x9000)
    memory.load_ram(0x8000, bytes([0x00]))
    cpu = CPU(memory=memory)
    cpu.reset()

    cpu.step()

    assert cpu.pc == 0x9000
    assert cpu.status.interrupt_disable is True
    assert cpu.sp == 0xFA


def test_rti_restores_status_and_pc():
    cpu = make_cpu(bytes([0x40]))
    cpu._push_word(0x8123)
    cpu._push_byte(0b11001011)

    cpu.step()

    assert cpu.pc == 0x8123
    assert cpu.status.negative is True
    assert cpu.status.overflow is True
    assert cpu.status.decimal is True
    assert cpu.status.zero is True
    assert cpu.status.carry is True


def test_decimal_adc_and_sbc():
    cpu = make_cpu(bytes([
        0xF8,        # SED
        0xA9, 0x15,  # LDA #$15
        0x69, 0x27,  # ADC #$27 => 42 BCD
        0x38,        # SEC
        0xE9, 0x12,  # SBC #$12 => 30 BCD
    ]))

    for _ in range(5):
        cpu.step()

    assert cpu.a == 0x30


def test_rol_and_ror_accumulator_use_carry():
    cpu = make_cpu(bytes([
        0x38,        # SEC
        0xA9, 0x80,  # LDA #$80
        0x2A,        # ROL A -> 01, carry set
        0x6A,        # ROR A -> 80, carry set from bit0
    ]))

    for _ in range(4):
        cpu.step()

    assert cpu.a == 0x80
    assert cpu.status.carry is True
