"""Conformance checks T1-T5 of spec section 9.3, plus the terrain sidecar.

Terrain is the part of the generator where a wrong number does not crash: it
compiles, loads, and then zombies walk in the air or fall through the floor.
Every test below therefore pins a property the spec states in prose and names
the known-bad item it guards:

* K5 - a column's top is flat over its whole cell; interpolating across it was
  measured to differ from what the generator emits by as much as 50 units.
* K6 - cell indices come from ``floor``, never truncation toward zero, so a
  point one cell outside the low edge is not silently reported as inside.
* K7 - a run whose rounded height is <= 0 is skipped, never emitted as a
  zero-height box (which the box constructor rejects, aborting the terrain).
* E13 - the mesh is padded by one duplicated row and column so its footprint
  equals the column footprint and fills the room.
"""

from __future__ import annotations

import math
import random
import subprocess
import sys

import pytest

from zmforge.blueprint.model import Blueprint
from zmforge.emit import mapfile
from zmforge.mapsource.document import PatchSolid
from zmforge.mapsource.reader import parse_map_text
from zmforge.mapsource.writer import render_map_text
from zmforge.spatial import Point, Span
from zmforge.surfaces.field import HeightField
from zmforge.surfaces.ground import (
    TerrainRecord,
    machine_height,
    prop_sink,
    read_json,
    spawner_height,
)
from zmforge.surfaces.noise import fractal_field
from zmforge.surfaces.patches import (
    DEFAULT_CHUNK,
    column_runs,
    mesh_chunks,
    padded,
)
from zmforge.surfaces.relief import Pad, Relief

CELL = 64.0
#: A non-zero anchor everywhere, so a test can never pass by accident on an
#: origin-anchored grid (the K6 defect hid behind exactly that).
ANCHOR = Point(-256.0, 128.0, 64.0)


def _rolling_field(rows: int, cols: int, *, step: float = 7.0) -> HeightField:
    """A grid with no two neighbours equal, so an off-by-one cell is visible."""
    return HeightField.from_rows(
        [[step * (1 + (row * cols + col) % 11) for col in range(cols)] for row in range(rows)]
    )


def _integer_field(rows: int, cols: int) -> HeightField:
    """Whole-unit heights, where a merged run's rounded top equals ``H`` exactly."""
    return HeightField.from_rows(
        [[float(16 + ((row * 3 + col * 5) % 6) * 8) for col in range(cols)] for row in range(rows)]
    )


# ---------------------------------------------------------------------------
# T1. Columns
# ---------------------------------------------------------------------------
def test_t1_box_count_equals_cells_with_positive_rounded_height() -> None:
    """The blocky style must emit one box per raised cell, merged runs once.

    Counting matters because the brush budget is enforced against it: a style
    that quietly emits extra boxes blows a budget that was checked and passed.
    """
    field = HeightField.from_rows(
        [
            [10.0, 10.0, 10.0, 25.0],
            [0.0, 0.4, 12.0, 12.0],
            [-5.0, 0.0, 0.0, 9.0],
        ]
    )
    runs = column_runs(field, ANCHOR, CELL, merge=True)

    # Expected runs derived independently: walk each row, group consecutive
    # cells that survive the skip threshold and round to the same integer.
    expected = 0
    for row in field.cells:
        col = 0
        while col < len(row):
            if row[col] <= 0.0:
                col += 1
                continue
            last = col
            while (
                last + 1 < len(row)
                and row[last + 1] > 0.0
                and round(row[last + 1]) == round(row[col])
            ):
                last += 1
            if round(row[col]) > 0:
                expected += 1
            col = last + 1

    assert expected == 4  # (10,10,10) (25) (12,12) (9); the 0.4 cell is gone
    assert len(runs) == expected
    assert sum(run.cells for run in runs) == 7

    unmerged = column_runs(field, ANCHOR, CELL, merge=False)
    positive_cells = sum(1 for value in field.values() if value > 0.0)
    assert len(unmerged) == positive_cells


def test_t1_every_box_top_equals_oz_plus_the_cell_height() -> None:
    """A box top that is not ``oz + H`` puts the surface where no lookup expects it.

    Unmerged the top is the exact height; merged it is the run's rounded
    integer, which is what the spec says the merged box carries.
    """
    field = _rolling_field(4, 5, step=6.5)

    for run in column_runs(field, ANCHOR, CELL, merge=False):
        assert run.first_col == run.last_col
        assert run.box.maxs.z == pytest.approx(ANCHOR.z + field.at(run.row, run.first_col))
        assert run.box.mins.z == pytest.approx(ANCHOR.z)
        assert run.box.mins.x == pytest.approx(ANCHOR.x + run.first_col * CELL)
        assert run.box.maxs.x == pytest.approx(ANCHOR.x + (run.last_col + 1) * CELL)
        assert run.box.mins.y == pytest.approx(ANCHOR.y + run.row * CELL)
        assert run.box.maxs.y == pytest.approx(ANCHOR.y + (run.row + 1) * CELL)

    for run in column_runs(field, ANCHOR, CELL, merge=True):
        for col in range(run.first_col, run.last_col + 1):
            assert run.box.maxs.z == pytest.approx(ANCHOR.z + round(field.at(run.row, col)))


