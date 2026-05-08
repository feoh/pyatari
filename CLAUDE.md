# PyAtari — Claude Code Project Instructions

## Purpose

PyAtari is an educational Atari 800XL emulator. The primary goals are
**clarity and correctness**, in that order. Readability is a feature.
Optimizations are welcome, but must leave the code understandable.

## Architecture Decision Records

After completing any meaningful group of changes — a new subsystem, a
behavioral fix, a performance improvement, a refactor, or a removal —
**write or update an ADR** in `docs/adr/`.

Steps:
1. Pick the next sequence number (check `docs/adr/README.md`).
2. Create `docs/adr/NNNN-short-kebab-title.md` following the format in
   `docs/adr/0001-real-rom-boot-without-synthetic-shell.md`.
3. Add the new file to the "Current ADRs" list in `docs/adr/README.md`.
4. Include the ADR commit in the same PR or branch as the changes it
   documents.

The goal is a navigable record of *why* the emulator is built the way it is.
Future contributors (and future Claude sessions) depend on it.

## Benchmarks

When touching a hot path, capture a before/after snapshot:

```bash
# Before making changes:
uv run pytest benchmarks/ --benchmark-save=before-<label>

# After making changes:
uv run pytest benchmarks/ --benchmark-save=after-<label>

# Compare:
uv run pytest benchmarks/ --benchmark-compare=before-<label>

# Regenerate BENCHMARKS.md from the latest snapshot:
uv run python benchmarks/report.py benchmarks/results/<platform>/<file>.json
```

Commit the updated `BENCHMARKS.md` and the new JSON snapshot together.

## Running Tests

```bash
uv run pytest tests/          # correctness tests
uv run pytest benchmarks/     # performance benchmarks (separate run)
```
