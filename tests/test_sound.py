r"""Custom sound: the bank, the wave file, and the three rules that bite.

Nothing here needs the mod tools. What the tools' own files look like is
pinned by the fixture below, which is a stripped copy of the *shape* of
``share\raw\sound\aliases\user_aliases.csv`` (column names and one example
row), not of Treyarch's data: the real header is read off whatever install
a map is written into, and a test cannot assume one is present.

The build these tests stand in for: ``zm_ringprobe``,
one synthesised alias, compiled and linked under Wine, and its
packed asset list carried ``sound,zm_ringprobe.all``.
"""

from __future__ import annotations

import csv
import io
import wave

import pytest

from zmforge import Project, verify
from zmforge.audio import SAMPLE_RATE, ringing_tone, write_wav
from pathlib import Path

from zmforge.emit.sound import (
    ALIAS_ROW_CEILING,
    FALLBACK_ALIAS_HEADER,
    FALLBACK_REVERB_HEADER,
    CustomSound,
    SoundAlias,
    count_alias_rows,
    read_alias_header,
    render_alias_bank,
    render_localised_bank,
)
from zmforge.recipes import one_room_map

#: The mod tools install, when one is configured.  Only the two
#: files a bank is built from are wanted.
_TOOLS = Path("<bo3-wine>/tools")
INSTALLED_ALIASES = _TOOLS / "share" / "raw" / "sound" / "aliases" / "user_aliases.csv"
INSTALLED_REVERB = _TOOLS / "share" / "raw" / "sound" / "reverb" / "common_reverb.csv"

#: The columns a bank has, in the order the install spells them. Shortened
#: to the ones this package sets plus a couple it does not, because the
#: point of every test here is that a row lines up with *whatever* header
#: the install has, not with a header this repository carries.
HEADER = (
    "Name",
    "Behavior",
    "Storage",
    "FileSpec",
    "FileSpecSustain",
    "Template",
    "Bus",
    "VolMin",
    "VolMax",
    "DistMin",
    "DistMaxDry",
    "DistMaxWet",
    "Looping",
    "FadeIn",
    "FadeOut",
    "RowSourceLineNumber",
)


def _install(tmp_path, *, header=HEADER):
    """A tools root with the files a bank and its companions are built from.

    Two of them: the alias header, and the reverb table the linker refuses
    to link without (``ERROR: reverb failed to load for zone <map>``).
    """
    aliases = tmp_path / "share" / "raw" / "sound" / "aliases"
    aliases.mkdir(parents=True)
    (aliases / "user_aliases.csv").write_text(
        ",".join(header) + "\r\n", encoding="utf-8"
    )
    reverb = tmp_path / "share" / "raw" / "sound" / "reverb"
    reverb.mkdir(parents=True)
    (reverb / "common_reverb.csv").write_text(
        "Name,MasterReturn\r\ncinematic,-18\r\n", encoding="utf-8"
    )
    return tmp_path


def _sound(name: str = "zmf_ring_loop") -> CustomSound:
    tone = ringing_tone(seconds=0.25)
    return CustomSound(
        alias=SoundAlias(
            name=name,
            wav=f"zm_ringprobe\\{name}.wav",
            template="EVT_EVENT_3D_MOD",
            looping=True,
        ),
        wav_bytes=tone.wav,
        credit=f"synthesised by zmforge.audio: {tone.description}",
    )


# ---------------------------------------------------------------- the format
def test_the_header_is_read_from_the_install_not_carried_here(tmp_path) -> None:
    root = _install(tmp_path, header=("Name", "Behavior", "Storage", "FileSpec", "Extra"))
    assert read_alias_header(root / "share/raw/sound/aliases/user_aliases.csv") == (
        "Name",
        "Behavior",
        "Storage",
        "FileSpec",
        "Extra",
    )


def test_a_header_from_something_that_is_not_an_alias_table_is_refused(tmp_path) -> None:
    path = tmp_path / "not_aliases.csv"
    path.write_text("a,b,c\r\n", encoding="utf-8")
    with pytest.raises(ValueError, match="alias table"):
        read_alias_header(path)


