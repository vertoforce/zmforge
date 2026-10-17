"""What a mod tools install can actually resolve.

A shipped map source is not proof that an asset exists: ``zm_giant.map``
places ``zombie_sign_please_wait`` and a stock install neither declares nor
compiles it (cod2map64: ``Missing xmodel 'zombie_sign_please_wait'``).  The only authority is the compiler, so the ledger beside this
module records, measured with a probe map compiled by the mod tools:

* ``misc_model_ok`` / ``misc_model_missing`` -- names a throwaway probe map
  placed as ``misc_model`` and what cod2map64 said about each;
* ``xmodels_declared`` -- every name declared by a ``.gdt`` on the install
  (a subset of what the compiler resolves: stock assets such as
  ``p7_zm_der_chainlink_fence_post_cap`` compile without a GDT line);
* ``xmodels_local`` -- every xmodel the GDTs of the configured tools install declare,
  which includes the models zmforge converts itself (``zmf_prop_*``), which
  a stock install does not declare; kept apart from ``xmodels_declared`` so
  a refresh or ``--check`` compares a stock install with a stock install
  (:func:`scan_declared_xmodels`);
* ``prefabs`` -- every ``.map`` under ``map_source/_prefabs``;
* ``xmodels_unlinkable`` -- GDT-declared models whose ``.xmodel_bin`` files
  (LODs or bullet collision) are absent from the configured tools install's
  ``model_export``, mapped to the first missing file.  cod2map64 compiles
  them, then the linker stops: ``Could not find xmodel file:
  t7_props\\p7_desk_metal_military_03\\p7_desk_metal_military_03_tablet_col.XMODEL_BIN``
  (zm_dmv and a test map; ``p6_bar_beer_glass`` on corn maze),
  or whose material's colour or normal image is declared but absent
  (``p7_foliage_grass_dry_03``, corn maze).  Measured by :func:`scan_unlinkable` (``scripts/scan-local-tools.py``,
  which scans a local mod tools folder).

Names are identifiers; the ledger carries no game content.  A missing ledger
is not an error, only a lost check, so a checkout without a mod tools install
still verifies everything else.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..localtools import tools_dir as _local_tools_dir
from ..materials import PLACEHOLDER_IMAGES

__all__ = [
    "LEDGER_PATH",
    "InstalledAssets",
    "load_ledger",
    "judge_misc_model",
    "scan_unlinkable",
    "bin_materials",
    "tiff_layout",
    "UNREADABLE_TIFF",
    "DEFAULT_LOCAL_TOOLS",
]

#: The local mod tools copy builds link with; ``ZMFORGE_WINE_TOOLS`` overrides
#: it (:mod:`zmforge.localtools`).
DEFAULT_LOCAL_TOOLS = _local_tools_dir()

LEDGER_PATH = Path(__file__).with_name("installed_assets.json")


@dataclass(frozen=True, slots=True)
class InstalledAssets:
    measured: str
    tools_installed: str
    misc_model_ok: frozenset[str]
    misc_model_missing: frozenset[str]
    xmodels_declared: frozenset[str]
    prefabs: frozenset[str]
    xmodels_unlinkable: dict[str, str] = field(default_factory=dict)
    local_tools_measured: str = ""
    xmodels_local: frozenset[str] = frozenset()

    def has_prefab(self, path: str) -> bool:
        return path.replace("\\", "/") in self.prefabs


def load_ledger(path: Path = LEDGER_PATH) -> InstalledAssets | None:
    """The ledger, or ``None`` when it has not been measured."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return InstalledAssets(
        measured=str(raw.get("measured", "")),
        tools_installed=str(raw.get("tools_installed", "")),
        misc_model_ok=frozenset(raw.get("misc_model_ok", ())),
        misc_model_missing=frozenset(raw.get("misc_model_missing", ())),
        xmodels_declared=frozenset(raw.get("xmodels_declared", ())),
        prefabs=frozenset(raw.get("prefabs", ())),
        xmodels_unlinkable=dict(raw.get("xmodels_unlinkable", {})),
        local_tools_measured=str(raw.get("local_tools_measured", "")),
        xmodels_local=frozenset(raw.get("xmodels_local", ())),
    )


