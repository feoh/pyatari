# PyAtari -- Educational Atari 800XL Emulator in Python

## Context

Build a readable, well-documented Atari 800XL emulator in Python for educational purposes. The goal is helping people understand how an 8-bit computer works by seeing every hardware component represented in a modern high-level language. Performance is explicitly not a goal -- clarity is.

## Project Structure

```
pyatari/
├── pyproject.toml
├── README.md
├── roms/
│   └── .gitkeep
├── tests/
│   ├── conftest.py
│   ├── test_cpu.py
│   ├── test_cpu_addressing.py
│   ├── test_cpu_opcodes.py
│   ├── test_memory.py
│   ├── test_antic.py
│   ├── test_gtia.py
│   ├── test_pokey.py
│   ├── test_pia.py
│   ├── test_sio.py
│   ├── test_integration.py
│   └── roms/                   # Hand-crafted test ROM stubs
│       ├── test_os.bin
│       └── test_basic.bin
├── src/
│   └── pyatari/
│       ├── __init__.py
│       ├── cpu.py              # MOS 6502C core
│       ├── addressing.py       # Address mode logic
│       ├── opcodes.py          # Opcode table (enums + dataclasses)
│       ├── disassembler.py     # 6502 disassembler
│       ├── memory.py           # 64KB address space, bank switching
│       ├── antic.py            # Display list processor, DMA
│       ├── gtia.py             # Color, P/M graphics, collisions
│       ├── pokey.py            # Sound, keyboard, timers, IRQ, RNG
│       ├── pia.py              # Joystick ports, bank config
│       ├── sio.py              # Serial bus, ATR/XEX loader
│       ├── clock.py            # Master clock, cycle sync
│       ├── machine.py          # Top-level integration
│       ├── display.py          # pygame rendering
│       ├── audio.py            # pygame audio from POKEY
│       ├── debugger.py         # Interactive debugger/inspector
│       ├── rom_loader.py       # ROM loading/validation
│       └── constants.py        # Memory map, timing, enums
└── tools/
    ├── dis6502.py              # Standalone disassembler CLI
    └── inspect_atr.py          # ATR disk image inspector
```

## Dependencies

- Python >= 3.12, managed with `uv`
- `pygame-ce` -- display, audio, input (community edition, actively maintained)
- `numpy` -- frame buffers, audio sample generation
- Dev: `pytest`, `pytest-cov`, `mypy`, `ruff`

## Key Architectural Decisions

- **Status register**: Dataclass with named boolean fields + `to_byte()`/`from_byte()` for readability
- **Scanline-based main loop**: Each of 262 scanlines: ANTIC DMA, CPU runs remaining cycles, POKEY ticks, GTIA renders
- **Register I/O dispatch**: MemoryBus uses a dict mapping address ranges to chip handler callables
- **Frame buffer**: numpy `(240, 384)` uint32 array, blitted to pygame Surface per frame
- **ROM handling**: Users supply their own ROM images; test stubs provided for automated testing

---

## Implementation Phases

Each phase is sized for one Claude session (~2-4 hours). Each produces something testable.

### Phase 1: Project Skeleton and Constants
- Create `pyatari/` folder, `pyproject.toml` with uv, directory structure
- `constants.py`: Memory map addresses (ANTIC $D400-$D40F, GTIA $D000-$D01F, POKEY $D200-$D20F, PIA $D300-$D303), timing constants (114 cycles/scanline, 262 scanlines/frame, 1789773 Hz CPU clock)
- `conftest.py` with initial test fixtures
- **Test**: `uv run pytest` passes with a trivial test

### Phase 2: Memory Subsystem
- `memory.py`: `MemoryBus` class -- 64KB bytearray, read/write, ROM overlays (read-only regions), hardware register dispatch via callbacks, bank switching via PIA PORTB bits, hex dump utility
- `rom_loader.py`: Load/validate ROM files, create test stubs
- **Test**: RAM r/w, ROM read-only, bank switching toggles, register dispatch, hex dump

