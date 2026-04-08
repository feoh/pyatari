"""Tests for opcode metadata."""

from pyatari.opcodes import AddressMode, OPCODES


class TestOpcodeTable:
    def test_opcode_table_includes_official_and_common_undocumented_entries(self):
        assert len(OPCODES) == 203

    def test_all_opcodes_have_consistent_metadata(self):
        for code, opcode in OPCODES.items():
            assert opcode.code == code
            assert opcode.bytes in {1, 2, 3}
            assert isinstance(opcode.mode, AddressMode)

    def test_known_opcodes_decode_correctly(self):
        assert OPCODES[0xA9].mnemonic == "LDA"
        assert OPCODES[0xA9].mode == AddressMode.IMMEDIATE
        assert OPCODES[0x6C].mnemonic == "JMP"
        assert OPCODES[0x6C].mode == AddressMode.INDIRECT
        assert OPCODES[0x00].mnemonic == "BRK"
        assert OPCODES[0xEA].mnemonic == "NOP"
        assert OPCODES[0xA7].mnemonic == "LAX"
        assert OPCODES[0x67].mnemonic == "RRA"
