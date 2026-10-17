"""Contact sheets and before/after sheets from render PNGs (Pillow only).

A contact sheet is every shot of a run in one image, one row per room, each
tile labelled ``room / view``: the thing to look at first.  A compare sheet
puts the same view from two runs side by side (``before | after``), matched
by file name, so a fix can be judged at a glance.  Sheets are written as JPEG
and kept at most :data:`MAX_SIDE` px on the long side, the size an agent
should look at.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

#: Longest side of any sheet; agents should read images no larger than this.
MAX_SIDE = 1024
TILE_W = 480
LABEL_H = 22
GAP = 6
BG = (24, 24, 24)
FG = (235, 235, 235)
MISSING = (90, 20, 20)


def _font(size: int = 15):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _tile(path: Path | None, label: str, width: int = TILE_W,
          aspect: float = 790 / 1468) -> Image.Image:
    """One labelled thumbnail; a dark-red box saying 'missing' when *path* is None."""
    h = round(width * aspect)
    tile = Image.new("RGB", (width, h + LABEL_H), BG)
    if path is not None and Path(path).is_file():
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((width, h))
            tile.paste(im, ((width - im.width) // 2, LABEL_H + (h - im.height) // 2))
    else:
        ImageDraw.Draw(tile).rectangle((0, LABEL_H, width, h + LABEL_H), fill=MISSING)
        ImageDraw.Draw(tile).text((8, LABEL_H + h // 2 - 8), "missing", fill=FG, font=_font())
    ImageDraw.Draw(tile).text((6, 3), label, fill=FG, font=_font())
    return tile


def grid(tiles: Sequence[Sequence[Image.Image]], *, max_side: int = MAX_SIDE) -> Image.Image:
    """Rows of tiles into one image, scaled so its long side is at most *max_side*."""
    rows = [r for r in tiles if r]
    if not rows:
        raise ValueError("no tiles")
    tw, th = rows[0][0].size
    cols = max(len(r) for r in rows)
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * GAP, len(rows) * th + (len(rows) + 1) * GAP),
                      BG)
    for ri, row in enumerate(rows):
        for ci, t in enumerate(row):
            sheet.paste(t, (GAP + ci * (tw + GAP), GAP + ri * (th + GAP)))
    sheet.thumbnail((max_side, max_side))
    return sheet


def _chunks(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)] or [[]]


def contact_sheet(shots: Mapping[str, Iterable[Path | str]], out: Path, *,
                  per_row: int = 3, max_side: int = MAX_SIDE) -> Path:
    """One row per room (wrapped at *per_row*), each tile labelled with its file stem."""
    rows = []
    for _room, paths in shots.items():
        tiles = [_tile(Path(p), Path(p).stem.replace("--", " / ")) for p in paths]
        rows.extend(_chunks(tiles, per_row))
    grid(rows, max_side=max_side).save(out, quality=85)
    return out


def contact_sheets(shots: Mapping[str, Iterable[Path | str]], out_dir: Path, *,
                   rooms_per_sheet: int = 4, per_row: int = 3,
                   max_side: int = MAX_SIDE) -> list[Path]:
    """``sheet.jpg`` for a small run, else ``sheet-01.jpg`` ... a few rooms each, so
    tiles stay big enough to read at *max_side*."""
    rooms = list(shots)
    if len(rooms) <= rooms_per_sheet:
        return [contact_sheet(shots, out_dir / "sheet.jpg", per_row=per_row,
                              max_side=max_side)]
    out = []
    for i, part in enumerate(_chunks(rooms, rooms_per_sheet), 1):
        out.append(contact_sheet({r: shots[r] for r in part}, out_dir / f"sheet-{i:02d}.jpg",
                                 per_row=per_row, max_side=max_side))
    return out


def pair_shots(before: Path, after: Path) -> list[tuple[str, Path | None, Path | None]]:
    """``(stem, before png, after png)`` for every view in either run, by file name."""
    old = {p.stem: p for p in Path(before).glob("*--*.png")}
    new = {p.stem: p for p in Path(after).glob("*--*.png")}
    return [(stem, old.get(stem), new.get(stem)) for stem in sorted(old.keys() | new.keys())]


def compare_sheets(before: Path, after: Path, out_dir: Path, *,
                   rooms: Iterable[str] | None = None, max_side: int = MAX_SIDE) -> list[Path]:
    """``compare/<room>--<view>.jpg``: the view from *before* left, *after* right.

    Only views present in *after* (the run just made) are paired unless it has
    none; *rooms* limits it further.  Returns the sheets written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = None if rooms is None else set(rooms)
    written = []
    for stem, old, new in pair_shots(before, after):
        room = stem.split("--", 1)[0]
        if new is None or (wanted is not None and room not in wanted):
            continue
        row = [_tile(old, f"before  {stem}"), _tile(new, f"after  {stem}")]
        path = out_dir / f"{stem}.jpg"
        grid([row], max_side=max_side).save(path, quality=85)
        written.append(path)
    return written