def test_t1_a_cell_rounding_to_zero_is_skipped_not_emitted_as_a_flat_box() -> None:
    """K7: quantising a 0.3-unit cell to 0 emitted a box the constructor rejected.

    One such cell aborted the whole terrain in the reference, so the check is
    not "the box is harmless" but "the box never exists".
    """
    field = HeightField.from_rows([[0.3, 0.3, 0.3], [0.3, 40.0, 0.3]])

    runs = column_runs(field, ANCHOR, CELL, merge=True)

    assert len(runs) == 1, "only the 40-unit cell rounds to a positive height"
    assert runs[0].height == 40.0
    assert all(run.box.maxs.z > run.box.mins.z for run in runs)
    assert all(run.height > 0.0 for run in runs)

    # And nothing in the emitted blueprint either (the path that aborted).
    blueprint = Blueprint("k7", seed="k7")
    terrain = blueprint.add_terrain(field, ANCHOR, CELL, style="columns", lift=0.0)
    assert len(terrain.runs) == 1
    assert all(run.top_z > ANCHOR.z for run in terrain.runs)


def test_t1_a_merged_run_that_rounds_to_zero_is_skipped_as_a_whole() -> None:
    """K7 on the merged path: the defect was in run quantisation, not per cell."""
    field = HeightField.from_rows([[0.3, 0.4, 0.2, 0.49]])

    assert column_runs(field, ANCHOR, CELL, merge=True) == []


# ---------------------------------------------------------------------------
# T2. Mesh
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def mesh_case() -> tuple[HeightField, list, int]:
    """A 7x10 field chunked at k=4, giving 3x2 chunks including short ones."""
    field = _rolling_field(7, 10)
    chunk = 4
    return field, mesh_chunks(field, ANCHOR, CELL, chunk), chunk


def test_t2_control_points_per_chunk_never_exceed_k_plus_one_squared(mesh_case) -> None:
    """The engine's per-patch limit is unverified; real files stop at 9 a side.

    Going over it is the kind of thing that compiles on one machine and is
    rejected on another, so the ceiling is asserted rather than assumed.
    """
    field, chunks, chunk = mesh_case
    for grid in chunks:
        assert grid.width <= chunk + 1
        assert grid.height <= chunk + 1
        assert grid.width * grid.height <= (chunk + 1) ** 2
        assert grid.width >= 2 and grid.height >= 2

    default_grids = mesh_chunks(_rolling_field(20, 20), ANCHOR, CELL)
    assert all(
        g.width <= DEFAULT_CHUNK + 1 and g.height <= DEFAULT_CHUNK + 1 for g in default_grids
    )


def test_t2_adjacent_chunks_share_edge_control_points_exactly(mesh_case) -> None:
    """Shared edges must be identical points, not merely close.

    A sub-unit mismatch opens a seam the player can see through and the
    navmesh generator can fall through; nothing rounds it away later.
    """
    field, chunks, chunk = mesh_case
    grid = padded(field)
    starts_x = list(range(0, grid.cols - 1, chunk))
    starts_y = list(range(0, grid.rows - 1, chunk))
    lanes = len(starts_y)
    assert len(chunks) == len(starts_x) * lanes

    for ix in range(len(starts_x)):
        for iy in range(lanes):
            here = chunks[ix * lanes + iy]
            if iy + 1 < lanes:  # neighbour along +Y shares the last inner line
                below = chunks[ix * lanes + iy + 1]
                for outer in range(here.width):
                    assert here.point(outer, here.height - 1) == below.point(outer, 0)
            if ix + 1 < len(starts_x):  # neighbour along +X shares the last group
                right = chunks[(ix + 1) * lanes + iy]
                assert here.points[-1] == right.points[0]


def test_t2_chunk_footprints_cover_the_padded_grid_of_n_cells(mesh_case) -> None:
    """E13: N heights span N-1 cells, so the mesh is padded to fill the room.

    Without the duplicated row and column the terrain stops one cell short of
    the wall on the high-X and high-Y sides and the player sees the void.
    """
    field, chunks, chunk = mesh_case
    expect_max_x = ANCHOR.x + field.cols * CELL
    expect_max_y = ANCHOR.y + field.rows * CELL

    xs = sorted({(g.points[0][0].x, g.points[-1][0].x) for g in chunks})
    ys = sorted({(g.points[0][0].y, g.points[0][-1].y) for g in chunks})
    assert xs[0][0] == pytest.approx(ANCHOR.x)
    assert ys[0][0] == pytest.approx(ANCHOR.y)
    assert xs[-1][1] == pytest.approx(expect_max_x)
    assert ys[-1][1] == pytest.approx(expect_max_y)
    for before, after in zip(xs, xs[1:]):  # tiling, no gap and no overlap
        assert before[1] == pytest.approx(after[0])
    for before, after in zip(ys, ys[1:]):
        assert before[1] == pytest.approx(after[0])

    grid = padded(field)
    assert grid.rows == field.rows + 1 and grid.cols == field.cols + 1
    assert grid.row(grid.rows - 1) == grid.row(grid.rows - 2)
    assert grid.column(grid.cols - 1) == grid.column(grid.cols - 2)


