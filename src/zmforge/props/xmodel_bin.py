"""``.XMODEL_EXPORT`` text to the ``.XMODEL_BIN`` the tools read, in Python.

WHY.  ``export2bin.exe`` does not convert under Wine (it writes the text
truncated, and Radiant draws a grey box), so under Wine a new ``zmf_`` prop has no binary
and a render cannot show it.  This module writes the same binary in Python.

THE FORMAT [measured]: read off a ``zmf_prop_hay_bale.XMODEL_BIN`` that the
Windows tools' ``export2bin`` wrote beside its own export.
The file is ``*LZ4*``, a uint32 payload size and one LZ4 block
(``render/propfix.py`` reads and writes that wrapper), compressed the way
LZ4 r131 compresses it (:mod:`zmforge.props.lz4block`); any other valid
block decodes the same but is not the same file.  The payload is the
text, one chunk per line: a uint16 chunk id, then the line's values, every
chunk padded to 4 bytes.  Strings are NUL-terminated and padded to 4; unit
vectors (bone axes, normals) are int16 scaled by 32767; everything else is a
float32 or a small int.  ``tests/test_xmodel_bin.py`` converts every kit
export in the tools tree and compares it byte for byte with the Windows
build (46 of 46 identical).

Only what :func:`zmforge.props.xmodel.xmodel_export_text` writes is handled:
one bone, up to 65535 vertices, face indices under 65536.  Anything else is
refused loudly rather than guessed at.
"""

from __future__ import annotations

import struct

__all__ = ["export_to_bin", "export_to_payload"]

# Chunk ids, as they appear (little endian uint16) in the Windows-built file.
_COMMENT, _MODEL, _VERSION = 0xC355, 0x46C8, 0x24D1
_NUMBONES, _BONE_INFO, _BONE_INDEX = 0x76BA, 0xF099, 0xDD9A
_OFFSET, _SCALE, _X, _Y, _Z = 0x9383, 0x1C56, 0xDCFD, 0xCCDC, 0xFCBF
_NUMVERTS, _VERT, _BONES, _BONE_WEIGHT = 0x950D, 0x8F03, 0xEA46, 0xF1AB
_NUMFACES, _TRI, _NORMAL, _COLOR, _UV = 0xBE92, 0x562F, 0x89EC, 0x6DD8, 0x1AD4
_NUMOBJECTS, _OBJECT, _NUMMATERIALS, _MATERIAL = 0x62AF, 0x87D4, 0xA1B2, 0xA700
_TRANSPARENCY, _AMBIENT, _INCANDESCENCE = 0x6DAB, 0x37FF, 0x4265
_COEFFS, _GLOW, _REFRACTIVE = 0xC835, 0xFE0C, 0x7E24
_SPECULAR, _REFLECTIVECOLOR, _REFLECTIVE = 0x317C, 0xE593, 0x7D76
_BLINN, _PHONG = 0x83C7, 0x5CD2


def _string(text: str) -> bytes:
    raw = text.encode("utf-8") + b"\x00"
    return raw + b"\x00" * (-len(raw) % 4)


def _head(chunk: int, small: int = 0) -> bytes:
    """The 4-byte chunk head: id, then a uint16 (a count or index, or padding)."""
    return struct.pack("<HH", chunk, small)


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _unit16(values) -> bytes:
    """Unit floats as int16 * 32767, computed in float32 and rounded half away
    from zero: that is what matches the Windows tools' output on every kit export
    (plain double rounding was off by one on 16 turkey normals at -20435.5)."""
    out = []
    for v in values:
        scaled = _f32(_f32(float(v)) * 32767.0)
        whole = int(abs(scaled) + 0.5)
        out.append(max(-32767, min(32767, -whole if scaled < 0 else whole)))
    return struct.pack("<3h", *out)


def _floats(values) -> bytes:
    return struct.pack(f"<{len(values)}f", *(float(v) for v in values))


def _quoted(line: str) -> list[str]:
    return line.split('"')[1::2]


