"""Which build steps may run at the same time on one machine, and the locks that say so.

Two builds of *different* maps share one copy of the mod tools and one Wine
prefix. Most of what a build writes is the map's own (``usermaps/<map>``,
``share/raw/maps/zm/<map>.*``, ``map_source/zm/<map>.map``, the prefix's
``UmbraDebug/<map>*``), and that is safe side by side. A few things are shared
by every map, and those are what the locks here guard
(``docs/public/wiring-your-build.md``, "Running builds side by side"):

* ``gdtdb/gdt.db`` and ``zone_source/all/assetlist/core_gfx.csv``: the HUD
  images are registered in the first, and the loading-screen override points
  the stock ``black`` image at one map's picture in both for the length of
  that map's link. Another map linked in that window would pack the wrong
  loading screen.
* ``share/raw/collmaps``: prop collision boxes, one file per model, written
  by every map and read by the compile. Two maps can write different boxes
  for the same model.
* ``share/assetconvert``: the tools' conversion cache and its signature
  databases, written by the compile and the link.
* The GPU, RAM and cores: the bake is the heavy stage.

So there are four kinds of lock, always taken in this order (which is what
keeps them from deadlocking):

1. **global**, ``<lock dir>/.radiant.lock``. Every build step holds it
   *shared*; a caller that needs everything to itself (an exclusive
   ``flock`` on the same file) and the Radiant renders hold it *exclusive*,
   so they run alone.
2. **map**, ``<lock dir>/locks/map-<name>.lock``, exclusive: one build of a
   map at a time.
3. **tools**, ``<lock dir>/locks/tools.lock``, exclusive: the steps that
   write the shared files above (staging into the tools copy, the compile,
   the link with its loading-screen override). Short: about 20 s for a
   compile and 40 s for a link.
4. **heavy slot** (:class:`HeavySlot`): the bake. Any number may run, as long
   as the free GPU memory covers every running bake's reservation plus a
   fixed headroom kept free, and RAM and cores do too.

A lock already held by this process or by one of its ancestors is not taken
again, so ``flock build-out/.radiant.lock <build command>`` and a
Python stage run inside ``buildlock hold tools -- ...`` both work.

    python -m zmforge.toolchain.buildlock hold --map zm_dmv --tools -- <cmd...>
    python -m zmforge.toolchain.buildlock status
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

try:
    import fcntl
except ImportError:  # Windows: these locks guard the Wine/Linux build path only,
    # but importing this module must still work there, because the CLI's error
    # handler imports render.radiant, which imports this.
    fcntl = None  # type: ignore[assignment]

__all__ = [
    "GLOBAL_LOCK_NAME",
    "BuildLock",
    "HeavySlot",
    "ancestors",
    "global_lock",
    "gpu_free_mb",
    "lock_dir",
    "lock_holders",
    "map_lock",
    "tools_lock",
]

REPO = Path(__file__).resolve().parents[3]

#: The machine-wide "take everything" lock.
GLOBAL_LOCK_NAME = ".radiant.lock"


def lock_dir() -> Path:
    """``$ZMFORGE_LOCK_DIR``, else ``build-out`` in the checkout."""
    return Path(os.environ.get("ZMFORGE_LOCK_DIR") or REPO / "build-out")


def _log(message: str) -> None:
    print(f"== {message}", file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------
# who holds what


def ancestors(pid: int | None = None) -> set[int]:
    """*pid* (default: this process) and every process above it."""
    pids, pid = set(), pid or os.getpid()
    while pid > 1:
        pids.add(pid)
        try:
            with open(f"/proc/{pid}/stat") as fh:
                pid = int(fh.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


def lock_holders(path: Path, *, mode: str | None = None) -> set[int]:
    """PIDs holding a ``flock`` on *path*, from ``/proc/locks``.

    *mode* ``"WRITE"`` (exclusive) or ``"READ"`` (shared) filters by kind.
    """
    try:
        inode = os.stat(path).st_ino
        text = Path("/proc/locks").read_text()
    except OSError:
        return set()
    out = set()
    for line in text.splitlines():
        f = line.split()
        # "1: FLOCK  ADVISORY  WRITE 1234 00:2e:5678 0 EOF"; "->" marks waiters.
        if len(f) >= 6 and f[1] == "FLOCK" and "->" not in f[:2]:
            if mode is not None and f[3] != mode:
                continue
            try:
                if int(f[5].rsplit(":", 1)[1]) == inode:
                    out.add(int(f[4]))
            except (ValueError, IndexError):
                continue
    return out


class BuildLock:
    """An ``flock`` on one file, shared or exclusive, that an ancestor can lend.

    If this process or an ancestor already holds the lock in a mode at least
    as strong as the one asked for, :meth:`acquire` returns at once with
    :attr:`inherited` set. An exclusive request under an ancestor's *shared*
    hold cannot be granted (the ancestor would wait for its own child) and
    raises instead of hanging.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        shared: bool = False,
        log: Callable[[str], None] = _log,
    ) -> None:
        self.path = Path(path)
        self.shared = shared
        self.log = log
        self.fh = None
        self.inherited = False

    def _try(self) -> bool:
        try:
            fcntl.flock(self.fh, (fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def acquire(self, timeout: float | None = None) -> "BuildLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a")
        if self._try():
            return self
        family = ancestors()
        if lock_holders(self.path, mode="WRITE") & family or (
            self.shared and lock_holders(self.path) & family
        ):
            self.fh.close()
            self.fh, self.inherited = None, True
            return self
        if lock_holders(self.path, mode="READ") & family:
            self.release()
            raise RuntimeError(
                f"{self.path}: an exclusive hold was asked for under this process's own "
                "shared hold, which would wait forever; take it before the shared one"
            )
        holders = lock_holders(self.path)
        self.log(f"waiting for {self.path.name} "
                 f"(held by pid {', '.join(map(str, sorted(holders))) or '?'})")
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self._try():
            if deadline is not None and time.monotonic() > deadline:
                self.release()
                raise TimeoutError(f"{self.path} still held after {timeout:.0f} s")
            time.sleep(1)
        return self

    def release(self) -> None:
        if self.fh is not None:
            self.fh.close()          # closing the file drops the flock
            self.fh = None

    __enter__ = acquire

    def __exit__(self, *exc) -> None:
        self.release()


def global_lock(*, exclusive: bool = False, **kw) -> BuildLock:
    return BuildLock(lock_dir() / GLOBAL_LOCK_NAME, shared=not exclusive, **kw)


def map_lock(map_name: str, **kw) -> BuildLock:
    if not map_name or map_name in (".", "..") or any(c in map_name for c in "/\\:"):
        raise ValueError(f"not a map name: {map_name!r}")
    return BuildLock(lock_dir() / "locks" / f"map-{map_name}.lock", **kw)


def tools_lock(**kw) -> BuildLock:
    return BuildLock(lock_dir() / "locks" / "tools.lock", **kw)


# ----------------------------------------------------------------------------
# the heavy-stage gate


def gpu_free_mb() -> int | None:
    """Free memory on the first GPU in MiB; ``None`` when nvidia-smi gave none."""
    try:
        done = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        return int(done.stdout.split()[0])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def mem_available_mb() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


#: What one lighting bake reserves. A bake needs a few GB of GPU memory for
#: its Xorg and Radiant, a few more GB of RAM, and several cores, more in
#: bursts. The defaults sit a margin above what whole bakes of the shipped
#: maps peaked at; ``BAKE_VRAM_MB``, ``BAKE_RAM_MB`` and ``BAKE_CORES``
#: override them.
BAKE_VRAM_MB = 2560
BAKE_RAM_MB = 5500
BAKE_CORES = 16

#: What is always left free, never handed to a bake.
#: ``ZMFORGE_GPU_HEADROOM_MB`` / ``ZMFORGE_RAM_HEADROOM_MB`` override them.
GPU_HEADROOM_MB = 2048
RAM_HEADROOM_MB = 8192


@dataclass
class Reservation:
    pid: int
    vram_mb: int
    ram_mb: int
    cores: int
    what: str


class HeavySlot:
    """Wait until one more heavy stage fits, then hold its reservation.

    A stage fits when

    * free GPU memory >= its VRAM + every running heavy stage's VRAM + the
      GPU headroom. Running stages are counted in full even though some of
      their memory is already out of "free": a stage still ramping up would
      otherwise be counted as nothing, and the next one would start into
      memory it is about to take. This over-counts, on purpose.
    * ``MemAvailable`` >= its RAM + every running stage's RAM + the RAM headroom,
    * the running stages' cores plus its own fit in the machine's cores.

    With no ``nvidia-smi`` at all (a machine without an NVIDIA GPU) only one
    heavy stage runs at a time. With ``nvidia-smi`` but no reading, it waits:
    the GPU is not guessed at.

    Reservations are files in ``<lock dir>/locks/heavy/``, each ``flock``-ed
    by its owner for as long as it runs, so a killed owner's reservation is
    recognised and removed by the next caller. Decisions are made one at a
    time under ``<lock dir>/locks/gate.lock``.
    """

    def __init__(
        self,
        what: str,
        *,
        vram_mb: int | None = None,
        ram_mb: int | None = None,
        cores: int | None = None,
        gpu: bool = True,
        poll_s: float = 20.0,
        log: Callable[[str], None] = _log,
    ) -> None:
        self.what = what
        self.vram_mb = vram_mb if vram_mb is not None else _env_int("BAKE_VRAM_MB", BAKE_VRAM_MB)
        self.ram_mb = ram_mb if ram_mb is not None else _env_int("BAKE_RAM_MB", BAKE_RAM_MB)
        self.cores = cores if cores is not None else _env_int("BAKE_CORES", BAKE_CORES)
        self.gpu = gpu
        self.poll_s = poll_s
        self.log = log
        self.dir = lock_dir() / "locks" / "heavy"
        self.fh = None
        self.path: Path | None = None
        self.inherited = False

    # -- the ledger --------------------------------------------------------

    def running(self) -> list[Reservation]:
        """Live reservations; a dead owner's file is removed on the way."""
        out = []
        for path in sorted(self.dir.glob("*.json")):
            if self.path is not None and path == self.path:
                continue
            try:
                with open(path, "a+") as fh:
                    try:
                        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:      # its owner is alive
                        fh.seek(0)
                        out.append(Reservation(**json.loads(fh.read())))
                        continue
                    path.unlink(missing_ok=True)  # nobody holds it: a dead owner's
            except (OSError, ValueError, TypeError):
                continue
        return out

    def _why_not(self, running: list[Reservation]) -> str | None:
        """``None`` when one more fits now, else what is short."""
        if self.gpu:
            if shutil.which("nvidia-smi") is None:
                if running:
                    return f"no nvidia-smi here, so one heavy stage at a time ({len(running)} running)"
            else:
                free = gpu_free_mb()
                if free is None:
                    return "nvidia-smi gave no reading"
                headroom = _env_int("ZMFORGE_GPU_HEADROOM_MB", GPU_HEADROOM_MB)
                want = self.vram_mb + sum(r.vram_mb for r in running) + headroom
                if free < want:
                    return (f"GPU has {free} MiB free, wants {want} ({self.vram_mb} for this, "
                            f"{sum(r.vram_mb for r in running)} for {len(running)} running, "
                            f"{headroom} headroom)")
        avail = mem_available_mb()
        if avail is not None:
            headroom = _env_int("ZMFORGE_RAM_HEADROOM_MB", RAM_HEADROOM_MB)
            want = self.ram_mb + sum(r.ram_mb for r in running) + headroom
            if avail < want:
                return f"RAM has {avail} MiB available, wants {want}"
        cores = os.cpu_count() or 1
        busy = sum(r.cores for r in running)
        if running and busy + self.cores > cores:
            return f"{busy} of {cores} cores reserved by {len(running)} running"
        return None

    # -- taking and giving back -------------------------------------------

    def acquire(self) -> "HeavySlot":
        held = os.environ.get("ZMFORGE_HEAVY_SLOT")
        if os.environ.get("ZMFORGE_NO_HEAVY_GATE") or (
            held and held.isdigit() and int(held) in ancestors()
        ):
            self.inherited = True
            return self
        self.dir.mkdir(parents=True, exist_ok=True)
        said = None
        while True:
            with BuildLock(self.dir.parent / "gate.lock", log=lambda s: None):
                running = self.running()
                why = self._why_not(running)
                if why is None:
                    self._reserve()
                    if said:
                        self.log(f"{self.what}: starting ({len(running)} other heavy stage(s) running)")
                    return self
            if why != said:
                self.log(f"{self.what}: waiting; {why}")
                said = why
            time.sleep(self.poll_s)

    def _reserve(self) -> None:
        self.path = self.dir / f"{os.getpid()}-{time.monotonic_ns()}.json"
        self.fh = open(self.path, "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        json.dump(vars(Reservation(os.getpid(), self.vram_mb, self.ram_mb, self.cores,
                                   self.what)), self.fh)
        self.fh.flush()

    def release(self) -> None:
        if self.fh is not None:
            if self.path is not None:
                self.path.unlink(missing_ok=True)
            self.fh.close()
            self.fh = None
            self.path = None

    __enter__ = acquire

    def __exit__(self, *exc) -> None:
        self.release()