### Phase 3: 6502 CPU -- Data Structures and Fetch/Decode
- `opcodes.py`: `AddressMode` enum, `Opcode` dataclass, full 151-entry official opcode table
- `addressing.py`: `resolve_address(cpu, mode)` for all 13 address modes
- `cpu.py`: `CPU` class (registers, status flags as dataclass), `fetch()`, `decode()`, `step()` skeleton
- `disassembler.py`: `disassemble(memory, addr) -> (str, int)`
- **Test**: Opcode table completeness, address resolution per mode, disassembler output

### Phase 4: 6502 CPU -- All Instructions
- Implement all instruction execution grouped by category: load/store, transfer, stack, arithmetic (ADC/SBC with decimal mode), logic, shift/rotate, inc/dec, compare, branch (with page-cross penalties), jump (including JMP indirect page-boundary bug), interrupt (BRK/RTI), flags, NOP
- **Test**: Klaus Dormann's 6502 functional test suite (exhaustive CPU validation), plus unit tests for decimal mode, JMP indirect bug, branch page-crossing

### Phase 5: Clock, Interrupts, and Machine Loop
- `clock.py`: `MasterClock` -- cycle counting, scanline/frame tracking, VBLANK detection
- CPU interrupt handling: `irq()`, `nmi()`, pending flags
- `machine.py` (initial): `Machine` class owning CPU + MemoryBus + Clock, `reset()`, `run_frame()`, `run_until(addr)`, `run_steps(n)`
- **Test**: Clock counts correctly, reset vector loads, NMI/IRQ fire properly, machine runs test ROM stub

### Phase 6: PIA (6520)
- `pia.py`: Ports A/B with data and direction registers, PACTL/PBCTL, joystick bits (Port A), bank switching (Port B), IRQ flags
- Wire to MemoryBus at $D300-$D3FF (mirrored every 4 bytes)
- Connect Port B writes to `MemoryBus.update_bank_config()`
- **Test**: DDR/data selection, joystick bits, bank switching via PORTB, register mirroring

### Phase 7: ANTIC -- Display List Processor (Core)
- `antic.py`: Registers (DMACTL, DLISTL/H, CHBASE, WSYNC, VCOUNT, NMIEN/NMIST), display list instruction parsing (blank lines, mode lines, JMP, JVB, LMS bit, DLI bit), scanline-by-scanline execution, WSYNC halt, VBI/DLI NMI generation
- **Test**: Parse simple display list, VCOUNT accuracy, WSYNC halt, DLI/VBI triggers, LMS loading

### Phase 8: GTIA -- Color and Playfield Rendering
- `gtia.py`: Write registers (COLPF0-3, COLBK, COLPM0-3, PRIOR, GRACTL), read registers (collision regs, CONSOL, TRIG), Atari color model (16 hues x 16 lum = 256 colors), `render_scanline()` producing RGB pixels
- `display.py` (initial): pygame window (384x240), numpy frame buffer blitting
- **Test**: Color registers, palette mapping, ANTIC mode 2 text rendering, static "hello world" screen

### Phase 9: ANTIC Graphics Modes and Character Sets
- All ANTIC text modes (2-7) and bitmap/map modes (8-F)
- Character set DMA from CHBASE, inverse video, CHACTL descenders
- GTIA rendering for each mode's color register mapping
- **Test**: Each mode renders correctly, inverse video, mode switching mid-display, CHBASE switching

### Phase 10: POKEY -- Timers, Keyboard, IRQ
- `pokey.py`: 4 hardware timers (AUDF/AUDC), AUDCTL clock selection, 16-bit timer chaining, KBCODE/SKSTAT keyboard, IRQEN/IRQST, RANDOM (17-bit LFSR), serial I/O registers
- **Test**: Timer countdown/IRQ, keyboard codes, IRQ masking, RANDOM variability, AUDCTL effects

### Phase 11: POKEY -- Sound Generation
- Square wave generation per channel, frequency calculation, volume/distortion from AUDC, polynomial counter sequences (4/5/9/17-bit LFSRs), high-pass filter, `generate_samples()` producing numpy audio buffers
- `audio.py`: pygame audio initialization, buffer queueing, volume control
- **Test**: Frequency accuracy, volume scaling, distortion patterns, 4-channel mixing, continuous playback