def test_t2_chunk_outer_index_runs_along_x_and_inner_along_y(mesh_case) -> None:
    """Spec 1.8: a floor patch built the other way round renders only from below.

    The player then walks on an invisible surface, which is why orientation is
    checked per chunk rather than once for the field.
    """
    field, chunks, chunk = mesh_case
    for grid in chunks:
        for outer in range(grid.width):
            group = grid.points[outer]
            assert len({round(p.x, 9) for p in group}) == 1, "a group must hold one X"
            for before, after in zip(group, group[1:]):
                assert after.y > before.y, "the inner index must increase in +Y"
        for before, after in zip(grid.points, grid.points[1:]):
            assert after[0].x > before[0].x, "the outer index must increase in +X"
        for outer in range(grid.width):
            for inner in range(grid.height):
                point = grid.point(outer, inner)
                col = round((point.x - ANCHOR.x) / CELL)
                row = round((point.y - ANCHOR.y) / CELL)
                expected = padded(field).clamped_at(row, col)
                assert point.z == pytest.approx(ANCHOR.z + expected)


@pytest.fixture(scope="module")
def emitted_document():
    """A mesh-terrain map read back out of rendered map text, not the objects."""
    blueprint = Blueprint("t2", seed="t2")
    blueprint.add_terrain(
        _rolling_field(6, 6),
        ANCHOR,
        CELL,
        style="mesh",
        chunk=4,
        # lift=0 dodges the add_terrain defect recorded below; the lift only
        # shifts Z and none of T2's properties depend on it.
        lift=0.0,
    )
    blueprint.enclose(id="enclosure")
    document = parse_map_text(render_map_text(mapfile.build_document(blueprint)))
    assert document.worldspawn is not None
    return document


@pytest.fixture(scope="module")
def emitted_patches(emitted_document) -> list[PatchSolid]:
    """Terrain patches read back out of rendered map text, not the objects."""
    return [
        solid
        for solid in emitted_document.worldspawn.solids
        if isinstance(solid, PatchSolid)
    ]


def test_t2_a_terrain_mesh_states_no_contents_at_all(emitted_patches) -> None:
    """Solid is the default for a mesh and is never written.

    No chunk emits a second, coincident mesh carrying ``contents weaponClip
    detail;`` as a twin for the navmesh generator to walk on.  Such a twin does
    not hold a player up (a player can fall through the outdoor ground and get
    stuck underneath it), and the shipped sources say why.

    Measured across the shipped ``.map`` files: ``contents solid`` appears
    **zero** times.  In
    ``_prefabs/mp/mp_sector/geo/mp_sector_terrain_north.map``, the walkable
    base layer is 172 patches with no ``contents`` line; 129 decorative
    alpha-blend overlays opt out with ``contents nonColliding;``; and 76
    carry ``contents weaponClip detail ai_nosight;`` (counted).
    Stating ``weaponClip`` *replaces* the default contents rather than adding
    to it, so a coincident weaponClip copy of the ground is at best redundant
    and at worst a bullet-only clip laid over the surface the player stands
    on.  The rule rests on those contents semantics, not on materials: 20 of
    the 76 carry the base layer's own sand.
    """
    patches = emitted_patches
    assert patches, "mesh terrain emitted no patches at all"
    for patch in patches:
        assert patch.contents == ()
        assert patch.kind == "mesh"


def test_t2_every_emitted_patch_faces_up_in_the_text_that_was_written(
    emitted_patches,
) -> None:
    """The one-sided-patch rule, asserted as a normal rather than as an order.

    A patch renders from one side only: the side its surface normal points at.
    Get the winding wrong and the surface is invisible in game, and no stage
    of the build says anything -- the compiler and the linker have no opinion
    about which way a patch faces.

    The test above asserts the *index order* the chunker builds, on the
    objects.  This asserts the *normal* the emitted text carries, after the
    writer has rendered it and the reader has read it back, because the two
    are only the same thing as long as nothing in between reorders a group.

    The convention is measured, not assumed.  Over the 757 ``.map`` files of
    the mod tools' own ``map_source`` tree, read with this package's reader
    (0 unparsed, 12,690 patches), the normal taken as
    ``(outer step) x (inner step)`` points at the open side every time it can
    be classified: **252 of 252** flat patches with ``ceiling`` in the
    material name face **down**, 384 floor-ish ones face **up**, and the 33
    floor-ish ones facing down are all ``t7_metal_floor_catwalk_reinforced``
    (29) and ``t7_metal_grate_flooring`` (4) -- the underside of a walkway.

    So the rule for this package is not "patches face +Z", it is "a patch
    faces the space a player is in".  In this package those are the same
    statement, because the only thing that emits a patch is terrain
    (``mapfile._terrain_patches``) and terrain is always a floor.  Once
    something emits a ceiling or an overhang, this test is the one that has
    to change, and ``PatchGrid.reversed_inner`` is the unused hook for it.
    """
    assert emitted_patches, "mesh terrain emitted no patches at all"
    quads = 0
    for patch in emitted_patches:
        grid = patch.grid
        for outer in range(len(grid) - 1):
            for inner in range(len(grid[outer]) - 1):
                here = grid[outer][inner].position
                along = grid[outer + 1][inner].position
                across = grid[outer][inner + 1].position
                du = (along.x - here.x, along.y - here.y, along.z - here.z)
                dv = (across.x - here.x, across.y - here.y, across.z - here.z)
                normal_z = du[0] * dv[1] - du[1] * dv[0]
                assert normal_z > 0.0, (
                    f"patch quad ({outer}, {inner}) at {here} winds the other "
                    "way: it renders from below and is invisible from the floor"
                )
                quads += 1
    assert quads, "no patch quad had two dimensions to take a normal from"


