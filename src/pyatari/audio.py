"""Minimal audio helpers for PyAtari."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyatari.pokey import DEFAULT_AUDIO_SAMPLE_RATE, POKEY


@dataclass(slots=True)
class AudioOutput:
    """Small buffer-oriented audio wrapper for future real output."""

    sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE
    buffers: list[list[float]] = field(default_factory=list)

    def queue_from_pokey(self, pokey: POKEY, sample_count: int) -> list[float]:
        samples = pokey.generate_samples(sample_count, sample_rate=self.sample_rate)
        self.buffers.append(samples)
        return samples
