# 0002: Performance Benchmarking Infrastructure and Hot-Path Optimizations

## Status

Accepted

## Date

2026-05-08

## Context

PyAtari is intentionally clarity-first. The codebase prioritizes readable,
pedagogically correct emulation over speed. Even so, performance matters at
two levels:

1. **Regression tracking**: without a baseline, future changes could silently
   make the emulator slower.
2. **Developer experience**: an emulator that runs at under 1fps for a demo
   screen is hard to use interactively, even for educational purposes.

Before any optimization work, there was no way to measure frame throughput,
instruction cost, or the relative expense of each subsystem. The codebase
also had several obviously avoidable allocations and loop structures in the
hottest paths that a profiler confirmed as real bottlenecks.

## Decision

### Benchmarking infrastructure

We add `pytest-benchmark >= 4.0` as a dev dependency and a `benchmarks/`
directory at the project root. Benchmark files follow the pattern
`bench_<module>.py` so they are clearly separate from correctness tests in
`tests/`. The `[tool.pytest.ini_options]` section in `pyproject.toml` adds
`python_files = ["test_*.py", "bench_*.py"]` to allow pytest to collect both.

Five benchmark modules cover the full call stack:

- `bench_cpu.py` — individual instruction types (NOP, LDA, STA, BNE, JMP,
  1000-step bulk)
- `bench_memory.py` — plain RAM vs hardware-register dispatch
- `bench_rendering.py` — GTIA color conversion, per-scanline render, full
  frame render, ANTIC tick cost
- `bench_machine.py` — `machine.step()`, `run_frame()` (with and without
  audio), 10-frame bulk
- `bench_input.py` — key press/release, joystick, trigger, POKEY tick,
  POKEY audio generation

All benchmarks run ROM-free: they use the `bare_machine` fixture (NOPs loaded
at `$2000`, PC set there) or the `demo_machine` fixture (built-in graphics
demo, no external ROM files required). This matches the pattern established
in `tests/test_integration.py`.

### Baseline results persistence

Raw JSON snapshots from `pytest --benchmark-save=<label>` are committed to
`benchmarks/results/`. A small `benchmarks/report.py` script reads a JSON
file and regenerates `BENCHMARKS.md` in the project root. Both the JSON and
the Markdown are tracked in git so the performance history is visible in the
commit log.

Baseline numbers (Linux CPython 3.12 64-bit, 2026-05-08):

- `run_frame` NOP sled: **56.9 ms** → **17.6 fps**
- `run_frame` demo screen: **1198 ms** → **0.8 fps**

### Hot-path optimizations (post-baseline)

Profiling 30 NOP-sled frames with `cProfile` identified four call sites
responsible for the majority of overhead. Each change is a semantically
equivalent transformation that preserves readability:

**1. `ANTIC.tick()` — arithmetic instead of a per-cycle loop**

The old implementation incremented `cycles_into_scanline` once per cycle in a
`for _ in range(cycles)` loop. With 29,868 CPU cycles per frame, that loop
body executed ~30 K times per frame even when no scanline boundary was
crossed. Replaced with a single `divmod` on the total cycle count; the
per-scanline loop now runs at most ~262 iterations per frame.

**2. `CPU._resolve_operand()` — singleton for implied/accumulator modes**

`_resolve_operand` previously called `AddressResult(address=None)` for every
implied or accumulator instruction, allocating a new frozen dataclass on each
call. A module-level `_IMPLIED_OPERAND = AddressResult(address=None)`
singleton eliminates the allocation for the roughly half of all instructions
that have no operand.

**3. `MemoryBus._read_rom_overlay()` — fast-path return for low RAM**

The ROM overlay check started with `BASIC_ROM_START` ($A000), which meant
every plain RAM read in the `$0000`–`$4FFF` range (stack, zero page, program
code) ran through two or three range comparisons before returning `None`.
Adding `if address < SELF_TEST_START: return None` at the top short-circuits
these checks for the address range that will never match any ROM region.

**4. `MasterClock.tick_instruction()` removed**

`tick_instruction` was a single-line passthrough that called `self.tick()`.
The indirection added a Python call-frame for every instruction executed.
Removing the wrapper and calling `clock.tick()` directly eliminates the extra
frame with no behavioral change.

Post-optimization numbers (same hardware):

- `run_frame` NOP sled: **30.2 ms** → **33.1 fps** (+88%)
- `run_frame` demo screen: **920 ms** → **1.09 fps** (+36%)

## Consequences

### Positive

- Frame throughput has a documented baseline; future regressions are
  detectable via `--benchmark-compare`.
- The four optimizations together nearly double NOP-sled frame rate with no
  change to observable emulator behavior.
- All changes are local and semantically transparent; a reader can verify each
  one is correct by inspection.
- No new abstractions, no magic numbers, no behavioral flags introduced.

### Negative

- `pytest benchmarks/` is a separate run from `pytest tests/`; contributors
  need to remember to run benchmarks explicitly when touching hot paths.
- `BENCHMARKS.md` must be regenerated manually after each benchmark save;
  it is not updated automatically by CI.
- The demo-screen frame rate (1.09 fps) is still far below interactive speed.
  The remaining bottleneck is the GTIA rendering path, which was not touched
  in this session.

### Ongoing Implications

- Before any further performance work, run `pytest benchmarks/ --benchmark-save=<label>`
  to capture a new snapshot, then use `--benchmark-compare` to confirm
  improvement.
- Any future optimization must keep the code readable; the project's purpose
  is education, not raw performance.
- When a new subsystem is added or a hot path is refactored, add a matching
  benchmark in the appropriate `bench_*.py` file and update `BENCHMARKS.md`.