def judge_misc_model(name: str, ledger: InstalledAssets) -> str:
    """``"ok"``, ``"missing"``, ``"unlinkable"`` or ``"unverified"`` for a
    ``misc_model`` name.

    ``missing`` is the compiler's own word.  ``unlinkable`` means a GDT
    declares it but the install lacks one of its model files, so the
    linker fails after a full compile and bake.  ``unverified`` means neither
    the probe nor any GDT knows the name: it may well exist, and the ledger
    should be refreshed with the name before the map is built.
    """
    if name in ledger.misc_model_missing:
        return "missing"
    if name in ledger.xmodels_unlinkable:
        return "unlinkable"
    if name in ledger.misc_model_ok or name in ledger.xmodels_declared or name in ledger.xmodels_local:
        return "ok"
    return "unverified"


# One xmodel entry of a GDT: ``\t"name" ( "xmodel.gdf" )\n\t{ ... \n\t}``.
_GDT_XMODEL = re.compile(
    r'^\t"([^"]+)"\s*\(\s*"xmodel\.gdf"\s*\)\s*\n\t\{(.*?)^\t\}', re.S | re.M
)
_GDT_FIELD = re.compile(r'"(\w+)"\s+"([^"]*)"')
#: Each LOD file field, with the distance and autogen fields that decide
#: whether the linker reads it.  A LOD at distance 0 is unused, and an
#: autogen LOD is reduced from lod0 ("Converting xmesh ..._lod0 (Desired
#: Faces: 2254)"): ``p7_crate_plastic_tech_02`` names an absent lod4 file
#: with ``lod4Dist 0`` and linked (a test map).
_LOD_FIELDS = {
    "mediumLod": ("mediumLodDist", "autogenMediumLod"),
    "lowLod": ("lowLodDist", "autogenLowLod"),
    "lowestLod": ("lowestLodDist", "autogenLowestLod"),
    **{f"lod{n}File": (f"lod{n}Dist", f"autogenLod{n}") for n in range(4, 8)},
}


def _norm(path: str) -> str:
    return re.sub(r"[\\/]+", "/", path).lower()


def _files_the_linker_reads(fields: dict[str, str]) -> list[str]:
    """The ``.xmodel_bin`` paths one GDT xmodel entry makes the linker open:
    ``filename`` always, ``BulletCollisionFile`` when the collision LOD is
    ``Custom`` (the tablet's missing ``_col`` stopped zm_dmv), and each
    hand-made LOD that is in use (non-zero distance, not autogenerated)."""
    out = []
    if fields.get("filename"):
        out.append(fields["filename"])
    col = fields.get("BulletCollisionFile")
    if col and fields.get("BulletCollisionLOD", "Custom") == "Custom":
        out.append(col)
    for key, (dist, autogen) in _LOD_FIELDS.items():
        path = fields.get(key)
        if not path:
            continue
        try:
            used = float(fields.get(dist, "0") or 0.0) > 0.0
        except ValueError:
            used = True
        if used and fields.get(autogen, "0") != "1":
            out.append(path)
    return [f for f in out if f.lower().endswith(".xmodel_bin")]


#: Any asset entry of a GDT: ``"name" ( "type.gdf" )`` or a derived one,
#: ``"name" [ "parent" ]``, which takes its parent's type and fields and
#: overrides some (``mtl_p7_foliage_grass_tussock_dry`` derives from
#: ``mtl_p7_foliage_grass_tussock`` and keeps its images).
_GDT_ENTRY = re.compile(
    r'^\t"([^"]+)"\s*(?:\(\s*"(\w+)\.gdf"\s*\)|\[\s*"([^"]+)"\s*\])\s*\n\t\{(.*?)^\t\}',
    re.S | re.M,
)
#: The material fields every lit material type samples.  Which of the other
#: image fields the linker loads depends on the material type's techset: a
#: ``lit_decal_diffuse_spec_gloss`` material names an absent
#: ``alphaRevealMap`` and links (``t7_zm_decal_logo_935_metal``, on the stock
#: buy door, in every map), a ``lit_detail`` one an absent ``specColorMap``
#: (the magic box lid).  So only these two are checked: the grass tussock
#: link stopped on its ``colorMap`` and ``normalMap``.
_MATERIAL_BASE_MAPS = ("colorMap", "normalMap")
#: The MATERIAL chunk of an ``.XMODEL_BIN`` payload: id ``0xA700``, a uint16
#: index, then the material name, NUL-padded to 4 bytes
#: (:mod:`zmforge.props.xmodel_bin` writes the same layout).
_MATERIAL_CHUNK = b"\x00\xa7"


