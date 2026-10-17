"""Running the mod tools on this machine, under Wine, in a container.

WHY a Wine runner: the tools only exist as Windows executables, but they are
ordinary console programs, and two of the four run correctly under Wine
[measured, Wine 11.0 stable]:

* ``cod2map64.exe`` compiles. Exit 0, same log structure as Windows,
  2.0 s on ``zm_forge_gate`` where Windows took about the same. Its
  output is **not** byte-identical to Windows's - three of the
  BSP's twenty-five lumps differ and the file is 152 bytes shorter
  (measured).
* ``linker_modtools.exe`` links, but **only** with Microsoft's own VC++ 2012
  runtime in the prefix. Against Wine's builtin ``msvcr110`` it aborts on
  ``??0_TaskCollection@details@Concurrency@@QEAA@XZ`` - the Concurrency
  Runtime task scheduler - before printing a single line of its own.
* ``radiant_modtools.exe -ledSilent`` bakes [measured], given
  three things this runner supplies for the ``bake`` stage and nothing else:
  a display (``with-display`` in the image starts Xorg on the GPU, or
  Xvfb without one; Radiant is a Qt program and will not start without an X
  connection), ``--gpus all`` with DXVK for its D3D11 probe renderer
  (:data:`BAKE_DLL_OVERRIDES`), and a shim over ``bin\\avx\\embree64r.dll``.
  The shim is the whole difference between a bake that finishes and one that
  spins forever: embree 2.3.3 pins every scheduler thread with
  ``SetThreadIdealProcessorEx``, which Wine stubs to ``FALSE`` (still so in
  Wine 11.17), so embree throws after creating its first worker and every
  ray-tracing phase runs on one thread against barriers sized for every core
  on the machine. With the import renamed to ``GetCurrentProcessId`` (never zero, ignores its
  arguments) ``zm_forge_gate`` exported its ``.led``: 88 s end to end through
  wined3d, 17 s through DXVK, against about 12 s on Windows.
* ``gdtdb.exe`` is not offered here: it is a .NET program and the image has
  no runtime for it.

The container is addressed, not imported: this class builds a ``docker run``
argument list and hands it to the same process supervision
:class:`~zmforge.toolchain.runner.LocalRunner` uses, so the stall detector,
the byte-exact log capture and every verdict rule stay in one place. The
executable and its arguments stay in their Windows spelling all the way
down, because the prefix maps the tools to the *same absolute Windows path*
the Steam install has on Windows - which is why a ``.map`` file, a
GDT or a cached asset that names that path resolves here unchanged.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path, PurePath, PureWindowsPath
from typing import Sequence

from ..errors import ToolchainError
from .layout import ToolsLayout, stage_environment
from .runner import LocalRunner, RunResult, _drain

__all__ = [
    "BAKE_DLL_OVERRIDES",
    "BAKE_EXPORTED_MARKER",
    "DEFAULT_BAKE_LINGER_S",
    "DEFAULT_BAKE_TIMEOUT_S",
    "DEFAULT_IMAGE",
    "DEFAULT_WINDOWS_ROOT",
    "EMBREE_IMPORT_NEW",
    "EMBREE_IMPORT_OLD",
    "RADIANT_LOG_MARKER",
    "WineRunner",
]


# The default Steam install path of the tools on Windows, reproduced inside the
# Wine prefix. Not a guess: Section 7.1's measured root.
DEFAULT_WINDOWS_ROOT = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130"
)

# Built by docker/bo3-wine/Dockerfile. Locally built, so no digest to pin.
DEFAULT_IMAGE = "bo3-wine:local"

_CONTAINER_TOOLS = "/tools"
_CONTAINER_PREFIX = "/wineprefix"

#: The bake's hard time limit. Under Wine the failure mode is a spin at
#: 400% CPU with no output, which a "no CPU progress" stall detector cannot
#: see (and the docker client's /proc is not the tool's anyway), so the only
#: honest guard is a cap. Measured with the embree shim: zm_forge_gate
#: bakes in 88 s; without the shim, nothing finished in 9 minutes.
DEFAULT_BAKE_TIMEOUT_S = 1800.0

#: How long Radiant may stay alive after printing its export line before the
#: container is stopped. Measured: with a crashed helper held by
#: winedbg, Radiant sat at 250% CPU after "Radiant init time" and never
#: exited on its own; the .led was complete.
DEFAULT_BAKE_LINGER_S = 30.0

#: Radiant's one line of stdout on a successful silent bake.
BAKE_EXPORTED_MARKER = b"LED Exported for "

#: The bake's DLL overrides: the image's defaults (no .NET prompt, Microsoft's
#: VC++ 2012 runtime) plus DXVK for D3D11. WHY DXVK [measured]:
#: through wined3d the probe pass spent ~60 s in glLinkProgram on the
#: translated compute shader and still logged "program object is not
#: successfully linked" and "No active compute shader" on its dispatches;
#: through DXVK the same bake logged no D3D error and took 17 s instead of
#: 88 s. The DLLs are in the prefix's system32 (the image's entrypoint puts
#: them there); this override is what makes the bake, and only the bake,
#: load them.
BAKE_DLL_OVERRIDES = "mscoree=d;msvcr110,msvcp110=n;d3d11,dxgi,d3d10core=n"
_DXVK_LOG_DIR = "dxvk-logs"

#: Separates Radiant's own log, appended by the runner, from the console
#: output in a bake stage log. The parser splits on it.
RADIANT_LOG_MARKER = "== Radiant.log"
_RADIANT_DOCUMENTS = "drive_c/users/root/Documents"
_RADIANT_LOG = f"{_RADIANT_DOCUMENTS}/Radiant.log"
#: Per-bake scratch under the prefix: Radiant's Documents (its log) and the
#: DXVK logs, one directory per bake so two bakes side by side never read or
#: delete each other's log (zmforge.toolchain.buildlock).
_BAKE_RUNS = "bake-runs"

# The embree import shim (see the module docstring). Same length, so the
# import name table keeps its layout; the hint word before the name is not
# consulted by Wine.
EMBREE_IMPORT_OLD = b"SetThreadIdealProcessorEx\0"
EMBREE_IMPORT_NEW = b"GetCurrentProcessId\0".ljust(len(EMBREE_IMPORT_OLD), b"\0")
_EMBREE_DLLS = ("bin/avx/embree64r.dll", "bin/embree64r.dll")

# Radiant spawns this 32-bit tray helper at start. Under Wine it page-faults
# in msvcr110 within a second, Wine's crash handler holds the corpse under
# winedbg, and the "Unhandled page fault" line lands in the bake's stdout
# where it reads as a loader failure. An empty file mounted over it keeps it
# from ever starting; a bake on Windows does not depend on it either
# (a Windows install's gdtdb\live holds the same single keepme.txt).
_TRAY_LAUNCHER = "bin/GdtDBTrayLauncher.exe"


def _write_atomically(path: Path, data: bytes) -> None:
    """Write *path* whole or not at all: a bake starting beside this one may
    be mounting it this very moment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class WineRunner(LocalRunner):
    """Start a stage as ``docker run ... wine <tool.exe> <args>``.

    *tools_dir* is the local copy of the mod-tools install - your own
    files, never committed and never served. *windows_root* is the path that
    copy answers to inside the prefix and must match the root the
    :class:`~zmforge.toolchain.layout.ToolsLayout` was built with, because
    every path in a stage's command line is rendered from that layout.
    """

    #: The image starts its own X server for the bake (``with-display``), so
    #: this runner can promise Radiant a display. It is *display*, not
    #: *desktop*: nothing is drawn for anyone, but a Qt program only needs
    #: the connection [measured].
    provides_interactive_desktop = True

    def __init__(
        self,
        tools_dir: Path | str,
        *,
        windows_root: str = DEFAULT_WINDOWS_ROOT,
        prefix_dir: Path | str | None = None,
        image: str = DEFAULT_IMAGE,
        docker: str = "docker",
        docker_args: Sequence[str] = (),
        poll_interval_s: float = 0.2,
        gpu: bool = True,
        bake_timeout_s: float = DEFAULT_BAKE_TIMEOUT_S,
        bake_linger_s: float = DEFAULT_BAKE_LINGER_S,
    ) -> None:
        super().__init__(interactive_desktop=True, poll_interval_s=poll_interval_s)
        self.tools_dir = Path(tools_dir).resolve()
        self.windows_root = windows_root.rstrip("\\")
        self.prefix_dir = (
            Path(prefix_dir).resolve()
            if prefix_dir is not None
            else self.tools_dir.parent / "wineprefix"
        )
        self.image = image
        self.docker = docker
        self.docker_args = list(docker_args)
        self.gpu = gpu
        self.bake_timeout_s = bake_timeout_s
        self.bake_linger_s = bake_linger_s

    # -- addressing --------------------------------------------------------

    @property
    def container_bin_dir(self) -> str:
        """``<prefix>/drive_c/<root without its drive>/bin``, inside the container.

        The working directory has to be the tools' *Windows* bin directory
        (Section 7.2: without it the compiler's relative search paths break),
        so it is addressed through the prefix rather than through ``/tools``:
        the latter is ``Z:\\tools`` to Wine and would leave every relative
        path resolving off the wrong drive.
        """
        without_drive = PureWindowsPath(self.windows_root).as_posix().split(":/", 1)[-1]
        return f"{_CONTAINER_PREFIX}/drive_c/{without_drive}/bin"

    def local_path(self, path: PurePath | str) -> Path | None:
        """Where *path*, a Windows path under the tools root, is on this disk.

        ``None`` when the path is outside the root, which is the honest
        answer: this runner can say nothing about the rest of a C: drive
        that does not exist here.
        """
        text = str(path).replace("/", "\\")
        root = self.windows_root
        if text.lower() == root.lower():
            return self.tools_dir
        prefix = root + "\\"
        if not text.lower().startswith(prefix.lower()):
            return None
        rest = PureWindowsPath(text[len(prefix) :]).as_posix()
        return self.tools_dir / rest if rest else self.tools_dir

    @property
    def shim_dir(self) -> Path:
        """Where the patched embree and the blank tray launcher live.

        Under the prefix, which is gitignored: the patched DLL is still the
        user's own Activision binary and must never be committed or served.
        """
        return self.prefix_dir / "shims"

    @property
    def radiant_log(self) -> Path:
        """Radiant's log in the shared prefix. A bake never reads it: each
        bake mounts its own ``Documents`` (``bake-runs/<container>``)."""
        return self.prefix_dir / _RADIANT_LOG

    def ensure_shims(self) -> list[tuple[Path, str]]:
        """Create the bake's file shims and say where to mount them.

        Returns ``(host_path, container_path)`` pairs. Each embree DLL in the
        tools copy that still imports ``SetThreadIdealProcessorEx`` gets a
        patched twin (same size, one import renamed); one that does not is
        left alone and not mounted. The tray launcher, when present, is
        covered by an empty file.
        """
        mounts: list[tuple[Path, str]] = []
        for rel in _EMBREE_DLLS:
            source = self.tools_dir / rel
            if not source.is_file():
                continue
            data = source.read_bytes()
            if data.count(EMBREE_IMPORT_OLD) != 1:
                continue
            target = self.shim_dir / rel
            if not target.is_file() or target.stat().st_size != len(data):
                _write_atomically(target, data.replace(EMBREE_IMPORT_OLD, EMBREE_IMPORT_NEW))
            mounts.append((target, f"{_CONTAINER_TOOLS}/{rel}"))
        if (self.tools_dir / _TRAY_LAUNCHER).is_file():
            blank = self.shim_dir / _TRAY_LAUNCHER
            if not blank.is_file() or blank.stat().st_size:
                _write_atomically(blank, b"")
            mounts.append((blank, f"{_CONTAINER_TOOLS}/{_TRAY_LAUNCHER}"))
        return mounts

    def command_line(
        self,
        command: Sequence[str],
        layout: ToolsLayout,
        *,
        stage: str | None = None,
        container_name: str | None = None,
        run_dir: Path | None = None,
    ) -> list[str]:
        """The full ``docker run`` argument list for *command*.

        Separate from :meth:`run` so it can be asserted on without a
        container: the argument order, the mounts and the ``TA_*`` overlay
        are the part that breaks silently.

        Only the ``bake`` stage gets the GPU, the display wrapper, the shims
        and a container name (so a run over its time limit can be killed by
        name: ``docker run`` proxies SIGTERM to a Wine loader that ignores
        it). The compile and the link keep the argument list they were
        measured with.

        *run_dir*, a directory under the prefix, gives the bake its own
        Radiant ``Documents`` (where its log goes) and its own DXVK log
        directory, so bakes can run side by side.
        """
        argv = [
            self.docker,
            "run",
            "--rm",
            "-v",
            f"{self.tools_dir}:{_CONTAINER_TOOLS}",
            "-v",
            f"{self.prefix_dir}:{_CONTAINER_PREFIX}",
            "-w",
            self.container_bin_dir,
        ]
        launcher: list[str] = []
        if stage == "bake":
            if self.gpu:
                argv += ["--gpus", "all"]
            if container_name:
                argv += ["--name", container_name]
            for host_path, container_path in self.ensure_shims():
                argv += ["-v", f"{host_path}:{container_path}:ro"]
            # DXVK writes a log per DLL into DXVK_LOG_PATH; without it, next
            # to the executable, which is the user's tools copy.
            if run_dir is not None:
                documents = run_dir / "Documents"
                documents.mkdir(parents=True, exist_ok=True)
                (run_dir / _DXVK_LOG_DIR).mkdir(parents=True, exist_ok=True)
                argv += ["-v", f"{documents}:{_CONTAINER_PREFIX}/{_RADIANT_DOCUMENTS}"]
                inside = f"{_CONTAINER_PREFIX}/{run_dir.relative_to(self.prefix_dir).as_posix()}"
                dxvk_logs = f"{inside}/{_DXVK_LOG_DIR}"
            else:
                (self.prefix_dir / _DXVK_LOG_DIR).mkdir(parents=True, exist_ok=True)
                dxvk_logs = f"{_CONTAINER_PREFIX}/{_DXVK_LOG_DIR}"
            argv += ["-e", f"WINEDLLOVERRIDES={BAKE_DLL_OVERRIDES}"]
            argv += ["-e", f"DXVK_LOG_PATH={dxvk_logs}"]
            launcher = ["with-display"]
        for name, value in stage_environment(layout).items():
            argv += ["-e", f"{name}={value}"]
        argv += self.docker_args
        argv += [self.image, *launcher, "wine", *command]
        return argv

    # -- running -----------------------------------------------------------

    def run(
        self,
        command: Sequence[str],
        *,
        layout: ToolsLayout,
        stage: str,
        stall_window_s: float | None = None,
        timeout_s: float | None = None,
    ) -> RunResult:
        """Run the stage in the container and hand back its raw output.

        The ``TA_*`` variables travel as ``docker run -e`` rather than in
        this process's environment, because they are absolute *Windows*
        paths and mean nothing to anything on this side of Wine.
        """
        # Imported here, not at the top: ``python -m zmforge.toolchain.buildlock``
        # imports this package first, and a top-level import would load the
        # module twice (runpy warns).
        from .buildlock import HeavySlot, tools_lock

        self.require_prefix()
        if stage == "bake":
            # The heavy stage: waits for GPU memory, RAM and cores, then runs
            # beside any other bakes that fit (zmforge.toolchain.buildlock).
            with HeavySlot(f"bake {os.getpid()}", gpu=self.gpu):
                return self._run_bake(command, layout, timeout_s)
        # Every other stage writes files all maps share (the conversion
        # cache, collision maps, gdt.db), so one at a time.
        with tools_lock():
            argv = self.command_line(command, layout, stage=stage)
            started = time.monotonic()
            process = self._start(argv, stage)
            if stall_window_s is None:
                return self._wait(process, started, timeout_s)
            return self._wait_watching_for_stall(process, started, stall_window_s, timeout_s)

    def _start(self, argv: Sequence[str], stage: str) -> "subprocess.Popen[bytes]":
        try:
            return subprocess.Popen(  # noqa: S603 - argv is built from the layout
                list(argv),
                env=dict(os.environ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as problem:
            raise ToolchainError(f"could not start {stage} under wine: {problem}") from problem

    def _run_bake(
        self,
        command: Sequence[str],
        layout: ToolsLayout,
        timeout_s: float | None,
    ) -> RunResult:
        """Run Radiant's silent bake and hand back console output plus its log.

        The stall detector is not used here on purpose: the measured failure
        is a spin, not a stall, and the docker client's CPU time says
        nothing about the tool's. Instead the run has a hard cap, and once
        Radiant has printed its export line it gets ``bake_linger_s`` to exit
        before the container is stopped, because it has been seen never to.
        Radiant's own log is appended after :data:`RADIANT_LOG_MARKER`; it is
        the only record of the phases and of the export.
        """
        name = f"zmforge-bake-{os.getpid()}-{time.monotonic_ns()}"
        run_dir = self.prefix_dir / _BAKE_RUNS / name
        radiant_log = run_dir / "Documents" / "Radiant.log"
        argv = self.command_line(
            command, layout, stage="bake", container_name=name, run_dir=run_dir
        )
        limit = self.bake_timeout_s if timeout_s is None else timeout_s
        started = time.monotonic()
        process = self._start(argv, "bake")
        chunks: list[bytes] = []
        stream = process.stdout
        assert stream is not None
        reader = threading.Thread(target=_drain, args=(stream, chunks), daemon=True)
        reader.start()
        timed_out = False
        exported_at: float | None = None
        try:
            while process.poll() is None:
                time.sleep(self.poll_interval_s)
                now = time.monotonic()
                if exported_at is None and BAKE_EXPORTED_MARKER in b"".join(chunks):
                    exported_at = now
                if exported_at is not None and now - exported_at >= self.bake_linger_s:
                    self._stop_container(name, process)
                    break
                if now - started >= limit:
                    timed_out = True
                    self._stop_container(name, process)
                    break
            process.wait()
        finally:
            reader.join(timeout=5.0)
            stream.close()
        output = b"".join(chunks)
        try:
            output += f"\n{RADIANT_LOG_MARKER}\n".encode() + radiant_log.read_bytes()
        except OSError:
            output += f"\n{RADIANT_LOG_MARKER}\n(not written)\n".encode()
        # The log is in the stage log now; the scratch is not needed again.
        shutil.rmtree(run_dir, ignore_errors=True)
        exit_code = process.returncode if process.returncode is not None else -1
        return RunResult(
            exit_code, output, time.monotonic() - started, stalled=timed_out, timed_out=timed_out
        )

    def _stop_container(self, name: str, process: "subprocess.Popen[bytes]") -> None:
        """Kill by name, then the client: the loader inside ignores SIGTERM."""
        subprocess.run(  # noqa: S603 - fixed argv
            [self.docker, "kill", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        process.kill()

    def require_prefix(self) -> None:
        """Make sure the prefix directory exists before a container wants it.

        A bind mount of a missing directory is created by the daemon owned by
        root and empty, which looks like a corrupt prefix later; creating it
        here keeps the failure at "wine has to initialise a prefix", which
        the image's entrypoint does on its own.
        """
        self.prefix_dir.mkdir(parents=True, exist_ok=True)

    # -- questions about the tools install's filesystem ------------------------

    def size_of(self, path: PurePath | str) -> int | None:
        local = self.local_path(path)
        if local is None:
            return None
        try:
            return local.stat().st_size
        except OSError:
            return None

    def mtime_of(self, path: PurePath | str) -> float | None:
        """Modification time of the tools file, on the local clock."""
        local = self.local_path(path)
        if local is None:
            return None
        try:
            return local.stat().st_mtime
        except OSError:
            return None

    def is_directory(self, path: PurePath | str) -> bool:
        local = self.local_path(path)
        return local is not None and local.is_dir()

    # -- availability -------------------------------------------------------

    def unavailable_because(self) -> str | None:
        """Why this runner cannot be used here, or ``None`` when it can.

        Checked rather than assumed, because the alternative is a build that
        fails deep inside a stage with docker's error text in a tool log.
        """
        if shutil.which(self.docker) is None:
            return f"{self.docker} is not on PATH"
        if not self.tools_dir.is_dir():
            return f"no local mod-tools copy at {self.tools_dir}"
        # Each of these is named on its own. "an incomplete tools copy" tells
        # nobody which file to go and fetch, and the alternative is a stage
        # that dies inside Wine with an error naming none of them: a missing
        # executable as "Application could not be started", a missing
        # share/raw as a linker ERROR: line about an asset.
        for rel in ("bin/cod2map64.exe", "bin/linker_modtools.exe"):
            if not (self.tools_dir / rel).is_file():
                return f"{self.tools_dir / rel} is missing (an incomplete tools copy)"
        for rel in ("share/raw", "map_source"):
            if not (self.tools_dir / rel).is_dir():
                return f"{self.tools_dir / rel} is missing (an incomplete tools copy)"
        inspect = subprocess.run(  # noqa: S603 - fixed argv
            [self.docker, "image", "inspect", self.image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if inspect.returncode != 0:
            return f"docker image {self.image} is not built"
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"WineRunner({str(self.tools_dir)!r}, image={self.image!r})"
