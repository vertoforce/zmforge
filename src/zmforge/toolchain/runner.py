"""How a stage's process is started, and nothing else.

WHY a separate layer: keeping process start-up behind one small interface
lets the verdict logic in :mod:`zmforge.toolchain.stages` stay identical for
every way a stage can be started (a child process here, or under Wine in a
container, :mod:`zmforge.toolchain.wine`), and lets the tests run a stage
with no mod tools anywhere in sight.

Two things every runner must answer besides "run this":

``provides_interactive_desktop``
    the lighting bake is a GUI program; started with no desktop it reaches
    840 MB, burns 0.2 CPU-seconds in four minutes, prints nothing and never
    exits (Section 7.3, K4). A runner that cannot promise a desktop has to
    say so before the bake is launched, not after.
``size_of`` / ``is_directory``
    a link counts as good only when each of the two fastfiles is on disk
    with a size above zero (K3), and a missing tools directory is a
    configuration error (Section 7.1). They are asked of the runner, not of
    this process's filesystem, because the tools may live somewhere this
    process does not see them the same way (inside a container, for one).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import PurePath
from typing import Protocol, Sequence, runtime_checkable

from ..errors import ToolchainError
from .evidence import decode_tool_output
from .layout import ToolsLayout, stage_environment

__all__ = [
    "LocalRunner",
    "RunResult",
    "StageRunner",
]


@dataclass(frozen=True, slots=True)
class RunResult:
    """What starting a process produced, before anyone judges it.

    ``exit_code`` is carried but deliberately not interpreted here; the
    linker's own success codes are 154000 and 2000 (Section 7.3).
    ``stalled`` is set only when a runner killed the process itself under
    the bake stall rule, because "killed for making no progress" cannot be
    told apart from "exited" by an exit code alone. ``timed_out`` narrows
    that: the runner killed it for running past a hard time limit, which is
    the Wine bake's only guard (its measured failure is a spin, which no
    progress detector sees). A timed-out result is also ``stalled`` so
    every verdict that checks the wider flag keeps working.
    """

    exit_code: int
    stdout_bytes: bytes
    duration_s: float
    stalled: bool = False
    timed_out: bool = False

    @property
    def text(self) -> str:
        """The output decoded with replacement, never strictly (K12)."""
        return decode_tool_output(self.stdout_bytes)


@runtime_checkable
class StageRunner(Protocol):
    """The whole contract :class:`~zmforge.toolchain.stages.Toolchain` needs."""

    provides_interactive_desktop: bool

    def run(
        self,
        command: Sequence[str],
        *,
        layout: ToolsLayout,
        stage: str,
        stall_window_s: float | None = None,
        timeout_s: float | None = None,
    ) -> RunResult:
        ...

    def size_of(self, path: PurePath | str) -> int | None:
        """Size in bytes on the tools install, or ``None`` when absent."""

    def is_directory(self, path: PurePath | str) -> bool:
        ...

    def read_text(self, path: PurePath | str) -> str:
        """A text file from the tools install, or ``""`` when it is not there.

        For the small reports the linker leaves beside a fastfile, which a
        verdict has to read wherever the tools ran.  Never used for a tool's
        own log: those come back with the :class:`RunResult`.
        """


def _cpu_seconds(pid: int) -> float | None:
    """CPU time a live process has accrued, or ``None`` where unknowable.

    Only ``/proc`` is consulted, so this answers on Linux and returns
    ``None`` on Windows rather than pulling in a dependency. That is not a
    hole in the stall detector: the measured headless bake printed nothing
    *and* made no CPU progress, so silence alone already catches it; CPU
    time is the second signal that keeps a slow-but-working tool alive.
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as handle:
            fields = handle.read().rsplit(b")", 1)[1].split()
        ticks = float(fields[11]) + float(fields[12])  # utime + stime
    except (OSError, IndexError, ValueError):
        return None
    return ticks / os.sysconf("SC_CLK_TCK")


def _host_has_desktop() -> bool:
    """Best-effort guess at whether this process could show a window.

    Windows names an interactive station ``WinSta0``; a service or a
    process with no desktop reports ``Services`` in ``SESSIONNAME``.
    On Linux a display server variable is the equivalent evidence. Guessing
    wrong the optimistic way only costs the stall detector one window, which
    is why the default is conservative and the flag is overridable.
    """
    if os.name == "nt":  # pragma: no cover - not reachable on the test host
        session = os.environ.get("SESSIONNAME", "")
        return bool(session) and session.lower() != "services"
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


