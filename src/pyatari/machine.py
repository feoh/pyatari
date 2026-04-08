"""Initial top-level machine integration for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.clock import MasterClock
from pyatari.constants import CYCLES_PER_FRAME
from pyatari.cpu import CPU, Opcode
from pyatari.memory import MemoryBus


@dataclass(slots=True)
class Machine:
    """Own the major emulator subsystems and drive execution."""

    memory: MemoryBus = field(default_factory=MemoryBus)
    cpu: CPU = field(init=False)
    clock: MasterClock = field(default_factory=MasterClock)

    def __post_init__(self) -> None:
        self.cpu = CPU(memory=self.memory)

    def reset(self) -> None:
        self.clock.reset()
        self.cpu.reset()

    def step(self) -> Opcode:
        before = self.cpu.cycles
        opcode = self.cpu.step()
        self.clock.tick_instruction(self.cpu.cycles - before)
        return opcode

    def run_steps(self, steps: int) -> list[Opcode]:
        if steps < 0:
            msg = "steps must be non-negative"
            raise ValueError(msg)
        return [self.step() for _ in range(steps)]

    def run_until(self, address: int, max_steps: int = 100_000) -> int:
        address &= 0xFFFF
        if self.cpu.pc == address:
            return 0

        for executed in range(1, max_steps + 1):
            self.step()
            if self.cpu.pc == address:
                return executed

        msg = f"CPU did not reach address {address:#06x} within {max_steps} steps"
        raise TimeoutError(msg)

    def run_frame(self) -> int:
        target_cycles = self.clock.total_cycles + CYCLES_PER_FRAME
        steps = 0
        while self.clock.total_cycles < target_cycles:
            self.step()
            steps += 1
        return steps
