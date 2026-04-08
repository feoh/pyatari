"""Optional peripheral abstractions for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CassetteDeck:
    """Tiny cassette abstraction for loading/storing byte streams."""

    data: bytes = b""
    position: int = 0

    def load_tape(self, data: bytes) -> None:
        self.data = bytes(data)
        self.position = 0

    def read_block(self, size: int) -> bytes:
        if size < 0:
            msg = "size must be non-negative"
            raise ValueError(msg)
        chunk = self.data[self.position : self.position + size]
        self.position += len(chunk)
        return chunk

    def rewind(self) -> None:
        self.position = 0


@dataclass(slots=True)
class PrinterDevice:
    """Simple line-buffered printer sink for tests and debugging."""

    output: list[str] = field(default_factory=list)

    def write(self, text: str) -> None:
        self.output.append(text)

    def clear(self) -> None:
        self.output.clear()
