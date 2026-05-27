# 0007: CPU Packed Status Byte, Dispatch Table, and Stack Bypass

## Status

Accepted

## Date

2026-05-27

## Context

Profiling identified three CPU hot-path bottlenecks that together consumed a
substantial fraction of per-frame CPU time:

1. **StatusRegister dataclass overhead (~0.103 s/20 frames).**  
   The `status` field was a `StatusRegister` dataclass with 8 `bool` fields.
   `to_byte()` — which must pack those fields into a single byte — called
   `int()` on each of the 8 booleans and then OR'd the results together.
   `to_byte()` was called ~85,000 times per frame for interrupt handling
   alone.

2. **60+ if/elif chain in `_execute()` (~0.153 s/20 frames).**  
   Every instruction dispatch went through a string-equality chain up to 60+
   comparisons deep.  The common mnemonics (LDA, STA, BNE, …) were near the
   top, but uncommon ones at the bottom paid the full chain cost.

3. **Full memory-bus dispatch for stack reads/writes.**  
   `_push_byte()` / `_pop_byte()` called `memory.write_byte()` /
   `memory.read_byte()`, which walk a 65536-entry handler table even though
   the stack page (0x0100–0x01FF) is always plain RAM with no handlers ever
   registered there.

## Decision

### 1. Replace StatusRegister field with a packed integer `p`

All flag state is now held in `self.p: int` (a single Python `int`), using
the standard 6502 NV1BDIZC bit layout.  All flag operations inside the CPU
use direct bitwise operations:

```python
# update N and Z in one expression, no attribute access
self.p = (self.p & 0x7D) | (value & 0x80) | (0x02 if value == 0 else 0)
```

This eliminates every `int()` cast and attribute store that `to_byte()` used.

### 2. Two-class design to support a property on a slots dataclass

Python 3.10+ does not allow `@property` on a `dataclass(slots=True)`.  The
solution is a split:

- `_CPUBase` — `@dataclass(slots=True)` holding all primitive fields including `p`.
- `CPU(_CPUBase)` — subclass with `__slots__ = ()` that adds the `status`
  property as a backward-compatibility shim.

### 3. `status` property returns a live proxy (`_StatusProxy`)

A large amount of existing code (tests, `machine.py`) mutates individual flags
through `cpu.status.carry = True`-style attribute writes.  Rather than rewrite
every call site, `CPU.status` returns a `_StatusProxy` object that intercepts
all attribute reads and writes and translates them directly into bit operations
on `self.p`.  The proxy has `__slots__ = ("_cpu",)` and uses
`object.__getattribute__` to avoid its own property overhead.

Assigning a full `StatusRegister` to `cpu.status` (used by the Klaus Dormann
test harness and the `reset()` path) goes through the setter, which calls
`value.to_byte() | _P_R` and stores the result in `self.p`.

### 4. Per-mnemonic dispatch table instead of if/elif chain

A dict mapping `mnemonic → handler method` is built once in `__post_init__`.
`_execute()` becomes a single dict lookup:

```python
def _execute(self, opcode, operand):
    self._dispatch[opcode.mnemonic](opcode, operand)
```

Each mnemonic gets its own `_exec_<mnemonic>` method.  This removes O(n)
linear search and makes each hot instruction path a single dict hit.

### 5. Stack bypass — direct `memory.ram` access

`_push_byte()` / `_pop_byte()` now index `self.memory.ram` directly:

```python
def _push_byte(self, value: int) -> None:
    self.memory.ram[STACK_BASE + self.sp] = value & 0xFF
    self.sp = (self.sp - 1) & 0xFF
```

This is safe because the stack page is always backed by the `bytearray` at
`memory.ram` and no hardware or ROM handler is ever registered there.

## Consequences

- **Correctness unchanged**: all 182 existing tests continue to pass.  The
  `StatusRegister` class and `_StatusProxy` maintain the full external API;
  code that reads or writes individual flag attributes through `cpu.status`
  still works without modification.
- **`StatusRegister` is still importable** from `pyatari.cpu` for tests and
  external code that constructs status values by name.
- **`Opcode` is still importable** from `pyatari.cpu` (re-exported from
  `pyatari.opcodes`) as `machine.py` depends on it.
- **Performance**: the three bottlenecks described above are eliminated.
  `to_byte()` calls drop to near zero; `_execute()` dispatch is O(1); stack
  R/W bypasses the full handler-table walk.
- **Readability**: each instruction is now a self-contained method rather than
  a branch buried in a long chain, making it easier to locate and audit any
  single mnemonic's behavior.
- **Maintainability**: adding a new undocumented opcode requires only a new
  `_exec_<mnemonic>` method and one entry in the `_dispatch` dict.
