"""Make a render show zmforge's own materials and models, not black.

WHY.  Radiant draws a material only if the asset database (``gdtdb/gdt.db``)
has a row for it; the ``.gdt`` text beside the textures is only that
database's input (see :mod:`zmforge.texture.gdtdb`).  ``gdtdb.exe`` does not
run under Wine, so a zmforge texture, wall-art panel or kit prop whose
``.gdt`` was written but never registered draws black in the editor.

HOW, without touching the shared tools tree.  The render gets a *private copy*
of ``gdt.db`` (bind-mounted over ``/tools/gdtdb/gdt.db`` in the render
container only) and every ``.gdt`` zmforge wrote for this map is registered
into that copy with :func:`zmforge.texture.gdtdb.register_gdt`, the same SQL
your build script uses before a link.  The ``.gdt`` files and the
images they name are bind-mounted at the Windows paths the rows point at, so
the shared tree gains nothing.  Radiant converts the images on first sight
(its converted-image cache under ``share/assetconvert`` is shared, as it
already is for every model it converts).

Where the ``.gdt`` files come from, in order: the render's own generated tree
(``gen/``), the recipe's staging tree under :data:`STAGING_ROOT` (set with
``ZMFORGE_STAGING_ROOT``; a recipe's staged art is written there), and
``.gdt`` files already in the shared tools tree that the shared ``gdt.db`` never took
in.  Only files that declare a name the map uses and the database lacks are
registered.

``gdt.db`` needs a SQLite built with a wide column limit (``assets-cache/
sqlite-wide``); the database work runs in a child process with it preloaded
(:func:`run_wide`), as ``texture.hud_icons`` does.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

REPO = Path(__file__).resolve().parents[3]
WIDE = REPO / "assets-cache" / "sqlite-wide" / "libsqlite3.so.0"
STAGING_ROOT = Path(os.environ.get("ZMFORGE_STAGING_ROOT", "build-out/staging"))
WIN_ROOT = r"C:\Program Files (x86)\Steam\steamapps\common\Call of Duty Black Ops III 455130"

_FACE = re.compile(r"^\s*(?:\([^)]*\)\s*){3}(\S+)")
_MODEL = re.compile(r'^"model"\s+"([^"]+)"', re.M)
_GDT_HEAD = re.compile(r'^\s*"([^"]+)"\s*\(\s*"([^"]+)"\s*\)', re.M)
_BASE_IMAGE = re.compile(r'^\s*"(baseImage|colorMap|normalMap|specColorMap|glossMap)"\s*"([^"]+)"',
                         re.M)


def used_assets(map_text: str) -> tuple[set[str], set[str]]:
    """``(materials, models)`` the map names; prefab references are not models."""
    materials = set()
    lines = map_text.splitlines()
    for i, line in enumerate(lines):
        m = _FACE.match(line)
        if m:
            materials.add(m.group(1))
        elif line.strip() in ("mesh", "curve") and i + 2 < len(lines):
            # iwmap patch: "mesh", "{", then the material on its own line.
            name = lines[i + 2].strip()
            if name and " " not in name:
                materials.add(name)
    models = {m for m in _MODEL.findall(map_text) if not m.startswith("_prefabs")
              and not m.endswith(".map")}
    return materials, models


def gdt_declares(path: Path) -> set[str]:
    try:
        return {m.group(1) for m in _GDT_HEAD.finditer(path.read_text(encoding="utf-8",
                                                                      errors="replace"))}
    except OSError:
        return set()


def candidate_roots(gen: Path | None, recipe: str | None, tools: Path) -> list[Path]:
    roots = [p for p in (gen,) if p]
    if recipe:
        roots += [STAGING_ROOT / f"zmforge-{recipe}", STAGING_ROOT / f"zmforge-{recipe.replace('_', '-')}"]
    roots.append(tools)
    return [r for r in roots if r and r.is_dir()]


def find_gdts(names: Iterable[str], roots: Sequence[Path]) -> list[tuple[Path, Path]]:
    """``(root, gdt file)`` for every zmforge ``.gdt`` under *roots* declaring one of *names*.

    The shared tools tree is large, so only its ``texture_assets`` and
    ``model_export`` top level and ``zm*``/``zmf*``/``zmforge*`` folders are
    searched; the first root that declares a name wins.
    """
    want = set(names)
    found: list[tuple[Path, Path]] = []
    seen_rel: set[str] = set()
    for root in roots:
        for top in ("texture_assets", "model_export"):
            base = root / top
            if not base.is_dir():
                continue
            files = list(base.glob("*.gdt"))
            for sub in base.iterdir():
                if sub.is_dir() and sub.name.lower().startswith(("zm", "zmf", "zmforge")):
                    files += list(sub.rglob("*.gdt"))
            for gdt in sorted(files):
                rel = gdt.relative_to(root).as_posix().lower()
                if rel in seen_rel:
                    continue
                hits = gdt_declares(gdt) & want
                if hits:
                    found.append((root, gdt))
                    seen_rel.add(rel)
                    want -= hits
    return found


def gdt_sources(gdt: Path, root: Path) -> list[Path]:
    """Files a ``.gdt`` points at (images, model exports), relative to *root*, that exist."""
    text = gdt.read_text(encoding="utf-8", errors="replace")
    out = []
    for value in re.findall(r'"([^"]+\.(?:tif|tiff|png|tga|dds|xmodel_export|xmodel_bin))"', text,
                            flags=re.I):
        rel = Path(value.replace("\\", "/"))
        if (root / rel).is_file():
            out.append(rel)
    return out


# ----------------------------------------------------------------------
# Database work: runs in a child with the wide SQLite preloaded.
# ----------------------------------------------------------------------
def run_wide(command: dict) -> dict:
    """Run :func:`_child` in a Python with the wide-column SQLite preloaded."""
    if not WIDE.exists():
        raise RuntimeError(f"{WIDE} is missing; build it once with scripts/asset-setup.py --build-sqlite")
    env = dict(os.environ)
    env["LD_PRELOAD"] = f"{WIDE}:{env['LD_PRELOAD']}" if env.get("LD_PRELOAD") else str(WIDE)
    done = subprocess.run([sys.executable, "-m", "zmforge.render.assets"], input=json.dumps(command),
                          capture_output=True, text=True, env=env, cwd=str(REPO), timeout=600)
    if done.returncode != 0:
        raise RuntimeError(f"gdt.db helper failed: {done.stderr[-600:]}")
    return json.loads(done.stdout)


def _child(command: dict) -> dict:
    from ..texture.gdtdb import connect, register_gdt

    db = command["db"]
    if command["op"] == "missing":
        con = connect(db, read_only=True)
        try:
            have = set()
            names = list(command["names"])
            for i in range(0, len(names), 500):
                part = names[i:i + 500]
                q = f"select name from _entity where name in ({','.join('?' * len(part))})"
                have |= {r[0] for r in con.execute(q, part)}
        finally:
            con.close()
        return {"missing": sorted(set(command["names"]) - have)}
    if command["op"] == "register":
        done = []
        for gdt, rel in command["files"]:
            try:
                res = register_gdt(gdt, db, tools_root=WIN_ROOT, relative=rel)
                done.append({"gdt": rel, "entries": len(res.entries)})
            except (ValueError, OSError) as exc:
                done.append({"gdt": rel, "error": str(exc)})
        return {"registered": done}
    if command["op"] == "drop":
        # Delete the named entities (from whatever .gdt registered them), so a
        # render-only replacement .gdt can register them afresh.
        from ..texture.gdtdb import _present_tables

        con = connect(db)
        try:
            con.execute("PRAGMA foreign_keys = ON")
            dropped = []
            for name in command["names"]:
                pks = [int(r[0]) for r in con.execute("select PK_id from _entity where name=?",
                                                       (name,))]
                for table in sorted(_present_tables(con)):
                    for pk in pks:
                        con.execute(f"delete from {table} where PK_id = ?", (pk,))
                for pk in pks:
                    con.execute("delete from _entity where PK_id = ?", (pk,))
                if pks:
                    dropped.append(name)
            con.commit()
        finally:
            con.close()
        return {"dropped": dropped}
    if command["op"] == "relit":
        # Rewrite each material to the field layout of a stock "lit" material,
        # keeping its own colour map (see :func:`relight`).
        con = connect(db)
        try:
            cols = [r[1] for r in con.execute("pragma table_info(material)")
                    if r[1] != "PK_id" and not r[1].startswith("_")]

            def pk(name):
                row = con.execute("select PK_id from _entity where name=?", (name,)).fetchone()
                return row[0] if row else None
            src_pk = pk(command["template"])
            if src_pk is None:
                raise ValueError(f"no template material {command['template']}")
            src = dict(zip(cols, con.execute(f"select {','.join(cols)} from material "
                                             "where PK_id=?", (src_pk,)).fetchone()))
            done = []
            for name in command["materials"]:
                mpk = pk(name)
                if mpk is None:
                    continue
                colour = con.execute("select colorMap from material where PK_id=?",
                                     (mpk,)).fetchone()
                if not colour or not colour[0]:
                    continue
                vals = dict(src, colorMap=colour[0])
                con.execute(f"update material set {','.join(k + '=?' for k in cols)} "
                            "where PK_id=?", [*vals.values(), mpk])
                done.append(name)
            con.commit()
        finally:
            con.close()
        return {"relit": done}
    if command["op"] == "images":
        # Every image a set of materials uses, as tools-relative source
        # paths; models are first resolved to the materials their LOD0 file
        # names (see :func:`stock_images`).
        con = connect(db, read_only=True)
        try:
            def rows(table, names):
                names = list(names)
                cols = [r[1] for r in con.execute(f"pragma table_info({table})")]
                for i in range(0, len(names), 400):
                    part = names[i:i + 400]
                    q = (f"select e.name, t.* from {table} t join _entity e on e.PK_id = t.PK_id "
                         f"where e.name in ({','.join('?' * len(part))})")
                    for r in con.execute(q, part):
                        yield r[0], dict(zip(cols, r[1:]))
            files = {name: (row.get("filename") or "") for name, row in rows("xmodel", command["models"])}
            mats = set(command["materials"])
            for name, rel in files.items():
                mats |= set(_model_materials(Path(command["tools"]) / "model_export", rel))
            known = {r[0] for r in con.execute(
                "select e.name from _entity e join material m on m.PK_id = e.PK_id")}
            mats &= known
            images = {r[0] for r in con.execute(
                "select e.name from _entity e join image i on i.PK_id = e.PK_id")}
            used = set()
            for _name, row in rows("material", mats):
                used |= {v for v in row.values() if isinstance(v, str) and v in images}
            out = sorted({(row.get("baseImage") or "").replace("\\\\", "/").replace("\\", "/")
                          for _n, row in rows("image", used)} - {""})
        finally:
            con.close()
        return {"materials": sorted(mats), "images": out}
    raise ValueError(command["op"])


@dataclass
class Registration:
    """What the render did for the map's own assets; goes into views.json."""

    missing_before: list[str] = field(default_factory=list)
    registered: list[dict] = field(default_factory=list)
    still_missing: list[str] = field(default_factory=list)
    mounts: list[tuple[str, str]] = field(default_factory=list)   # host path, container path
    db: str | None = None

    def as_dict(self) -> dict:
        return {"missing_before": self.missing_before, "registered": self.registered,
                "still_missing": self.still_missing, "private_gdt_db": self.db}


