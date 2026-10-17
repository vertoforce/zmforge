"""One command from "a prop is in the library" to "the tools have everything".

:func:`build` writes a staging tree that the install step copies onto the mod
tools install verbatim::

    model_export/<map>/<asset>.XMODEL_EXPORT       one file per prop
    model_export/<map>/<asset>_col.XMODEL_EXPORT   its bullet collision box
    collmaps/<asset>.map                           its brush collmap
    model_export/<map>_props.gdt                   the xmodel entities
    texture_assets/<map>/<stem>.tif            one source image per kit
    texture_assets/<map>_props_tex.gdt         the image + material entities
    PROP-CREDITS.md                            sources and licences, for the map
    props.json                                 every measured number
    build-vars.json                          what the deploy step needs

Nothing is written unless every prop converted, so a half-built set cannot be
deployed by accident.  Everything is a pure function of the library entry and
the downloaded kit, so the same inputs always give the same files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .. import mapsource
from ..texture.gdt import NormalAsset, TextureAsset, gdt_document as texture_gdt, image_asset_name
from .collision import (COLLISION_SUFFIX, bounds_of, box_mesh, check_kit_box, kit_box,
                        kit_collmap_document)
from .fetch import extract_prop, extract_texture, extract_texture_member
from .gdt import XModelAsset, gdt_document as xmodel_gdt
from .library import KITS, PHOTO_V, PROPS, Prop, PropMaterial, credits_markdown, source_file
from .textures import build_palette, png_to_tif, read_mtl_colours, write_tif
from .wavefront import Mesh, read_obj
from .xmodel import MaterialBinding, decimate, to_game_space, xmodel_export_text

__all__ = ["BuiltProp", "BuildResult", "build", "kit_palette", "palette_colours",
           "load_mesh", "game_mesh", "prop_image", "swatch_uv"]


def load_mesh(entry: Prop, work: Path, cache: Path | None = None) -> Mesh:
    """The prop's source mesh, however its kit delivers it (``Kit.kind``)."""
    kind = KITS[entry.kit].kind
    if kind == "generated":
        from .generated import generate

        return generate(entry.member)
    path = extract_prop(entry.kit, entry.member, Path(work) / entry.kit, cache)
    if kind == "gltf":
        from .gltf import read_gltf

        return read_gltf(path)
    return read_obj(path)


def game_mesh(entry: Prop, work: Path, cache: Path | None = None):
    """``(game-space mesh, scale, decimation note)``: what build writes for *entry*."""
    game, scale = to_game_space(load_mesh(entry, work, cache), entry.size_units)
    game, note = _reduce(entry, game)
    return game, scale, note


def _reduce(entry: Prop, game: Mesh) -> tuple[Mesh, str]:
    """Cut *game* to the prop's budget with the prop's own decimation."""
    if entry.decimation == "quadric":
        from .simplify import decimate_quadric

        return decimate_quadric(game, entry.max_triangles)
    return decimate(game, entry.max_triangles)


def swatch_uv(material: PropMaterial, name: str) -> tuple[float, float]:
    """The flat UV of swatch *name* in a :class:`PropMaterial` image (v runs down).

    The swatches share the strip below ``PHOTO_V``, one equal cell each,
    and each UV is its cell's centre.
    """
    names = [n for n, _ in material.swatches]
    index = names.index(name)
    return ((index + 0.5) / len(names), (PHOTO_V + 1.0) / 2)


def painted_images(material: PropMaterial):
    """``(colour, normal or None)`` from the material's own painter, cached per run."""
    from .generated import paint

    return paint(material.painter, material.size)


