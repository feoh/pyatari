# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for PyAtari.

ADRs capture architectural decisions that materially affect emulator behavior,
code structure, or long-term maintenance. They are intentionally short and
written for future contributors who need to understand why a decision was made,
not just what changed.

## Format

Each ADR uses this naming pattern:

- `NNNN-short-title.md`

Where:

- `NNNN` is a zero-padded sequence number
- `short-title` is a concise kebab-case summary

## Recommended Sections

- `Status`
- `Context`
- `Decision`
- `Consequences`

Optional sections are fine when they add clarity, but the goal is a readable
record rather than a template exercise.

## Current ADRs

- [0001-real-rom-boot-without-synthetic-shell](./0001-real-rom-boot-without-synthetic-shell.md)
- [0002-performance-benchmarking-and-hot-path-optimizations](./0002-performance-benchmarking-and-hot-path-optimizations.md)
- [0003-gtia-rendering-hot-path-optimizations](./0003-gtia-rendering-hot-path-optimizations.md)
