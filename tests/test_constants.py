"""Tests for hardware constants -- verify key values are correct."""

from pyatari.constants import (
    ANTIC_MODES,
    ANTICRegister,
    AUDCTLBits,
    CPU_CLOCK_HZ,
    CYCLES_PER_FRAME,
    CYCLES_PER_SCANLINE,
    DMACTLBits,
    GTIAReadRegister,
    GTIAWriteRegister,
    IRQBits,
    IRQ_VECTOR,
    NMI_VECTOR,
    NMIBits,
    PIARegister,
    POKEYReadRegister,
    POKEYWriteRegister,
    RESET_VECTOR,
    SCANLINES_PER_FRAME,
    SKCTLBits,
    SKSTATBits,
)


class TestTimingConstants:
    def test_cpu_clock(self):
        assert CPU_CLOCK_HZ == 1_789_773

    def test_cycles_per_scanline(self):
        assert CYCLES_PER_SCANLINE == 114

    def test_scanlines_per_frame(self):
        assert SCANLINES_PER_FRAME == 262

    def test_cycles_per_frame(self):
        assert CYCLES_PER_FRAME == 114 * 262


class TestCPUVectors:
    def test_nmi_vector(self):
        assert NMI_VECTOR == 0xFFFA

    def test_reset_vector(self):
        assert RESET_VECTOR == 0xFFFC

    def test_irq_vector(self):
        assert IRQ_VECTOR == 0xFFFE


class TestGTIARegisters:
    def test_gtia_base_address(self):
        assert GTIAWriteRegister.HPOSP0 == 0xD000

    def test_color_registers(self):
        assert GTIAWriteRegister.COLPF0 == 0xD016
        assert GTIAWriteRegister.COLBK == 0xD01A

    def test_collision_read_registers(self):
        assert GTIAReadRegister.M0PF == 0xD000
        assert GTIAReadRegister.P0PF == 0xD004

    def test_consol_register(self):
        assert GTIAReadRegister.CONSOL == 0xD01F


class TestPOKEYRegisters:
    def test_pokey_base_address(self):
        assert POKEYWriteRegister.AUDF1 == 0xD200

    def test_audio_registers_contiguous(self):
        assert POKEYWriteRegister.AUDF2 == 0xD202
        assert POKEYWriteRegister.AUDF3 == 0xD204
        assert POKEYWriteRegister.AUDF4 == 0xD206

    def test_random_register(self):
        assert POKEYReadRegister.RANDOM == 0xD20A

    def test_irq_bits(self):
        assert IRQBits.TIMER1 == 0x01
        assert IRQBits.KEYBOARD == 0x40
        assert IRQBits.BREAK_KEY == 0x80

    def test_keyboard_status_and_control_bits(self):
        assert SKSTATBits.KEY_DOWN == 0x04
        assert SKSTATBits.SHIFT == 0x08
        assert SKCTLBits.KEYBOARD_DEBOUNCE == 0x01
        assert SKCTLBits.KEYBOARD_SCAN == 0x02
        assert SKCTLBits.FAST_POT_SCAN == 0x04

    def test_audctl_bits(self):
        assert AUDCTLBits.POLY9 == 0x80
        assert AUDCTLBits.CLOCK_15KHZ == 0x01


class TestPIARegisters:
    def test_pia_addresses(self):
        assert PIARegister.PORTA == 0xD300
        assert PIARegister.PACTL == 0xD301
        assert PIARegister.PORTB == 0xD302
        assert PIARegister.PBCTL == 0xD303


class TestANTICRegisters:
    def test_antic_base_address(self):
        assert ANTICRegister.DMACTL == 0xD400

    def test_key_registers(self):
        assert ANTICRegister.DLISTL == 0xD402
        assert ANTICRegister.WSYNC == 0xD40A
        assert ANTICRegister.VCOUNT == 0xD40B
        assert ANTICRegister.NMIEN == 0xD40E

    def test_dmactl_bits(self):
        assert DMACTLBits.DL_DMA == 0x20
        assert DMACTLBits.PLAYER_DMA == 0x08

    def test_nmi_bits(self):
        assert NMIBits.DLI == 0x80
        assert NMIBits.VBI == 0x40


class TestANTICModes:
    def test_all_modes_present(self):
        for mode_num in range(2, 16):
            assert mode_num in ANTIC_MODES

    def test_mode_2_is_standard_text(self):
        mode2 = ANTIC_MODES[2]
        assert mode2.is_text is True
        assert mode2.bytes_per_line == 40
        assert mode2.scanlines_per_row == 8
        assert mode2.colors == 2

    def test_mode_15_is_hires(self):
        mode15 = ANTIC_MODES[15]
        assert mode15.is_text is False
        assert mode15.bytes_per_line == 40
        assert mode15.scanlines_per_row == 1
        assert mode15.colors == 2
