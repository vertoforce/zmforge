"""The one source image each kit needs, in the form the asset converter reads.

Two cases:

* the kit ships a texture atlas (Kenney's food kit does): it is converted to an
  uncompressed 24-bit ``.tif``, which is what ``baseImage`` points at in every
  real GDT and what the mod tools' texture pipeline converts;
* the kit ships none, only a flat ``Kd`` colour per material (Kenney's
  furniture kit): a swatch atlas is generated from those colours and each
  material is pinned to the centre of its own cell, so the model comes out in
  the colours its author chose without inventing any artwork.

Cells are large on purpose.  A swatch grid whose cells are a few pixels across
bleeds neighbouring colours into a prop as soon as the engine mips it down; at
16 cells on a 256 px image each cell is 64 px, so bleeding needs six mip levels
before it can reach a neighbour.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .wavefront import Vec2

__all__ = ["Palette", "build_palette", "write_tif", "png_to_tif"]


@dataclass(frozen=True, slots=True)
class Palette:
    """A swatch atlas: one cell per material name."""

    size: int
    cells: int  # cells per side
    order: tuple[str, ...]
    colours: dict[str, tuple[int, int, int]]

    def uv(self, material: str) -> Vec2:
        """The centre of ``material``'s cell, with v running down the image."""
        index = self.order.index(material)
        col, row = index % self.cells, index // self.cells
        return ((col + 0.5) / self.cells, (row + 0.5) / self.cells)

    def pixels(self) -> bytes:
        cell = self.size // self.cells
        rows = []
        for y in range(self.size):
            row = bytearray()
            for x in range(self.size):
                index = (y // cell) * self.cells + (x // cell)
                name = self.order[index] if index < len(self.order) else None
                row += bytes(self.colours[name] if name else (32, 32, 32))
            rows.append(bytes(row))
        return b"".join(rows)


def build_palette(colours: dict[str, tuple[float, float, float]], size: int = 256) -> Palette:
    """Lay the materials out on the smallest power-of-two grid that holds them."""
    if not colours:
        raise ValueError("no colours to lay out")
    order = tuple(sorted(colours))
    cells = 2
    while cells * cells < len(order):
        cells *= 2
    return Palette(
        size=size,
        cells=cells,
        order=order,
        colours={
            name: tuple(max(0, min(255, round(c * 255))) for c in rgb)  # type: ignore[misc]
            for name, rgb in colours.items()
        },
    )


def read_mtl_colours(path: Path) -> dict[str, tuple[float, float, float]]:
    """``newmtl`` -> its ``Kd``, for a kit that ships colours instead of a map."""
    out: dict[str, tuple[float, float, float]] = {}
    name = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("newmtl "):
            name = line[7:].strip()
        elif line.startswith("Kd ") and name:
            parts = line.split()
            out[name] = (float(parts[1]), float(parts[2]), float(parts[3]))
    return out


def _pillow():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on the extra
        raise RuntimeError(
            "the props image step needs Pillow: pip install -e '.[textures]'"
        ) from exc
    return Image


def write_tif(width: int, height: int, pixels: bytes, path: Path) -> Path:
    """Write RGB bytes as the uncompressed ``.tif`` the converter reads."""
    Image = _pillow()
    image = Image.frombytes("RGB", (width, height), pixels)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, compression=None)
    return path


def png_to_tif(source: Path, path: Path) -> tuple[Path, tuple[int, int]]:
    """Convert a kit's shipped PNG atlas (palette or RGBA) to a 24-bit ``.tif``."""
    Image = _pillow()
    image = Image.open(source).convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, compression=None)
    return path, image.size
