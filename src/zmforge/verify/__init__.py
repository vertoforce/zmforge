"""Checking a map before and after it is written.

Three entry points, matching the three moments a mistake can be caught:

``blueprint``
    model-level, before anything touches disk, so a wrong zone tag costs a
    message instead of a build;
``files``
    over the text a commit wrote, parsed back with the reader -- the compiler
    reads the text, so the text is what gets checked (spec section 9);
``stages``
    over the build logs, because the compiler exits 0 on a leak and the linker
    never exits 0 at all;
``navmesh_file``
    over ``<map>_navmesh.hkt``, the mesh the compiler built, which is the only
    thing on disk that says where the zombies can walk.

Every finding carries the spec's own check label as its ``code`` (``F7``,
``G9``, ``Z10``), so a failure points at the paragraph that explains it.  The
``N`` and ``L`` codes of :mod:`~zmforge.verify.documented` are the exception:
those point at Treyarch's own shipped documentation instead.

:func:`run_all` is the fourth entry point and runs the other three, scoring
every row of :data:`~zmforge.verify.registry.CHECKS` -- including the rows
nothing automates and the rows this caller had no evidence for.
``docs/playable-map-requirements.md`` is the prose against that table.
"""

from __future__ import annotations

from .coverage import FAIL, MANUAL, PASS, SKIP, WARN, Audit, Outcome, run_all
from .documented import (
    check_light_lod,
    check_nav_apertures,
    check_navmesh_geometry,
    check_pathing_width,
    check_step_height,
    check_walkable_slope,
)
from .files import (
    check_client_script,
    check_gameplay,
    check_declarations,
    check_manifest,
    check_map_text,
    check_presentation,
    check_prop_layout_text,
    check_purchase_text,
    check_script_soundness,
    check_linked_sound_audio,
    check_packed_sound,
    check_sound_bank,
    deps_audio_files,
    packed_bank_evidence,
    check_server_script,
    check_localized_strings,
    check_written_files,
)
from .hanging import check_nothing_hangs
from .hkt import NavmeshUnreadable, RawNavMesh, read_navmesh, read_navmesh_bytes
from .model import check_blueprint, check_prop_layout
from .navmesh import NavFace, NavMesh, check_navmesh, check_navmesh_file
from .playtest import (
    check_blueprint_playtest,
    check_files_playtest,
    check_route_props,
)
from .approach import check_interactive_approach, dressed_flood
from .climb import check_zombie_climb, zombie_flood
from .reachability import check_reachability, flood_from_spawn
from .registry import BY_CODE, CHECKS, CODES, Check, automated, manual
from .report import Finding, Report, error, warning
from .stages import check_outcomes, check_stage_evidence

__all__ = [
    "Audit",
    "Check",
    "Finding",
    "Outcome",
    "Report",
    "BY_CODE",
    "CHECKS",
    "CODES",
    "PASS",
    "FAIL",
    "WARN",
    "SKIP",
    "MANUAL",
    "automated",
    "manual",
    "run_all",
    "error",
    "warning",
    "blueprint",
    "files",
    "stages",
    "check_blueprint",
    "check_map_text",
    "check_gameplay",
    "check_server_script",
    "check_client_script",
    "check_declarations",
    "check_manifest",
    "check_presentation",
    "check_purchase_text",
    "check_script_soundness",
    "check_linked_sound_audio",
    "check_packed_sound",
    "check_sound_bank",
    "deps_audio_files",
    "packed_bank_evidence",
    "check_localized_strings",
    "check_written_files",
    "check_prop_layout",
    "check_prop_layout_text",
    "check_stage_evidence",
    "check_outcomes",
    "check_blueprint_playtest",
    "check_files_playtest",
    "check_route_props",
    "check_nothing_hangs",
    "check_reachability",
    "check_zombie_climb",
    "check_interactive_approach",
    "dressed_flood",
    "zombie_flood",
    "flood_from_spawn",
    "NavFace",
    "NavMesh",
    "NavmeshUnreadable",
    "RawNavMesh",
    "check_navmesh",
    "check_navmesh_file",
    "read_navmesh",
    "read_navmesh_bytes",
    "navmesh_file",
    "check_navmesh_geometry",
    "check_step_height",
    "check_nav_apertures",
    "check_walkable_slope",
    "check_pathing_width",
    "check_light_lod",
]


def blueprint(model, *, strict_materials: bool = False) -> Report:
    """Model-level checks (spec 8.4, ``verify.blueprint``)."""
    return check_blueprint(model, strict_materials=strict_materials)


def files(
    project, *, strict_materials: bool = False, presentation: bool = True,
    player_slots: int | None = None,
) -> Report:
    """Static checks over the files a project committed.

    ``presentation`` is what a caller that committed with
    ``loading_screen=False`` passes as ``False``: the two PNGs are then
    absent on purpose, and P1/P2 would be reporting the caller's own
    decision back at them as an error.
    """
    paths = project.paths()
    return check_written_files(
        paths["map"],
        paths["server_script"],
        paths["client_script"],
        paths["manifest"],
        map_name=project.name,
        strict_materials=strict_materials,
        loading_image_path=paths["loading_image"] if presentation else None,
        preview_image_path=paths["preview_image"] if presentation else None,
        player_slots=player_slots,
        weapon_table_path=paths.get("weapon_table"),
        localized_strings_path=paths.get("localized_strings"),
        props_gdt_path=paths.get("props_gdt"),
        model_export_dir=paths.get("model_export_dir"),
        collmap_dir=paths.get("collmap_dir"),
        sound_bank_dir=str(project.layout.sound_bank_dir),
        platform_sound_bank_dir=str(
            project.layout.root / "pc" / "raw" / "sound" / "zone"
        ),
        sound_source_dir=str(project.layout.sound_source_dir),
    )


def stages(outcomes) -> Report:
    """Findings read out of the build logs (spec 8.4, ``verify.stages``)."""
    return check_outcomes(outcomes)


def navmesh_file(model, path) -> Report:
    """``H1`` over the navmesh a build wrote, against the model it was built from.

    The fourth moment a mistake can be caught, and the only one that reads what
    the compiler *made* rather than what it was given: the walkers' own mesh.
    """
    return check_navmesh_file(model, path)