#: TIFF layouts ``(bits per sample, samples per pixel)`` the linker rejects
#: with ``(image ....tif) format not supported`` and then ``image '...' is
#: missing``.  Measured, not guessed: of the colour and normal images the
#: local GDTs declare, every layout but this one has images the linker
#: converted (``share/assetconvert/image/v29``: 16-bit grey 369, RGB 767,
#: RGBA 188, 8-bit grey+alpha 1), and the one 16-bit grey+alpha file in the
#: stock tools, ``p7_rebar_cap_01_rusty_c.tif`` (``p7_rebar_column_128``),
#: stopped a test map link.  Layouts no link has
#: tried yet (JPEG-compressed, five samples) are not listed: unmeasured.
UNREADABLE_TIFF: dict[tuple[int, int], str] = {(16, 2): "16-bit grey+alpha"}


def tiff_layout(path: Path) -> tuple[int, int] | None:
    """``(bits per sample, samples per pixel)`` of a TIFF's first image, or
    ``None`` for a file that is absent or not a classic TIFF."""
    import struct

    try:
        with open(path, "rb") as f:
            head = f.read(8)
            order = {b"II": "<", b"MM": ">"}.get(head[:2])
            if order is None or struct.unpack(order + "H", head[2:4])[0] != 42:
                return None
            f.seek(struct.unpack(order + "I", head[4:8])[0])
            count = struct.unpack(order + "H", f.read(2))[0]
            entries = f.read(12 * count)
            bits, samples = 1, 1
            for i in range(0, len(entries) - 11, 12):
                tag, kind, n = struct.unpack(order + "HHI", entries[i:i + 8])
                if tag not in (258, 277):
                    continue
                if kind == 3 and n <= 2:
                    value = struct.unpack(order + "H", entries[i + 8:i + 10])[0]
                elif kind == 3:  # one short per sample, stored elsewhere
                    here = f.tell()
                    f.seek(struct.unpack(order + "I", entries[i + 8:i + 12])[0])
                    value = struct.unpack(order + "H", f.read(2))[0]
                    f.seek(here)
                elif kind == 4 and n == 1:
                    value = struct.unpack(order + "I", entries[i + 8:i + 12])[0]
                else:
                    continue
                if tag == 258:
                    bits = value
                else:
                    samples = value
            return bits, samples
    except (OSError, struct.error):
        return None


def _bin_payload(data: bytes) -> bytes:
    """The decompressed payload of an ``*LZ4*`` model file, or ``b""``."""
    if data[:5] != b"*LZ4*" or len(data) < 9:
        return b""
    size = int.from_bytes(data[5:9], "little")
    try:
        import lz4.block  # optional and fast; the pure decoder below is exact

        return lz4.block.decompress(data[9:], uncompressed_size=size)
    except ImportError:
        from ..render.propfix import lz4_block_decompress

        return lz4_block_decompress(data[9:], size)
    except Exception:  # noqa: BLE001 -- a damaged file names no material
        return b""


def bin_materials(data: bytes) -> list[str]:
    """The material names an ``.XMODEL_BIN`` file's MATERIAL chunks carry."""
    payload = _bin_payload(data)
    out: list[str] = []
    for i in range(0, len(payload) - 8, 4):
        if payload[i:i + 2] == _MATERIAL_CHUNK:
            end = payload.find(b"\x00", i + 4)
            name = payload[i + 4:end].decode("ascii", "replace") if end > i + 4 else ""
            if name and re.fullmatch(r"[\w/.-]+", name) and name not in out:
                out.append(name)
    return out


