"""PIA (6520) emulation for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass

from pyatari.constants import JoystickBits, PIARegister, PORTBBits
from pyatari.memory import MemoryBus

PIA_MIRROR_BASE = int(PIARegister.PORTA)
PIA_MIRROR_MASK = 0x03
DDR_ACCESS_BIT = 0x04


@dataclass(slots=True)
class PIA:
    """Readable model of the Atari 800XL's 6520 PIA chip."""

    memory: MemoryBus
    porta_output: int = 0xFF
    portb_output: int = int(
        PORTBBits.OS_ROM_ENABLE | PORTBBits.BASIC_ROM_ENABLE | PORTBBits.SELF_TEST_ENABLE
    )
    porta_ddr: int = 0x00
    portb_ddr: int = 0xFF
    pactl: int = DDR_ACCESS_BIT
    pbctl: int = DDR_ACCESS_BIT
    joystick_state: int = 0xFF

    def __post_init__(self) -> None:
        self.memory.update_bank_config(self.portb_output)

    def install(self) -> None:
        self.memory.register_read_handler(0xD300, 0xD3FF, self.read_register)
        self.memory.register_write_handler(0xD300, 0xD3FF, self.write_register)

    def reset(self) -> None:
        self.porta_output = 0xFF
        self.portb_output = int(
            PORTBBits.OS_ROM_ENABLE
            | PORTBBits.BASIC_ROM_ENABLE
            | PORTBBits.SELF_TEST_ENABLE
        )
        self.porta_ddr = 0x00
        self.portb_ddr = 0xFF
        self.pactl = DDR_ACCESS_BIT
        self.pbctl = DDR_ACCESS_BIT
        self.joystick_state = 0xFF
        self.memory.update_bank_config(self.portb_output)

    def read_register(self, address: int) -> int:
        register = self._normalize(address)
        if register == PIARegister.PORTA:
            return self.porta_ddr if not (self.pactl & DDR_ACCESS_BIT) else self._compose_porta()
        if register == PIARegister.PACTL:
            return self.pactl
        if register == PIARegister.PORTB:
            return self.portb_ddr if not (self.pbctl & DDR_ACCESS_BIT) else self._compose_portb()
        if register == PIARegister.PBCTL:
            return self.pbctl
        raise ValueError(f"Unknown PIA register {register:#06x}")

    def write_register(self, address: int, value: int) -> None:
        value &= 0xFF
        register = self._normalize(address)

        if register == PIARegister.PORTA:
            if self.pactl & DDR_ACCESS_BIT:
                self.porta_output = value
            else:
                self.porta_ddr = value
            return

        if register == PIARegister.PACTL:
            self.pactl = value
            return

        if register == PIARegister.PORTB:
            if self.pbctl & DDR_ACCESS_BIT:
                self.portb_output = value
                self.memory.update_bank_config(self._compose_portb())
            else:
                self.portb_ddr = value
                self.memory.update_bank_config(self._compose_portb())
            return

        if register == PIARegister.PBCTL:
            self.pbctl = value
            return

        raise ValueError(f"Unknown PIA register {register:#06x}")

    def set_joystick_state(self, *, stick0: int | None = None, stick1: int | None = None) -> None:
        if stick0 is not None:
            self.joystick_state = (self.joystick_state & 0xF0) | (stick0 & 0x0F)
        if stick1 is not None:
            self.joystick_state = (self.joystick_state & 0x0F) | ((stick1 & 0x0F) << 4)

    def press_joystick(self, *directions: JoystickBits) -> None:
        for direction in directions:
            self.joystick_state &= ~int(direction)

    def release_joystick(self, *directions: JoystickBits) -> None:
        for direction in directions:
            self.joystick_state |= int(direction)

    def _compose_porta(self) -> int:
        inputs = self.joystick_state
        outputs = self.porta_output
        return ((outputs & self.porta_ddr) | (inputs & (~self.porta_ddr & 0xFF))) & 0xFF

    def _compose_portb(self) -> int:
        floating_inputs = 0xFF
        outputs = self.portb_output
        return ((outputs & self.portb_ddr) | (floating_inputs & (~self.portb_ddr & 0xFF))) & 0xFF

    def _normalize(self, address: int) -> int:
        return PIA_MIRROR_BASE + ((address - PIA_MIRROR_BASE) & PIA_MIRROR_MASK)