def test_a_mesh_terrain_is_backed_by_solid_brushes(emitted_document) -> None:
    """A mesh is a surface, not a volume, so something has to be under it.

    The real fix for falling through: whatever the patch collision does, the
    volume under the heightfield is filled with brushes, so there is no void
    to be stuck in.  Treyarch does the same thing at map scale --
    ``zm_giant_geo.map`` line 6008 is one caulk block spanning
    x -7776..6680, y -10624..8880 down to z -288.
    """
    from zmforge.mapsource.document import BrushSolid, PatchSolid

    world = emitted_document.worldspawn
    patches = [s for s in world.solids if isinstance(s, PatchSolid)]
    fill = [
        s
        for s in world.solids
        if isinstance(s, BrushSolid)
        and {f.material for f in s.facets} == {"caulk"}
        and s.contents == ("detail",)
    ]
    assert patches and fill

    # Under every control point of every patch there is fill, and its top is
    # close under the surface rather than far below it: a flat slab under a
    # hill leaves a pocket a player can stand in, which is the same bug.
    def top_under(x: float, y: float) -> float | None:
        best = None
        for solid in fill:
            zs = [p.z for f in solid.facets for p in f.points]
            xs = [p.x for f in solid.facets for p in f.points]
            ys = [p.y for f in solid.facets for p in f.points]
            if min(xs) - 1e-6 <= x <= max(xs) + 1e-6 and min(ys) - 1e-6 <= y <= max(ys) + 1e-6:
                best = max(zs) if best is None else max(best, max(zs))
        return best

    for patch in patches:
        for group in patch.grid:
            for vertex in group:
                lid = top_under(vertex.position.x, vertex.position.y)
                assert lid is not None, (vertex.position.x, vertex.position.y)
                # Never above the surface, and never a player's height below it.
                assert lid <= vertex.position.z + 1e-6
                assert vertex.position.z - lid < 72.0


def test_every_map_gets_a_trigger_hurt_under_it(emitted_document) -> None:
    """The floor of last resort, and it is not optional.

    The player did not fall out of the map, they fell *into* it and were stuck
    alive under the terrain with nothing to kill or reset them.  Shipped
    practice is a ``trigger_hurt`` brush volume: six occurrences across the
    724 shipped ``.map`` files, two each in ``zm_giant_geo.map``,
    ``mp_sector_geo.map`` and ``mp_combine_geo.map``, always material
    ``trigger``.  ``zm_giant_geo.map`` entity 2 is ``"dmg" "1000"``,
    ``"script_hazard" "false"``, ``"_color" "1 0.3 0.1"``.  There is no
    fell-out-of-world handler in ``share/raw/scripts`` at all; the engine
    raises MOD_TRIGGER_HURT and the scripts only react to it.
    """
    catchers = [
        e for e in emitted_document.entities if e.value("classname") == "trigger_hurt"
    ]
    assert len(catchers) == 1
    catcher = catchers[0]
    assert catcher.value("dmg") == "1000"
    assert catcher.value("script_hazard") == "false"
    assert catcher.solids
    for solid in catcher.solids:
        assert {f.material for f in solid.facets} == {"trigger"}

    # It sits under everything walkable, and inside the sky shell rather than
    # outside it, so nothing can pass it without leaving sealed space.
    from zmforge.mapsource.document import PatchSolid

    lid = max(
        p.z for solid in catcher.solids for f in solid.facets for p in f.points
    )
    floor = min(
        p.z for solid in catcher.solids for f in solid.facets for p in f.points
    )
    ground = min(
        vertex.position.z
        for solid in emitted_document.worldspawn.solids
        if isinstance(solid, PatchSolid)
        for group in solid.grid
        for vertex in group
    )
    assert lid < ground
    sky = [
        p.z
        for solid in emitted_document.worldspawn.solids
        for f in getattr(solid, "facets", ())
        if f.material == "sky"
        for p in f.points
    ]
    assert min(sky) <= floor


def test_t2_no_emitted_terrain_patch_uses_caulk(emitted_patches) -> None:
    """E9: a caulked patch renders black and trips the compiler's caulk banner.

    The fill under the terrain is caulk, and it is brushes, never patches --
    which is the distinction this test keeps honest.
    """
    for patch in emitted_patches:
        assert "caulk" not in patch.material.lower()
        assert patch.material


