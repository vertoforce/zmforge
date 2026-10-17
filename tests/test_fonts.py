"""Fonts resolve on any OS: cache, then OS dirs, then a fetched OFL face."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from zmforge import fonts

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def bare_machine(tmp_path, monkeypatch):
    """No OS fonts and an empty cache: what a fresh Windows/macOS user has."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("ZMFORGE_FONT_DIR", str(cache))
    monkeypatch.setattr(fonts, "_os_font_dirs", lambda: [tmp_path / "no-os-fonts"])
    fonts._index.cache_clear()
    yield cache
    fonts._index.cache_clear()


def test_no_hardcoded_os_font_paths_in_the_painter():
    src = (REPO / "src" / "zmforge" / "texture" / "paint.py").read_text(encoding="utf-8")
    assert "/usr/share/fonts" not in src


def test_os_font_found_by_name_in_any_os_dir(tmp_path, monkeypatch, bare_machine):
    win = tmp_path / "Windows" / "Fonts"
    win.mkdir(parents=True)
    (win / "ARIALBD.TTF").write_bytes(b"x")  # case-insensitive, as on Windows
    monkeypatch.setattr(fonts, "_os_font_dirs", lambda: [win])
    assert fonts.resolve("sign", fetch=False) == win / "ARIALBD.TTF"


def test_fetches_the_ofl_face_and_its_licence_on_first_use(monkeypatch, bare_machine):
    fetched = []

    def fake(request, timeout):
        fetched.append(request.full_url)
        return io.BytesIO(b"font-bytes")

    monkeypatch.setattr(fonts.urllib.request, "urlopen", fake)
    path = fonts.resolve("typewriter")
    assert path == bare_machine / "ptmono" / "PTM55FT.ttf" and path.read_bytes() == b"font-bytes"
    assert (bare_machine / "ptmono" / "OFL.txt").is_file()
    assert len(fetched) == 2
    # Second use reads the cache; no network.
    monkeypatch.setattr(fonts.urllib.request, "urlopen", None)
    assert fonts.resolve("typewriter_light") == path


def test_offline_is_one_clear_line(monkeypatch, bare_machine):
    def offline(request, timeout):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(fonts.urllib.request, "urlopen", offline)
    with pytest.raises(fonts.FontMissing) as caught:
        fonts.resolve("sign")
    message = str(caught.value)
    assert "\n" not in message and "'sign'" in message and "go online once" in message


def test_every_download_is_recorded_with_its_licence():
    records = json.loads((REPO / "assets-cache" / "fonts" / "FONTS.json").read_text())
    by_file = {r["file"]: r for r in records}
    for kind, (_names, download) in fonts.FACES.items():
        rec = by_file.get(download.file)
        assert rec is not None, (kind, download.file)
        assert rec["url"] == download.url and rec["licence_url"] == download.licence_url
        assert "Open Font License" in rec["licence"]


def test_painter_uses_the_resolver(monkeypatch, bare_machine):
    pytest.importorskip("PIL")
    from zmforge.texture import paint

    monkeypatch.setattr(fonts, "resolve", lambda kind, **k: Path("/nonexistent/x.ttf"))
    with pytest.raises(OSError):
        paint.font("sign", 12)  # reached ImageFont.truetype with the resolved path
    with pytest.raises(KeyError):
        paint.font("no_such_face", 12)