def prop_image(entry: Prop, mesh: Mesh, work: Path, cache: Path | None = None,
               material: PropMaterial | None = None):
    """The prop's own colour map as an RGB Pillow image, ``size`` x ``size``.

    The photo is the texture source's ``member``, or with no source the
    mesh's own colour map (a glTF ``baseColorTexture``).  With swatches the
    photo is squeezed into the rows above ``PHOTO_V`` and the swatch colours
    fill the strip below, in cells laid out as :func:`swatch_uv` reads them.
    """
    from PIL import Image

    material = material or entry.material
    assert material is not None
    if material.painter:
        return painted_images(material)[0]
    if material.source:
        photo = extract_texture_member(material.source, material.member,
                                       Path(work) / "_textures", cache)
    else:
        maps = sorted(set(mesh.textures.values()))
        if len(maps) != 1:
            raise ValueError(f"{entry.name}: expected one colour map in the model, found {maps}")
        photo = Path(maps[0])
    size = material.size
    with Image.open(photo) as im:
        rgb = im.convert("RGB")
    if material.crop is not None:
        rgb = rgb.crop(material.crop)
    if material.rotate:
        rgb = rgb.rotate(material.rotate, expand=True)
    if material.grade is not None:
        import numpy as np

        if material.grade_end is not None:
            rgb = rgb.resize((size, size), Image.LANCZOS)
        pixels = np.asarray(rgb, dtype=np.float64)
        mean = pixels.reshape(-1, 3).mean(axis=0)
        target = np.array(material.grade, dtype=np.float64)
        if material.grade_end is not None:
            # Column by column from grade (left) to grade_end (right).
            f = np.linspace(0.0, 1.0, pixels.shape[1])[None, :, None]
            target = target * (1 - f) + np.array(material.grade_end) * f
        gain = target * 255.0 / np.maximum(mean, 1.0)
        rgb = Image.fromarray(np.clip(pixels * gain, 0, 255).round().astype(np.uint8), "RGB")
    if not material.swatches:
        return rgb.resize((size, size), Image.LANCZOS)
    photo_rows = round(size * PHOTO_V)
    out = Image.new("RGB", (size, size))
    out.paste(rgb.resize((size, photo_rows), Image.LANCZOS), (0, 0))
    cells = len(material.swatches)
    for i, (_name, colour) in enumerate(material.swatches):
        x0, x1 = size * i // cells, size * (i + 1) // cells
        fill = tuple(max(0, min(255, round(c * 255))) for c in colour)
        out.paste(Image.new("RGB", (x1 - x0, size - photo_rows), fill), (x0, photo_rows))
    return out

#: The date stamp in every generated export, so a rebuild of the same library
#: produces byte-identical files.
STAMP = "Thu Jan 01 00:00:00 2026"


@dataclass(frozen=True, slots=True)
class BuiltProp:
    prop: Prop
    triangles: int
    vertices: int
    scale: float
    size: tuple[float, float, float]
    materials: tuple[str, ...]
    decimation: str
    export: Path
    #: What collision was generated, in words, for the build report.
    collision: str = "none"


@dataclass(slots=True)
class BuildResult:
    map_name: str
    out: Path
    props: list[BuiltProp] = field(default_factory=list)
    images: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def triangles(self) -> int:
        return sum(p.triangles for p in self.props)


def palette_colours(uses) -> dict[str, tuple[float, float, float]]:
    """The swatch colours of one kit: each material's ``Kd``, or a prop's override.

    *uses* is ``(prop, its mesh's materials, its .mtl colours)`` per chosen
    prop.  A material keeps one cell (so UVs stay put), which means every
    prop sharing it must agree on its colour; a clash is an error, not a
    silent last-one-wins.
    """
    colours: dict[str, tuple[float, float, float]] = {}
    owner: dict[str, str] = {}
    for entry, materials, from_file in uses:
        override = dict(entry.colours)
        unknown = set(override) - set(materials)
        if unknown:
            raise ValueError(f"{entry.name}: colour override for unknown material(s) "
                             f"{sorted(unknown)}")
        for m in materials:
            rgb = override.get(m, from_file.get(m))
            if rgb is None:
                continue
            rgb = tuple(float(c) for c in rgb)
            if m in colours and colours[m] != rgb:
                raise ValueError(f"kit material {m!r} is {colours[m]} for {owner[m]} "
                                 f"but {rgb} for {entry.name}: one swatch cell each")
            colours[m], owner[m] = rgb, entry.name  # type: ignore[assignment]
    return colours