def test_t2_emitted_patch_grids_respect_the_size_and_orientation_rules(emitted_patches) -> None:
    """The same T2 shape rules, verified on what actually reaches the file."""
    for patch in emitted_patches:
        assert patch.width <= 5 and patch.height <= 5
        assert patch.width * patch.height <= 25
        for group in patch.grid:
            for before, after in zip(group, group[1:]):
                assert after.position.y > before.position.y
        for before, after in zip(patch.grid, patch.grid[1:]):
            assert after[0].position.x > before[0].position.x


# ---------------------------------------------------------------------------
# T3. Lookup, columns
# ---------------------------------------------------------------------------
def test_t3_column_lookup_reads_the_flat_cell_top() -> None:
    """K5: bilinear sampling drifted up to 50 units from the written brush top.

    Whole-unit heights are used so a merged run's rounded top is the cell's
    own height, and the emitted geometry and the lookup can be compared
    number for number.
    """
    field = _integer_field(6, 8)
    record = TerrainRecord(anchor=ANCHOR, cell=CELL, heights=field, style="columns")
    tops = {
        (run.row, col): run.top_z
        for run in column_runs(field, ANCHOR, CELL, merge=True)
        for col in range(run.first_col, run.last_col + 1)
    }
    assert len(tops) == field.rows * field.cols, "this fixture raises every cell"

    rng = random.Random(20260917)
    for _ in range(100):
        row = rng.randrange(field.rows)
        col = rng.randrange(field.cols)
        x = ANCHOR.x + (col + rng.uniform(0.001, 0.999)) * CELL
        y = ANCHOR.y + (row + rng.uniform(0.001, 0.999)) * CELL
        sample = record.sample(x, y)
        assert sample.found
        assert abs(sample.z - tops[(row, col)]) <= 1e-6

    # The flatness itself: two points in one cell agree even where the
    # neighbouring cells differ, which is what interpolation would break.
    left = record.sample(ANCHOR.x + 0.02 * CELL, ANCHOR.y + 0.5 * CELL)
    right = record.sample(ANCHOR.x + 0.98 * CELL, ANCHOR.y + 0.5 * CELL)
    assert left.z == right.z == ANCHOR.z + field.at(0, 0)
    assert field.at(0, 1) != field.at(0, 0), "the fixture must have a step here"


def test_t3_a_point_one_cell_outside_the_low_edge_is_not_found() -> None:
    """K6: ``int()`` mapped (-30, -30) to cell (0, 0) and called it inside.

    Truncation toward zero makes the whole band one cell below the low edges
    report a surface that is not there, so entities were placed off the map.
    """
    field = _integer_field(4, 4)
    at_origin = TerrainRecord(
        anchor=Point(0.0, 0.0, 0.0), cell=CELL, heights=field, style="columns"
    )

    outside = at_origin.sample(-30.0, -30.0)
    assert outside.found is False, "floor(-30/64) is -1, not 0"
    assert outside.z == 0.0
    assert "outside the terrain footprint" in outside.message

    for x, y in ((-1.0, 10.0), (10.0, -1.0), (-0.001, -0.001)):
        assert at_origin.sample(x, y).found is False
    assert at_origin.sample(0.0, 0.0).found is True

    # Same defect on the mesh path and on a negative anchor.
    mesh = TerrainRecord(anchor=ANCHOR, cell=CELL, heights=field, style="mesh")
    assert mesh.sample(ANCHOR.x - 30.0, ANCHOR.y - 30.0).found is False
    assert mesh.sample(ANCHOR.x + 1.0, ANCHOR.y + 1.0).found is True
    # The high edges are exclusive at exactly N*c, the first point past the grid.
    assert mesh.sample(ANCHOR.x + field.cols * CELL, ANCHOR.y).found is False


def test_t3_placement_helpers_sit_on_the_column_top() -> None:
    """Spawners clear the surface, machines sit on it, props sink with slope."""
    field = _integer_field(4, 4)
    record = TerrainRecord(anchor=ANCHOR, cell=CELL, heights=field, style="columns")
    sample = record.sample(ANCHOR.x + 0.5 * CELL, ANCHOR.y + 0.5 * CELL)

    assert spawner_height(sample) == pytest.approx(sample.z + 4.0)
    assert machine_height(sample) == sample.z
    assert prop_sink(sample) <= sample.z
    assert sample.z - prop_sink(sample) <= 8.0


# ---------------------------------------------------------------------------
# T4. Lookup, mesh
# ---------------------------------------------------------------------------
def test_t4_mesh_lookup_returns_the_control_height_at_every_control_point() -> None:
    """A control point is the one place the surface height is known exactly.

    Any offset there means every interpolated point inherits it, and props
    placed on the mesh float or sink across the whole field.
    """
    field = _rolling_field(5, 6)
    record = TerrainRecord(anchor=ANCHOR, cell=CELL, heights=field, style="mesh")

    for row in range(field.rows):
        for col in range(field.cols):
            sample = record.sample(ANCHOR.x + col * CELL, ANCHOR.y + row * CELL)
            assert sample.found
            assert sample.z == pytest.approx(ANCHOR.z + field.at(row, col), abs=1e-9)

    # E13's duplicated border: just inside the high edges the surface is flat
    # at the last real height, which is what the index clamping reproduces.
    edge = record.sample(
        ANCHOR.x + field.cols * CELL - 1e-6, ANCHOR.y + field.rows * CELL - 1e-6
    )
    assert edge.found
    assert edge.z == pytest.approx(ANCHOR.z + field.at(field.rows - 1, field.cols - 1))
    assert edge.spread == pytest.approx(0.0), "the padded border cell is flat"


