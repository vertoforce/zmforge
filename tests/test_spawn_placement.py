"""Every generated AI spawn is placed by its spawn point, never teleported
in the frame it was spawned (the stock spawn
code undoes the teleport and sends the boss to a random riser;
:func:`zmforge.script.tricks.spawn_point_lines`)."""

from __future__ import annotations

import re

from zmforge.script.bosses import Boss, boss_script, boss_strings
from zmforge.script.tricks import closet_ambush, job_creation_on_fire, spawn_point_lines

_SPAWN = re.compile(r"(\w+)\s*=\s*zombie_utility::spawn_zombie\(([^;]*)\);")
_MOVE = re.compile(r"\b(\w+)\s+(?:forceteleport|teleport|setorigin)\s*\(", re.I)
_WAIT = re.compile(r"\b(?:wait\b|waittill|wait_till|waittillframeend)", re.I)


def same_frame_teleports(body: str) -> list[str]:
    """Lines that move a just-spawned AI before any wait, in one function body."""
    bad, live = [], set()
    for line in body.split("\n"):
        m = _SPAWN.search(line)
        if m:
            live.add(m.group(1))
            continue
        if _WAIT.search(line):
            live.clear()
            continue
        mv = _MOVE.search(line)
        if mv and mv.group(1) in live:
            bad.append(line.strip())
    return bad


def spawns_without_a_point(body: str) -> list[str]:
    return [m.group(0) for m in _SPAWN.finditer(body) if m.group(2).count(",") < 2]


def test_the_scanner_catches_a_teleport_in_the_spawn_frame() -> None:
    body = 'ai = zombie_utility::spawn_zombie( e, "z" );\nai forceteleport( v, ( 0, 0, 0 ) );'
    assert same_frame_teleports(body) == ["ai forceteleport( v, ( 0, 0, 0 ) );"]
    assert spawns_without_a_point(body)
    later = 'ai = zombie_utility::spawn_zombie( e, "z", s );\nwait 1;\nai forceteleport( v, a );'
    assert same_frame_teleports(later) == [] and spawns_without_a_point(later) == []


def test_every_spawn_zombie_call_in_the_generators_passes_a_spawn_point() -> None:
    """Source-level backstop for a spawn site the test above does not build."""
    from pathlib import Path

    import zmforge
    root = Path(zmforge.__file__).parent
    for path in root.rglob("*.py"):
        for n, line in enumerate(path.read_text().split("\n"), 1):
            if "zombie_utility::spawn_zombie(" in line and "``" not in line and "symbols.py" not in str(path):
                assert re.search(r"spawn_zombie\( *e_spawner, *\"[^\"]+\", *\w+ *\)", line), (path.name, n)


def test_the_spawn_point_walks_in_and_hunts() -> None:
    lines = spawn_point_lines("s", "v", 90.0)
    assert lines[0] == "s = SpawnStruct();"
    assert 's.script_string = "find_flesh";' in lines and "s.angles = ( 0, 90, 0 );" in lines