### Phase 12: Player/Missile Graphics (Sprites)
- ANTIC P/M DMA from PMBASE, single/double-line resolution
- GTIA: HPOS registers, SIZE registers, priority (PRIOR), overlay onto playfield, collision detection registers, HITCLR, 5th player mode, GTIA special modes ($40/$80/$C0)
- **Test**: Player positioning, size doubling, priority rendering, collision detection, 5th player, P/M DMA

### Phase 13: SIO Bus and Disk/Program Loading
- `sio.py`: `SIOBus` + `DiskDrive` (ATR format parsing, Status/Read/Write/Format commands), XEX binary loader (multi-segment, INIT/RUN vectors)
- High-level SIO (OS vector intercept) and low-level SIO (POKEY serial registers)
- **Test**: ATR parsing, SIO command protocol, XEX loading, boot from ATR sectors

### Phase 14: Interactive Debugger
- `debugger.py`: step/next/continue, breakpoints, watchpoints, register display, disassembly, memory dump, chip state display (antic/gtia/pokey/pia), display list viewer, instruction trace, execution history ring buffer
- **Test**: Step advances PC, breakpoints halt, watchpoints trigger, disassembly correct, history works

### Phase 15: Input Handling and Scrolling
- PC keyboard -> Atari KBCODE mapping, START/SELECT/OPTION -> CONSOL, RESET -> NMI, BREAK -> IRQ, joystick via arrow keys -> PIA Port A, fire -> TRIG0
- ANTIC fine scrolling: HSCROL/VSCROL with VS/HS display list bits, coarse scrolling via LMS
- **Test**: Key mappings, CONSOL register, joystick bits, fine scroll pixel shifts

### Phase 16: Integration and Boot to Ready Prompt
- Full frame loop: per-scanline ANTIC DMA + CPU + POKEY + GTIA rendering, DMA cycle stealing, frame rendering + audio + input
- Status bar (PC, FPS, scanline), turbo toggle
- **Test with real ROMs**: Boot to MEMO PAD or BASIC READY, type on keyboard, run `10 PRINT "HELLO" : GOTO 10`
- **Test without ROMs**: Load and run a raw XEX binary

### Phase 17 (Optional): Additional Peripherals
- Cassette (CAS format), printer emulation, second joystick, paddle controllers

### Phase 18 (Optional): Undocumented 6502 Opcodes
- ~105 illegal opcodes (LAX, SAX, DCP, ISB, SLO, RLA, SRE, RRA, etc.) used by many commercial games

---

## Dependency Graph

```
Phase 1 (Constants)
  └─ Phase 2 (Memory)
       └─ Phase 3 (CPU Structure)
            └─ Phase 4 (CPU Opcodes)
                 └─ Phase 5 (Clock/Machine)
                      ├─ Phase 6 (PIA)
                      ├─ Phase 7 (ANTIC Core)
                      │    ├─ Phase 8 (GTIA/Display)
                      │    │    └─ Phase 9 (All Modes)
                      │    └─ Phase 12 (P/M Graphics)
                      ├─ Phase 10 (POKEY Timers/KB)
                      │    └─ Phase 11 (POKEY Sound)
                      ├─ Phase 13 (SIO/Disk)
                      └─ Phase 14 (Debugger)

Phases 6-14 can be worked somewhat in parallel after Phase 5.
Phase 15 (Input/Scroll) depends on Phases 6, 7, 10.
Phase 16 (Integration) depends on all prior phases.
```

## Verification Plan

1. **Per-phase**: Each phase includes specific unit tests described above
2. **CPU validation**: Klaus Dormann's 6502 functional test suite (Phase 4)
3. **Visual validation**: Hand-crafted display lists producing known screen output (Phase 8-9)
4. **Audio validation**: Known frequency/tone sequences (Phase 11)
5. **End-to-end**: Boot with real Atari ROMs to BASIC READY prompt (Phase 16)
6. **ROM-free**: Load and execute XEX binaries without needing copyrighted ROMs