#: Names the stock database never has and Radiant never needs a row for.
_IGNORE = re.compile(r"^(caulk|clip.*|trigger|sky|nodraw.*|umbra_volume|sun_volume|"
                     r"portal.*|hint.*|skip|lightmap_gray|\$.*)$", re.I)


def prepare(map_file: Path, *, tools: Path, work: Path, gen: Path | None = None,
            recipe: str | None = None, log=lambda s: None) -> Registration:
    """A private ``gdt.db`` with this map's own assets registered, and the mounts it needs."""
    reg = Registration()
    materials, models = used_assets(map_file.read_text(encoding="utf-8", errors="replace"))
    names = sorted(n for n in materials | models if not _IGNORE.match(n))
    shared_db = tools / "gdtdb" / "gdt.db"
    reg.missing_before = run_wide({"op": "missing", "db": str(shared_db), "names": names})["missing"]
    if not reg.missing_before:
        return reg
    log(f"{len(reg.missing_before)} asset(s) the shared gdt.db lacks: "
        f"{', '.join(reg.missing_before[:8])}{' ...' if len(reg.missing_before) > 8 else ''}")
    found = find_gdts(reg.missing_before, candidate_roots(gen, recipe, tools))
    if not found:
        reg.still_missing = reg.missing_before
        log("  no zmforge .gdt declares them; Radiant cannot draw them (missing or black)")
        return reg
    work.mkdir(parents=True, exist_ok=True)
    private = work / "gdt.db"
    shutil.copyfile(shared_db, private)
    reg.db = str(private)
    files = []
    for root, gdt in found:
        rel = gdt.relative_to(root)
        files.append((str(gdt), str(rel).replace("/", "\\")))
        if root != tools:   # outside the shared tree: mount it where the row says it is
            for p in (rel, *gdt_sources(gdt, root)):
                if not (tools / p).exists():
                    reg.mounts.append((str(root / p), f"/tools/{p.as_posix()}"))
    reg.registered = run_wide({"op": "register", "db": str(private), "files": files})["registered"]
    reg.still_missing = run_wide({"op": "missing", "db": str(private),
                                  "names": reg.missing_before})["missing"]
    reg.mounts.append((str(private), "/tools/gdtdb/gdt.db"))
    log(f"  registered {sum(r.get('entries', 0) for r in reg.registered)} entr(ies) from "
        f"{len(files)} .gdt into the render's private gdt.db"
        + (f"; still missing: {', '.join(reg.still_missing)}" if reg.still_missing else ""))
    return reg



