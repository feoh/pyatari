"""Tests for pygame frontend event translation."""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque

import pygame

from pyatari import frontend


@dataclass(slots=True)
class FakeKeyEvent:
    type: int
    key: int
    unicode: str = ""


class FakeMachine:
    def __init__(self) -> None:
        self.pressed_keys: list[str] = []
        self.release_count = 0
        self.console_events: list[dict[str, bool]] = []
        self.reset_count = 0

    def press_key(self, key: str) -> None:
        self.pressed_keys.append(key)

    def release_key(self) -> None:
        self.release_count += 1

    def set_console_switches(
        self, *, start: bool | None = None, select: bool | None = None, option: bool | None = None
    ) -> None:
        event: dict[str, bool] = {}
        if start is not None:
            event["start"] = start
        if select is not None:
            event["select"] = select
        if option is not None:
            event["option"] = option
        self.console_events.append(event)

    def press_reset(self) -> None:
        self.reset_count += 1


def test_printable_unicode_key_is_queued_for_buffered_delivery(monkeypatch):
    machine = FakeMachine()
    events = [
        FakeKeyEvent(type=pygame.KEYDOWN, key=pygame.K_QUOTE, unicode='"'),
        FakeKeyEvent(type=pygame.KEYUP, key=pygame.K_QUOTE),
    ]
    monkeypatch.setattr(pygame.event, "get", lambda: events)
    keyboard = frontend.KeyboardBuffer(queued_keys=deque())

    assert frontend._handle_events(machine, keyboard) is True

    assert list(keyboard.queued_keys) == ['"']
    assert machine.pressed_keys == []
    assert machine.release_count == 0


def test_console_keyup_does_not_release_keyboard_key(monkeypatch):
    machine = FakeMachine()
    events = [
        FakeKeyEvent(type=pygame.KEYDOWN, key=pygame.K_F2),
        FakeKeyEvent(type=pygame.KEYUP, key=pygame.K_F2),
    ]
    monkeypatch.setattr(pygame.event, "get", lambda: events)
    keyboard = frontend.KeyboardBuffer(queued_keys=deque())

    assert frontend._handle_events(machine, keyboard) is True

    assert machine.pressed_keys == []
    assert machine.release_count == 0
    assert machine.console_events == [{"start": True}, {"start": False}]


def test_keyboard_buffer_feeds_one_key_across_multiple_frames():
    machine = FakeMachine()
    keyboard = frontend.KeyboardBuffer(queued_keys=deque(['"', "a"]))

    keyboard.update(machine)
    for _ in range(frontend.KEY_HOLD_FRAMES - 1):
        keyboard.update(machine)
    keyboard.update(machine)

    assert machine.pressed_keys == ['"']
    assert machine.release_count == 1
    assert list(keyboard.queued_keys) == ["a"]

    for _ in range(frontend.KEY_RELEASE_FRAMES):
        keyboard.update(machine)
    keyboard.update(machine)

    assert machine.pressed_keys == ['"', "a"]