def test_t4_mesh_lookup_is_linear_along_cell_edges() -> None:
    """Bilinear matches the engine's triangulation exactly only on the edges.

    Inside a quad the true surface is two triangles whose diagonal is
    unverified, so the edges are the part a test can pin.
    """
    field = _rolling_field(4, 4)
    record = TerrainRecord(anchor=ANCHOR, cell=CELL, heights=field, style="mesh")

    for row, col in ((0, 0), (1, 2), (2, 1)):
        h00 = field.at(row, col)
        h10 = field.at(row, col + 1)
        h01 = field.at(row + 1, col)
        for t in (0.0, 0.125, 0.5, 0.75, 1.0 - 1e-9):
            along_x = record.sample(
                ANCHOR.x + (col + t) * CELL, ANCHOR.y + row * CELL
            )
            assert along_x.z == pytest.approx(ANCHOR.z + h00 + (h10 - h00) * t, abs=1e-6)
            along_y = record.sample(
                ANCHOR.x + col * CELL, ANCHOR.y + (row + t) * CELL
            )
            assert along_y.z == pytest.approx(ANCHOR.z + h00 + (h01 - h00) * t, abs=1e-6)


def test_t4_mesh_lookup_never_leaves_the_range_of_the_four_corners() -> None:
    """A surface that overshoots its own control points is not the mesh.

    Overshoot is how a smoothed (curve) reading of a mesh patch shows up, and
    it would put the walkable surface above the geometry the player sees.
    """
    field = _rolling_field(6, 6, step=13.0)
    record = TerrainRecord(anchor=ANCHOR, cell=CELL, heights=field, style="mesh")
    rng = random.Random(4242)

    for _ in range(300):
        col = rng.randrange(field.cols)
        row = rng.randrange(field.rows)
        fx = rng.random()
        fy = rng.random()
        sample = record.sample(
            ANCHOR.x + (col + fx) * CELL, ANCHOR.y + (row + fy) * CELL
        )
        corners = [
            field.clamped_at(row, col),
            field.clamped_at(row, col + 1),
            field.clamped_at(row + 1, col),
            field.clamped_at(row + 1, col + 1),
        ]
        assert sample.found
        assert ANCHOR.z + min(corners) - 1e-9 <= sample.z <= ANCHOR.z + max(corners) + 1e-9
        assert sample.spread == pytest.approx(max(corners) - min(corners))


# ---------------------------------------------------------------------------
# T5. Post-processing
# ---------------------------------------------------------------------------
def test_t5_every_relief_pass_is_a_no_op_at_its_default() -> None:
    """A filter that changes the field when nobody asked silently rewrites terrain.

    The record then no longer describes what was emitted, and every later
    placement reads the wrong heights.
    """
    field = _rolling_field(6, 7)

    assert Relief().applied_to(field, ANCHOR, CELL).cells == field.cells
    for relief in (
        Relief(coverage=None),
        Relief(ceiling=None),
        Relief(smooth_passes=0),
        Relief(feather_units=0.0),
        Relief(pads=()),
        Relief(floor_height=12.5),  # floor_height alone does nothing
    ):
        assert relief.applied_to(field, ANCHOR, CELL).cells == field.cells


def test_t5_feathering_brings_boundary_cells_to_floor_height() -> None:
    """Edge feather is what lets terrain meet a wall without a step.

    A boundary cell left raised leaves a lip zombies path around or stick on,
    which is the pathing problem of spec 3.1 in miniature.
    """
    field = HeightField.level(6, 7, 100.0)
    relief = Relief(floor_height=10.0, feather_units=2 * CELL)

    out = relief.applied_to(field, ANCHOR, CELL)

    span = 2
    for row in range(out.rows):
        for col in range(out.cols):
            distance = min(row, col, out.rows - 1 - row, out.cols - 1 - col)
            if distance == 0:
                assert out.at(row, col) == pytest.approx(10.0), "boundary must reach floor"
            elif distance < span:
                assert out.at(row, col) == pytest.approx(10.0 + 90.0 * distance / span)
            else:
                assert out.at(row, col) == pytest.approx(100.0)


