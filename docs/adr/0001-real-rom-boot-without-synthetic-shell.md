# 0001: Real ROM Boot Without a Synthetic Shell

## Status

Accepted

## Date

2026-04-10

## Context

PyAtari originally used a synthetic BASIC/MEMO PAD shell so `uv run pyatari`
would show a visible and interactive text screen even though the real XL OS and
BASIC ROM path was not yet booting correctly.

That shell was useful as a temporary frontend fallback, but it introduced a
serious architectural problem for this project:

- it was not emulation of the real Atari 800XL
- it obscured real hardware and ROM bring-up bugs
- it created shell-specific behavior and tests that could be mistaken for ROM
  correctness
- it worked against the project's educational goal of showing how the actual
  machine behaves

The project direction is explicit: accuracy and clarity come first, even when
that exposes incomplete emulation.

## Decision

PyAtari will no longer provide a synthetic BASIC/MEMO PAD runtime path.

The supported startup paths are now:

- real ROM boot when OS ROMs are present
- ROM-free graphics demo only when no ROMs are available
- raw XEX loading as a separate non-ROM execution path

Related consequences of this decision:

- shell-only machine state and input handling were removed from `machine.py`
- shell-backed integration tests were deleted
- Phase 16 planning was updated to record shell removal as completed work
- ongoing work focuses on the actual OS/BASIC boot sequence, especially ANTIC,
  POKEY, PIA, SIO, and interrupt semantics

## Consequences

### Positive

- Runtime behavior now reflects actual emulator state more honestly.
- Boot failures are visible as emulator bugs rather than hidden by a fallback UI.
- Tests now align better with ROM-observable behavior.
- The codebase is simpler because it no longer carries a second fake execution
  model.

### Negative

- Until the real ROM boot path is complete, users may see an incomplete boot
  rather than a friendlier fake READY prompt.
- Some previous demo-style interaction is gone.

### Ongoing Implications

- Emulator progress should be measured against real ROM milestones, not shell
  parity.
- When temporary diagnostics are needed, they should be trace tools, debug
  switches, or narrowly scoped instrumentation, not alternate fake machine
  behavior.