def register_current_props(root: Path, *, tools: Path, work: Path, db: str | None,
                           log=lambda s: None) -> tuple[str | None, list[tuple[str, str]]]:
    """Register a render-only props tree (``propfix.stage_current``) in the private db.

    The tree's own ``.gdt`` files replace whatever rows the shared database has
    for the same names (the deployed kit hay bale, say), under a file name no
    deployed ``.gdt`` uses, and every file they point at is mounted at the
    path its row names.  Returns ``(private db, mounts)``.
    """
    gdts = sorted(root.glob("*/*.gdt"))
    if not gdts:
        return db, []
    if db is None:
        work.mkdir(parents=True, exist_ok=True)
        db = str(work / "gdt.db")
        shutil.copyfile(tools / "gdtdb" / "gdt.db", db)
    names = sorted(set().union(*(gdt_declares(g) for g in gdts)))
    run_wide({"op": "drop", "db": db, "names": names})
    files = [(str(g), str(g.relative_to(root)).replace("/", "\\")) for g in gdts]
    done = run_wide({"op": "register", "db": db, "files": files})["registered"]
    errors = [d for d in done if "error" in d]
    mounts = [(str(g), f"/tools/{g.relative_to(root).as_posix()}") for g in gdts]
    for g in gdts:
        for rel in gdt_sources(g, root):
            mounts.append((str(root / rel), f"/tools/{rel.as_posix()}"))
    log(f"== {len(names)} current prop asset(s) registered for the render"
        + (f"; errors: {errors}" if errors else ""))
    return db, mounts


