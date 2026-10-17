"""The local prop conversion: LZ4 as export2bin.exe writes it, the install step,
and the gdt.db registrar's match with gdtdb.exe."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from zmforge.props.lz4block import compress
from zmforge.render.propfix import lz4_block_decompress, read_model_bin

TOOLS = Path("<bo3-wine>/tools")
DEPLOYED = TOOLS / "model_export" / "zm_forge_gate"


@pytest.mark.parametrize("size", [0, 1, 12, 13, 100, 5000, 70000])
def test_lz4_round_trip(size):
    rng = random.Random(size)
    words = [bytes(rng.randrange(256) for _ in range(rng.randrange(1, 9))) for _ in range(40)]
    data = b"".join(rng.choice(words) for _ in range(size))[:size]
    assert lz4_block_decompress(compress(data), len(data)) == data


def test_lz4_long_runs_round_trip():
    data = b"\x00" * 3000 + b"abc" * 900 + bytes(range(256)) * 3
    assert lz4_block_decompress(compress(data), len(data)) == data


def _deployed_pairs():
    if not DEPLOYED.is_dir():
        return []
    return [e for e in sorted(DEPLOYED.glob("*.XMODEL_EXPORT"))
            if e.with_suffix(".XMODEL_BIN").is_file()
            and e.with_suffix(".XMODEL_BIN").stat().st_size > 0]


@pytest.mark.skipif(not _deployed_pairs(), reason="no export2bin-written props in the tools tree")
def test_every_deployed_bin_is_reproduced_byte_for_byte():
    """Each .XMODEL_BIN in the tools tree that the Windows tools'
    export2bin.exe wrote comes out identical from the Python writer."""
    from zmforge.props.xmodel_bin import export_to_bin

    differ = []
    for export in _deployed_pairs():
        windows = export.with_suffix(".XMODEL_BIN").read_bytes()
        if export_to_bin(export.read_text(encoding="utf-8")) != windows:
            differ.append(export.stem)
    assert differ == []


@pytest.mark.skipif(not _deployed_pairs(), reason="no export2bin-written props in the tools tree")
def test_lz4_matches_windows_on_payloads():
    for export in _deployed_pairs()[:10]:
        windows = export.with_suffix(".XMODEL_BIN").read_bytes()
        assert compress(read_model_bin(windows)) == windows[9:], export.stem


def _staging(tmp: Path, map_name: str) -> Path:
    root = tmp / "staging"
    models = root / "model_export" / map_name
    models.mkdir(parents=True)
    src = next(iter(_deployed_pairs()), None)
    if src is None:
        pytest.skip("needs one deployed export to stage")
    (models / src.name).write_bytes(src.read_bytes())
    (root / "model_export" / f"{map_name}_props.gdt").write_text(
        '{\n\t"zmf_x" ( "xmodel.gdf" )\n\t{\n\t\t"filename" "a\\\\zmf_x.XMODEL_BIN"\n\t}\n}\n')
    (root / "collmaps").mkdir()
    (root / "collmaps" / "zmf_x.map").write_text("iwmap 4\n")
    (root / "texture_assets" / map_name).mkdir(parents=True)
    (root / "texture_assets" / map_name / "zmf_x_c.tif").write_bytes(b"II*\x00")
    (root / "PROP-CREDITS.md").write_text("credits\n")
    return root


def test_install_copies_what_the_play_copies(tmp_path):
    from zmforge.props.install import install

    staging = _staging(tmp_path, "zm_t")
    tools = tmp_path / "tools"
    first = install(staging, tools, "zm_t", register=False)
    assert first.bins == 1
    for rel in ("share/raw/collmaps/zmf_x.map", "texture_assets/zm_t/zmf_x_c.tif",
                "model_export/zm_t_props.gdt", "usermaps/zm_t/PROP-CREDITS.md"):
        assert (tools / rel).is_file(), rel
    assert len(list((tools / "model_export" / "zm_t").glob("*.XMODEL_BIN"))) == 1
    again = install(staging, tools, "zm_t", register=False)
    assert again.copied == [] and again.unchanged == len(first.copied)


def test_install_refuses_a_gdt_naming_the_text_export(tmp_path):
    from zmforge.props.install import install

    staging = _staging(tmp_path, "zm_t")
    gdt = staging / "model_export" / "zm_t_props.gdt"
    gdt.write_text(gdt.read_text().replace(".XMODEL_BIN", ".XMODEL_EXPORT"))
    with pytest.raises(ValueError):
        install(staging, tmp_path / "tools", "zm_t", register=False)


def test_gdt_entry_line_is_the_closing_brace():
    """gdtdb.exe stores the closing brace's line in _entity._gdt_linenum."""
    from zmforge.texture.gdtdb import parse_gdt

    text = '{\n\t"a" ( "image.gdf" )\n\t{\n\t\t"k" "v"\n\t}\n\t"b" ( "image.gdf" )\n\t{\n\t}\n}\n'
    assert [e.line for e in parse_gdt(text)] == [5, 8]


def test_registrar_refuses_derived_entries(tmp_path):
    from zmforge.texture.gdtdb import register_gdt

    gdt = tmp_path / "d.gdt"
    gdt.write_text('{\n\t"child" [ "parent" ]\n\t{\n\t}\n}\n')
    with pytest.raises(ValueError, match="derived"):
        register_gdt(gdt, tmp_path / "gdt.db", tools_root="C:\\t", relative="d.gdt")
