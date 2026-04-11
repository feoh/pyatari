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

## 2026-04-10 Follow-Up Notes

After shell removal, the next ROM-boot blockers turned out to be machine reset
state and SIO behavior rather than display setup alone.

This session recorded and implemented these follow-up decisions:

- `Machine.reset()` must restore PIA banking and immediately sync seeded OS
  display shadows into live ANTIC/GTIA state so ROM boot starts from a coherent
  XL-visible reset state.
- The low-level SIO bus path must not synthesize an immediate "no device"
  response for an absent drive. Per the Altirra Hardware Reference Manual,
  an unaddressed or absent peripheral ignores the command and forces a host-side
  timeout/retry path instead.
- A high-level `SIOV` fast path is acceptable as a temporary educational aid
  while low-level serial timeout behavior is still incomplete, as long as it
  returns OS-visible results that match the ROM's expectations and does not
  hide the remaining hardware gaps.

Relevant Altirra guidance used for this session:

- SIO peripherals ignore commands not meant for them or with invalid framing,
  rather than replying with a synthetic error.
- The host only waits briefly for ACK/NAK before retrying.
- Disk status includes timeout information that the stock OS uses for command
  retry behavior.

Observed outcome from these changes:

- Real ROM boot no longer stalls in the previous `$EB18` D1: probe loop when
  no disk is attached.
- The ROM path now progresses into the `$F2FD`-`$F312` area and produces the
  first visible non-black frame during boot tracing.
- The ROM path reaches the BASIC `READY` prompt and waits in the editor's
  keyboard polling loop around `$F2FD`-`$F312`.
- POKEY keyboard state now follows the Altirra-described scan contract more
  closely for the emulator's current level of detail: `SKCTL` bit 1 gates
  keyboard scanning, debounced key-down state clears `SKSTAT` bit 2, `KBCODE`
  remains latched after release, and a key press asserts the keyboard IRQ when
  `IRQEN` enables it.
- Shifted keyboard input now sets the `KBCODE` Shift modifier bit and the
  active-low `SKSTAT` Shift state so ROM-driven BASIC entry can produce quoted
  strings and other shifted punctuation through the real editor path.
- A ROM smoke test can now type `10PRINT"A"`, press Return, type `RUN`, press
  Return, print `A`, and return to the BASIC `READY` prompt without using the
  removed synthetic shell.
- The pygame frontend now tracks which key events generated Atari key presses
  so printable punctuation entered through `event.unicode` is released on the
  matching `KEYUP`. This matters for ROM-driven BASIC entry because quoted
  strings and colon-separated statements depend on shifted punctuation not
  leaving POKEY's key-down state stuck.
- Real ROM boot is now the default startup path whenever an OS ROM is available;
  `--real-rom-boot` remains accepted for compatibility, and `--demo` is the
  explicit opt-in path for the built-in ROM-free graphics demo.
- Frontend keyboard input is now buffered and delivered to the emulator one key
  at a time across multiple frames. This avoids losing fast host typing when
  pygame receives multiple keydown/keyup pairs before the slower Python emulator
  has advanced far enough for the Atari ROM keyboard handler to observe them.

This keeps the project aligned with the original decision in this ADR:
temporary help for incomplete ROM boot should come from targeted diagnostics and
narrow compatibility shims, not from restoring a fake shell runtime.