def export_to_payload(text: str) -> bytes:
    """The uncompressed binary payload for one export's text."""
    out = bytearray()
    in_bone = in_material = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            out += _head(_COMMENT) + _string(line[2:].strip())
            continue
        key, _, rest = line.partition(" ")
        args = rest.split()
        if key == "MODEL":
            out += _head(_MODEL)
        elif key == "VERSION":
            if args != ["7"]:
                raise ValueError(f"only VERSION 7 is known, not {rest!r}")
            out += _head(_VERSION, 7)
        elif key == "NUMBONES":
            out += _head(_NUMBONES, int(args[0]))
        elif key == "BONE" and len(args) >= 3 and '"' in rest:
            out += _head(_BONE_INFO) + struct.pack("<ii", int(args[0]), int(args[1]))
            out += _string(_quoted(rest)[0])
        elif key == "BONE" and len(args) == 1:
            out += _head(_BONE_INDEX, int(args[0]))
            in_bone = True
        elif key == "BONE" and len(args) == 2:
            out += _head(_BONE_WEIGHT, int(args[0])) + _floats([args[1]])
        elif key == "OFFSET":
            out += _head(_OFFSET) + _floats(args[:3])
        elif key == "SCALE":
            out += _head(_SCALE) + _floats(args[:3])
        elif key in ("X", "Y", "Z") and in_bone:
            out += struct.pack("<H", {"X": _X, "Y": _Y, "Z": _Z}[key]) + _unit16(args[:3])
        elif key == "NUMVERTS":
            n = int(args[0])
            if n > 0xFFFF:
                raise ValueError(f"{n} vertices: only the 16-bit vertex chunk is known")
            out += _head(_NUMVERTS, n)
            in_bone = False
        elif key == "VERT":
            out += _head(_VERT, int(args[0]))
        elif key == "BONES":
            out += _head(_BONES, int(args[0]))
        elif key == "NUMFACES":
            out += _head(_NUMFACES) + struct.pack("<I", int(args[0]))
        elif key == "TRI":
            obj, mat = int(args[0]), int(args[1])
            if obj > 0xFF or mat > 0xFF:
                raise ValueError("only the 8-bit object and material TRI chunk is known")
            out += struct.pack("<HBB", _TRI, obj, mat)
        elif key == "NORMAL":
            out += struct.pack("<H", _NORMAL) + _unit16(args[:3])
        elif key == "COLOR":
            rgba = bytes(max(0, min(255, round(float(v) * 255))) for v in args[:4])
            out += _head(_COLOR) + rgba
        elif key == "UV":
            count = int(args[0])
            out += _head(_UV, count) + _floats(args[1:1 + 2 * count])
        elif key == "NUMOBJECTS":
            out += _head(_NUMOBJECTS, int(args[0]))
        elif key == "OBJECT":
            out += _head(_OBJECT, int(args[0])) + _string(_quoted(rest)[0])
        elif key == "NUMMATERIALS":
            out += _head(_NUMMATERIALS, int(args[0]))
            in_material = True
        elif key == "MATERIAL" and in_material:
            name, kind, image = _quoted(rest)[:3]
            out += _head(_MATERIAL, int(args[0]))
            out += _string(name) + _string(kind) + _string(image)
        elif key in ("TRANSPARENCY", "AMBIENTCOLOR", "INCANDESCENCE", "SPECULARCOLOR",
                     "REFLECTIVECOLOR"):
            chunk = {"TRANSPARENCY": _TRANSPARENCY, "AMBIENTCOLOR": _AMBIENT,
                     "INCANDESCENCE": _INCANDESCENCE, "SPECULARCOLOR": _SPECULAR,
                     "REFLECTIVECOLOR": _REFLECTIVECOLOR}[key]
            out += _head(chunk) + _floats(args[:4])
        elif key == "COEFFS":
            out += _head(_COEFFS) + _floats(args[:2])
        elif key == "GLOW":
            out += _head(_GLOW) + _floats(args[:1]) + struct.pack("<i", int(args[1]))
        elif key == "REFRACTIVE":
            out += _head(_REFRACTIVE) + _floats(args[:2])
        elif key == "REFLECTIVE":
            out += _head(_REFLECTIVE) + _floats(args[:2])
        elif key == "BLINN":
            out += _head(_BLINN) + _floats(args[:2])
        elif key == "PHONG":
            out += _head(_PHONG) + _floats(args[:1])
        else:
            raise ValueError(f"unknown XMODEL_EXPORT line {line!r}")
    return bytes(out)


def export_to_bin(text: str) -> bytes:
    """The whole ``.XMODEL_BIN`` file (``*LZ4*`` wrapped) for one export's text."""
    from ..render.propfix import write_model_bin

    return write_model_bin(export_to_payload(text))
