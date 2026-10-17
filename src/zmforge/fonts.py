"""Find a font file for a job name, on any OS, without vendoring fonts.

The painters (:mod:`zmforge.texture.paint`) ask for faces by job ("sign",
"serif", "typewriter").  Each job has a list of candidate file names, in
order of preference: the free faces named in :data:`FACES` first (on Debian
these come from the packages listed there), then the metric-compatible faces
macOS and Windows ship, then one open-licence
(SIL OFL 1.1) face that is downloaded on first use.  For each candidate, in
order, it looks in:

1. the font cache (``assets-cache/fonts`` in a checkout, else a per-user cache
   dir; ``ZMFORGE_FONT_DIR`` overrides), whose downloadable faces and their
   licences are recorded in ``assets-cache/fonts/FONTS.json``;
2. the OS font directories (Linux, macOS, Windows).

Only when no candidate is found anywhere is the OFL face fetched into the
cache, with its ``OFL.txt`` beside it.  Offline, that fails with one line
naming the job and how to fix it.  No font bytes live in the repository.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import ForgeError

__all__ = ["FACES", "FontMissing", "Download", "font_cache_dir", "resolve", "user_cache_dir"]

_REPO = Path(__file__).resolve().parents[2]


class FontMissing(ForgeError):
    """No file for a face, and the open-licence fallback could not be fetched."""


def user_cache_dir(*parts: str) -> Path:
    """A per-user cache directory for zmforge, on any OS (not created).

    ``ZMFORGE_CACHE_DIR`` replaces the whole ``<os cache>/zmforge`` part.
    """
    named = os.environ.get("ZMFORGE_CACHE_DIR")
    if named:
        return Path(named).joinpath(*parts)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base.joinpath("zmforge", *parts)


def font_cache_dir() -> Path:
    """Where downloaded faces go: the checkout's assets-cache, else per-user."""
    named = os.environ.get("ZMFORGE_FONT_DIR")
    if named:
        return Path(named)
    if (_REPO / "pyproject.toml").is_file():
        return _REPO / "assets-cache" / "fonts"
    return user_cache_dir("fonts")


@dataclass(frozen=True)
class Download:
    """An OFL face fetched on first use: ``<cache>/<file>`` plus its licence."""

    file: str
    url: str
    licence_file: str
    licence_url: str


_GF = "https://github.com/google/fonts/raw/main/ofl/"


def _pt(folder: str, name: str) -> Download:
    return Download(f"{folder}/{name}", _GF + f"{folder}/{name}",
                    f"{folder}/OFL.txt", _GF + f"{folder}/OFL.txt")


_PT_SANS_BOLD = _pt("ptsans", "PT_Sans-Web-Bold.ttf")
_PT_SANS = _pt("ptsans", "PT_Sans-Web-Regular.ttf")
_PT_NARROW_BOLD = _pt("ptsansnarrow", "PT_Sans-Narrow-Web-Bold.ttf")
_PT_SERIF_BOLD = _pt("ptserif", "PT_Serif-Web-Bold.ttf")
_PT_SERIF = _pt("ptserif", "PT_Serif-Web-Regular.ttf")
_PT_SERIF_ITALIC = _pt("ptserif", "PT_Serif-Web-Italic.ttf")
_PT_MONO = _pt("ptmono", "PTM55FT.ttf")