class LocalRunner:
    """Start the stage as a child process of this one.

    Correct when the mod tools run natively on this machine.
    """

    def __init__(
        self,
        *,
        interactive_desktop: bool | None = None,
        poll_interval_s: float = 0.2,
    ) -> None:
        self.provides_interactive_desktop = (
            _host_has_desktop() if interactive_desktop is None else interactive_desktop
        )
        self.poll_interval_s = poll_interval_s

    def run(
        self,
        command: Sequence[str],
        *,
        layout: ToolsLayout,
        stage: str,
        stall_window_s: float | None = None,
        timeout_s: float | None = None,
    ) -> RunResult:
        """Run *command* in ``<root>\\bin`` with the ``TA_*`` overlay (B1).

        The environment is an overlay on the inherited one, never a
        replacement: the tools need the rest of the machine's environment to
        find their own DLLs.
        """
        environment = dict(os.environ)
        environment.update(stage_environment(layout))
        started = time.monotonic()
        try:
            process = subprocess.Popen(  # noqa: S603 - the command is built from the layout
                list(command),
                cwd=str(layout.bin_dir),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as problem:
            raise ToolchainError(f"could not start {stage}: {problem}") from problem

        if stall_window_s is None:
            return self._wait(process, started, timeout_s)
        return self._wait_watching_for_stall(process, started, stall_window_s, timeout_s)

    def _wait(
        self,
        process: "subprocess.Popen[bytes]",
        started: float,
        timeout_s: float | None,
    ) -> RunResult:
        try:
            output, _ = process.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            return RunResult(
                process.returncode or -1, output, time.monotonic() - started, True, timed_out=True
            )
        return RunResult(process.returncode, output, time.monotonic() - started)

    def _wait_watching_for_stall(
        self,
        process: "subprocess.Popen[bytes]",
        started: float,
        stall_window_s: float,
        timeout_s: float | None,
    ) -> RunResult:
        """Kill a process that stops producing output and stops using CPU.

        This is the (b) branch of Section 7.3: rather than trust a desktop
        check, watch the process and end it once it has clearly stopped
        making progress, so a headless bake costs one stall window instead
        of hanging forever.
        """
        chunks: list[bytes] = []
        stream = process.stdout
        assert stream is not None
        reader = threading.Thread(target=_drain, args=(stream, chunks), daemon=True)
        reader.start()

        produced = 0
        cpu = _cpu_seconds(process.pid)
        last_progress = time.monotonic()
        stalled = False
        try:
            while process.poll() is None:
                time.sleep(self.poll_interval_s)
                now = time.monotonic()
                grown = sum(len(chunk) for chunk in chunks)
                spent = _cpu_seconds(process.pid)
                moved = grown > produced or (
                    spent is not None and cpu is not None and spent > cpu + 0.01
                )
                if moved:
                    produced, cpu, last_progress = grown, spent, now
                elif now - last_progress >= stall_window_s:
                    stalled = True
                    break
                if timeout_s is not None and now - started >= timeout_s:
                    stalled = True
                    break
            if stalled:
                process.kill()
            process.wait()
        finally:
            reader.join(timeout=5.0)
            stream.close()
        exit_code = process.returncode if process.returncode is not None else -1
        return RunResult(exit_code, b"".join(chunks), time.monotonic() - started, stalled)

    def size_of(self, path: PurePath | str) -> int | None:
        try:
            return os.stat(str(path)).st_size
        except OSError:
            return None

    def mtime_of(self, path: PurePath | str) -> float | None:
        """Modification time (the local clock), or ``None`` when absent."""
        try:
            return os.stat(str(path)).st_mtime
        except OSError:
            return None

    def is_directory(self, path: PurePath | str) -> bool:
        return os.path.isdir(str(path))

    def read_text(self, path: PurePath | str) -> str:
        try:
            with open(str(path), "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return ""


def _drain(stream: "object", chunks: list[bytes]) -> None:
    """Copy a pipe into *chunks* so the poll loop never blocks on a read.

    ``read1`` and not ``read``: on a pipe ``read(4096)`` blocks until 4096
    bytes or EOF, so a tool that prints one short line and then works in
    silence looks silent until it exits [measured: Radiant's
    ``LED Exported for`` line was never seen while it lingered]. ``read1``
    hands over whatever has arrived.
    """
    read = getattr(stream, "read1", None) or stream.read  # type: ignore[attr-defined]
    try:
        while True:
            chunk = read(4096)
            if not chunk:
                return
            chunks.append(chunk)
    except (ValueError, OSError):  # pipe closed under us by the kill
        return
