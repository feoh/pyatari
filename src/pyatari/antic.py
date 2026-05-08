"""ANTIC core emulation for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.constants import (
    ANTIC_MODES,
    ANTICRegister,
    CYCLES_PER_SCANLINE,
    DL_DLI_BIT,
    DL_HSCROL_BIT,
    DL_LMS_BIT,
    DL_MODE_MASK,
    DL_VSCROL_BIT,
    DLInstruction,
    DMACTLBits,
    NMIBits,
    SCANLINES_PER_FRAME,
    VBLANK_START_SCANLINE,
)
from pyatari.memory import MemoryBus

ANTIC_MIRROR_BASE = int(ANTICRegister.DMACTL)
ANTIC_MIRROR_MASK = 0x0F
DL_DMA = int(DMACTLBits.DL_DMA)


@dataclass(slots=True)
class DisplayListLine:
    instruction_address: int
    instruction: int
    mode: int | None
    scanlines: int
    screen_address: int | None = None
    load_memory_scan: bool = False
    dli: bool = False
    hscroll: bool = False
    vscroll: bool = False
    jump_target: int | None = None
    wait_for_vblank: bool = False


@dataclass(slots=True)
class ANTIC:
    memory: MemoryBus
    dmactl: int = 0
    chactl: int = 0
    dlist: int = 0
    hscrol: int = 0
    vscrol: int = 0
    pmbase: int = 0
    chbase: int = 0
    nmien: int = 0
    nmist: int = 0
    scanline: int = 0
    cycles_into_scanline: int = 0
    display_list_pc: int = 0
    screen_memory_address: int = 0
    current_line: DisplayListLine | None = None
    current_line_remaining: int = 0
    wsync_requested: bool = False
    _last_triggered_events: list[str] = field(default_factory=list)
    _nmi_asserted: bool = False

    def install(self) -> None:
        self.memory.register_read_handler(0xD400, 0xD4FF, self.read_register)
        self.memory.register_write_handler(0xD400, 0xD4FF, self.write_register)

    def reset(self) -> None:
        self.dmactl = 0
        self.chactl = 0
        self.dlist = 0
        self.hscrol = 0
        self.vscrol = 0
        self.pmbase = 0
        self.chbase = 0
        self.nmien = 0
        self.nmist = 0
        self.scanline = 0
        self.cycles_into_scanline = 0
        self.display_list_pc = 0
        self.screen_memory_address = 0
        self.current_line = None
        self.current_line_remaining = 0
        self.wsync_requested = False
        self._last_triggered_events = []
        self._nmi_asserted = False

    def read_register(self, address: int) -> int:
        register = self._normalize(address)
        if register == ANTICRegister.DMACTL:
            return self.dmactl
        if register == ANTICRegister.CHACTL:
            return self.chactl
        if register == ANTICRegister.DLISTL:
            return self.dlist & 0xFF
        if register == ANTICRegister.DLISTH:
            return (self.dlist >> 8) & 0xFF
        if register == ANTICRegister.HSCROL:
            return self.hscrol
        if register == ANTICRegister.VSCROL:
            return self.vscrol
        if register == ANTICRegister.PMBASE:
            return self.pmbase
        if register == ANTICRegister.CHBASE:
            return self.chbase
        if register == ANTICRegister.WSYNC:
            return 0
        if register == ANTICRegister.VCOUNT:
            return (self.scanline // 2) & 0xFF
        if register == ANTICRegister.PENH:
            return 0
        if register == ANTICRegister.PENV:
            return self.scanline & 0xFF
        if register == ANTICRegister.NMIEN:
            return self.nmien
        if register == ANTICRegister.NMIST:
            return self.nmist
        raise ValueError(f"Unknown ANTIC register {register:#06x}")

    def write_register(self, address: int, value: int) -> None:
        value &= 0xFF
        register = self._normalize(address)
        if register == ANTICRegister.DMACTL:
            self.dmactl = value
        elif register == ANTICRegister.CHACTL:
            self.chactl = value
        elif register == ANTICRegister.DLISTL:
            self.dlist = (self.dlist & 0xFF00) | value
            self.display_list_pc = self.dlist
        elif register == ANTICRegister.DLISTH:
            self.dlist = (self.dlist & 0x00FF) | (value << 8)
            self.display_list_pc = self.dlist
        elif register == ANTICRegister.HSCROL:
            self.hscrol = value & 0x0F
        elif register == ANTICRegister.VSCROL:
            self.vscrol = value & 0x0F
        elif register == ANTICRegister.PMBASE:
            self.pmbase = value
        elif register == ANTICRegister.CHBASE:
            self.chbase = value
        elif register == ANTICRegister.WSYNC:
            self.wsync_requested = True
        elif register == ANTICRegister.NMIEN:
            previous_nmien = self.nmien
            self.nmien = value & (int(NMIBits.DLI) | int(NMIBits.VBI))
            newly_enabled = self.nmien & ~previous_nmien
            if self.nmist & newly_enabled:
                self._nmi_asserted = True
        elif register == ANTICRegister.NMIST:
            self.nmist = 0
        else:
            return

    def tick(self, cycles: int, *, trigger_nmi: bool = True) -> list[str]:
        end = self.cycles_into_scanline + cycles
        if end < CYCLES_PER_SCANLINE:
            self.cycles_into_scanline = end
            return []
        scanlines, self.cycles_into_scanline = divmod(end, CYCLES_PER_SCANLINE)
        events: list[str] = []
        for _ in range(scanlines):
            events.extend(self._advance_scanline(trigger_nmi=trigger_nmi))
        return events

    def consume_wsync(self) -> bool:
        requested = self.wsync_requested
        self.wsync_requested = False
        return requested

    def consume_nmi(self) -> bool:
        asserted = self._nmi_asserted
        self._nmi_asserted = False
        return asserted

    def fetch_next_display_list_line(self) -> DisplayListLine:
        instruction_address = self.display_list_pc & 0xFFFF
        instruction = self.memory.read_byte(self.display_list_pc)
        self.display_list_pc = (self.display_list_pc + 1) & 0xFFFF

        low_nibble = instruction & DL_MODE_MASK
        if low_nibble == DLInstruction.JMP:
            target = self.memory.read_word(self.display_list_pc)
            self.display_list_pc = target
            return DisplayListLine(
                instruction_address=instruction_address,
                instruction=instruction,
                mode=None,
                scanlines=0,
                jump_target=target,
                wait_for_vblank=instruction == DLInstruction.JVB,
            )

        if low_nibble == 0:
            scanlines = ((instruction >> 4) & 0x07) + 1
            return DisplayListLine(
                instruction_address=instruction_address,
                instruction=instruction,
                mode=None,
                scanlines=scanlines,
                dli=bool(instruction & DL_DLI_BIT),
            )

        mode = low_nibble
        mode_info = ANTIC_MODES[mode]
        load_memory_scan = bool(instruction & DL_LMS_BIT)
        screen_address = None
        if load_memory_scan:
            screen_address = self.memory.read_word(self.display_list_pc)
            self.display_list_pc = (self.display_list_pc + 2) & 0xFFFF
            self.screen_memory_address = screen_address
        elif self.screen_memory_address:
            screen_address = self.screen_memory_address

        line = DisplayListLine(
            instruction_address=instruction_address,
            instruction=instruction,
            mode=mode,
            scanlines=mode_info.scanlines_per_row,
            screen_address=screen_address,
            load_memory_scan=load_memory_scan,
            dli=bool(instruction & DL_DLI_BIT),
            hscroll=bool(instruction & DL_HSCROL_BIT),
            vscroll=bool(instruction & DL_VSCROL_BIT),
        )
        if screen_address is not None:
            self.screen_memory_address = (screen_address + mode_info.bytes_per_line) & 0xFFFF
        return line

    def step_scanline(self, *, trigger_nmi: bool = True) -> DisplayListLine | None:
        triggered_events: list[str] = []
        if self.current_line_remaining <= 0:
            if self.dmactl & DL_DMA:
                self.current_line = self.fetch_next_display_list_line()
                if self.current_line.wait_for_vblank:
                    self.current_line_remaining = max(
                        1, SCANLINES_PER_FRAME - self.scanline
                    )
                else:
                    self.current_line_remaining = max(1, self.current_line.scanlines)
            else:
                self.current_line = None
                self.current_line_remaining = 1

        active_line = self.current_line
        self.current_line_remaining -= 1
        if self.current_line_remaining == 0 and active_line and active_line.dli:
            if self._set_nmist(NMIBits.DLI, trigger_nmi=trigger_nmi):
                triggered_events.append("dli")

        self.scanline = (self.scanline + 1) % SCANLINES_PER_FRAME
        if self.scanline == VBLANK_START_SCANLINE:
            if self._set_nmist(NMIBits.VBI, trigger_nmi=trigger_nmi):
                triggered_events.append("vbi")
        if self.scanline == 0:
            self.current_line = None
            self.current_line_remaining = 0
        self._last_triggered_events = triggered_events
        return active_line

    def _advance_scanline(self, *, trigger_nmi: bool) -> list[str]:
        line = self.step_scanline(trigger_nmi=trigger_nmi)
        events: list[str] = []
        if line is not None:
            events.append("scanline")
        events.extend(self._last_triggered_events)
        return events

    def _set_nmist(self, bit: NMIBits, *, trigger_nmi: bool) -> bool:
        del trigger_nmi
        bit_mask = int(bit)
        was_set = bool(self.nmist & bit_mask)
        self.nmist |= bit_mask
        triggered = not was_set and bool(self.nmien & bit_mask)
        if triggered:
            self._nmi_asserted = True
        return triggered

    def _normalize(self, address: int) -> int:
        return ANTIC_MIRROR_BASE + ((address - ANTIC_MIRROR_BASE) & ANTIC_MIRROR_MASK)