#: job -> (candidate file names in preference order, OFL download).  The
#: first names are free faces (on Debian they come from the packages
#: fonts-liberation, fonts-urw-base35 and fonts-dejavu-core); then macOS /
#: Windows equivalents.
FACES: dict[str, tuple[tuple[str, ...], Download]] = {
    "sign": (("LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"), _PT_SANS_BOLD),
    "sign_narrow": (("NimbusSansNarrow-Bold.otf", "Arial Narrow Bold.ttf", "ARIALNB.TTF"),
                    _PT_NARROW_BOLD),
    "sign_light": (("LiberationSans-Regular.ttf", "Arial.ttf", "arial.ttf"), _PT_SANS),
    "serif": (("NimbusRoman-Bold.otf", "Times New Roman Bold.ttf", "timesbd.ttf"), _PT_SERIF_BOLD),
    "serif_light": (("NimbusRoman-Regular.otf", "Times New Roman.ttf", "times.ttf"), _PT_SERIF),
    "serif_italic": (("NimbusRoman-Italic.otf", "Times New Roman Italic.ttf", "timesi.ttf"),
                     _PT_SERIF_ITALIC),
    "book": (("URWBookman-Demi.otf", "BOOKOSB.TTF", "Georgia Bold.ttf", "georgiab.ttf"),
             _PT_SERIF_BOLD),
    "book_light": (("URWBookman-Light.otf", "BOOKOS.TTF", "Georgia.ttf", "georgia.ttf"), _PT_SERIF),
    "script": (("Z003-MediumItalic.otf", "Apple Chancery.ttf", "Zapfino.ttf", "GABRIOLA.TTF"),
               _PT_SERIF_ITALIC),
    "chancery": (("C059-Bold.otf", "CENSCBK.TTF", "Georgia Bold.ttf", "georgiab.ttf"),
                 _PT_SERIF_BOLD),
    "palatino": (("P052-Bold.otf", "Palatino.ttc", "palab.ttf"), _PT_SERIF_BOLD),
    "gothic": (("URWGothic-Demi.otf", "Avenir Next.ttc", "GOTHICB.TTF", "Century Gothic Bold.ttf"),
               _PT_SANS_BOLD),
    "typewriter": (("NimbusMonoPS-Bold.otf", "Courier New Bold.ttf", "courbd.ttf"), _PT_MONO),
    "typewriter_light": (("NimbusMonoPS-Regular.otf", "Courier New.ttf", "cour.ttf"), _PT_MONO),
    "stencil": (("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"), _PT_SANS_BOLD),
}


def _os_font_dirs() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        local = os.environ.get("LOCALAPPDATA")
        dirs = [windir / "Fonts"]
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
        return dirs
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"), home / "Library" / "Fonts"]
    data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
            data_home / "fonts", home / ".fonts"]


@lru_cache(maxsize=None)
def _index(root: str) -> dict[str, Path]:
    """Lower-cased file name -> first path found under *root*, recursively."""
    found: dict[str, Path] = {}
    base = Path(root)
    if not base.is_dir():
        return found
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            found.setdefault(name.lower(), Path(dirpath) / name)
    return found


def _find(name: str, roots: list[Path]) -> Path | None:
    for root in roots:
        hit = _index(str(root)).get(name.lower())
        if hit is not None:
            return hit
    return None


def _fetch(item: Download, cache: Path, kind: str) -> Path:
    target = cache / item.file
    for rel, url in ((item.file, item.url), (item.licence_file, item.licence_url)):
        dest = cache / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "zmforge"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
        except (urllib.error.URLError, OSError) as exc:
            raise FontMissing(
                f"no font for {kind!r} on this machine and could not download "
                f"{url} ({getattr(exc, 'reason', exc)}); go online once, or put "
                f"{Path(item.file).name} in {cache}"
            ) from None
        part = dest.with_name(dest.name + ".part")
        part.write_bytes(data)
        part.replace(dest)
    _index.cache_clear()
    return target


def resolve(kind: str, *, fetch: bool = True) -> Path:
    """The font file for job *kind*, fetching the OFL fallback if need be."""
    try:
        names, download = FACES[kind]
    except KeyError:
        raise KeyError(f"no face called {kind!r}; known: {', '.join(sorted(FACES))}") from None
    cache = font_cache_dir()
    roots = [cache, *_os_font_dirs()]
    for name in (*names, Path(download.file).name):
        hit = _find(name, roots)
        if hit is not None:
            return hit
    if not fetch:
        raise FontMissing(f"no font for {kind!r} on this machine (looked for "
                          f"{', '.join(names)})")
    return _fetch(download, cache, kind)