def test_t5_pads_flatten_exactly_the_cells_whose_centres_are_within_the_radius() -> None:
    """Pads are what makes terrain meet a door sill; over-reach eats the terrain.

    "Exactly" is the property: one cell too few leaves a step in the doorway,
    one too many flattens the room.
    """
    field = _rolling_field(7, 7, step=9.0)
    pad = Pad(
        centre_x=ANCHOR.x + 3.0 * CELL,
        centre_y=ANCHOR.y + 3.0 * CELL,
        radius=1.5 * CELL,
        height=5.0,
    )
    relief = Relief(pads=(pad,))

    out = relief.applied_to(field, ANCHOR, CELL)

    covered = 0
    for row in range(field.rows):
        for col in range(field.cols):
            cx = ANCHOR.x + (col + 0.5) * CELL
            cy = ANCHOR.y + (row + 0.5) * CELL
            inside = math.hypot(cx - pad.centre_x, cy - pad.centre_y) <= pad.radius
            if inside:
                covered += 1
                assert out.at(row, col) == pytest.approx(5.0)
            else:
                assert out.at(row, col) == pytest.approx(field.at(row, col))
                assert out.at(row, col) != 5.0
    assert covered == 4, "the disc must cover a real, non-empty set of cells"


def test_t5_the_documented_pass_order_is_broken_floor_clamp_smooth_feather_pads() -> None:
    """Order changes the result, so the record can only be reproduced if it is fixed.

    A pad flattened before feathering, for example, is then feathered away and
    the doorway stops meeting the sill.
    """
    field = HeightField.level(5, 5, 100.0)
    pad = Pad(
        centre_x=ANCHOR.x + 0.5 * CELL,
        centre_y=ANCHOR.y + 0.5 * CELL,
        radius=0.25 * CELL,
        height=42.0,
    )
    out = Relief(
        floor_height=0.0, ceiling=80.0, feather_units=CELL, pads=(pad,)
    ).applied_to(field, ANCHOR, CELL)

    assert out.at(0, 0) == pytest.approx(42.0), "pads run last, after feathering"
    assert out.at(2, 2) == pytest.approx(80.0), "the clamp ran"
    assert out.at(0, 2) == pytest.approx(0.0), "a boundary cell the pad misses"


# ---------------------------------------------------------------------------
# Sources and the sidecar record
# ---------------------------------------------------------------------------
def test_fractal_field_is_deterministic_for_a_seed() -> None:
    """The whole generator's "same inputs, same bytes" promise starts here.

    Python's ``hash()`` is salted per process, so a lattice built on it would
    give a different map on every run; the check therefore crosses a process
    boundary with hash randomisation on.
    """
    first = fractal_field(9, 11, seed=1234, peak=192.0)
    second = fractal_field(9, 11, seed=1234, peak=192.0)
    assert first.cells == second.cells
    assert fractal_field(9, 11, seed=1235, peak=192.0).cells != first.cells
    assert first.lowest == pytest.approx(0.0)
    assert first.highest == pytest.approx(192.0)

    script = (
        "from zmforge.surfaces.noise import fractal_field;"
        "print(repr(fractal_field(9, 11, seed=1234, peak=192.0).cells))"
    )
    other_process = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": "random", "PATH": "/usr/bin:/bin"},
    )
    assert other_process.stdout.strip() == repr(first.cells)


def test_terrain_record_round_trips_through_write_json_and_read_json(tmp_path) -> None:
    """Later placements read this sidecar instead of regenerating the terrain.

    If the style or the processed heights do not survive the round trip, the
    lookup silently switches between flat-top and bilinear, which is K5.
    """
    field = fractal_field(6, 8, seed=99, peak=120.0)
    record = TerrainRecord(
        anchor=ANCHOR,
        cell=CELL,
        heights=field,
        style="columns",
        settings={"chunk": 8, "lift": 2.0, "material": "t7_dirt_grassy_forest_ground"},
    )

    path = record.write_json(tmp_path / "map.terrain-record.json")
    back = read_json(path)

    assert back.anchor == record.anchor
    assert back.cell == record.cell
    assert back.style == "columns"
    assert back.heights.cells == field.cells
    assert back.settings == record.settings
    assert back.to_dict() == record.to_dict()

    probe = (ANCHOR.x + 2.5 * CELL, ANCHOR.y + 1.5 * CELL)
    assert back.sample(*probe).z == record.sample(*probe).z


def test_add_terrain_applies_the_default_lift_to_the_record() -> None:
    """Spec 3.2: the lift is recorded so height lookups include it.

    Without the lift a mesh laid on a floor slab z-fights with it; the lift
    only helps if it reaches the record, which is what this pins.
    """
    blueprint = Blueprint("lift", seed="lift")
    terrain = blueprint.add_terrain(
        HeightField.level(3, 3, 24.0), ANCHOR, CELL, style="mesh", lift=2.0
    )
    assert terrain.record.heights.at(0, 0) == pytest.approx(26.0)


def test_z15_fires_when_terrain_has_no_enclosure_to_catch_under_it() -> None:
    """The model-level half of the fall-through rule.

    The emitter generates the fill and the trigger_hurt; what the model can
    say is whether the inputs they need are there.  A map with terrain and no
    enclosure gets no catch volume at all.
    """
    from zmforge.verify import blueprint as check_blueprint

    plan = Blueprint("t2_bare", seed="t2_bare")
    plan.add_terrain(_rolling_field(6, 6), ANCHOR, CELL, style="mesh", chunk=4, lift=0.0)
    errors = [f for f in check_blueprint(plan).errors if f.code == "Z15"]
    assert len(errors) == 1
    assert "trigger_hurt" in errors[0].message

    plan.enclose(id="enclosure")
    assert [f for f in check_blueprint(plan).errors if f.code == "Z15"] == []