def test_a_root_that_is_not_an_install_falls_back_to_the_carried_header(tmp_path):
    """A staging tree has none of Treyarch's files and still has to generate.

    A map may be written into a staging tree and copied from there onto the
    machine that runs the tools, so the generator cannot require the install
    to be under the root it writes into.
    """
    assert read_alias_header(tmp_path / "nothing.csv") == FALLBACK_ALIAS_HEADER


@pytest.mark.skipif(
    not INSTALLED_ALIASES.exists(), reason="no local copy of the mod tools"
)
def test_the_carried_header_still_matches_the_install() -> None:
    """A game update that moves a column has to be a failing test, not a bank.

    The install wins whenever it is present, so this failing does not mean a
    bank was written wrong; it means the fallback used for staging trees has
    gone stale and the literal needs updating.
    """
    assert read_alias_header(INSTALLED_ALIASES) == FALLBACK_ALIAS_HEADER


@pytest.mark.skipif(
    not INSTALLED_REVERB.exists(), reason="no local copy of the mod tools"
)
def test_the_carried_reverb_header_still_matches_the_install() -> None:
    import csv as _csv

    with INSTALLED_REVERB.open(encoding="utf-8-sig", newline="") as handle:
        assert tuple(next(_csv.reader(handle))) == FALLBACK_REVERB_HEADER


def test_a_row_fills_the_columns_the_install_has_and_leaves_the_rest_empty() -> None:
    bank = render_alias_bank([_sound().alias], HEADER)
    rows = list(csv.DictReader(io.StringIO(bank)))
    assert len(rows) == 1
    row = rows[0]
    assert row["Name"] == "zmf_ring_loop"
    assert row["FileSpec"] == "zm_ringprobe\\zmf_ring_loop.wav"
    assert row["Template"] == "EVT_EVENT_3D_MOD"
    assert row["Looping"] == "LOOPING"
    # Every column the linker requires carries a value, because the linker
    # does not read the template: a row shaped like Treyarch's own example,
    # with those cells blank, got 108 ERROR lines out of a real link.
    assert row["Bus"] == "BUS_FX"
    assert row["Storage"] == "LOADED"
    # A column it does not require and this alias did not choose stays empty.
    assert row["FileSpecSustain"] == ""


def test_the_bank_is_crlf_like_every_shipped_one() -> None:
    bank = render_alias_bank([_sound().alias], HEADER)
    assert bank.count("\r\n") == 2
    assert "\n\n" not in bank


def test_the_english_companion_is_a_header_and_no_rows() -> None:
    companion = render_localised_bank(HEADER)
    assert count_alias_rows(companion) == 0
    assert companion.startswith("Name,")


def test_a_row_that_sets_a_column_the_install_does_not_have_is_refused() -> None:
    with pytest.raises(ValueError, match="does not have a column"):
        render_alias_bank([_sound().alias], ("Name", "FileSpec"))


def test_two_rows_under_one_name_are_refused() -> None:
    with pytest.raises(ValueError, match="both called"):
        render_alias_bank([_sound().alias, _sound().alias], HEADER)


def test_the_row_ceiling_is_the_measured_one() -> None:
    assert ALIAS_ROW_CEILING == 104_729
    aliases = [
        SoundAlias(name=f"a_{index}", wav="zm_ringprobe\\tone.wav")
        for index in range(ALIAS_ROW_CEILING + 1)
    ]
    with pytest.raises(ValueError, match="ceiling"):
        render_alias_bank(aliases, HEADER)
    assert count_alias_rows(render_alias_bank(aliases[:-1], HEADER)) == ALIAS_ROW_CEILING


def test_a_template_no_mod_carries_is_refused() -> None:
    with pytest.raises(ValueError, match="template_mod.csv"):
        SoundAlias(name="x", wav="a\\b.wav", template="AMB_AMBIENCE_3D")


def test_audio_without_a_credit_is_refused() -> None:
    with pytest.raises(ValueError, match="credit"):
        CustomSound(alias=_sound().alias, wav_bytes=b"RIFF", credit="  ")