def kit_palette(slug: str, work: Path, props: list[Prop] | None = None,
                cache: Path | None = None):
    """The swatch atlas :func:`build` would write for one flat-colour kit.

    Same inputs and layout as build's pass one (every library prop of the kit
    by default), without writing any models.  ``render/propfix.py`` uses it
    to give renders the current colours before they are deployed.
    """
    kit = KITS[slug]
    if kit.texture is not None:
        raise ValueError(f"{slug} ships a texture; it has no generated palette")
    uses = []
    for entry in (props if props is not None else PROPS):
        if entry.kit != slug or entry.material is not None:
            continue
        obj_path = extract_prop(slug, entry.member, Path(work) / slug, cache)
        mtl = obj_path.with_suffix(".mtl")
        uses.append((entry, read_obj(obj_path).materials,
                     read_mtl_colours(mtl) if mtl.is_file() else {}))
    colours = palette_colours(uses)
    if not colours:
        raise ValueError(f"{slug}: kit ships no texture and no Kd colours were found")
    return build_palette(colours)


def build(
    map_name: str,
    out: Path,
    props: list[Prop] | None = None,
    *,
    cache: Path | None = None,
    work: Path | None = None,
    stock_material: str | None = None,
) -> BuildResult:
    """Convert every prop and write the whole staging tree under ``out``.

    ``stock_material`` binds every prop to one material the game already ships
    instead of to the kits' own.  The props come out the wrong colour, but no
    custom image or material is involved at all, which is the one-flag way to
    find out whether a build failure is the models or their materials.
    """
    chosen = list(props if props is not None else PROPS)
    if not chosen:
        raise ValueError("no props selected")
    out = Path(out)
    work = Path(work) if work else out / "_obj"
    result = BuildResult(map_name=map_name, out=out)

    kits = sorted({p.kit for p in chosen})
    meshes: dict[str, object] = {}
    palettes: dict[str, object] = {}

    # Pass one: read every mesh, and collect the flat colours of the kits that
    # ship no texture, so each kit's palette is laid out once for all its props.
    raw: dict[str, tuple] = {}
    for entry in chosen:
        kit = KITS[entry.kit]
        obj_path = (extract_prop(entry.kit, entry.member, work / entry.kit, cache)
                    if kit.kind == "zip" else None)
        mesh = read_obj(obj_path) if obj_path else load_mesh(entry, work, cache)
        raw[entry.name] = (kit, obj_path, mesh)

    # A kit's shared material is only needed by its props that did not opt
    # into their own (``Prop.material``).
    shared = sorted({p.kit for p in chosen if p.material is None})
    for slug in shared:
        kit = KITS[slug]
        if kit.texture is not None:
            continue
        uses = []
        for entry in chosen:
            if entry.kit != slug or entry.material is not None:
                continue
            _, obj_path, mesh = raw[entry.name]
            mtl = obj_path.with_suffix(".mtl")
            uses.append((entry, mesh.materials, read_mtl_colours(mtl) if mtl.is_file() else {}))
        colours = palette_colours(uses)
        if not colours:
            raise ValueError(f"{slug}: kit ships no texture and no Kd colours were found")
        palettes[slug] = build_palette(colours)

    # Images: one per kit, into texture_assets/<map>/.  Skipped entirely when
    # the props are bound to a material the game already ships.
    tex_dir = out / "texture_assets" / map_name
    assets: list[TextureAsset | NormalAsset] = []
    for slug in [] if stock_material else shared:
        kit = KITS[slug]
        target = tex_dir / f"{kit.image_stem}.tif"
        if kit.texture is not None:
            source = extract_texture(slug, work / slug, cache)
            assert source is not None
            _, size = png_to_tif(source, target)
            result.images[kit.image_stem] = f"{kit.texture.rsplit('/', 1)[-1]} {size[0]}x{size[1]} atlas"
        else:
            palette = palettes[slug]
            write_tif(palette.size, palette.size, palette.pixels(), target)  # type: ignore[attr-defined]
            result.images[kit.image_stem] = (
                f"generated {palette.size}x{palette.size} swatch atlas, "  # type: ignore[attr-defined]
                f"{len(palette.order)} colours on a {palette.cells}x{palette.cells} grid"  # type: ignore[attr-defined]
            )
        assets.append(
            TextureAsset(
                material=kit.material,
                file_stem=kit.image_stem,
                # Verified value from a real BO3 prop material entity
                # (p7_zm_der_magic_box_fade.gdt): every material in it reads
                # "usage" "<not in editor>".  Not a guess at an enum.
                usage="<not in editor>",
            )
        )

    # Per-prop materials: one image and one material each, shared only by
    # props naming the same material asset (the two straw bales).
    own: dict[str, PropMaterial] = {}
    for entry, pm in [] if stock_material else [
            (e, m) for e in chosen for m in (e.material, *e.extra_materials)]:
        if pm is None:
            continue
        if pm.asset in own:
            if own[pm.asset] != pm:
                raise ValueError(f"material {pm.asset!r} is defined twice, differently")
            continue
        if any(pm.asset == KITS[k].material for k in shared):
            raise ValueError(f"{entry.name}: {pm.asset!r} is a kit's shared material name")
        own[pm.asset] = pm
        image = prop_image(entry, raw[entry.name][2], work, cache, material=pm)
        target = tex_dir / f"{pm.image_stem}.tif"
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, compression=None)
        origin = (f"painted by props/generated.py PAINTERS[{pm.painter!r}]" if pm.painter
                  else f"{pm.source}:{pm.member}" if pm.source
                  else f"{source_file(entry)} base colour")
        result.images[pm.image_stem] = (
            f"{origin} {pm.size}x{pm.size}"
            + (f", swatches {', '.join(n for n, _ in pm.swatches)}" if pm.swatches else ""))
        normal_name = ""
        if pm.normal:
            normal = painted_images(pm)[1]
            if normal is None:
                raise ValueError(f"{pm.asset}: painter {pm.painter!r} returned no normal map")
            normal_stem = f"{pm.image_stem.removesuffix('_c')}_n"
            normal_name = f"i_{pm.asset}_n"
            normal.save(tex_dir / f"{normal_stem}.tif", compression=None)
            result.images[normal_stem] = f"{origin} normal map {normal.size[0]}x{normal.size[1]}"
            assets.append(NormalAsset(normal_name, normal_stem))
        kind = {}
        if pm.emissive > 0:
            # The stock emissive screens' layout (mtl_p7_elevator_screen_graphic,
            # t7_props gdts): colorMap is the diffuse, colorMap00 the emissive
            # map, scaleRGB its strength.  One painted image serves as both.
            kind = {"material_type": "lit_emissive", "scale_rgb": f"{pm.emissive:g}",
                    "emissive_map": image_asset_name(pm.asset)}
        assets.append(TextureAsset(material=pm.asset, file_stem=pm.image_stem,
                                   usage="<not in editor>", normal_map=normal_name, **kind))

    # Models.
    model_dir = out / "model_export" / map_name
    model_dir.mkdir(parents=True, exist_ok=True)
    collmap_dir = out / "collmaps"
    collmap_dir.mkdir(parents=True, exist_ok=True)
    xmodels: list[XModelAsset] = []
    for entry in chosen:
        kit, _, mesh = raw[entry.name]
        pm = entry.material
        if stock_material:
            material, image_file = stock_material, f"{stock_material}.tif"
        elif pm is not None:
            material, image_file = pm.asset, f"{pm.image_stem}.tif"
        else:
            material, image_file = kit.material, f"{kit.image_stem}.tif"
        game, scale = to_game_space(mesh, entry.size_units)
        game, note = _reduce(entry, game)
        extra = {} if stock_material else {
            face: (m.asset, f"{m.image_stem}.tif") for m in entry.extra_materials for face in m.faces}
        palette = palettes.get(entry.kit) if pm is None else None
        swatches = {n for n, _ in pm.swatches} if pm is not None else set()

        def flat(name: str):
            if palette is not None:
                return palette.uv(name)  # type: ignore[attr-defined]
            if name in swatches:
                return swatch_uv(pm, name)  # type: ignore[arg-type]
            return None

        bindings = [
            MaterialBinding(obj_material=name, asset=extra.get(name, (material,))[0],
                            color_map=extra.get(name, (None, image_file))[1],
                            flat_uv=flat(name))
            for name in game.materials
        ]
        used = tuple(dict.fromkeys(b.asset for b in bindings))
        text = xmodel_export_text(game, entry.name, bindings, stamp=STAMP)
        export = model_dir / f"{entry.name}.XMODEL_EXPORT"
        export.write_text(text, newline="\n")

        # Collision, when the prop is meant to be solid: a bullet mesh and a
        # brush collmap, both a box around the model's bounding volume.  See
        # props/collision.py for the measurements that settle the shape and
        # the naming.
        collision_file = ""
        collision_map = ""
        collision_note = "none (walk-through by design)"
        if entry.solid:
            from ..recipes.props import KIT_COLLISION_BOX

            box = bounds_of(game)
            # A tree's collision is its trunk (KIT_COLLISION_BOX), not its crown.
            col_box = kit_box(entry.name) if entry.name in KIT_COLLISION_BOX else box
            col_name = f"{entry.name}{COLLISION_SUFFIX}"
            col_mesh = box_mesh(col_box, bindings[0].obj_material)
            (model_dir / f"{col_name}.XMODEL_EXPORT").write_text(
                xmodel_export_text(col_mesh, col_name, bindings, stamp=STAMP),
                newline="\n",
            )
            collision_file = f"{map_name}\\{col_name}.XMODEL_BIN"
            collision_map = f"{entry.name}.map"
            # The collmap is the recorded box, the same file the map
            # generator writes (props/collision.py kit_collmap_document).
            check_kit_box(entry.name, box)
            mapsource.write(collmap_dir / collision_map, kit_collmap_document(entry.name))
            collision_note = (
                f"box {col_box.maxs.x - col_box.mins.x:.1f} x {col_box.maxs.y - col_box.mins.y:.1f} "
                f"x {col_box.maxs.z - col_box.mins.z:.1f} units: 12-triangle bullet mesh "
                f"plus a one-brush collmap"
            )
        result.props.append(
            BuiltProp(
                prop=entry,
                triangles=len(game.triangles),
                vertices=len(game.positions),
                scale=scale,
                size=game.size(),
                materials=used,
                decimation=note,
                export=export,
                collision=collision_note,
            )
        )
        xmodels.append(
            XModelAsset(
                name=entry.name,
                source=f"{map_name}\\{entry.name}.XMODEL_BIN",
                materials=used,
                collision_file=collision_file,
                collision_map=collision_map,
            )
        )
        meshes[entry.name] = game

    (out / "model_export" / f"{map_name}_props.gdt").write_text(
        xmodel_gdt(xmodels), newline="\n"
    )
    if assets:
        (out / "texture_assets" / f"{map_name}_props_tex.gdt").write_text(
            texture_gdt(map_name, assets), newline="\n"
        )
    else:
        result.notes.append(f"every prop bound to the stock material {stock_material!r}")
    (out / "PROP-CREDITS.md").write_text(credits_markdown(chosen), newline="\n")

    report = {
        "map": map_name,
        "generated": date.today().isoformat(),
        "total_triangles": result.triangles,
        "images": result.images,
        "props": [
            {
                "asset": b.prop.name,
                "kit": b.prop.kit,
                "source_file": source_file(b.prop),
                "licence": KITS[b.prop.kit].licence,
                "source_url": KITS[b.prop.kit].archive,
                "texture": (None if b.prop.material is None else {
                    "material": b.prop.material.asset,
                    "source": b.prop.material.source or "the model's own",
                    "member": b.prop.material.member or None,
                }),
                "triangles": b.triangles,
                "vertices": b.vertices,
                "scale_applied": round(b.scale, 4),
                "size_units": [round(v, 2) for v in b.size],
                "material": b.materials[0],
                "polygon_budget": b.prop.max_triangles,
                "decimation": b.decimation,
                "solid": b.prop.solid,
                "collision": b.collision,
                "joke": b.prop.joke,
            }
            for b in result.props
        ],
    }
    (out / "props.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "build-vars.json").write_text(
        json.dumps(
            {
                "map_name": map_name,
                "prop_exports": [
                    f"{name}.XMODEL_EXPORT"
                    for b in result.props
                    for name in ([b.prop.name] + ([b.prop.name + COLLISION_SUFFIX] if b.prop.solid else []))
                ],
                "prop_assets": [b.prop.name for b in result.props],
                "collmap_files": [
                    f"{b.prop.name}.map" for b in result.props if b.prop.solid
                ],
                "prop_materials": sorted({b.materials[0] for b in result.props}),
                "prop_images": sorted(result.images),
                "tif_files": sorted(f"{stem}.tif" for stem in result.images),
            },
            indent=2,
        )
        + "\n"
    )
    return result
