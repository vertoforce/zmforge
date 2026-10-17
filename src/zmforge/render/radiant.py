"""Pictures from Radiant's own 3D camera, driven under Wine in a container.

WHY Radiant: it draws the map with the game's real converted models and
materials (``share/assetconvert``), on the GPU through DXVK, so what it shows
is what the stock assets look like, not stand-in boxes.  It needs only the
mod tools, not the game, so it is the closest view a tools-only install can
make.

How one run goes [measured, zm_dmv]:

* the ``.map`` is copied to ``map_source/zm/zmforge_render/`` in the tools
  tree (a separate folder, so a build of the real map is never touched);
* a container from ``docker/radiant-render`` (bo3-wine plus xdotool, xwd,
  imagemagick) starts Xorg on the GPU and Radiant inside a Wine *virtual
  desktop*: without one, Wine ignores focus and typed keys in its dialogs;
* loading zm_dmv takes about 3 minutes; the run waits for Radiant's CPU to
  settle, then drags the camera pane to 1902x826;
* each view goes through Radiant's "Go To Position/Orientation" dialog
  (``X Y Z pitch yaw``; negative pitch looks down), then the camera pane is
  grabbed with ``xwd`` and scaled to at most 1024 px.

Radiant's helper drawing (clip, caulk, triggers, volumes, path nodes, spawn
markers) is switched off through its filter settings in a private copy of
the Wine prefix, so the real prefix used by builds is never written to.
Custom materials that were never registered in the local gdtDB (``gdtdb``
does not run under Wine) draw black; stock assets draw as in the editor.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from ..localtools import bo3_wine_dir, tools_dir, wine_prefix_dir
from ..toolchain.buildlock import GLOBAL_LOCK_NAME, BuildLock, lock_dir
from ..toolchain.buildlock import ancestors as _ancestors  # noqa: F401 - old name
from ..toolchain.buildlock import lock_holders  # noqa: F401 - re-exported
from .cameras import View

REPO = Path(__file__).resolve().parents[3]
BO3_WINE = bo3_wine_dir()             # $ZMFORGE_BO3_WINE (zmforge.localtools)
IMAGE = "zmforge-radiant-render:local"   # built from docker/radiant-render
DOCKERFILE_DIR = REPO / "docker" / "radiant-render"
WIN_ROOT = r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130"
RENDER_DIR = "zmforge_render"            # under map_source/zm in the tools tree
DLL_OVERRIDES = "mscoree=d;msvcr110,msvcp110=n;d3d11,dxgi,d3d10core=n"

# Screen geometry of Radiant's default layout on a 1920x1080 Wine desktop
# [measured].  The camera pane is enlarged by dragging the splitter
# under it to the bottom and the one on its right to the edge.
SPLIT_BOTTOM = ((800, 639), (800, 1030))
SPLIT_RIGHT = ((1634, 400), (1910, 400))
GOTO_BUTTON = (651, 1073)
GOTO_TEXT_BOX = (953, 576)   # the text box of the (centred) Go To Position dialog
#: Mean absolute difference (0-1) of two 64x36 thumbnails under which a shot
#: counts as the previous one again.
SAME_SHOT_MAE = 0.01
# Game View letterboxes the 1902x826 pane to a centred 16:9 frame
# (1468x826 at x 219); the bottom 36 rows carry Radiant's exposure/stats text.
CAMERA_CROP = "1468x790+219+197"   # less the HUD text along its foot
PARK_MOUSE = (1000, 600)   # inside the camera pane, so it keeps redrawing
RENDER_METHOD_BUTTON = (24, 178)   # first icon of the camera pane's toolbar (a toggle, not a menu)
#: Radiant's render-method hotkeys (View > Render Method).  The old
#: toolbar-menu clicks at (24, 178) then (50, 270) never opened a menu: the
#: first icon is a toggle, so a render that clicks it blind gets
#: Radiant's default view-based fake lighting (measured: picture identical,
#: View > Render Method still ticked on the default).  F8 ticks Real Lighting;
#: the camera repaints on the next jump.  View-based fake lighting (Radiant's
#: default) has no key.
LIGHTING_KEYS = {"wireframe": "F5", "fullbright": "F6", "normal": "F7", "real": "F8",
                 "baked": "F8"}
LIGHTING_ITEMS = LIGHTING_KEYS   # old name
#: Build Lighting (the lightning bolt) lives on the Exposure toolbar, which a
#: fresh prefix hides: View (menu) > View Toolbar > Exposure shows it, in the
#: camera pane's toolbar row.  Positions measured on the
#: 1920x1080 desktop after :meth:`RadiantCamera._layout`.
VIEW_MENU = (145, 42)
VIEW_TOOLBAR_ITEM = (181, 110)
EXPOSURE_TOOLBAR_ITEM = (452, 163)
BAKE_BUTTON = (640, 178)
BAKE_QUALITY = {"low": (529, 178), "medium": (569, 178), "high": (607, 178)}
#: Radiant.log's last line of a finished bake (sun, probes, four bounces).
BAKE_DONE = "All Probes Done"

#: Radiant filter groups switched *off* for a render: editor helpers a player
#: never sees.  Radiant keeps these as ``"name"="true"`` (shown) in the
#: prefix's user.reg under Software\\Treyarch\\Radiant\\Filters\\Groups.
HIDDEN_FILTERS: dict[str, tuple[str, ...]] = {
    "Entities": ("ActionNodes", "AISpawners", "CoOpSpawns", "CoverNodes", "Info",
                 "info_player_start", "PathNodes", "ReflectionProbes", "script_origins",
                 "TraversalNodes", "heli_height_lock", "Build Lighting", "MP_entities"),
    "Geometry": ("Caulk", "Clip", "ClipOnly", "CollisionMap", "FullClip", "HintSkip",
                 "Ladder", "Mantle", "MonsterClip", "NoDraw", "nodraw_notsolid",
                 "OutOfBounds", "PhysicsClip", "PlayerClip", "Sky", "traverse",
                 "VehicleClip", "WeaponClip"),
    "Triggers": ("*",),
    "Triggers\\\\In": ("*",),
    "Volumes": ("*",),
}


def without_script_lights(map_text: str) -> tuple[str, int]:
    """*map_text* without its exploder lights, and how many were left out.

    An exploder light (``exploder_count`` key, :func:`zmforge.script.glow.place_owned_glow`)
    is switched by the map's script, e.g. the cemetery's will-o'-wisp flashes;
    the game never bakes it (``exploderDisabled 1``).  Radiant's Real Lighting
    draws every light it loads, so a photo would show an event's light as if
    it were always on.  Presentation and review renders show the map at rest.
    """
    parts = re.split(r"(?m)^(?=// entity \d+\n)", map_text)
    kept, dropped = [], 0
    for part in parts:
        if (part.startswith("// entity") and '"classname" "light"' in part
                and '"exploder_count"' in part and part.count("\n{\n") == 1):
            dropped += 1
            continue
        kept.append(part)
    return "".join(kept), dropped


class RenderError(RuntimeError):
    """Radiant could not be started, loaded or driven."""


#: Radiant preferences set for a render.  Game View is the Filter window's
#: "camera window displays only those items that will be visible in game":
#: without it every entity keeps its blue box and every light its bulb icon.
RENDER_PREFS = {"Filter_ShowGameView": "true"}


#: Fog preview (``ZMFORGE_RENDER_FOG=1``, added): these Volumes
#: filter groups stay shown, so the fog, exposure and grade volumes reach
#: Radiant's camera.  Radiant's own "WorldFogEnabled" preference and its
#: ``RENDER_OPTION_ENABLE_VOLUMETRIC_*`` / ``ENABLE_COLOR_GRADING`` render
#: options are already on in the prefix.  Off by default: every other render
#: hides all volumes, as before.  Measured (zm_cemetery, --baked
#: --hero): the picture is pixel-identical with and without it, so Radiant's
#: camera as driven here draws no lit fog or grade (docs/fog-and-gloom.md).
FOG_PREVIEW_SHOWN: dict[str, tuple[str, ...]] = {
    "Volumes": ("Litfog", "WorldFogVolumes", "WorldFogModifierVolumes", "ExposureVolumes",
                "PBGVolumes", "VColorVolumes", "LUTVolumes"),
}


def bolt_visible(fraction: str) -> bool:
    """Whether the share of bolt-coloured pixels (white when idle, yellow when
    lit) around BAKE_BUTTON (``convert``'s ``%[fx:mean]`` text) says the Build
    Lighting bolt is on screen; with the Exposure toolbar hidden that spot is
    bare dark toolbar.  Each render logs the share it saw."""
    try:
        return float(fraction.strip()) >= 0.05
    except ValueError:
        return False


def fog_preview() -> bool:
    """Whether this render keeps the fog volumes (``ZMFORGE_RENDER_FOG=1``)."""
    return os.environ.get("ZMFORGE_RENDER_FOG", "") == "1"


def hide_helpers(user_reg: str, hidden: dict[str, tuple[str, ...]] = HIDDEN_FILTERS,
                 prefs: dict[str, str] = RENDER_PREFS,
                 shown: dict[str, tuple[str, ...]] | None = None) -> str:
    """*user_reg* with the listed Radiant filter groups hidden and *prefs* set.

    Names in *shown* are set shown even where *hidden* would hide them."""
    shown = shown or {}
    for name, value in prefs.items():
        user_reg = re.sub(rf'^"{re.escape(name)}"="[^"]*"$', f'"{name}"="{value}"',
                          user_reg, flags=re.MULTILINE)
    out, section = [], None
    head = re.compile(r'^\[Software\\\\Treyarch\\\\Radiant\\\\Filters\\\\Groups\\\\(.+?)\]')
    for line in user_reg.splitlines(keepends=True):
        if line.startswith("["):
            m = head.match(line)
            section = m.group(1) if m else None
        elif section in hidden and line.startswith('"'):
            name = line.split('"')[1]
            names = hidden[section]
            if name in shown.get(section, ()):
                line = re.sub(r'="false"', '="true"', line)
            elif "*" in names or name in names:
                line = re.sub(r'="true"', '="false"', line)
        out.append(line)
    return "".join(out)


def gpu_free_mb() -> int | None:
    try:
        done = subprocess.run(["nvidia-smi", "--query-gpu=memory.free",
                               "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return int(done.stdout.split()[0])
    except (IndexError, ValueError):
        return None


#: The machine-wide lock (``zmforge.toolchain.buildlock``). Build steps hold it
#: shared and run side by side; a Radiant render holds it *exclusive*, so it
#: runs alone: its Radiant writes the same conversion cache and tools
#: databases the builds do, and that has not been measured side by side.  A
#: lock, not a process scan: a ``pgrep -f`` guard matches its own waiters'
#: command lines and deadlocks them.
LOCK_FILE = REPO / "build-out" / GLOBAL_LOCK_NAME


class RadiantLock(BuildLock):
    """Hold the global lock exclusively for one Radiant session.

    If an ancestor of this process already holds it (``flock ... zmforge
    render``, or a build script run under flock), the session
    runs under that hold instead of waiting for itself forever.
    """

    def __init__(self, path: Path | None = None, log: Callable[[str], None] = lambda s: None):
        super().__init__(path or lock_dir() / GLOBAL_LOCK_NAME, shared=False, log=log)


def require_render_tools(tools: Path) -> None:
    """One-line :class:`RenderError` when render cannot run here at all.

    Without this a first ``zmforge render`` on a machine with no tools copy
    (or no docker) ran the generate, then died in a FileNotFoundError or
    CalledProcessError traceback from deep inside the asset or docker steps.
    """
    if not (Path(tools) / "bin" / "radiant_modtools.exe").is_file():
        raise RenderError(
            f"no mod tools at {tools}: render needs the Wine tools copy "
            "(run docker/bo3-wine/setup.sh, or set ZMFORGE_WINE_TOOLS)"
        )
    if shutil.which("docker") is None:
        raise RenderError("render needs docker on PATH: it runs Radiant in a container")


#: Docker label on a container started under ``ZMFORGE_RENDER_KEEP=1``: left
#: running on purpose for a later session to attach to, so never swept.
KEEP_LABEL = "zmforge.render.keep"
CONTAINER_PREFIX = "zmforge-render-"

#: Sessions with a container up, closed at interpreter exit or on SIGTERM.
_LIVE: dict[int, "RadiantCamera"] = {}
_EXIT_HOOKED = False


def _close_live() -> None:
    for camera in list(_LIVE.values()):
        try:
            camera.close()
        except Exception:  # pragma: no cover - best effort at exit
            pass


def _on_sigterm(signum, frame) -> None:
    # Python's default SIGTERM ends the process without running ``finally``
    # blocks or atexit; turning it into SystemExit runs both.
    raise SystemExit(128 + signum)


def _guard_exit(camera: "RadiantCamera") -> None:
    """Remove *camera*'s container however this process ends (bar SIGKILL)."""
    global _EXIT_HOOKED
    _LIVE[id(camera)] = camera
    if _EXIT_HOOKED:
        return
    import atexit
    import signal
    import threading

    atexit.register(_close_live)
    if threading.current_thread() is threading.main_thread():
        if signal.getsignal(signal.SIGTERM) is signal.SIG_DFL:
            signal.signal(signal.SIGTERM, _on_sigterm)
    _EXIT_HOOKED = True


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:          # EPERM: alive, someone else's
        return True
    return True


def sweep_stale_containers(log: Callable[[str], None] = lambda s: None) -> list[str]:
    """Remove ``zmforge-render-<pid>`` containers whose process is gone.

    What a SIGKILLed or crashed render leaves behind: a GPU container holding
    VRAM with nobody to close it.  Containers labelled :data:`KEEP_LABEL` were
    left on purpose and stay.  Returns the names removed.
    """
    try:
        listed = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}",
             "--format", '{{.Names}}\t{{.Label "' + KEEP_LABEL + '"}}'],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    removed = []
    for row in listed.stdout.splitlines():
        name, _, keep = row.partition("\t")
        suffix = name[len(CONTAINER_PREFIX):] if name.startswith(CONTAINER_PREFIX) else ""
        if not suffix.isdigit() or keep.strip() == "1":
            continue
        pid = int(suffix)
        if pid == os.getpid() or _pid_alive(pid):
            continue
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        log(f"removed {name}, left running by a render (pid {pid}) that is gone")
        removed.append(name)
    return removed