#: A stock material whose layout Radiant draws on a model with its colour map
#: (``lit``: colour, normal and gloss maps, nothing else).
RELIGHT_TEMPLATE = "t7_wood_panel_01"


def relight(materials: Iterable[str], *, tools: Path, work: Path, db: str | None,
            log=lambda s: None) -> tuple[str | None, list[str]]:
    """Give the kit props' materials a stock ``lit`` layout in the render's private gdt.db.

    WHY [measured, two otherwise identical renders]: the
    kit materials are written as ``lit_detail`` with no normal map (the layout
    zmforge uses for wall textures).  On a model Radiant then ignores their
    colour map: a red/green checker in its place changed nothing.  With the
    same rows rewritten to :data:`RELIGHT_TEMPLATE`'s fields, keeping their
    own colour map, the checker showed.  Render only; the shipped material
    is untouched, and whether the game draws it is not verified here.

    Returns ``(private db path or None, materials rewritten)``.
    """
    names = sorted(set(materials))
    if not names:
        return db, []
    if db is None:
        work.mkdir(parents=True, exist_ok=True)
        db = str(work / "gdt.db")
        shutil.copyfile(tools / "gdtdb" / "gdt.db", db)
    done = run_wide({"op": "relit", "db": db, "materials": names,
                     "template": RELIGHT_TEMPLATE})["relit"]
    if done:
        log(f"== {len(done)} kit material(s) given a lit layout for the render: {', '.join(done)}")
    return db, done


