"""POKEY timer, keyboard, IRQ, and random support for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.constants import IRQBits, POKEYReadRegister, POKEYWriteRegister
from pyatari.memory import MemoryBus

POKEY_MIRROR_BASE = 0xD200
POKEY_MIRROR_MASK = 0x0F
CHANNEL_TO_IRQ = {
    0: int(IRQBits.TIMER1),
    1: int(IRQBits.TIMER2),
    3: int(IRQBits.TIMER4),
}


@dataclass(slots=True)
class PokeyTimer:
    reload_value: int = 1
    counter: int = 1
    enabled: bool = False


@dataclass(slots=True)
class POKEY:
    memory: MemoryBus
    audf: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    audc: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    audctl: int = 0
    skctl: int = 0
    serout: int = 0
    serin: int = 0
    irqen: int = 0
    irqst: int = 0xFF
    kbcode: int = 0xFF
    skstat: int = 0xFF
    allpot: int = 0xFF
    pot_values: list[int] = field(default_factory=lambda: [228] * 8)
    timers: list[PokeyTimer] = field(default_factory=lambda: [PokeyTimer() for _ in range(4)])
    random_state: int = 0x1FFFF

    def install(self) -> None:
        self.memory.register_read_handler(0xD200, 0xD2FF, self.read_register)
        self.memory.register_write_handler(0xD200, 0xD2FF, self.write_register)

    def reset(self) -> None:
        self.audf = [0, 0, 0, 0]
        self.audc = [0, 0, 0, 0]
        self.audctl = 0
        self.skctl = 0
        self.serout = 0
        self.serin = 0
        self.irqen = 0
        self.irqst = 0xFF
        self.kbcode = 0xFF
        self.skstat = 0xFF
        self.allpot = 0xFF
        self.pot_values = [228] * 8
        self.timers = [PokeyTimer() for _ in range(4)]
        self.random_state = 0x1FFFF

    def read_register(self, address: int) -> int:
        register = self._normalize(address)
        if int(POKEYReadRegister.POT0) <= register <= int(POKEYReadRegister.POT7):
            return self.pot_values[register - int(POKEYReadRegister.POT0)]
        if register == int(POKEYReadRegister.ALLPOT):
            return self.allpot
        if register == int(POKEYReadRegister.KBCODE):
            return self.kbcode
        if register == int(POKEYReadRegister.RANDOM):
            return self._next_random_byte()
        if register == int(POKEYReadRegister.SERIN):
            return self.serin
        if register == int(POKEYReadRegister.IRQST):
            return self.irqst
        if register == int(POKEYReadRegister.SKSTAT):
            return self.skstat
        return 0

    def write_register(self, address: int, value: int) -> None:
        register = self._normalize(address)
        value &= 0xFF
        if int(POKEYWriteRegister.AUDF1) <= register <= int(POKEYWriteRegister.AUDF4):
            channel = (register - int(POKEYWriteRegister.AUDF1)) // 2
            self.audf[channel] = value
            self._reload_timer(channel)
            return
        if int(POKEYWriteRegister.AUDC1) <= register <= int(POKEYWriteRegister.AUDC4):
            channel = (register - int(POKEYWriteRegister.AUDC1)) // 2
            self.audc[channel] = value
            return
        if register == int(POKEYWriteRegister.AUDCTL):
            self.audctl = value
            return
        if register == int(POKEYWriteRegister.STIMER):
            self.start_timers()
            return
        if register == int(POKEYWriteRegister.SKRES):
            self.skstat = 0xFF
            return
        if register == int(POKEYWriteRegister.POTGO):
            self.allpot = 0x00
            return
        if register == int(POKEYWriteRegister.SEROUT):
            self.serout = value
            return
        if register == int(POKEYWriteRegister.IRQEN):
            self.irqen = value
            self.irqst |= ~value & 0xFF
            return
        if register == int(POKEYWriteRegister.SKCTL):
            self.skctl = value

    def tick(self, cycles: int) -> bool:
        irq_triggered = False
        for _ in range(cycles):
            for channel, timer in enumerate(self.timers):
                if not timer.enabled:
                    continue
                timer.counter -= 1
                if timer.counter > 0:
                    continue
                timer.counter = timer.reload_value
                irq_bit = self._timer_irq_bit(channel)
                if irq_bit is not None:
                    self.irqst &= ~irq_bit & 0xFF
                    if self.irqen & irq_bit:
                        irq_triggered = True
        return irq_triggered

    def start_timers(self) -> None:
        for channel, timer in enumerate(self.timers):
            timer.enabled = True
            timer.reload_value = self._timer_period(channel)
            timer.counter = timer.reload_value

    def press_key(self, keycode: int) -> None:
        self.kbcode = keycode & 0xFF
        self.skstat &= ~int(IRQBits.KEYBOARD) & 0xFF
        self.irqst &= ~int(IRQBits.KEYBOARD) & 0xFF

    def release_key(self) -> None:
        self.kbcode = 0xFF
        self.skstat |= int(IRQBits.KEYBOARD)
        self.irqst |= int(IRQBits.KEYBOARD)

    def _reload_timer(self, channel: int) -> None:
        timer = self.timers[channel]
        timer.reload_value = self._timer_period(channel)
        timer.counter = timer.reload_value

    def _timer_period(self, channel: int) -> int:
        if channel == 0 and self.audctl & 0x10:
            return (((self.audf[1] << 8) | self.audf[0]) + 1)
        if channel == 2 and self.audctl & 0x08:
            return (((self.audf[3] << 8) | self.audf[2]) + 1)
        return self.audf[channel] + 1

    def _timer_irq_bit(self, channel: int) -> int | None:
        return CHANNEL_TO_IRQ.get(channel)

    def _next_random_byte(self) -> int:
        bit = ((self.random_state >> 16) ^ (self.random_state >> 11)) & 1
        self.random_state = ((self.random_state << 1) | bit) & 0x1FFFF
        return self.random_state & 0xFF

    def _normalize(self, address: int) -> int:
        return POKEY_MIRROR_BASE + ((address - POKEY_MIRROR_BASE) & POKEY_MIRROR_MASK)