# ----------------------------------------------------------------- the audio
def test_the_ring_is_48k_16_bit_mono_as_the_tools_ask_for() -> None:
    tone = ringing_tone(seconds=0.5)
    with wave.open(io.BytesIO(tone.wav), "rb") as handle:
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getsampwidth() == 2
        assert handle.getnchannels() == 1
        assert handle.getnframes() == tone.frames


def test_the_ring_loops_without_a_step_at_the_seam() -> None:
    """A loop that ends mid-cycle clicks on every repeat.

    The last sample and the first have to be close enough that the jump is
    smaller than one cycle's worth of movement, which is what a whole number
    of cycles buys.
    """
    tone = ringing_tone(seconds=1.0)
    with wave.open(io.BytesIO(tone.wav), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    samples = [
        int.from_bytes(frames[i : i + 2], "little", signed=True)
        for i in range(0, len(frames), 2)
    ]
    # A 4.5 kHz tone sampled at 48 kHz moves a long way between neighbouring
    # samples, so "seamless" cannot mean "the ends are equal".  It means the
    # wrap is no bigger a step than the steps inside the loop already are.
    seam = abs(samples[0] - samples[-1])
    interior = max(abs(b - a) for a, b in zip(samples, samples[1:]))
    assert seam <= interior, (seam, interior)


def test_the_tone_reports_the_frequency_it_actually_holds() -> None:
    tone = ringing_tone(frequency_hz=4_500.0, seconds=2.0)
    assert tone.frequency_hz == pytest.approx(4_500.0, abs=0.5)
    assert (tone.frequency_hz * tone.seconds) % 1 == pytest.approx(0.0, abs=1e-6)


def test_an_amplitude_over_full_scale_is_refused() -> None:
    with pytest.raises(ValueError, match="fraction of full scale"):
        ringing_tone(amplitude=1.5)


def test_samples_outside_the_range_clip_rather_than_wrap() -> None:
    blob = write_wav([2.0, -2.0])
    with wave.open(io.BytesIO(blob), "rb") as handle:
        frames = handle.readframes(2)
    assert int.from_bytes(frames[0:2], "little", signed=True) == 32_767
    assert int.from_bytes(frames[2:4], "little", signed=True) == -32_767


# ------------------------------------------------------------- the whole map
def test_a_map_that_carries_a_sound_writes_bank_companion_wav_and_manifest(tmp_path):
    root = _install(tmp_path)
    blueprint = one_room_map("zm_ringprobe")
    blueprint.add_custom_sound(_sound())
    project = Project.create("zm_ringprobe", root, blueprint=blueprint, overwrite=True)
    result = project.commit(force=True)

    paths = project.paths()
    bank = paths["sound_bank"]
    assert bank.name == "zm_ringprobe.all.alias.sz"
    assert bank.parent == root / "share" / "raw" / "sound" / "zone"
    assert paths["localised_sound_bank"].exists()
    # The five companions the linker opens beside the bank.
    for suffix in (".all.reverb.sz", ".all.ducklist.sz", ".all.ambient.sz",
                   ".all.musiclist.sz", ".all.scriptid.sz"):
        companion = paths[f"sound_table:{suffix}"]
        assert companion.exists(), companion
        assert companion.name == f"zm_ringprobe{suffix}"
    wav = paths["sound_wav:zmf_ring_loop"]
    assert wav == root / "sound_assets" / "zm_ringprobe" / "zmf_ring_loop.wav"
    assert wav.read_bytes()[:4] == b"RIFF"

    manifest = paths["manifest"].read_text(encoding="utf-8")
    assert "sound,zm_ringprobe" in manifest.splitlines()
    assert manifest.count("sound,zm_ringprobe") == 1
    assert count_alias_rows(bank.read_text(encoding="utf-8")) == 1
    assert "Z24" not in {finding.code for finding in result.report}


def test_a_map_with_no_sound_owns_no_bank_and_declares_none(tmp_path) -> None:
    root = _install(tmp_path)
    project = Project.create(
        "zm_quietprobe", root, blueprint=one_room_map("zm_quietprobe"), overwrite=True
    )
    result = project.commit(force=True)
    assert "sound_bank" not in project.paths()
    assert "sound," not in project.paths()["manifest"].read_text(encoding="utf-8")
    assert "Z24" not in {finding.code for finding in result.report}


def test_the_checks_catch_a_wave_file_deleted_after_the_commit(tmp_path) -> None:
    root = _install(tmp_path)
    blueprint = one_room_map("zm_ringprobe")
    blueprint.add_custom_sound(_sound())
    project = Project.create("zm_ringprobe", root, blueprint=blueprint, overwrite=True)
    project.commit(force=True)
    project.paths()["sound_wav:zmf_ring_loop"].unlink()
    report = verify.files(project)
    assert [f.code for f in report.errors if f.code == "Z24"] == ["Z24"]


def test_two_sounds_under_one_name_are_refused() -> None:
    blueprint = one_room_map("zm_ringprobe")
    blueprint.add_custom_sound(_sound())
    with pytest.raises(Exception, match="already carries a sound"):
        blueprint.add_custom_sound(_sound())


# ------------------------------------------------ after the link: is it packed
def _assetinfo(tmp_path, *rows: str):
    path = tmp_path / "zm_ringprobe.csv"
    path.write_text("\r\n".join(rows) + "\r\n", encoding="utf-8")
    return path


def test_the_packed_bank_is_found_in_the_linker_s_own_report(tmp_path) -> None:
    """The row a real link wrote, verbatim."""
    path = _assetinfo(
        tmp_path,
        "1148,material,mc/mtl_x,120,0,||assetlist",
        "1149,sound,zm_ringprobe.all,7179,0,||assetlist",
    )
    assert list(verify.check_packed_sound(path, map_name="zm_ringprobe")) == []


def test_a_bank_absent_from_the_packed_list_is_an_error(tmp_path) -> None:
    path = _assetinfo(tmp_path, "1148,material,mc/mtl_x,120,0,||assetlist")
    report = verify.check_packed_sound(path, map_name="zm_ringprobe")
    assert [f.code for f in report.errors] == ["Z24"]
    assert "silently absent" in report.findings[0].message


def test_a_bank_packed_at_zero_bytes_is_an_error(tmp_path) -> None:
    path = _assetinfo(tmp_path, "1149,sound,zm_ringprobe.all,0,0,||assetlist")
    report = verify.check_packed_sound(path, map_name="zm_ringprobe")
    assert [f.code for f in report.errors] == ["Z24"]


def test_a_report_the_link_never_wrote_is_a_warning_not_an_error(tmp_path) -> None:
    report = verify.check_packed_sound(tmp_path / "nothing.csv", map_name="zm_ringprobe")
    assert [f.code for f in report.warnings] == ["Z24"]
    assert not report.errors


# ------------------------------------ after the link: does the bank hold audio
#
# The crash this guards: the link says everything is fine and the game dies
# loading the level, naming the map's own sound bank.  The link says so
# quietly: it packs the bank and never opens a wave file.
#
# The fixtures below are written here rather than copied from a real link:
# three or four lines in the shape each report uses is all the rule reads.

_POOL_PACKED = "type,limit,total\nmaterial,2048,7\nsound,32,1\nsound_patch,16,0\n"
_POOL_EMPTY = "type,limit,total\nmaterial,2048,7\nsound,32,0\nsound_patch,16,0\n"
_ASSETLIST_PACKED = "material,mc/mtl_wall\nsound,zm_ringprobe\nrawfile,scripts/zm/x.gsc\n"

#: A .deps with the map's alias tables under it and no audio, which is what
#: the crashed build's looked like: unindented asset, indented dependencies.
_DEPS_TABLES_ONLY = (
    "sound,zm_ringprobe,english\n"
    "assetlist,zm_ringprobe\n"
    "\tfile,C:\\tools\\share\\raw\\sound\\zone\\zm_ringprobe.english.alias.sz,1234567800,\n"
    "\tfile,C:\\tools\\share\\raw\\sound\\zone\\zm_ringprobe.all.ducklist.sz,1234567850,\n"
    "errorcount,0\n"
)

#: The same, plus the one line that says the linker read the audio.
_DEPS_WITH_WAVE = _DEPS_TABLES_ONLY.replace(
    "errorcount,0\n",
    "\tfile,C:\\tools\\sound_assets\\zm_ringprobe\\ring_loop.wav,1234567890,\n"
    "errorcount,0\n",
)


def test_a_packed_bank_with_no_audio_in_the_deps_is_an_error() -> None:
    report = verify.check_linked_sound_audio(
        "zm_ringprobe",
        pool_report=_POOL_PACKED,
        asset_list=_ASSETLIST_PACKED,
        deps=_DEPS_TABLES_ONLY,
        label="link, english zone",
    )
    assert [f.code for f in report.errors] == ["Z24"]
    message = report.errors[0].message
    assert "zm_ringprobe" in message
    assert "no audio file" in message
    assert "refuses" in message


def test_a_packed_bank_whose_deps_names_a_wave_passes() -> None:
    report = verify.check_linked_sound_audio(
        "zm_ringprobe",
        pool_report=_POOL_PACKED,
        asset_list=_ASSETLIST_PACKED,
        deps=_DEPS_WITH_WAVE,
    )
    assert list(report) == []


def test_the_asset_list_alone_is_enough_to_say_a_bank_was_packed() -> None:
    """Whichever of the two reports a caller has on hand, the rule applies."""
    report = verify.check_linked_sound_audio(
        "zm_ringprobe", asset_list=_ASSETLIST_PACKED, deps=_DEPS_TABLES_ONLY
    )
    assert [f.code for f in report.errors] == ["Z24"]
    assert "the asset list carries sound,zm_ringprobe" in report.errors[0].message


def test_a_map_that_packs_no_bank_is_left_alone() -> None:
    """A map with no sound of its own has no audio in its deps either."""
    report = verify.check_linked_sound_audio(
        "zm_ringprobe",
        pool_report=_POOL_EMPTY,
        asset_list="material,mc/mtl_wall\n",
        deps=_DEPS_TABLES_ONLY,
    )
    assert list(report) == []


def test_the_deps_section_header_alone_is_not_a_packed_bank() -> None:
    """A link that failed to load the bank still writes that header.

    Measured on a probe map whose link stopped with "sound
    aliases failed to load": the deps carried ``sound,<map>,all``, the pool
    report said zero and neither asset list mentioned sound. That link
    already failed on its own ERROR: line and must not also be accused of
    shipping a silent bank.
    """
    report = verify.check_linked_sound_audio(
        "zm_ringprobe",
        pool_report=_POOL_EMPTY,
        asset_list="",
        deps=_DEPS_TABLES_ONLY,
    )
    assert list(report) == []


def test_a_packed_bank_with_no_deps_to_read_is_a_warning() -> None:
    report = verify.check_linked_sound_audio(
        "zm_ringprobe", pool_report=_POOL_PACKED, deps=""
    )
    assert [f.code for f in report.warnings] == ["Z24"]
    assert not report.errors


def test_the_deps_reader_takes_audio_by_suffix_or_by_folder() -> None:
    deps = (
        "sound,zm_ringprobe,all\n"
        "\tgdt,sound,zm_ringprobe,AA-BB\n"
        "\tasset,material,mc/mtl_wall\n"
        "\tfile,C:\\tools\\share\\raw\\sound\\zone\\zm_ringprobe.all.alias.sz,1234567850,\n"
        "\tfile,C:\\tools\\sound_assets\\zm_ringprobe\\ring_loop.flac,1234567890,aa,bb\n"
        "\tfile,C:\\tools\\sound_assets\\zm_ringprobe\\ring_tail,1234567891,\n"
    )
    found = verify.deps_audio_files(deps)
    assert len(found) == 2
    assert all("sound_assets" in path for path in found)
    # The section headers and the gdt/asset lines are not files.
    assert not [path for path in found if path.endswith(".sz")]


def test_a_deps_line_is_read_by_its_own_shape_not_by_splitting_on_commas() -> None:
    """A path may carry a comma; the timestamp after it is what ends it."""
    deps = "\tfile,C:\\tools\\sound_assets\\ring, mixed\\take_01.wav,1234567890,aa\n"
    assert verify.deps_audio_files(deps) == ["C:\\tools\\sound_assets\\ring, mixed\\take_01.wav"]
