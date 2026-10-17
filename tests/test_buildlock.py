"""The build locks: shared global hold, exclusive old callers, the heavy-stage gate."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from zmforge.toolchain import buildlock
from zmforge.toolchain.buildlock import BuildLock, HeavySlot, global_lock


def _holder(path: Path, flag: str) -> subprocess.Popen:
    """A separate process holding flock(1)-style *flag* ('-s' or '-x') on *path*."""
    # -o: the lock stays with flock itself, so killing it frees the lock.
    proc = subprocess.Popen(["flock", "-o", flag, str(path), "sleep", "30"])
    mode = "WRITE" if flag == "-x" else "READ"
    for _ in range(50):
        if proc.pid in buildlock.lock_holders(path, mode=mode):
            return proc
        time.sleep(0.1)
    proc.kill()
    raise AssertionError("holder never took the lock")


def test_build_steps_share_the_global_lock_and_an_old_exclusive_caller_excludes_them():
    path = buildlock.lock_dir() / buildlock.GLOBAL_LOCK_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    other = _holder(path, "-s")                  # another build, holding it shared
    try:
        with global_lock() as mine:              # shared: granted at once
            assert not mine.inherited
    finally:
        other.kill(); other.wait()
    old = _holder(path, "-x")                    # `flock build-out/.radiant.lock cmd`
    try:
        with pytest.raises(TimeoutError):
            global_lock().acquire(timeout=1.5)
    finally:
        old.kill(); old.wait()


def test_a_lock_held_by_an_ancestor_is_lent_and_an_upgrade_is_refused(tmp_path):
    path = tmp_path / "x.lock"
    code = ("import sys; from pathlib import Path; from zmforge.toolchain.buildlock import BuildLock;"
            f"l = BuildLock(Path({str(path)!r}), shared=sys.argv[1] == 'sh');"
            "\ntry:\n    print(l.acquire(timeout=3).inherited)\nexcept RuntimeError:\n    print('refused')")
    for held, asked, expect in (("-x", "sh", "True"), ("-x", "ex", "True"), ("-s", "ex", "refused")):
        out = subprocess.run(["flock", held, str(path), sys.executable, "-c", code, asked],
                             capture_output=True, text=True, timeout=30)
        assert out.stdout.strip() == expect, (held, asked, out.stdout, out.stderr)


def test_the_gate_counts_running_bakes_against_free_vram(monkeypatch):
    monkeypatch.delenv("ZMFORGE_NO_HEAVY_GATE", raising=False)
    monkeypatch.setenv("ZMFORGE_GPU_HEADROOM_MB", "1000")
    monkeypatch.setattr(buildlock, "mem_available_mb", lambda: 10**6)
    monkeypatch.setattr(buildlock.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(buildlock, "gpu_free_mb", lambda: 6999)
    first = HeavySlot("a", vram_mb=2000, cores=1).acquire()      # 2000 + 1000 <= 6999
    second = HeavySlot("b", vram_mb=2000, cores=1).acquire()     # 2000 + 2000 + 1000 <= 6999
    third = HeavySlot("c", vram_mb=2000, cores=1)
    assert "wants 7000" in third._why_not(third.running())      # 6000 + 1000 > 6999
    first.release()
    assert third._why_not(third.running()) is None
    second.release()


def test_a_dead_owners_reservation_is_dropped(monkeypatch):
    slot = HeavySlot("probe")
    slot.dir.mkdir(parents=True, exist_ok=True)
    stale = slot.dir / "123-1.json"
    stale.write_text(json.dumps({"pid": 123, "vram_mb": 9999, "ram_mb": 0, "cores": 0,
                                 "what": "gone"}))
    assert slot.running() == [] and not stale.exists()


def test_no_nvidia_smi_means_one_heavy_stage_at_a_time(monkeypatch):
    monkeypatch.delenv("ZMFORGE_NO_HEAVY_GATE", raising=False)
    monkeypatch.setattr(buildlock, "mem_available_mb", lambda: 10**6)
    monkeypatch.setattr(buildlock.shutil, "which", lambda name: None)
    first = HeavySlot("a", cores=1).acquire()
    second = HeavySlot("b", cores=1)
    assert "one heavy stage at a time" in second._why_not(second.running())
    first.release()
