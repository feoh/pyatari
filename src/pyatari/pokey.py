"""POKEY timer, keyboard, IRQ, random, and basic sound support for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.constants import (
    AUDCTLBits,
    IRQBits,
    POKEYReadRegister,
    POKEYWriteRegister,
    SKCTLBits,
    SKSTATBits,
)
from pyatari.memory import MemoryBus

DEFAULT_AUDIO_SAMPLE_RATE = 44_100
CPU_CYCLES_PER_POKEY_64KHZ_TICK = 28
CPU_CYCLES_PER_POKEY_15KHZ_TICK = 114
CPU_CYCLES_PER_SERIAL_BYTE = CPU_CYCLES_PER_POKEY_64KHZ_TICK * 10

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
    cycle_accumulator: int = 0


@dataclass(slots=True)
class PokeyAudioChannel:
    phase: float = 0.0


@dataclass(slots=True)
class PokeySerialEvent:
    irq_bit: int
    cycles_remaining: int
    data: int | None = None
    skstat: int | None = None


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
    audio_channels: list[PokeyAudioChannel] = field(default_factory=lambda: [PokeyAudioChannel() for _ in range(4)])
    random_state: int = 0x1FFFF
    serial_events: list[PokeySerialEvent] = field(default_factory=list)
    serial_transfer_active: bool = False
    serial_output_bytes: list[int] = field(default_factory=list)

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
        self.audio_channels = [PokeyAudioChannel() for _ in range(4)]
        self.random_state = 0x1FFFF
        self.serial_events = []
        self.serial_transfer_active = False
        self.serial_output_bytes = []

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
        audf_registers = [
            int(POKEYWriteRegister.AUDF1),
            int(POKEYWriteRegister.AUDF2),
            int(POKEYWriteRegister.AUDF3),
            int(POKEYWriteRegister.AUDF4),
        ]
        audc_registers = [
            int(POKEYWriteRegister.AUDC1),
            int(POKEYWriteRegister.AUDC2),
            int(POKEYWriteRegister.AUDC3),
            int(POKEYWriteRegister.AUDC4),
        ]
        if register in audf_registers:
            channel = audf_registers.index(register)
            self.audf[channel] = value
            self._reload_timer(channel)
            return
        if register in audc_registers:
            channel = audc_registers.index(register)
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
            self.serial_transfer_active = True
            self.serial_output_bytes.append(value)
            self._queue_serial_event(int(IRQBits.SERIAL_OUT_NEED))
            return
        if register == int(POKEYWriteRegister.IRQEN):
            previous_irqen = self.irqen
            self.irqen = value
            self.irqst |= ~value & 0xFF
            if (
                not (previous_irqen & int(IRQBits.SERIAL_OUT_DONE))
                and (self.irqen & int(IRQBits.SERIAL_OUT_DONE))
                and self.serial_transfer_active
                and not self._serial_event_pending(int(IRQBits.SERIAL_OUT_NEED))
                and not self._serial_event_pending(int(IRQBits.SERIAL_OUT_DONE))
            ):
                self._queue_serial_event(int(IRQBits.SERIAL_OUT_DONE))
            return
        if register == int(POKEYWriteRegister.SKCTL):
            self.skctl = value

    def tick(self, cycles: int) -> bool:
        irq_triggered = False
        for channel, timer in enumerate(self.timers):
            if not timer.enabled:
                continue
            divider = self._timer_clock_divider(channel)
            timer.cycle_accumulator += cycles
            timer_ticks, timer.cycle_accumulator = divmod(timer.cycle_accumulator, divider)
            if timer_ticks == 0:
                continue
            irq_triggered |= self._advance_timer(channel, timer, timer_ticks)
        irq_triggered |= self._advance_serial(cycles)
        return irq_triggered

    def start_timers(self) -> None:
        for channel, timer in enumerate(self.timers):
            timer.enabled = True
            timer.reload_value = self._timer_period(channel)
            timer.counter = timer.reload_value
            timer.cycle_accumulator = 0
        self.irqst |= (
            int(IRQBits.TIMER1) | int(IRQBits.TIMER2) | int(IRQBits.TIMER4)
        )

    def press_key(self, keycode: int, *, shift: bool = False, control: bool = False) -> bool:
        if not self.skctl & int(SKCTLBits.KEYBOARD_SCAN):
            return False
        modifiers = (0x40 if shift else 0x00) | (0x80 if control else 0x00)
        self.kbcode = (keycode & 0x3F) | modifiers
        self.skstat &= ~int(SKSTATBits.KEY_DOWN) & 0xFF
        if shift:
            self.skstat &= ~int(SKSTATBits.SHIFT) & 0xFF
        else:
            self.skstat |= int(SKSTATBits.SHIFT)
        self.irqst &= ~int(IRQBits.KEYBOARD) & 0xFF
        return bool(self.irqen & int(IRQBits.KEYBOARD))

    def release_key(self) -> None:
        self.skstat |= int(SKSTATBits.KEY_DOWN | SKSTATBits.SHIFT)
        self.irqst |= int(IRQBits.KEYBOARD)

    def queue_serial_input(self, data: int, *, skstat: int = 0x00) -> None:
        delay = CPU_CYCLES_PER_SERIAL_BYTE
        pending_input = [
            event.cycles_remaining
            for event in self.serial_events
            if event.irq_bit == int(IRQBits.SERIAL_IN_DONE)
        ]
        if pending_input:
            delay = max(pending_input) + CPU_CYCLES_PER_SERIAL_BYTE
        self.serial_events.append(
            PokeySerialEvent(
                irq_bit=int(IRQBits.SERIAL_IN_DONE),
                cycles_remaining=delay,
                data=data & 0xFF,
                skstat=skstat & 0xFF,
            )
        )
        self.irqst |= int(IRQBits.SERIAL_IN_DONE)

    def channel_frequency(self, channel: int) -> float:
        base_clock = 15_699.0 if (self.audctl & 0x01) else 63_921.0
        period = max(1, self._timer_period(channel))
        return base_clock / period

    def channel_volume(self, channel: int) -> float:
        return (self.audc[channel] & 0x0F) / 15.0

    def set_paddle(self, paddle: int, value: int) -> None:
        if not 0 <= paddle < len(self.pot_values):
            msg = "paddle index out of range"
            raise ValueError(msg)
        if not 0 <= value <= 228:
            msg = "paddle value must be in range 0..228"
            raise ValueError(msg)
        self.pot_values[paddle] = value
        self.allpot = 0xFF

    def generate_samples(self, sample_count: int, sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE) -> list[float]:
        if sample_count < 0:
            msg = "sample_count must be non-negative"
            raise ValueError(msg)
        if sample_rate <= 0:
            msg = "sample_rate must be positive"
            raise ValueError(msg)

        samples: list[float] = []
        for _ in range(sample_count):
            mixed = 0.0
            active = 0
            for channel, state in enumerate(self.audio_channels):
                volume = self.channel_volume(channel)
                if volume <= 0.0:
                    continue
                frequency = self.channel_frequency(channel)
                state.phase = (state.phase + (frequency / sample_rate)) % 1.0
                waveform = 1.0 if state.phase < 0.5 else -1.0
                mixed += waveform * volume
                active += 1
            samples.append(mixed / active if active else 0.0)
        return samples

    def _reload_timer(self, channel: int) -> None:
        timer = self.timers[channel]
        timer.reload_value = self._timer_period(channel)
        timer.counter = timer.reload_value
        timer.cycle_accumulator = 0

    def _timer_period(self, channel: int) -> int:
        if channel == 0 and self.audctl & 0x10:
            return (((self.audf[1] << 8) | self.audf[0]) + 1)
        if channel == 2 and self.audctl & 0x08:
            return (((self.audf[3] << 8) | self.audf[2]) + 1)
        return self.audf[channel] + 1

    def _timer_irq_bit(self, channel: int) -> int | None:
        return CHANNEL_TO_IRQ.get(channel)

    def _timer_clock_divider(self, channel: int) -> int:
        if channel in {0, 1} and self.audctl & int(AUDCTLBits.CH1_179MHZ):
            return 1
        if channel in {2, 3} and self.audctl & int(AUDCTLBits.CH3_179MHZ):
            return 1
        if self.audctl & int(AUDCTLBits.CLOCK_15KHZ):
            return CPU_CYCLES_PER_POKEY_15KHZ_TICK
        return CPU_CYCLES_PER_POKEY_64KHZ_TICK

    def _advance_timer(self, channel: int, timer: PokeyTimer, ticks: int) -> bool:
        irq_triggered = False
        while ticks > 0:
            if ticks < timer.counter:
                timer.counter -= ticks
                break
            ticks -= timer.counter
            timer.counter = timer.reload_value
            irq_bit = self._timer_irq_bit(channel)
            if irq_bit is None:
                continue
            if self.irqen & irq_bit:
                self.irqst &= ~irq_bit & 0xFF
                irq_triggered = True
        return irq_triggered

    def _queue_serial_event(self, irq_bit: int) -> None:
        self.serial_events = [
            event for event in self.serial_events if event.irq_bit != irq_bit
        ]
        self.serial_events.append(
            PokeySerialEvent(
                irq_bit=irq_bit,
                cycles_remaining=CPU_CYCLES_PER_SERIAL_BYTE,
            )
        )
        self.irqst |= irq_bit

    def _advance_serial(self, cycles: int) -> bool:
        if not self.serial_events:
            return False

        irq_triggered = False
        remaining_events: list[PokeySerialEvent] = []
        for event in self.serial_events:
            event.cycles_remaining -= cycles
            if event.cycles_remaining > 0:
                remaining_events.append(event)
                continue
            if self.irqen & event.irq_bit:
                if event.data is not None:
                    self.serin = event.data
                if event.skstat is not None:
                    self.skstat = event.skstat
                self.irqst &= ~event.irq_bit & 0xFF
                if event.irq_bit == int(IRQBits.SERIAL_OUT_DONE):
                    self.serial_transfer_active = False
                irq_triggered = True
            else:
                self.irqst |= event.irq_bit
                # Keep matured serial events latched until software enables the
                # relevant IRQ source; the ROM can enable serial IRQs after the
                # byte has already finished shifting.
                event.cycles_remaining = 0
                remaining_events.append(event)
        self.serial_events = remaining_events
        return irq_triggered

    def _serial_event_pending(self, irq_bit: int) -> bool:
        return any(event.irq_bit == irq_bit for event in self.serial_events)

    def _next_random_byte(self) -> int:
        bit = ((self.random_state >> 16) ^ (self.random_state >> 11)) & 1
        self.random_state = ((self.random_state << 1) | bit) & 0x1FFFF
        return self.random_state & 0xFF

    def _normalize(self, address: int) -> int:
        return POKEY_MIRROR_BASE + ((address - POKEY_MIRROR_BASE) & POKEY_MIRROR_MASK)
