"""Render-only copies of zmforge's kit props, so Radiant draws them in colour.

WHY [measured]: the kit
props (``zmf_prop_*``) draw black in Radiant although their gdt.db rows and
converted textures exist.  Every triangle corner in their exports carries
``COLOR 0 0 0 1`` (``props/xmodel.py``), and the colour map is multiplied by
it.  (``export2bin.exe`` does not convert under Wine: it writes the text
truncated, which Radiant draws as grey boxes, so a local rebuild is no way out.)

What this does: it reads each placed kit prop's Windows-built ``.XMODEL_BIN``
(``*LZ4*`` + size + one LZ4 block), sets the vertex colour records (chunk
0x6dd8 + RGBA bytes) from black to white, writes the copy to
``build-out/render/.radiant/propfix`` (cached by content hash), and returns
bind mounts that lay the copies over the originals in the render container
only.  The shared tools tree and the shipped models are never written.

``props/xmodel.py`` writes white vertex colours at the
source, so kit props it builds need nothing here (``prepare`` skips a
model with no black records).  This stays as the fallback for the ``.XMODEL_BIN``
files built before the fix, until the kit props are rebuilt.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

REPO = Path(__file__).resolve().parents[3]
CACHE = REPO / "build-out" / "render" / ".radiant" / "propfix"

_MATERIAL = re.compile(r'^MATERIAL\s+\d+\s+"([^"]+)"\s+"[^"]*"\s+"color_map:([^"]+)"', re.M)
_BLACK = "COLOR 0.000000 0.000000 0.000000 1.000000"
_WHITE = "COLOR 1.000000 1.000000 1.000000 1.000000"


def whiten(export_text: str) -> tuple[str, int]:
    """*export_text* with every per-corner vertex colour set to white.

    Only ``COLOR`` lines that follow a ``VERT`` line are vertex colours; the
    ``COLOR`` inside a ``MATERIAL`` block is the material's and stays.
    Returns ``(text, how many were changed)``.
    """
    out, changed, after_vert = [], 0, False
    for line in export_text.splitlines(keepends=True):
        s = line.strip()
        if s.startswith("VERT "):
            after_vert = True
        elif after_vert and s.startswith("COLOR "):
            after_vert = False
            if s == _BLACK:
                line = _WHITE + ("\n" if line.endswith("\n") else "")
                changed += 1
        elif s.startswith(("TRI ", "MATERIAL ", "NUMOBJECTS")):
            after_vert = False
        out.append(line)
    return "".join(out), changed


def color_maps(export_text: str) -> list[tuple[str, str]]:
    """``(material, colour map file name)`` of each material in an export."""
    return [(m.group(1), m.group(2)) for m in _MATERIAL.finditer(export_text)]


def tif_bits(path: Path) -> int | None:
    """Bits per sample of a ``.tif`` (8 or 16), or None if unreadable."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            bits = im.tag_v2.get(258)
    except (OSError, ImportError):
        return None
    if isinstance(bits, tuple):
        bits = bits[0]
    return int(bits) if bits else None


def find_export(tools: Path, model: str, overlay: Path | None = None) -> Path | None:
    """The kit prop's ``.XMODEL_EXPORT`` under ``model_export/zm*/``.

    *overlay* (a :func:`stage_current` tree) is looked in first: what the
    render will actually mount wins over the deployed copy.
    """
    for root in ([overlay] if overlay else []) + [tools]:
        base = root / "model_export"
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if sub.is_dir() and sub.name.lower().startswith("zm"):
                p = sub / f"{model}.XMODEL_EXPORT"
                if p.is_file() and (sub / f"{model}.XMODEL_BIN").is_file():
                    return p
    return None


def find_tif(tools: Path, name: str, overlay: Path | None = None) -> Path | None:
    for root in ([overlay] if overlay else []) + [tools]:
        base = root / "texture_assets"
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if sub.is_dir() and sub.name.lower().startswith("zm") and (sub / name).is_file():
                return sub / name
    return None