class _CaseInsensitiveFiles:
    """``exists(rel)`` for a Windows path under *root*, as Wine resolves it
    (case-insensitively); each directory is listed once."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._dirs: dict[str, dict[str, str] | None] = {}

    def _listing(self, rel: str) -> dict[str, str] | None:
        if rel not in self._dirs:
            if rel == "":
                real: Path | None = self.root
            else:
                parent, _, leaf = rel.rpartition("/")
                up = self._listing(parent)
                real = (self.root / self._real(parent) / up[leaf]) if up and leaf in up else None
            try:
                if real is not None and real.is_dir():
                    with os.scandir(real) as it:
                        self._dirs[rel] = {e.name.lower(): e.name for e in it}
                else:
                    self._dirs[rel] = None
            except OSError:
                self._dirs[rel] = None
        return self._dirs[rel]

    def _real(self, rel: str) -> str:
        if rel == "":
            return ""
        parent, _, leaf = rel.rpartition("/")
        return str(Path(self._real(parent)) / (self._listing(parent) or {}).get(leaf, leaf))

    def exists(self, path: str) -> bool:
        rel = _norm(path).strip("/")
        parent, _, leaf = rel.rpartition("/")
        listing = self._listing(parent)
        return bool(listing) and leaf in listing


def _gdt_entries(tools_root: Path):
    """``(name, kind, parent, fields)`` of every asset entry of every GDT."""
    for gdt in sorted(Path(tools_root).rglob("*.gdt")):
        try:
            text = gdt.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        except OSError:
            continue
        for m in _GDT_ENTRY.finditer(text):
            yield m.group(1), m.group(2), m.group(3), dict(_GDT_FIELD.findall(m.group(4)))


def scan_declared_xmodels(tools_root: Path) -> set[str]:
    """Every xmodel name a ``.gdt`` under *tools_root* declares.

    The probe records the stock install's own declarations; a mod tools
    folder zmforge has built into also carries the models zmforge converts
    itself (``zmf_prop_*``, :mod:`zmforge.props`), which no stock install
    declares.  ``scripts/scan-local-tools.py`` records them as
    ``xmodels_local`` so Z13 stops calling a converted model unverified.
    """
    return {name for name, kind, _parent, _fields in _gdt_entries(tools_root) if kind == "xmodel"}


def scan_unlinkable(tools_root: Path) -> dict[str, str]:
    """Every xmodel a ``.gdt`` under *tools_root* declares that the linker
    cannot build from the files under *tools_root*, mapped to the first missing file
    (``/``-separated):

    * one of its ``.xmodel_bin`` files (those :func:`_files_the_linker_reads`)
      is not under ``model_export``; or
    * a material it uses (named in its model files, or a ``skinOverride``
      target) is declared with a colour or normal image
      (:data:`_MATERIAL_BASE_MAPS`) whose ``baseImage`` file is absent.
      The value is then ``"<material>: <image file>"``.
      ``p7_foliage_grass_dry_03`` skins ``mtl_p7_foliage_grass_tussock_dry``,
      whose tussock images the install lacks, so a map placing it fails to
      link with ``image 'i_mtl_p7_foliage_grass_tussock_dry_c' is missing``.
    * a material it uses names a placeholder colour or normal image
      (:data:`zmforge.materials.PLACEHOLDER_IMAGES`).  It links, and the game
      draws it magenta with DELETE lettering: ``p7_desk_metal_old_01`` uses
      only ``mtl_p_ger_metal_desk``, colorMap ``deleteme`` (zm_cemetery shed
      desk).  The value is then
      ``"<material>: placeholder image '<image>'"``.
    * a material it uses names a colour or normal image whose TIFF has a
      layout the linker cannot read (:data:`UNREADABLE_TIFF`):
      ``p7_rebar_column_128`` skins ``p7_rebar_cap_01_rusty_c.tif``, 16-bit
      grey+alpha, and a test map link stopped with ``format not
      supported``.

    Materials and images no GDT declares are the stock ones the tools ship
    compiled (``i_mtl_p7_foliage_grass_dry_g`` is in no GDT and linked), so
    only declared ones are checked.  The GDT's paths are Windows paths (models
    ``model_export``-relative, images tools-relative); Wine resolves them
    case-insensitively, so the comparison is too.  A name declared twice is
    unlinkable only if no declaration is whole."""
    tools_root = Path(tools_root)
    export = tools_root / "model_export"
    present: set[str] = set()
    for dirpath, _dirs, files in os.walk(export):
        rel = _norm(os.path.relpath(dirpath, export))
        prefix = "" if rel == "." else rel + "/"
        present.update(prefix + f.lower() for f in files)
    files = _CaseInsensitiveFiles(tools_root)

    declared: dict[str, tuple[str | None, str | None, dict[str, str]]] = {}
    xmodels: list[tuple[str, dict[str, str]]] = []
    for name, kind, parent, fields in _gdt_entries(tools_root):
        declared.setdefault(name, (kind, parent, fields))
        if kind == "xmodel":
            xmodels.append((name, fields))

    def resolved(name: str) -> tuple[str | None, dict[str, str]]:
        chain, seen = [], set()
        while name in declared and name not in seen:
            seen.add(name)
            kind, parent, fields = declared[name]
            chain.append(fields)
            if kind is not None:
                merged: dict[str, str] = {}
                for f in reversed(chain):
                    merged.update(f)
                return kind, merged
            name = parent or ""
        return None, {}

    material_verdict: dict[str, str] = {}

    def missing_image(material: str) -> str:
        if material not in material_verdict:
            kind, fields = resolved(material)
            verdict = ""
            if kind == "material":
                for value in (fields.get(k, "") for k in _MATERIAL_BASE_MAPS):
                    if value.lower() in PLACEHOLDER_IMAGES:
                        # Links, then draws magenta with DELETE lettering.
                        verdict = f"{material}: placeholder image '{value}'"
                        break
                    ikind, ifields = resolved(value) if value in declared else (None, {})
                    base = ifields.get("baseImage", "") if ikind == "image" else ""
                    if base and not files.exists(base):
                        verdict = material + ": " + re.sub(r"[\\/]+", "/", base)
                        break
                # Any image field, not only the base maps: the unreadable
                # rebar cap image is a lit_micro_tiled_macro_color
                # material's ``colorMap00`` (its ``colorMap`` is
                # ``$white_diffuse``).  An unloaded field can only make this
                # refuse a model that would link, never let a broken one by.
                for value in fields.values() if not verdict else ():
                    ikind, ifields = resolved(value) if value in declared else (None, {})
                    base = ifields.get("baseImage", "") if ikind == "image" else ""
                    layout = tiff_layout(tools_root / files._real(_norm(base).strip("/"))) if base else None
                    if layout in UNREADABLE_TIFF:
                        shown = re.sub(r"[\\/]+", "/", base)
                        verdict = f"{material}: {shown} is a {UNREADABLE_TIFF[layout]} TIFF the linker cannot read"
                        break
            material_verdict[material] = verdict
        return material_verdict[material]

    bins: dict[str, list[str]] = {}

    def materials_of(paths: list[str], fields: dict[str, str]) -> list[str]:
        out: list[str] = []
        for p in paths:
            key = _norm(p)
            if key not in bins:
                try:
                    bins[key] = bin_materials((export / key).read_bytes()) if (export / key).is_file() \
                        else bin_materials(_read_ci(export, key))
                except OSError:
                    bins[key] = []
            out += [m for m in bins[key] if m not in out]
        # "from to" pairs, one per line; the GDT writes the line breaks as
        # the two characters backslash-r backslash-n.
        for name in re.split(r"(?:\\+[rn]|\s)+", fields.get("skinOverride", "")):
            if name and name not in out:
                out.append(name)
        return out

    broken: dict[str, str] = {}
    whole: set[str] = set()
    for name, fields in xmodels:
        reads = _files_the_linker_reads(fields)
        missing = [f for f in reads if _norm(f) not in present]
        if missing:
            broken.setdefault(name, re.sub(r"[\\/]+", "/", missing[0]))
            continue
        bad = next((v for v in map(missing_image, materials_of(reads, fields)) if v), "")
        if bad:
            broken.setdefault(name, bad)
        else:
            whole.add(name)
    return {k: v for k, v in sorted(broken.items()) if k not in whole}


def _read_ci(export: Path, key: str) -> bytes:
    """Read a ``model_export`` file named case-insensitively (*key* is lower)."""
    here = export
    for part in key.split("/"):
        with os.scandir(here) as it:
            match = next((e for e in it if e.name.lower() == part), None)
        if match is None:
            raise OSError(key)
        here = Path(match.path)
    return here.read_bytes()
