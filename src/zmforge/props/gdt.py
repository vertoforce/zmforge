"""The asset-database entity for a custom ``xmodel``.

An ``.xmodel`` entity is 150-odd keys, nearly all of them LOD and submodel
slots a background prop does not use, and the converter reads the whole set.
The key names and the shape are from a real BO3 prop entity
(``p7_zm_der_magic_box_fade``, ``model_export/t7_props_zombie/...gdt`` in
``marinesciencedude/Black-Ops-Trilogy-Weapon-Packs``); the values here are our
own, chosen for *one* mesh with *no* collision and *no* LOD chain, because the
props carry ``no_collmap 1`` in the map anyway (spec section 4.13) and a
few-hundred-triangle mesh has nothing to shed.

Two format rules, both from the format reference section 2.1-2.2:

* keys come out in case-insensitive ASCII order, which is the order every real
  GDT is written in (``boneStabilizers`` then ``BulletCollisionFile`` then
  ``CollisionMap`` then ``cullOutDiameter``);
* backslashes in paths are **doubled**, and a value never contains a real
  newline -- the ``materials`` list spells its line breaks as the four
  characters ``\\r\\n``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["XModelAsset", "xmodel_entry", "gdt_document"]


def _submodel_keys() -> dict[str, str]:
    out: dict[str, str] = {}
    for slot in range(16):
        out[f"submodel{slot}_Name"] = ""
        out[f"submodel{slot}_OffsetPitch"] = "0"
        out[f"submodel{slot}_OffsetRoll"] = "0"
        out[f"submodel{slot}_OffsetX"] = "0"
        out[f"submodel{slot}_OffsetY"] = "0"
        out[f"submodel{slot}_OffsetYaw"] = "0"
        out[f"submodel{slot}_OffsetZ"] = "0"
        out[f"submodel{slot}_ParentTag"] = ""
    return out


#: Every key of an ``xmodel.gdf`` entity, with the value a single-mesh,
#: collision-free, single-LOD static prop wants.  ``filename`` and
#: ``materials`` are filled in per model.
XMODEL_DEFAULTS: dict[str, str] = {
    "arabicUnsafe": "0",
    "autogenLod4": "0",
    "autogenLod4Percent": "15",
    "autogenLod5": "0",
    "autogenLod5Percent": "10",
    "autogenLod6": "0",
    "autogenLod6Percent": "2",
    "autogenLod7": "0",
    "autogenLod7Percent": "1",
    "autogenLowestLod": "0",
    "autogenLowestLodPercent": "12",
    "autogenLowLod": "0",
    "autogenLowLodPercent": "25",
    "autogenMediumLod": "0",
    "autogenMediumLodPercent": "50",
    "boneControllers": "",
    "boneStabilizers": "",
    # Filled in per model.  A prop with collision names a "_col" bullet mesh
    # here and sets BulletCollisionLOD to "Custom"; measured on the mod tools install,
    # 675 of the 706 stock models that carry one use that suffix and all 686
    # "Custom" entities name a file.
    "BulletCollisionFile": "",
    "BulletCollisionLOD": "None",
    # "0" on 1421 of the 1463 stock xmodel entities, "1" on 42.  The flag's
    # meaning is undocumented, so the value the shipped assets overwhelmingly
    # carry is the one to default to.
    "BulletCollisionRigid": "0",
    # The brush collmap in share\raw\collmaps, by bare filename.  cod2map
    # bakes it into the static BSP, but only for a misc_model that says
    # "use_collmap" (bin\t7.def.json).
    "CollisionMap": "",
    "cullOutDiameter": "0",
    "cullOutOffsetCP": "1",
    "cullOutOffsetMP": "1",
    "customAutogenParams": "0",
    "DetailShadows": "0",
    "doNotUse": "0",
    "dropLOD": "Auto",
    "filename": "",
    "forceLod4Rigid": "1",
    "forceLod5Rigid": "1",
    "forceLod6Rigid": "1",
    "forceLod7Rigid": "1",
    "forceLowestLodRigid": "1",
    "forceLowLodRigid": "1",
    "forceMediumLodRigid": "1",
    "forceResident": "0",
    "fp32": "0",
    "germanUnsafe": "0",
    "heroAsset": "0",
    "heroLighting": "0",
    "highLodDist": "0",
    "hitBoxModel": "",
    "isSiege": "0",
    "japaneseUnsafe": "0",
    "lod4Dist": "0",
    "lod4File": "",
    "lod5Dist": "0",
    "lod5File": "",
    "lod6Dist": "0",
    "lod6File": "",
    "lod7Dist": "0",
    "lod7File": "",
    "LODBiasOffsetCP": "0",
    "LODBiasOffsetMP": "0",
    "LODBiasPercent": "0",
    "LodColorPriority": "0.008",
    "lodNormalPriority": "1.54",
    "lodPositionPriority": "4",
    "lodPresets": "custom",
    "LodUvPriority": "12",
    "lowestLod": "",
    "lowestLodDist": "0",
    "lowLod": "",
    "lowLodDist": "0",
    "materials": "",
    "mediumLod": "",
    "mediumLodDist": "0",
    "noCastShadow": "0",
    "noOutdoorOcclude": "0",
    "notInEditor": "0",
    "physicsConstraints": "",
    "physicsPreset": "",
    "preserveOriginalUVs": "0",
    "scale": "1",
    "scaleCollMap": "0",
    "ShadowLOD": "Auto",
    "skinOverride": "",
    "type": "rigid",
    "usage_attachment": "0",
    "usage_hero": "0",
    "usage_view": "0",
    "usage_weapon": "0",
    "usage_zombie_body": "0",
    "usage_zombie_world_prop": "0",
    **_submodel_keys(),
}


@dataclass(frozen=True, slots=True)
class XModelAsset:
    """One custom model: its asset name, its source file and its materials."""

    name: str  # the xmodel asset name, what a .map "model" key spells
    #: Path relative to ``model_export``, written with single backslashes;
    #: :func:`xmodel_entry` doubles them.
    source: str
    materials: tuple[str, ...]
    #: The bullet collision mesh, same form as ``source``.  Empty means the
    #: model converts with collision off.
    collision_file: str = ""
    #: The brush collmap's bare filename in ``share\raw\collmaps``.
    collision_map: str = ""

    def entry(self) -> str:
        return xmodel_entry(self)


def xmodel_entry(asset: XModelAsset) -> str:
    """The ``"<name>" ( "xmodel.gdf" ) { ... }`` block, tab indented, LF ended."""
    if not asset.name or " " in asset.name:
        raise ValueError(f"bad xmodel asset name {asset.name!r}")
    if not asset.materials:
        raise ValueError(f"{asset.name}: an xmodel entity must list its materials")
    values = dict(XMODEL_DEFAULTS)
    values["filename"] = asset.source.replace("\\", "\\\\")
    values["materials"] = "".join(f"{m}\\r\\n" for m in asset.materials)
    if asset.collision_file:
        values["BulletCollisionFile"] = asset.collision_file.replace("\\", "\\\\")
        values["BulletCollisionLOD"] = "Custom"
    values["CollisionMap"] = asset.collision_map
    lines = [f'\t"{asset.name}" ( "xmodel.gdf" )', "\t{"]
    for key in sorted(values, key=str.lower):
        lines.append(f'\t\t"{key}" "{values[key]}"')
    lines.append("\t}")
    return "\n".join(lines) + "\n"


def gdt_document(assets: list[XModelAsset]) -> str:
    """The whole ``.gdt``: one brace-wrapped list of xmodel entities."""
    if not assets:
        raise ValueError("no assets")
    names = [a.name for a in assets]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate xmodel asset names in {names}")
    return "{\n" + "".join(a.entry() for a in assets) + "}\n"