def _digest(path: Path, salt: str) -> str:
    h = hashlib.sha1(salt.encode())
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


@dataclass
class PropFix:
    models: list[str] = field(default_factory=list)       # whitened
    textures: list[str] = field(default_factory=list)     # promoted to 16 bit
    mounts: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    regenerated: list[str] = field(default_factory=list)  # from current props code
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"whitened_models": self.models, "16bit_textures": self.textures,
                "regenerated_textures": self.regenerated, "warnings": self.warnings,
                "errors": self.errors}


def plan(models: Iterable[str], tools: Path,
         overlay: Path | None = None) -> tuple[list[tuple[str, Path]], list[Path]]:
    """Which exports need whitening and which colour maps need 16 bits."""
    exports, tifs = [], []
    for model in sorted(set(models)):
        if not model.startswith("zmf_"):
            continue
        export = find_export(tools, model, overlay)
        if export is None:
            continue
        text = export.read_text(encoding="utf-8", errors="replace")
        if _BLACK in text and whiten(text)[1]:
            exports.append((model, export))
        for _mat, name in color_maps(text):
            tif = find_tif(tools, name, overlay)
            if tif is not None and tif not in tifs and tif_bits(tif) == 8:
                tifs.append(tif)
    return exports, tifs


def lz4_block_decompress(data: bytes, size: int) -> bytes:
    """Decode one raw LZ4 block (the format inside an ``*LZ4*`` model file)."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        token = data[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = data[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += data[i:i + lit]
        i += lit
        if i >= n:
            break
        offset = data[i] | (data[i + 1] << 8)
        i += 2
        mlen = token & 15
        if mlen == 15:
            while True:
                b = data[i]
                i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(out) - offset
        if offset <= 0 or start < 0:
            raise ValueError("bad LZ4 offset")
        for k in range(mlen):          # byte by byte: matches may overlap
            out.append(out[start + k])
    if len(out) != size:
        raise ValueError(f"LZ4 block gave {len(out)} bytes, header says {size}")
    return bytes(out)


def lz4_block_literals(payload: bytes) -> bytes:
    """*payload* as a valid LZ4 block of one literal run (no compression)."""
    n = len(payload)
    if n < 15:
        return bytes([n << 4]) + payload
    rest, ext = n - 15, bytearray()
    while rest >= 255:
        ext.append(255)
        rest -= 255
    ext.append(rest)
    return bytes([0xF0]) + bytes(ext) + payload


def read_model_bin(data: bytes) -> bytes:
    """The payload of an ``*LZ4*`` ``.XMODEL_BIN`` (magic, uint32 size, LZ4 block)."""
    if data[:5] != b"*LZ4*":
        raise ValueError("not an *LZ4* model file")
    size = int.from_bytes(data[5:9], "little")
    return lz4_block_decompress(data[9:], size)


def write_model_bin(payload: bytes) -> bytes:
    """An ``*LZ4*`` model file, compressed as ``export2bin.exe`` compresses it
    (:mod:`zmforge.props.lz4block`), so the file matches the one the mod tools write, byte for byte."""
    from ..props.lz4block import compress

    return b"*LZ4*" + len(payload).to_bytes(4, "little") + compress(payload)


#: In the binary model format each ``COLOR`` record is the chunk id 0x6dd8
#: (little endian, padded to 4 bytes) and then R, G, B, A as bytes.  Read off
#: zmf_prop_donut.XMODEL_BIN : 1081 records, 1080 per triangle
#: corner (360 triangles) and the material's own one after its name.
_COLOR_REC = b"\xd8\x6d\x00\x00"


def whiten_bin(data: bytes, materials: Iterable[str] = ()) -> tuple[bytes, int]:
    """A Windows-built ``.XMODEL_BIN`` with every black vertex colour made white.

    Records after the first material name (the material's own colour) are
    left alone.  Returns ``(new file bytes, records changed)``.
    """
    payload = bytearray(read_model_bin(data))
    stop = len(payload)
    for name in materials:
        at = payload.find(name.encode() + b"\x00")
        if at != -1:
            stop = min(stop, at)
    black, white = _COLOR_REC + b"\x00\x00\x00\xff", _COLOR_REC + b"\xff\xff\xff\xff"
    changed, i = 0, payload.find(black)
    while i != -1 and i < stop:
        payload[i:i + 8] = white
        changed += 1
        i = payload.find(black, i + 8)
    return write_model_bin(bytes(payload)), changed


def prepare(models: Iterable[str], *, tools: Path, cache: Path = CACHE,
            log: Callable[[str], None] = lambda s: None,
            overlay: Path | None = None) -> PropFix:
    """Make (or reuse) white-vertex copies of the map's kit props; return the mounts."""
    fix = PropFix()
    exports, _tifs = (plan(models, tools) if overlay is None else plan(models, tools, overlay))
    cache.mkdir(parents=True, exist_ok=True)
    for model, export in exports:
        src = export.with_suffix(".XMODEL_BIN")
        key = _digest(src, "white-bin-v1")
        done = cache / f"{model}-{key}.XMODEL_BIN"
        if not done.is_file():
            try:
                mats = [m for m, _ in color_maps(export.read_text(encoding="utf-8",
                                                                  errors="replace"))]
                data, n = whiten_bin(src.read_bytes(), mats)
            except (OSError, ValueError, IndexError) as exc:
                fix.errors.append(f"{model}: {exc}")
                continue
            if not n:
                continue
            tmp = done.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(done)
        fix.models.append(model)
        fix.mounts.append((str(done), f"/tools/{src.relative_to(tools).as_posix()}"))
    if fix.models:
        log(f"== {len(fix.models)} kit prop(s) drawn with white vertex colour: "
            f"{', '.join(fix.models)}")
    if fix.errors:
        log("!! " + "; ".join(fix.errors))
    return fix


def kit_materials(models: Iterable[str], tools: Path, overlay: Path | None = None) -> list[str]:
    """Material names the placed kit props' exports use."""
    out: list[str] = []
    for model in sorted(set(models)):
        if not model.startswith("zmf_"):
            continue
        export = find_export(tools, model, overlay)
        if export is None:
            continue
        for mat, _tif in color_maps(export.read_text(encoding="utf-8", errors="replace")):
            if mat not in out:
                out.append(mat)
    return out


def brush_materials(materials: Iterable[str]) -> dict[str, str]:
    """``material -> colour map .tif name`` for the brush surfaces the prop
    library makes (a :class:`~zmforge.props.library.PropMaterial` in a prop's
    ``extra_materials`` that names no mesh faces, such as the corn maze's
    ``zmf_corn_wall``) among *materials*, the brush materials a map uses.

    WHY [the corn-wall surface]: such a surface is written and
    registered exactly like a kit prop's (8-bit ``.tif``, ``lit_detail``, no
    normal map), so Radiant drew it as a flat blue-grey slab until the render
    gave it the same 16-bit copy and lit layout as the kit materials."""
    from ..props.library import PROPS

    known = {m.asset: f"{m.image_stem}.tif" for p in PROPS for m in p.extra_materials if not m.faces}
    return {m: known[m] for m in sorted(set(materials)) if m in known}


def _cells_of(palette, materials: Iterable[str]):
    """Boolean ``(size, size)`` mask of the atlas cells that hold *materials*."""
    import numpy as np

    mask = np.zeros((palette.size, palette.size), dtype=bool)
    cell = palette.size // palette.cells
    for m in materials:
        if m in palette.order:
            i = palette.order.index(m)
            r, c = divmod(i, palette.cells)
            mask[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell] = True
    return mask


def compare_atlas(old: bytes, new: bytes, size: int, recoloured) -> tuple[bool, int, int]:
    """Whether *new* keeps *old*'s layout: identical outside the *recoloured* mask.

    *old* and *new* are 8-bit RGB pixel bytes of a ``size`` x ``size`` atlas.
    Returns ``(layout matches, pixels differing outside the mask, inside)``.
    """
    import numpy as np

    a = np.frombuffer(old, dtype=np.uint8).reshape(size, size, 3)
    b = np.frombuffer(new, dtype=np.uint8).reshape(size, size, 3)
    diff = (a != b).any(axis=2)
    outside, inside = int((diff & ~recoloured).sum()), int((diff & recoloured).sum())
    return outside == 0, outside, inside


def regenerate(tif: Path, scratch: Path, *, palette_for=None) -> tuple[Path | None, str]:
    """The kit atlas *tif* rebuilt from the current props code, if it is safe to use.

    WHY [measured]: the tools-tree atlas only changes
    when the textures are redeployed, so a colour change in
    ``props/library.py`` (the corn's field-corn ``grass``) did not show in
    renders.  The models' UVs point at cells of the DEPLOYED atlas, so a
    rebuilt atlas is used only when every pixel outside the recoloured
    materials' cells is identical to the deployed one: colours may change,
    positions may not.  Returns ``(8-bit tif in scratch, why)``, or
    ``(None, why)`` to keep the tools-tree copy.  A layout mismatch reason
    starts with ``"layout"``.
    """
    from PIL import Image

    from ..props.library import KITS, PROPS

    kit = next((k for k in KITS.values() if f"{k.image_stem}.tif" == tif.name), None)
    if kit is None or kit.texture is not None:
        return None, "not a generated swatch atlas"
    if palette_for is None:
        from ..props.build import kit_palette

        def palette_for(slug):
            return kit_palette(slug, scratch / "_obj")
    palette = palette_for(kit.slug)
    recoloured = {m for p in PROPS if p.kit == kit.slug for m, _ in p.colours}
    with Image.open(tif) as im:
        if im.size != (palette.size, palette.size):
            return None, (f"layout differs: deployed {im.size[0]}x{im.size[1]}, "
                          f"current {palette.size}x{palette.size}")
        old = im.convert("RGB").tobytes()
    new = palette.pixels()
    same, outside, inside = compare_atlas(old, new, palette.size,
                                          _cells_of(palette, recoloured))
    if not same:
        return None, (f"layout differs: {outside} pixel(s) outside the recoloured cells "
                      f"({', '.join(sorted(recoloured)) or 'none'}) changed")
    if not inside:
        return None, "unchanged"
    from ..props.textures import write_tif

    scratch.mkdir(parents=True, exist_ok=True)
    out = write_tif(palette.size, palette.size, new, scratch / tif.name)
    return out, f"recoloured {inside} px ({', '.join(sorted(recoloured))})"


def _colour_type(path: Path) -> str:
    """ImageMagick ``-type`` for a 16-bit true-colour copy of *path*
    ("" when PIL cannot read it, which leaves ImageMagick's own choice)."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            alpha = "A" in im.getbands() or "transparency" in im.info
            return "TrueColorAlpha" if alpha else "TrueColor"
    except (OSError, ValueError):
        return ""


def needs_copy(path: Path) -> bool:
    """Whether Radiant under Wine needs a 16-bit true-colour copy of *path*:
    anything but a 16-bit RGB(A) source (see :func:`tif16_copies`)."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return not (tif_bits(path) == 16 and len(im.getbands()) >= 3)
    except (OSError, ValueError):
        return False


def tif16_copies(models: Iterable[str], *, tools: Path, image: str, cache: Path = CACHE,
                 log: Callable[[str], None] = lambda s: None,
                 current: bool = True, overlay: Path | None = None,
                 brush_tifs: Iterable[str] = (),
                 stock_tifs: Iterable[Path] = ()) -> PropFix:
    """16-bit deflate copies of the placed kit props' 8-bit colour maps, as mounts.
    *brush_tifs* adds the colour maps of library brush surfaces
    (:func:`brush_materials`) by file name; *stock_tifs* the stock images the
    map's materials and models use (:func:`zmforge.render.assets.stock_images`),
    of which every one that is not 16-bit RGB(A) gets a copy too.

    WHY [measured, two otherwise identical renders]:
    Radiant's image converter wrote no cache entry for an 8-bit uncompressed
    ``.tif`` (what ``props/textures.py`` writes), and did for the same pixels
    as 16-bit deflate, the format of the stock ``t7_*`` sources.  The copies
    are made with ImageMagick in the render image (*image*), cached by
    content hash, and mounted over the originals in the render container
    only.  The shipped textures are untouched.
    """
    import subprocess

    fix = PropFix()
    _exports, tifs = (plan(models, tools) if overlay is None else plan(models, tools, overlay))
    for name in brush_tifs:
        tif = find_tif(tools, name, overlay)
        if tif is not None and tif not in tifs and tif_bits(tif) == 8:
            tifs.append(tif)
    stock = []
    for tif in stock_tifs:
        tif = Path(tif)
        if (tif.is_file() and tif not in tifs and tif.is_relative_to(tools)
                and needs_copy(tif)):
            tifs.append(tif)
            stock.append(tif)
    if not tifs:
        return fix
    cache.mkdir(parents=True, exist_ok=True)
    regen = cache / "regen"
    todo = []
    for tif in tifs:
        # (host file, path inside the converter container, cache salt)
        staged = overlay is not None and tif.is_relative_to(overlay)
        root = overlay if staged else tools
        rel = tif.relative_to(root).as_posix()  # type: ignore[arg-type]
        src, inside, salt = tif, f"/{'overlay' if staged else 'tools'}/{rel}", "16bit-zip-v1"
        if current and not staged and tif not in stock:
            try:
                made, why = regenerate(tif, regen)
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                made, why = None, f"could not rebuild ({exc})"
            if made is not None:
                src, inside, salt = made, f"/regen/{made.name}", "16bit-zip-regen-v1"
                fix.regenerated.append(tif.name)
                log(f"== {tif.name}: rendered from the current props code, {why}")
            elif why != "unchanged" and why != "not a generated swatch atlas":
                fix.warnings.append(f"{tif.name}: {why}; rendering the deployed "
                                    "tools-tree colours instead")
        # Radiant under Wine converted only 16-bit RGB(A) sources (
        # 8-bit RGB failed, ImageMagick's one-channel grey copy of a flat-grey
        # RGB failed, and a stock 16-bit grey mask failed), so every copy is
        # written as 16-bit true colour.
        kind = _colour_type(src)
        salt += kind
        done = cache / f"{tif.stem}-{_digest(src, salt)}.tif"
        if not done.is_file():
            todo.append((inside, done, kind))
        fix.textures.append(tif.name)
        fix.mounts.append((str(done), f"/tools/{rel}"))
    for w in fix.warnings:
        log(f"!! WARNING {w}")
    if todo:
        work = cache / "work16"
        work.mkdir(parents=True, exist_ok=True)
        regen.mkdir(parents=True, exist_ok=True)
        # "; " not "&&": one bad source must not stop the rest (each result is
        # checked below); a first stock pass is a few hundred files.
        script = " ; ".join(f"convert {t} -depth 16{' -type ' + k if k else ''} -compress zip "
                            f"/work/{d.name}" for t, d, k in todo)
        run = subprocess.run(["docker", "run", "--rm", "--entrypoint", "sh",
                              "-v", f"{tools}:/tools:ro", "-v", f"{regen.resolve()}:/regen:ro",
                              *(["-v", f"{overlay.resolve()}:/overlay:ro"] if overlay else []),
                              "-v", f"{work.resolve()}:/work",
                              image, "-c", script], capture_output=True, text=True, timeout=3600)
        for _t, d, _k in todo:
            made = work / d.name
            if made.is_file() and tif_bits(made) == 16:
                made.replace(d)
            else:
                fix.errors.append(f"{d.name}: not converted ({run.stderr[-200:].strip()})")
    fix.mounts = [(h, c) for h, c in fix.mounts if Path(h).is_file()]
    if fix.textures:
        log(f"== {len(fix.mounts)} texture(s) given 16-bit copies for the render "
            f"({len(stock)} of them stock)")
    if fix.errors:
        log("!! " + "; ".join(fix.errors))
    return fix


def opted_in(models: Iterable[str]):
    """The placed library props that do not use their kit's shared material
    and atlas: a per-prop material, or a mesh that is not a kit ``.obj``."""
    from ..props.library import KITS, PROPS

    placed = set(models)
    return [p for p in PROPS if p.name in placed
            and (p.material is not None or KITS[p.kit].kind != "zip")]


#: The model and texture folder the prop install step installs the kit props
#: into; a staged prop goes where its installed row points.
DEPLOYED_DIR = "zm_forge_gate"
STAGED_GDT = "zmf_render_current_props"


def stage_current(models: Iterable[str], *, tools: Path, cache: Path = CACHE,
                  log: Callable[[str], None] = lambda s: None) -> tuple[Path | None, PropFix]:
    """Build the placed opted-in props from the current code, for the render only.

    WHY: a new or changed ``zmf_`` prop has a current ``.XMODEL_BIN`` only once
    the Windows tools' ``export2bin`` writes one, and ``export2bin.exe`` does
    not run under Wine, so a render under Wine shows the old model or none.
    This builds :func:`opted_in` props with ``props.build`` into a cached
    tree laid out like the tools tree, writes each ``.XMODEL_BIN`` with
    :mod:`zmforge.props.xmodel_bin` (byte-identical to the Windows tools'
    output on every installed kit export), and returns ``(tree, mounts)``: the
    binaries mounted where the installed rows point.  The tree's ``.gdt`` files
    are renamed :data:`STAGED_GDT` so registering them (``assets.
    register_current_props``) cannot replace the installed kit's rows.
    Nothing is written to the tools tree.
    """
    import shutil

    from ..props.build import build
    from ..props.xmodel_bin import export_to_bin

    fix = PropFix()
    chosen = opted_in(models)
    if not chosen:
        return None, fix
    staging = cache / "current"
    tmp = staging / "_building"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        build(DEPLOYED_DIR, tmp, chosen, work=staging / "_obj")
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        fix.errors.append(f"current props: {exc}")
        log(f"!! could not build the current props for the render ({exc})")
        return None, fix
    h = hashlib.sha1(b"current-v1")
    for f in sorted(p for p in tmp.rglob("*") if p.is_file() and p.suffix != ".json"):
        h.update(f.relative_to(tmp).as_posix().encode())
        h.update(f.read_bytes())
    root = staging / h.hexdigest()[:16]
    if not root.is_dir():
        model_dir = tmp / "model_export" / DEPLOYED_DIR
        for export in sorted(model_dir.glob("*.XMODEL_EXPORT")):
            export.with_suffix(".XMODEL_BIN").write_bytes(
                export_to_bin(export.read_text(encoding="utf-8")))
        for sub, suffix in (("model_export", "_props"), ("texture_assets", "_props_tex")):
            gdt = tmp / sub / f"{DEPLOYED_DIR}{suffix}.gdt"
            if gdt.is_file():
                gdt.rename(tmp / sub / f"{STAGED_GDT}{suffix.replace('_props', '')}.gdt")
        tmp.rename(root)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    for binary in sorted((root / "model_export" / DEPLOYED_DIR).glob("*.XMODEL_BIN")):
        fix.models.append(binary.stem)
        fix.mounts.append((str(binary), f"/tools/model_export/{DEPLOYED_DIR}/{binary.name}"))
    log(f"== {len(chosen)} prop(s) rendered from the current props code: "
        f"{', '.join(p.name for p in chosen)}")
    return root, fix
