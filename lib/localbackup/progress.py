"""Render measured progress on stderr during interactive operations."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import os
import select
import sys
import termios
import threading
import time

from .terminal import plain, style


def duration(value: float) -> str:
    seconds = int(value)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return "".join(f"{part}{unit}" for part, unit in (
        (hours, "h"), (minutes, "m"), (seconds, "s"),
    ) if part) or "0s"


@dataclass
class Phase:
    label: str
    total: int = 0
    completed: int = 0
    started: float = field(default_factory=time.monotonic)

    def detail(self, now: float, width: int) -> tuple[str, str]:
        elapsed = now - self.started
        bar_width = min(22, max(5, width // 5))
        if self.total:
            completed = self.completed
            filled = bar_width * completed // self.total
            bar = "#" * filled + "." * (bar_width - filled)
            timing = f"{completed}/{self.total}  Elapsed {duration(elapsed)}"
            if completed and elapsed >= 1:
                eta = elapsed * (self.total - completed) / completed
                timing += f"  ETA {duration(eta)}"
        else:
            offset = int(elapsed * 6) % (bar_width + 4)
            bar = "".join("#" if (index - offset) % (bar_width + 4) < 4 else "."
                          for index in range(bar_width))
            timing = f"Elapsed {duration(elapsed)}"
        return f"[{bar}]", timing


@contextmanager
def discard_input():
    """Discard queued keystrokes while keeping Ctrl-C enabled."""
    descriptor = None
    try:
        if sys.stdin.isatty() and os.tcgetpgrp(sys.stdin.fileno()) == os.getpgrp():
            descriptor = sys.stdin.fileno()
            original = termios.tcgetattr(descriptor)
            active = termios.tcgetattr(descriptor)
            active[3] &= ~(termios.ECHO | termios.ICANON)
            active[6][termios.VMIN] = 1
            active[6][termios.VTIME] = 0
            termios.tcsetattr(descriptor, termios.TCSANOW, active)
    except (OSError, termios.error, ValueError):
        descriptor = None
    try:
        yield descriptor
    finally:
        if descriptor is not None:
            termios.tcsetattr(descriptor, termios.TCSAFLUSH, original)


class Activity:
    def __init__(self, label: str, stream):
        self.label = plain(label)
        self.stream = stream
        self.current = Phase("")
        self.started = self.current.started
        self.drawn = False

    def draw(self) -> None:
        try:
            columns = os.get_terminal_size(self.stream.fileno()).columns or 80
        except (OSError, ValueError):
            columns = 80
        phase = self.current
        bar, detail = phase.detail(time.monotonic(), columns)
        # Keep the update on one line so clearing it also works after a resize.
        prefix = f"{self.label} · {plain(phase.label)}" if phase.label else self.label
        available = columns - len(bar) - len(detail) - 3
        if available < 8:
            line = f"{bar} {detail}"[:max(0, columns - 1)]
            rendered = style(line, "bar", self.stream)
        else:
            title = prefix if len(prefix) <= available else prefix[:available - 1] + "…"
            rendered = (
                f"{style(title, 'info', self.stream)} "
                f"{style(bar, 'bar', self.stream)} "
                f"{style(detail, 'subtle', self.stream)}"
            )
        print(f"\r\x1b[2K{rendered}", end="", file=self.stream, flush=True)
        self.drawn = True

    def finish(self, outcome: str, color: str) -> None:
        if self.drawn:
            label = style(self.label, "info", self.stream)
            state = style(outcome, color, self.stream)
            elapsed = duration(time.monotonic() - self.started)
            print(f"\r\x1b[2K{label}: {state} ({elapsed})", file=self.stream, flush=True)


_active: ContextVar[Activity | None] = ContextVar("localbackup_activity", default=None)


def phase(label: str, total: int = 0) -> Phase | None:
    """Report a phase within the current CLI operation, if it has a display."""
    activity = _active.get()
    if activity is None:
        return None
    activity.current = Phase(label, total)
    return activity.current


@contextmanager
def activity(label: str, *, enabled: bool):
    stream = sys.stderr
    if not enabled or not stream.isatty() or os.environ.get("TERM") == "dumb":
        yield
        return
    display = Activity(label, stream)
    token = _active.set(display)
    stopped = threading.Event()
    outcome, color = "complete", "success"
    try:
        with discard_input() as descriptor:
            def animate() -> None:
                while not stopped.wait(0.2):
                    if descriptor is not None and select.select([descriptor], [], [], 0)[0]:
                        os.read(descriptor, 4096)
                    display.draw()

            worker = threading.Thread(target=animate, name="localbackup-progress", daemon=True)
            worker.start()
            try:
                yield
            except KeyboardInterrupt:
                outcome, color = "interrupted", "warning"
                raise
            except BaseException:
                outcome, color = "failed", "error"
                raise
            finally:
                stopped.set()
                worker.join()
                display.finish(outcome, color)
    finally:
        _active.reset(token)
