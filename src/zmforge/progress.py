"""Short progress lines for long runs, off unless a front end turns them on.

A big recipe (cemetery, corn_maze) takes minutes between ``zmforge generate``
and its first output line.  Library code calls :func:`stage` ("dressing rooms
3/9") at its natural milestones; nothing is printed unless :func:`enable` was
called (the CLI does, to stderr), so the library stays quiet for tests and
other callers.  Repeated identical lines and lines closer together than
``MIN_GAP`` seconds for the same stage are dropped, so a tight loop that
reports every step costs one line every few seconds at most.
"""

from __future__ import annotations

import time
from typing import TextIO

__all__ = ["enable", "disable", "stage", "count"]

#: Seconds between two ``count`` lines for one stage.
MIN_GAP = 2.0

#: A run shorter than this prints nothing: stages reached before it are
#: dropped, so a one-room generate stays as quiet as it always was.
QUIET_FOR = 2.0

_stream: TextIO | None = None
_last: dict[str, float] = {}
_start = 0.0
_quiet_for = QUIET_FOR


def enable(stream: TextIO, *, quiet_for: float | None = None) -> None:
    global _stream, _start, _quiet_for
    _stream, _start = stream, time.monotonic()
    _quiet_for = QUIET_FOR if quiet_for is None else quiet_for
    _last.clear()


def disable() -> None:
    global _stream
    _stream = None


def stage(message: str) -> None:
    """One line: ``[ 12s] message...``."""
    if _stream is None:
        return
    elapsed = time.monotonic() - _start
    if elapsed < _quiet_for:
        return
    print(f"[{elapsed:4.0f}s] {message}...", file=_stream, flush=True)


def count(label: str, done: int, total: int) -> None:
    """``label done/total``, rate-limited per label; the last step always prints."""
    if _stream is None:
        return
    now = time.monotonic()
    if done < total and now - _last.get(label, -MIN_GAP) < MIN_GAP:
        return
    _last[label] = now
    stage(f"{label} {done}/{total}")
