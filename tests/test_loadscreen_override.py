"""The per-recipe loading screen, and the link-time 'black' image override."""

from __future__ import annotations

import argparse
import io
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from zmforge.facade import cli
from zmforge.texture.loadscreens import LOADING_SCREENS, loading_screen_for
from zmforge.toolchain import loadscreen_override as ov

COLUMNS = ("baseImage", "semantic", "coreSemantic", "compressionMethod", "streamable", "noMipMaps")
STOCK_BLACK = ("texture_assets\\\\t7_default\\\\default_black_0.tif", "glossMap", "Linear1ch",
               "compressed", 1, 0)
MOD_LOADING = ("texture_assets\\\\menu_T7\\\\loadscreens\\\\img_t7_mod_loading.png", "2d",
               "Linear4ch", "compressed", 0, 1)
CORE_GFX = b"image,$white\r\nimage,black\r\nimage,blacktransparent\r\n"
ZONE = ">class,zm_mod_level\nscriptparsetree,scripts/zm/zm_x.gsc\n"


def _tools(tmp_path: Path) -> Path:
    tools = tmp_path / "tools"
    (tools / "gdtdb").mkdir(parents=True)
    (tools / "zone_source/all/assetlist").mkdir(parents=True)
    (tools / "zone_source/all/assetlist/core_gfx.csv").write_bytes(CORE_GFX)
    zone = tools / "usermaps/zm_x/zone"
    zone.mkdir(parents=True)
    Image.new("RGB", (1920, 1080), (40, 50, 50)).save(zone / "loadingimage.png")
    (tools / "usermaps/zm_x/zone_source").mkdir(parents=True)
    (tools / "usermaps/zm_x/zone_source/zm_x.zone").write_text(ZONE)
    db = sqlite3.connect(tools / "gdtdb/gdt.db")
    db.execute("create table _entity (PK_id integer primary key, name text)")
    cols = ",".join(f'"{c}"' for c in COLUMNS)
    db.execute(f"create table image (PK_id integer primary key, _precalc_md5, _name, "
               f"_derived_bits, {cols})")
    for pk, name, values in ((10, "black", STOCK_BLACK), (11, "img_t7_mod_loading", MOD_LOADING)):
        db.execute("insert into _entity values (?, ?)", (pk, name))
        db.execute(f"insert into image values (?, ?, ?, ?, {','.join('?' * len(COLUMNS))})",
                   (pk, "AB-CD", name, b"\xff\x03", *values))
    # A material also called 'black' must not be mistaken for the image.
    db.execute("insert into _entity values (9, 'black')")
    db.commit()
    db.close()
    return tools


def _connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(db)


def _black(tools: Path) -> tuple:
    db = sqlite3.connect(tools / "gdtdb/gdt.db")
    try:
        return db.execute("select * from image where PK_id = 10").fetchone()
    finally:
        db.close()


def test_apply_points_black_at_the_map_png_and_restore_puts_everything_back(tmp_path):
    tools = _tools(tmp_path)
    before = _black(tools)
    zone = tools / "usermaps/zm_x/zone_source/zm_x.zone"

    done = ov.apply(tools, "zm_x", connect=_connect)

    row = dict(zip(("PK_id", "_precalc_md5", "_name", "_derived_bits", *COLUMNS), _black(tools)))
    assert row["baseImage"] == ov.base_image("zm_x")
    assert (row["semantic"], row["coreSemantic"], row["noMipMaps"]) == ("2d", "Linear4ch", 1)
    assert (row["compressionMethod"], row["streamable"]) == ("uncompressed", 1)
    assert row["_name"] == "black" and row["_precalc_md5"] != "AB-CD"
    copy = tools / "texture_assets/zmforge_loadscreens/zm_x_loading.png"
    assert copy.read_bytes() == (tools / "usermaps/zm_x/zone/loadingimage.png").read_bytes()
    assert b"\r\n//image,black\r\n" in (tools / ov.CORE_GFX).read_bytes()
    assert zone.read_text().splitlines()[-1] == "image,black"
    assert (tools / "gdtdb" / ov.STATE_NAME).exists()
    assert len(done) == 3

    ov.restore(tools, connect=_connect)

    assert _black(tools) == before
    assert (tools / ov.CORE_GFX).read_bytes() == CORE_GFX
    assert zone.read_text() == ZONE
    assert not (tools / "gdtdb" / ov.STATE_NAME).exists()
    assert ov.restore(tools, connect=_connect) == []


def test_a_new_picture_changes_the_digest(tmp_path):
    tools = _tools(tmp_path)
    with ov.override(tools, "zm_x", connect=_connect):
        first = _black(tools)[1]
    Image.new("RGB", (1920, 1080), (200, 0, 0)).save(tools / "usermaps/zm_x/zone/loadingimage.png")
    with ov.override(tools, "zm_x", connect=_connect):
        second = _black(tools)[1]
    assert first != second


def test_override_restores_when_the_link_raises_and_apply_heals_a_leftover(tmp_path):
    tools = _tools(tmp_path)
    before = _black(tools)
    with pytest.raises(RuntimeError):
        with ov.override(tools, "zm_x", connect=_connect):
            raise RuntimeError("link died")
    assert _black(tools) == before
    assert (tools / ov.CORE_GFX).read_bytes() == CORE_GFX

    # A killed build leaves the state file; the next apply restores first, so
    # it never records the overridden row as the "original".
    ov.apply(tools, "zm_x", connect=_connect)
    ov.apply(tools, "zm_x", connect=_connect)
    ov.restore(tools, connect=_connect)
    assert _black(tools) == before
    assert (tools / ov.CORE_GFX).read_bytes() == CORE_GFX