_NAME_RUN = re.compile(rb"[a-z0-9_$]{4,}")


def _case_insensitive(root: Path, rel: str) -> Path:
    """``root / rel``, matching each part case-insensitively when the exact
    spelling is not on disk.

    WHY [measured]: the gdt.db names the hurricane lamp's file
    ``p7_light_hurricane_lamp_lod1.XMODEL_BIN`` but the export on disk is
    ``..._lod1.xmodel_bin``; Windows does not care, Linux does, so the model
    resolved to no materials, its images got no 16-bit copies, and every
    cemetery lantern drew Radiant's pale-blue missing-image fallback."""
    path = root / rel
    if path.exists():
        return path
    here = root
    for part in Path(rel).parts:
        nxt = here / part
        if not nxt.exists():
            try:
                nxt = next((c for c in here.iterdir() if c.name.lower() == part.lower()), nxt)
            except OSError:
                return root / rel
        here = nxt
    return here


def _model_materials(export_root: Path, rel: str) -> list[str]:
    """Candidate material names in a stock model's LOD0 file (``.XMODEL_BIN``
    is LZ4, ``.xmodel_export`` text): every identifier-like run in it, which
    the caller intersects with the gdt.db's materials."""
    path = _case_insensitive(export_root, rel.replace("\\\\", "/").replace("\\", "/"))
    try:
        data = path.read_bytes()
    except OSError:
        return []
    if data[:5] == b"*LZ4*":
        from .propfix import read_model_bin
        try:
            data = read_model_bin(data)
        except ValueError:
            return []
    return sorted({m.decode() for m in _NAME_RUN.findall(data.lower())})


def stock_images(materials: Iterable[str], models: Iterable[str], *, tools: Path,
                 db: str | None = None) -> list[Path]:
    """Source ``.tif`` of every image the map's brush materials and models use.

    WHY [measured]: the "blotchy
    teal" ceilings, mullions and cars in the baked README photos are stock
    materials whose images Radiant could not convert under Wine: its log
    reads ``Converting image t7_plastic_panels_white_c.tif`` then ``ERROR:
    Failed to load image 'i_t7_plastic_panels_white_c'`` and the surface draws
    Radiant's missing-image fallback.  The failing sources are 8-bit RGB or
    one-channel grey ``.tif``s; 16-bit RGB ones (plaster, ceramic, metal
    panels) draw (:func:`zmforge.render.propfix.needs_copy`).
    The kit props had the same failure and the same 16-bit fix
    (:func:`zmforge.render.propfix.tif16_copies`); this extends it to stock
    assets.
    """
    res = run_wide({"op": "images", "db": db or str(tools / "gdtdb" / "gdt.db"),
                    "tools": str(tools), "materials": sorted(set(materials)),
                    "models": sorted(set(models))})
    return [tools / rel for rel in res["images"]]


if __name__ == "__main__":
    print(json.dumps(_child(json.loads(sys.stdin.read()))))