# --------------------------------------------------------------------------
# The ground meets the walls
# --------------------------------------------------------------------------
# A terrain mesh that is narrower than the room's interior leaves strips along
# the walls with no ground in them, and a prop placed on the terrain there
# stands tens of units over the floor slab.  So the mesh is stretched onto the
# interior, and Z15 fires on one that stops short of a wall.
def _walled(name: str, bounds, wall: float = 16.0):
    plan = Blueprint(name, seed=name)
    room = plan.add_room(Span.between(*bounds), wall=wall, roofed=False, id="ground")
    return plan, room


def test_a_rooms_ground_is_stretched_onto_its_interior() -> None:
    """Ten cells of 96 inside a 992-unit interior."""
    plan, room = _walled("fit", ((1600, -576, 0), (2624, 448, 912)))
    terrain = plan.add_terrain(
        HeightField.level(10, 10, 32.0), Point(1624, -552, 16), 96.0, lift=0.0
    )
    plan.enclose(id="enclosure")

    plan_box = terrain.record.footprint
    assert (plan_box.mins.x, plan_box.maxs.x) == (
        room.interior.mins.x,
        room.interior.maxs.x,
    )
    assert (plan_box.mins.y, plan_box.maxs.y) == (
        room.interior.mins.y,
        room.interior.maxs.y,
    )
    assert terrain.record.x_cell == pytest.approx(99.2)
    assert terrain.record.square_cells


def test_the_stretched_ground_answers_at_the_wall_itself() -> None:
    """Sampling the last unit before a wall is the query a prop placed there makes."""
    plan, room = _walled("edge", ((1600, -576, 0), (2624, 448, 912)))
    terrain = plan.add_terrain(
        HeightField.level(10, 10, 32.0), Point(1624, -552, 16), 96.0, lift=0.0
    )
    for x, y in (
        (room.interior.mins.x + 0.5, 0.0),
        (room.interior.maxs.x - 0.5, 0.0),
        (0.0 + 1700.0, room.interior.mins.y + 0.5),
        (0.0 + 1700.0, room.interior.maxs.y - 0.5),
    ):
        sample = terrain.record.sample(x, y)
        assert sample.found, sample.message
        assert sample.z == pytest.approx(48.0)


def test_a_room_that_is_not_square_gets_one_spacing_per_axis() -> None:
    """The grid keeps the row and column count it was given, so the cells differ."""
    plan, room = _walled("oblong", ((0, 0, 0), (1024, 544, 256)))
    terrain = plan.add_terrain(
        HeightField.level(5, 10, 16.0), Point(8, 8, 16), 96.0, lift=0.0
    )
    record = terrain.record
    assert not record.square_cells
    assert record.x_cell == pytest.approx(992 / 10)
    assert record.y_cell == pytest.approx(512 / 5)
    assert record.footprint.maxs.x == pytest.approx(room.interior.maxs.x)
    assert record.footprint.maxs.y == pytest.approx(room.interior.maxs.y)
    assert record.to_dict()["cell_y"] == pytest.approx(512 / 5)
    assert TerrainRecord.from_dict(record.to_dict()).y_cell == record.y_cell


def test_a_patch_of_ground_inside_a_room_is_left_where_it_was_put() -> None:
    """A mound in the middle of a room is not that room's floor."""
    plan, _ = _walled("mound", ((0, 0, 0), (2048, 2048, 256)))
    anchor = Point(512, 512, 16)
    terrain = plan.add_terrain(HeightField.level(4, 4, 16.0), anchor, 64.0, lift=0.0)
    assert terrain.record.anchor == anchor
    assert terrain.record.cell == 64.0
    assert terrain.record.square_cells


def test_z15_fires_when_the_ground_stops_short_of_a_wall() -> None:
    """A mesh that stops short of a wall, on a record built by hand."""
    from zmforge.blueprint.elements import Terrain
    from zmforge.materials import Material
    from zmforge.verify import blueprint as check_blueprint

    plan, _ = _walled("short", ((1600, -576, 0), (2624, 448, 912)))
    plan.add_terrain(
        HeightField.level(10, 10, 32.0), Point(1624, -552, 16), 96.0, lift=0.0
    )
    plan.enclose(id="enclosure")
    assert [f for f in check_blueprint(plan).errors if f.code == "Z15"] == []

    terrain = plan.elements(Terrain)[0]
    terrain.record = TerrainRecord(
        anchor=Point(1624, -552, 16), cell=96.0, heights=HeightField.level(10, 10, 32.0)
    )
    errors = [f for f in check_blueprint(plan).errors if f.code == "Z15"]
    assert len(errors) == 4
    assert {"west", "east", "south", "north"} == {
        word
        for error in errors
        for word in ("west", "east", "south", "north")
        if word in error.message
    }
    assert "24 units" in " ".join(error.message for error in errors)