def test_refuses_an_install_whose_black_row_is_already_commented(tmp_path):
    tools = _tools(tmp_path)
    (tools / ov.CORE_GFX).write_bytes(CORE_GFX.replace(b"image,black\r", b"//image,black\r"))
    with pytest.raises(RuntimeError, match="expected one live"):
        ov.apply(tools, "zm_x", connect=_connect)
    assert not (tools / "gdtdb" / ov.STATE_NAME).exists()


@pytest.mark.parametrize("recipe", sorted(LOADING_SCREENS))
def test_every_registered_loading_screen_is_1920_by_1080_and_stable(recipe):
    blob = loading_screen_for(recipe)
    image = Image.open(io.BytesIO(blob))
    assert image.size == (1920, 1080)
    assert loading_screen_for(recipe) == blob


def test_generate_uses_the_loadscreen_image_never_the_recipe_art(tmp_path, monkeypatch):
    """Presentation rule: the plan (framed by ``zmforge loadscreen``) or a given file."""
    monkeypatch.setenv("ZMFORGE_PRESENTATION_ROOT", str(tmp_path))

    def ns(recipe, image=None, on=True, name="zm_dmv"):
        return argparse.Namespace(recipe=recipe, name=name, loading_image=image,
                                  loading_screen=on)

    assert cli._loading_image(ns("dmv")) is None  # no loadscreen yet: the plan view
    ready = tmp_path / "zm_dmv" / "loadingimage.png"
    ready.parent.mkdir()
    ready.write_bytes(b"png")
    assert cli._loading_image(ns("dmv")) == str(ready)
    assert cli._loading_image(ns("three-room", name="zm_three_room")) is None
    assert cli._loading_image(ns("dmv", "plan")) is None
    assert cli._loading_image(ns("dmv", "/x.png")) == "/x.png"
    assert cli._loading_image(ns("dmv", on=False)) is None


def _assetlist(tools: Path, rows: str) -> Path:
    listing = tools / "usermaps/zm_x/zone_source/all/assetlist/zm_x.csv"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text(rows)
    return listing


def test_packed_accepts_a_cache_hit_and_refuses_a_stale_or_missing_row(tmp_path):
    import os

    tools = _tools(tmp_path)
    # A cache hit: the log has no "Converting image black", but the linker's
    # own assetlist from this link lists the image.  That is enough.
    listing = _assetlist(tools, "image,$white\nimage,black\nxmodel,skybox_default_black\n")
    started = listing.stat().st_mtime - 1
    assert ov.packed(tools, "zm_x", started)
    # The override did not take: the assetlist has no image,black row.
    _assetlist(tools, "image,$white\nxmodel,skybox_default_black\n")
    assert ov.packed(tools, "zm_x", started) is None
    # An assetlist left by an earlier link does not count.
    listing = _assetlist(tools, "image,black\n")
    os.utime(listing, (started - 100, started - 100))
    assert ov.packed(tools, "zm_x", started) is None
    assert ov.packed(tools, "zm_missing", started) is None


def test_check_command_exit_codes(tmp_path):
    tools = _tools(tmp_path)
    marker = tmp_path / "start"
    marker.touch()
    import os

    os.utime(marker, (0, 0))
    _assetlist(tools, "image,black\n")
    assert ov.main(["check", str(tools), "zm_x", "--since-file", str(marker)]) == 0
    _assetlist(tools, "image,$white\n")
    assert ov.main(["check", str(tools), "zm_x", "--since-file", str(marker)]) == 1


# -- a killed --loading-screen build must not leave 'black' swapped ----------

_SIGTERM_DRIVER = r"""
import argparse, os, signal, sys, time
from pathlib import Path
from types import SimpleNamespace
from zmforge.toolchain import build

calls = Path(sys.argv[1])
build._override = lambda command: calls.open("a").write(" ".join(command) + "\n")

class Chain:
    def run_chain(self, name, stages, language):
        if "link" in stages:          # killed (kill <pid>) in the middle of the link
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(30)
        return SimpleNamespace(ok=True, outcomes=[])

args = argparse.Namespace(tools_dir=sys.argv[2], map_name="zm_x", language="english")
build._run_with_loading_screen(Chain(), args, ["compile", "link"])
"""


def test_a_sigterm_inside_the_link_window_still_restores_black(tmp_path):
    import os
    import signal
    import subprocess
    import sys

    calls = tmp_path / "override-calls.txt"
    env = dict(os.environ, ZMFORGE_LOCK_DIR=str(tmp_path / "locks"))
    done = subprocess.run(
        [sys.executable, "-c", _SIGTERM_DRIVER, str(calls), str(tmp_path / "tools")],
        env=env, capture_output=True, timeout=60,
    )
    assert done.returncode == 128 + signal.SIGTERM, done.stderr[-1500:]
    assert calls.read_text().splitlines() == [
        f"set {tmp_path / 'tools'} zm_x", f"restore {tmp_path / 'tools'}"]


def test_a_build_start_restores_a_swap_a_killed_build_left(tmp_path, monkeypatch):
    from zmforge.toolchain import build

    tools = tmp_path / "tools"
    (tools / "gdtdb").mkdir(parents=True)
    calls = []
    monkeypatch.setattr(build, "_override", calls.append)
    monkeypatch.setenv("ZMFORGE_LOCK_DIR", str(tmp_path / "locks"))
    args = argparse.Namespace(tools_dir=str(tools))
    build._restore_leftover_swap(args)
    assert calls == []                              # nothing left over: nothing done
    (tools / "gdtdb" / ov.STATE_NAME).write_text("{}")   # SIGKILL mid-window
    build._restore_leftover_swap(args)
    assert calls == [["restore", str(tools)]]