# ----------------------------------------------------------------------------
# command line: for shell scripts


def _hold(args: argparse.Namespace) -> int:
    locks: list = [] if args.no_global else [global_lock(exclusive=args.exclusive)]
    if args.map:
        locks.append(map_lock(args.map))
    if args.tools:
        locks.append(tools_lock())
    env = dict(os.environ)
    held = []
    try:
        for lock in locks:
            held.append(lock.acquire())
        if args.heavy:
            slot = HeavySlot(args.heavy, vram_mb=args.vram_mb).acquire()
            held.append(slot)
            env["ZMFORGE_HEAVY_SLOT"] = str(os.getpid())
        return subprocess.call(args.command, env=env)
    finally:
        for lock in reversed(held):
            lock.release()


def _status(_: argparse.Namespace) -> int:
    base = lock_dir()
    paths = [base / GLOBAL_LOCK_NAME, *sorted((base / "locks").glob("*.lock"))]
    for path in paths:
        write, read = lock_holders(path, mode="WRITE"), lock_holders(path, mode="READ")
        if write or read:
            print(f"{path.name}: exclusive {sorted(write)} shared {sorted(read)}")
    gate = HeavySlot("status")
    gate.dir.mkdir(parents=True, exist_ok=True)
    with BuildLock(gate.dir.parent / "gate.lock", log=lambda s: None):
        running = gate.running()
    for r in running:
        print(f"heavy: pid {r.pid} {r.what} vram {r.vram_mb} ram {r.ram_mb} cores {r.cores}")
    print(f"gpu free {gpu_free_mb()} MiB, ram available {mem_available_mb()} MiB")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m zmforge.toolchain.buildlock",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    hold = sub.add_parser("hold", help="run a command under the global lock and any others")
    hold.add_argument("--exclusive", action="store_true",
                      help="hold the global lock exclusively (run alone)")
    hold.add_argument("--no-global", action="store_true",
                      help="do not hold the global lock (e.g. a whole multi-step build, "
                      "whose render step takes it exclusively)")
    hold.add_argument("--map", help="also hold this map's lock")
    hold.add_argument("--tools", action="store_true", help="also hold the shared-tools lock")
    hold.add_argument("--heavy", metavar="WHAT", help="also wait for a heavy-stage slot")
    hold.add_argument("--vram-mb", type=int, default=None)
    hold.add_argument("command", nargs=argparse.REMAINDER)
    hold.set_defaults(func=_hold)
    sub.add_parser("status", help="who holds what").set_defaults(func=_status)
    args = parser.parse_args(argv)
    if args.cmd == "hold":
        if args.command[:1] == ["--"]:
            args.command = args.command[1:]
        if not args.command:
            parser.error("hold needs a command after --")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