@dataclass
class RadiantCamera:
    """One Radiant session showing one map; use as a context manager."""

    map_file: Path
    tools: Path = field(default_factory=tools_dir)            # $ZMFORGE_WINE_TOOLS
    base_prefix: Path = field(default_factory=wine_prefix_dir)  # $ZMFORGE_WINE_PREFIX
    work: Path = REPO / "build-out" / "render" / ".radiant"
    image: str = IMAGE
    vram_mb: int = 2500
    load_timeout: float = 900.0
    #: "fake" (Radiant's default view-based light), a LIGHTING_KEYS key, or
    #: "baked": Real Lighting after Radiant's own Build Lighting of this very
    #: map (sun, probes, bounces, medium quality like the builds' bake).
    lighting: str = "fake"
    bake_quality: str = "medium"
    bake_timeout: float = 1800.0
    log: Callable[[str], None] = lambda s: None
    container: str | None = None
    #: extra ``(host path, container path)`` bind mounts, e.g. the private
    #: ``gdt.db`` from :mod:`.assets`; read-only.
    mounts: Sequence[tuple[str, str]] = ()

    # ------------------------------------------------------------------
    def __enter__(self) -> "RadiantCamera":
        if self.container:          # attach to a session left by ZMFORGE_RENDER_KEEP
            self._wait_loaded()
        else:
            # ``start`` runs before the ``with`` body, so ``__exit__`` never
            # sees a failure (or a Ctrl-C) inside it: without this the GPU
            # container it had already started kept running, holding VRAM.
            try:
                self.start()
            except BaseException:
                self.close()
                raise
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    def _prefix(self) -> Path:
        prefix = self.work / "wineprefix"
        if not (prefix / "user.reg").is_file():
            if not (Path(self.base_prefix) / "user.reg").is_file():
                raise RenderError(
                    f"no Wine prefix at {self.base_prefix}: run docker/bo3-wine/setup.sh "
                    "first (or set ZMFORGE_WINE_PREFIX)"
                )
            self.log(f"copying the Wine prefix to {prefix}")
            prefix.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.base_prefix, prefix, symlinks=True)
        reg = prefix / "user.reg"
        shown = FOG_PREVIEW_SHOWN if fog_preview() else None
        if shown:
            self.log("fog preview: fog, exposure and grade volumes stay shown")
        reg.write_text(hide_helpers(reg.read_text(encoding="utf-8", errors="surrogateescape"),
                                    shown=shown),
                       encoding="utf-8", errors="surrogateescape")
        shims = prefix / "shims" / "bin"
        subprocess.run(["python3", str(BO3_WINE / "scripts" / "patch-embree.py"),
                        str(self.tools), str(prefix / "shims")],
                       capture_output=True, check=False)
        shims.mkdir(parents=True, exist_ok=True)
        (shims / "GdtDBTrayLauncher.exe").write_bytes(b"")
        return prefix

    def _stage_map(self) -> str:
        dest = self.tools / "map_source" / "zm" / RENDER_DIR / self.map_file.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        text, dropped = without_script_lights(self.map_file.read_text(encoding="utf-8",
                                                                     errors="surrogateescape"))
        if dropped:
            self.log(f"left out {dropped} script-switched (exploder) light(s): "
                     "the photo shows the map at rest")
        dest.write_text(text, encoding="utf-8", errors="surrogateescape")
        return f"{WIN_ROOT}\\map_source\\zm\\{RENDER_DIR}\\{self.map_file.name}"

    def _ensure_image(self) -> None:
        have = subprocess.run(["docker", "image", "inspect", self.image],
                              capture_output=True).returncode == 0
        if not have:
            self.log(f"building {self.image}")
            subprocess.run(["docker", "build", "-q", "-t", self.image, str(DOCKERFILE_DIR)],
                           check=True, capture_output=True)

    def _wait_vram(self) -> None:
        """Wait for free VRAM rather than fall back to software rendering (llvmpipe)."""
        waited = False
        while True:
            free = gpu_free_mb()
            if free is None:
                raise RenderError("nvidia-smi gave no reading; not starting Radiant on the CPU")
            if free >= self.vram_mb:
                return
            if not waited:
                self.log(f"waiting for {self.vram_mb} MiB of free VRAM (have {free})")
                waited = True
            time.sleep(30)

    def sh(self, script: str, timeout: float = 120.0, check: bool = False) -> str:
        """Run *script* with ``sh -c`` in the container on Radiant's display."""
        done = subprocess.run(["docker", "exec", "-e", "DISPLAY=:99", self.container,
                               "sh", "-c", script], capture_output=True, text=True,
                              timeout=timeout)
        if check and done.returncode != 0:
            raise RenderError(f"{script[:80]!r}: exit {done.returncode}: {done.stderr[-300:]}")
        return done.stdout

    # ------------------------------------------------------------------
    def _lock(self) -> None:
        """Take the machine-wide Radiant lock; held until :meth:`close`."""
        self._radiant_lock = RadiantLock(log=self.log).acquire()

    def start(self) -> None:
        self._lock()
        self._ensure_image()
        prefix = self._prefix()
        win_map = self._stage_map()
        self._wait_vram()
        self.work.mkdir(parents=True, exist_ok=True)
        sweep_stale_containers(log=self.log)
        self.container = f"zmforge-render-{os.getpid()}"
        subprocess.run(["docker", "rm", "-f", self.container], capture_output=True)
        _guard_exit(self)
        shims = prefix / "shims" / "bin"
        mounts = []
        for rel in ("avx/embree64r.dll", "GdtDBTrayLauncher.exe"):
            if (shims / rel).is_file():
                mounts += ["-v", f"{shims / rel}:/tools/bin/{rel}:ro"]
        for host, inside, *rest in self.mounts:
            # gdt.db is opened for writing by Radiant's gdtDB client, so it
            # is a private copy mounted read-write; everything else read-only
            # unless the mount says otherwise (a third item, "rw").
            mode = rest[0] if rest else ("rw" if inside.endswith("gdt.db") else "ro")
            mounts += ["-v", f"{Path(host).resolve()}:{inside}:{mode}"]
        keep = ([] if os.environ.get("ZMFORGE_RENDER_KEEP") != "1"
                else ["--label", f"{KEEP_LABEL}=1"])
        argv = ["docker", "run", "-d", "--name", self.container, *keep, "--gpus", "all", *mounts,
                "-v", f"{self.tools}:/tools", "-v", f"{prefix}:/wineprefix",
                "-e", f"TA_GAME_PATH={WIN_ROOT}\\", "-e", f"TA_TOOLS_PATH={WIN_ROOT}\\",
                "-e", f"TA_LOCAL_ASSET_CACHE={WIN_ROOT}\\share\\assetconvert\\",
                "-e", "WINEDEBUG=-all", "-e", f"WINEDLLOVERRIDES={DLL_OVERRIDES}",
                "-w", f"/wineprefix/drive_c/Program Files (x86)/Steam/steamapps/common/"
                      "Call of Duty Black Ops III 455130/bin",
                self.image, "with-display", "sleep", "infinity"]
        done = subprocess.run(argv, capture_output=True, text=True)
        if done.returncode != 0:
            raise RenderError(f"docker run failed: {done.stderr[-300:]}")
        exe = f"{WIN_ROOT}\\bin\\radiant_modtools.exe"
        launch = (f"wine explorer /desktop=zmforge,1920x1080 {shlex.quote(exe)} "
                  f"{shlex.quote(win_map)} >/tmp/radiant.out 2>&1")
        subprocess.run(["docker", "exec", "-d", "-e", "DISPLAY=:99", self.container,
                        "sh", "-c", launch], check=True)
        self.log(f"Radiant starting on {self.map_file.name} in {self.container}")
        self._wait_loaded()
        self._layout()

    def _wait_loaded(self) -> None:
        started = time.time()
        deadline = started + self.load_timeout
        stem = self.map_file.name
        quiet = 0
        while time.time() < deadline:
            if not self.sh("pgrep -fi radiant_modtools").strip():
                if time.time() - started > 120:
                    raise RenderError("Radiant is not running; see /tmp/radiant.out "
                                      f"in {self.container}")
                time.sleep(5)
                continue
            titles = self.sh("for w in $(xdotool search --onlyvisible --name . 2>/dev/null); "
                             "do xdotool getwindowname $w; done").splitlines()
            # Loaded once the main window names the map and neither progress
            # window ("Loading: ..." for prefabs, "Performing LiveUpdate" for
            # model conversion) has been visible for five samples in a row:
            # they close and reopen between passes.  Radiant's CPU never
            # settles, it redraws continuously.
            loaded = (any(t.startswith("C:/") and stem in t for t in titles)
                      and not any(t.startswith(("Loading", "Performing")) for t in titles))
            quiet = quiet + 1 if loaded else 0
            if quiet >= 5:
                self.log(f"Radiant loaded in {time.time() - started:.0f} s")
                time.sleep(5)
                return
            time.sleep(3)
        raise RenderError(f"Radiant did not finish loading in {self.load_timeout:.0f} s")

    def _layout(self) -> None:
        (a, b), (c, d) = SPLIT_BOTTOM, SPLIT_RIGHT
        self.sh(f"xdotool mousemove {a[0]} {a[1]} mousedown 1 mousemove {a[0]} 800 "
                f"mousemove {b[0]} {b[1]} mouseup 1; sleep 1; "
                f"xdotool mousemove {c[0]} {c[1]} mousedown 1 mousemove 1800 {c[1]} "
                f"mousemove {d[0]} {d[1]} mouseup 1; sleep 1", check=True)
        if self.lighting != "fake":
            self.set_lighting(self.lighting)

    def set_lighting(self, mode: str) -> None:
        # Real Lighting first: Build Lighting is greyed out in the other modes.
        self.sh(f"xdotool mousemove {PARK_MOUSE[0]} {PARK_MOUSE[1]}; "
                f"xdotool key {LIGHTING_KEYS[mode]}; sleep 2", check=True)
        if mode == "baked":
            self.build_lighting(self.bake_quality)
        self.lighting = mode

    def _radiant_log(self) -> Path:
        return self.work / "wineprefix" / "drive_c" / "users" / "root" / "Documents" / "Radiant.log"

    def _bolt_shown(self) -> bool:
        x, y = BAKE_BUTTON
        frac = self.sh(f"xwd -root -silent > /tmp/bolt.xwd && convert /tmp/bolt.xwd -crop "
                       f"15x15+{x - 7}+{y - 7} +repage -fx '(r>0.6&&g>0.5&&b<0.35)||(r>0.75&&g>0.75&&b>0.75)' "
                       f"-format '%[fx:mean]' info:")
        self.log(f"build-lighting bolt: {frac.strip() or '?'} of its box lit")
        return bolt_visible(frac)

    def build_lighting(self, quality: str = "medium") -> None:
        """Radiant's Build Lighting on the loaded map; returns when Radiant.log says done."""
        if not self._bolt_shown():
            (vx, vy), (tx, ty), (ex, ey) = VIEW_MENU, VIEW_TOOLBAR_ITEM, EXPOSURE_TOOLBAR_ITEM
            self.sh(f"xdotool mousemove {vx} {vy} click 1; sleep 1.2; xdotool mousemove {tx} {ty} "
                    f"click 1; sleep 1.2; xdotool mousemove {ex} {ey} click 1; sleep 2", check=True)
            if not self._bolt_shown():
                raise RenderError("the Exposure toolbar's Build Lighting button did not appear")
        log = self._radiant_log()
        seen = log.read_bytes().count(BAKE_DONE.encode()) if log.is_file() else 0
        (qx, qy), (bx, by) = BAKE_QUALITY[quality], BAKE_BUTTON
        self.sh(f"xdotool mousemove {qx} {qy} click 1; sleep 1; xdotool mousemove {bx} {by} click 1",
                check=True)
        self.log(f"building lighting ({quality})")
        started = time.time()
        while time.time() - started < self.bake_timeout:
            time.sleep(5)
            if log.is_file() and log.read_bytes().count(BAKE_DONE.encode()) > seen:
                self.log(f"lighting built in {time.time() - started:.0f} s")
                time.sleep(3)
                return
        raise RenderError(f"Build Lighting did not finish in {self.bake_timeout:.0f} s")

    def goto(self, view: View) -> None:
        x, y = GOTO_BUTTON
        for _attempt in range(3):
            self.sh(f"xdotool mousemove {x} {y} click 1; sleep 1.5")
            if self.sh("xdotool search --onlyvisible --name 'Go To Position'").strip():
                break
        else:
            raise RenderError("the Go To Position dialog did not open")
        # Only the first opening focuses the text box; later ones keep the
        # last text and focus elsewhere, so typing is lost and Return re-applies
        # the old position.  Click the box first, at its place on the screen
        # (the dialog opens centred; its X geometry is wrong inside a Wine
        # virtual desktop).  XTEST keys, not synthetic ones: Wine drops those.
        # Radiant's pitch is positive *up*, the opposite of View's.
        text = f"{view.x:.0f} {view.y:.0f} {view.z:.0f} {-view.pitch:.1f} {view.yaw:.1f}"
        bx, by = GOTO_TEXT_BOX
        self.sh(f"sleep 1; xdotool mousemove {bx} {by} click 1; sleep 0.2; "
                # "--": a negative x would otherwise be read as an option.
                f"xdotool key ctrl+a BackSpace; xdotool type --delay 12 -- "
                f"{shlex.quote(text)}; sleep 0.3; xdotool key Return", check=True)

    def capture(self, out: Path, *, width: int = 1024, settle: float = 3.0) -> Path:
        px, py = PARK_MOUSE
        self.sh(f"xdotool mousemove {px} {py}; sleep {settle / 2:.1f}; "
                f"xdotool mousemove {px + 2} {py}; sleep {settle / 2:.1f}")
        tmp = f"/tmp/{out.stem}.png"
        self.sh(f"xwd -root -silent > /tmp/grab.xwd && convert /tmp/grab.xwd -crop "
                f"{CAMERA_CROP} +repage -resize '{width}x{width}>' {shlex.quote(tmp)}",
                check=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("wb") as fh:
            subprocess.run(["docker", "exec", self.container, "cat", tmp], stdout=fh, check=True)
        return out

    def _unchanged(self, tmp: str) -> bool:
        """True when *tmp* looks like the previous shot: the jump did not happen."""
        diff = self.sh(f"[ -f /tmp/prev.png ] && compare -metric MAE "
                       f"\\( {shlex.quote(tmp)} -resize 64x36! \\) "
                       f"\\( /tmp/prev.png -resize 64x36! \\) null: 2>&1; "
                       f"cp {shlex.quote(tmp)} /tmp/prev.png").strip()
        m = re.search(r"\(([0-9.e-]+)\)", diff)
        return bool(m) and float(m.group(1)) < SAME_SHOT_MAE

    def shoot(self, view: View, out: Path, *, width: int = 1024) -> Path:
        """Jump to *view* and grab it; a jump that left the picture unchanged
        (the dialog lost the typing) is retried, then refused."""
        for attempt in range(3):
            self.goto(view)
            self.capture(out, width=width)
            if not self._unchanged(f"/tmp/{out.stem}.png"):
                return out
            self.log(f"  {out.stem}: picture unchanged after the jump, retrying")
        out.unlink(missing_ok=True)
        raise RenderError(f"Radiant's camera would not move to {view.radiant_text()}")

    def screenshot(self, out: Path, width: int = 1024) -> Path:
        """The whole Wine desktop, for when driving Radiant went wrong."""
        self.sh(f"xwd -root -silent > /tmp/grab.xwd && convert /tmp/grab.xwd "
                f"-resize '{width}x{width}>' -quality 70 /tmp/screen.jpg")
        with out.open("wb") as fh:
            subprocess.run(["docker", "exec", self.container, "cat", "/tmp/screen.jpg"],
                           stdout=fh, check=False)
        return out

    def close(self) -> None:
        if self.container and os.environ.get("ZMFORGE_RENDER_KEEP") == "1":
            self.log(f"leaving {self.container} running (ZMFORGE_RENDER_KEEP=1)")
            return
        if self.container:
            subprocess.run(["docker", "rm", "-f", self.container], capture_output=True)
            self.container = None
        _LIVE.pop(id(self), None)
        lock = getattr(self, "_radiant_lock", None)
        if lock is not None:
            lock.release()
            self._radiant_lock = None


def render_views(map_file: Path, views: Sequence[View], out_dir: Path, *,
                 width: int = 1024, log: Callable[[str], None] = lambda s: None,
                 timing: dict | None = None, **kwargs) -> list[tuple[View, Path]]:
    """Shoot every view of *map_file* into *out_dir* (``<room>--<view>.png``).

    One Radiant session serves every view: the load (75-180 s) is paid once
    per run, each view after it costs a few seconds.  *timing* receives
    ``radiant_load`` and ``shoot`` seconds.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = []
    timing = {} if timing is None else timing
    t0 = time.time()
    with RadiantCamera(Path(map_file), log=log, **kwargs) as cam:
        timing["radiant_load"] = round(time.time() - t0)
        t1 = time.time()
        for view in views:
            try:
                path = cam.shoot(view, out_dir / f"{view.slug}.png", width=width)
            except RenderError:
                log(f"failed; the screen is in {cam.screenshot(out_dir / '_failure.jpg')}")
                raise
            log(f"  {path.name}")
            shots.append((view, path))
            timing["shoot"] = round(time.time() - t1)
            timing["views"] = len(shots)
    return shots
