"""Pygame-based frontend for PyAtari: video, audio, and keyboard input."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pygame

from pyatari.pokey import DEFAULT_AUDIO_SAMPLE_RATE

if TYPE_CHECKING:
    from pyatari.audio import AudioOutput
    from pyatari.machine import Machine

DISPLAY_WIDTH = 384
DISPLAY_HEIGHT = 240
KEY_HOLD_FRAMES = 8
KEY_RELEASE_FRAMES = 4

# ---------------------------------------------------------------------------
# Pygame key -> Atari key name (must match machine.KEYCODE_MAP keys)
# ---------------------------------------------------------------------------
PYGAME_TO_ATARI_KEY: dict[int, str] = {
    pygame.K_a: "a", pygame.K_b: "b", pygame.K_c: "c", pygame.K_d: "d",
    pygame.K_e: "e", pygame.K_f: "f", pygame.K_g: "g", pygame.K_h: "h",
    pygame.K_i: "i", pygame.K_j: "j", pygame.K_k: "k", pygame.K_l: "l",
    pygame.K_m: "m", pygame.K_n: "n", pygame.K_o: "o", pygame.K_p: "p",
    pygame.K_q: "q", pygame.K_r: "r", pygame.K_s: "s", pygame.K_t: "t",
    pygame.K_u: "u", pygame.K_v: "v", pygame.K_w: "w", pygame.K_x: "x",
    pygame.K_y: "y", pygame.K_z: "z",
    pygame.K_0: "0", pygame.K_1: "1", pygame.K_2: "2", pygame.K_3: "3",
    pygame.K_4: "4", pygame.K_5: "5", pygame.K_6: "6", pygame.K_7: "7",
    pygame.K_8: "8", pygame.K_9: "9",
    pygame.K_SPACE: "space",
    pygame.K_RETURN: "return",
    pygame.K_BACKSPACE: "backspace",
}


@dataclass(slots=True)
class KeyboardBuffer:
    queued_keys: deque[str]
    active_key: str | None = None
    hold_frames_remaining: int = 0
    release_frames_remaining: int = 0

    def enqueue(self, key: str) -> None:
        self.queued_keys.append(key)

    def update(self, machine: Machine) -> None:
        if self.active_key is not None:
            self.hold_frames_remaining -= 1
            if self.hold_frames_remaining <= 0:
                machine.release_key()
                self.active_key = None
                self.release_frames_remaining = KEY_RELEASE_FRAMES
            return

        if self.release_frames_remaining > 0:
            self.release_frames_remaining -= 1
            return

        if self.queued_keys:
            self.active_key = self.queued_keys.popleft()
            machine.press_key(self.active_key)
            self.hold_frames_remaining = KEY_HOLD_FRAMES


_KEYBOARD_BUFFER = KeyboardBuffer(queued_keys=deque())


# ---------------------------------------------------------------------------
# Framebuffer conversion
# ---------------------------------------------------------------------------
def _blit_framebuffer(framebuffer: list[list[int]], surface: pygame.Surface) -> None:
    """Convert the emulator framebuffer to a pygame Surface in-place."""
    arr = np.array(framebuffer, dtype=np.uint32)
    rgb = np.empty((arr.shape[0], arr.shape[1], 3), dtype=np.uint8)
    rgb[:, :, 0] = (arr >> 16) & 0xFF
    rgb[:, :, 1] = (arr >> 8) & 0xFF
    rgb[:, :, 2] = arr & 0xFF
    # surfarray expects (width, height, 3) — transpose from (H, W, 3)
    pygame.surfarray.blit_array(surface, rgb.transpose(1, 0, 2))


# ---------------------------------------------------------------------------
# Audio flushing
# ---------------------------------------------------------------------------
def _flush_audio(audio: AudioOutput, channel: pygame.mixer.Channel) -> None:
    """Send buffered audio samples to the pygame mixer channel."""
    if not audio.buffers:
        return
    # If the channel already has a queued sound, drop buffers to avoid buildup
    if channel.get_queue() is not None:
        audio.buffers.clear()
        return
    samples = audio.buffers.pop(0)
    arr = np.clip(np.array(samples, dtype=np.float32), -1.0, 1.0)
    int_samples = (arr * 32767).astype(np.int16)
    sound = pygame.mixer.Sound(buffer=int_samples.tobytes())
    channel.queue(sound)
    audio.buffers.clear()


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------
def _handle_events(machine: Machine, keyboard: KeyboardBuffer | None = None) -> bool:
    """Process pygame events. Returns False when the frontend should quit."""
    keyboard = keyboard if keyboard is not None else _KEYBOARD_BUFFER
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key in {pygame.K_RETURN, pygame.K_BACKSPACE}:
                keyboard.enqueue(PYGAME_TO_ATARI_KEY[event.key])
                continue
            if event.unicode and " " <= event.unicode <= "~":
                keyboard.enqueue(event.unicode)
                continue
            if event.key in PYGAME_TO_ATARI_KEY:
                keyboard.enqueue(PYGAME_TO_ATARI_KEY[event.key])
            elif event.key == pygame.K_F2:
                machine.set_console_switches(start=True)
            elif event.key == pygame.K_F3:
                machine.set_console_switches(select=True)
            elif event.key == pygame.K_F4:
                machine.set_console_switches(option=True)
            elif event.key == pygame.K_F5:
                machine.press_reset()

        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_F2:
                machine.set_console_switches(start=False)
            elif event.key == pygame.K_F3:
                machine.set_console_switches(select=False)
            elif event.key == pygame.K_F4:
                machine.set_console_switches(option=False)

    return True


def _poll_joystick(machine: Machine) -> None:
    """Read held keys for joystick directions and fire button."""
    keys = pygame.key.get_pressed()
    machine.set_joystick(
        up=keys[pygame.K_UP],
        down=keys[pygame.K_DOWN],
        left=keys[pygame.K_LEFT],
        right=keys[pygame.K_RIGHT],
    )
    machine.set_trigger(keys[pygame.K_RCTRL] or keys[pygame.K_RALT])


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run(machine: Machine, *, scale: int = 2) -> None:
    """Run the emulator with a live pygame window."""
    pygame.mixer.pre_init(
        frequency=DEFAULT_AUDIO_SAMPLE_RATE, size=-16, channels=1, buffer=1024
    )
    pygame.init()
    pygame.key.set_repeat(0, 0)

    window = pygame.display.set_mode(
        (DISPLAY_WIDTH * scale, DISPLAY_HEIGHT * scale)
    )
    pygame.display.set_caption("PyAtari 800XL")
    native_surface = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))
    clock = pygame.time.Clock()
    audio_channel = pygame.mixer.Channel(0)
    keyboard = KeyboardBuffer(queued_keys=deque())

    running = True
    while running:
        if not _handle_events(machine, keyboard):
            break

        _poll_joystick(machine)
        keyboard.update(machine)

        machine.run_frame(queue_audio=True)

        fb = machine.display.frame_from_gtia(machine.gtia)
        _blit_framebuffer(fb, native_surface)
        scaled = pygame.transform.scale(native_surface, window.get_size())
        window.blit(scaled, (0, 0))
        pygame.display.flip()

        _flush_audio(machine.audio, audio_channel)

        clock.tick(60)

    pygame.quit()
