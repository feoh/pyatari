# AGENTS.md

## Development rules

- Use **`uv`** for all Python environment and package management.
  - Examples: `uv sync --extra dev`, `uv run pytest`, `uv run ruff check .`
- Do **not** use `pip`, `poetry`, or ad-hoc virtualenv management.
- All Python code and tests must pass **`ruff` clean** before being considered done.
- Prefer small, readable changes with strong tests.
- Keep the emulator educational: clarity and correctness matter more than cleverness.
