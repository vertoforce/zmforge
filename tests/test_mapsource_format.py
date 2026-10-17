"""Conformance checks F1-F12 from spec section 9.1, over real emitted text.

Every property here is checked against the *bytes that were written*, not
against the in-memory model that produced them.  That distinction is the whole
point of section 9: the compiler reads the text, so a check that trusts the
document would pass while the file on disk was unloadable.

The fixtures are a real ``Project.commit()`` into a temporary tools root, so a
regression anywhere between blueprint, emit and writer shows up here rather
than in a five-minute compile with no diagnostic.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import pytest

from zmforge import mapsource
from zmforge.mapsource import decimal_token, parse_map_text, render_map_text
from zmforge.mapsource.document import BrushSolid, OpaqueSolid, PatchSolid
from zmforge.mapsource.scalars import NUMBER_RE
from zmforge.project import Project
from zmforge.recipes.layouts import three_room_map
from zmforge.spatial import Point
from zmforge.surfaces.field import HeightField
from zmforge.verify.files import check_map_text

CORPUS = sorted((Path(__file__).parent / "corpus").glob("*.map"))

# A generated number, per spec 1.9: sign, digits, optional fraction, no exponent.
_NUM = r"-?\d+(?:\.\d+)?"
_POINT = rf"\(\s*{_NUM}\s+{_NUM}\s+{_NUM}\s*\)"
#: F8's shape: three point triples, a material, six numbers, the lightmap
#: material, six numbers, then whatever trailing tokens the face carried.
FACE_LINE_RE = re.compile(
    rf"^\s*{_POINT}\s*{_POINT}\s*{_POINT}\s+"
    rf"(?P<material>\S+)(?P<projection>(?:\s+{_NUM}){{6}})\s+"
    rf"(?P<lightmap>\S+)(?P<lightmap_projection>(?:\s+{_NUM}){{6}})"
    rf"(?P<trailing>.*)$"
)
#: The trailing forms spec 1.5 names; anything else is the reader's problem to
#: carry, not the generator's to invent.
KNOWN_TRAILING_RE = re.compile(
    r"^(?:smoothing\s+\S+|decalLayerSort\s+\"[^\"]*\"\s+decalEditorSort\s+-?\d+)?$"
)
ENTITY_COMMENT_RE = re.compile(r"^// entity (\d+)$")
BRUSH_COMMENT_RE = re.compile(r"^// brush (\d+)$")
LAYER_LINE_RE = re.compile(r'^"[^"]*"\s+flags\b')
PAIR_LINE_RE = re.compile(r'^"[^"]+" ".*"$')
TAGGED_LINE_RE = re.compile(r'^(?:guid|layer) ".*"$')
GUID_LINE_RE = re.compile(
    r'^\s*guid "\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}"$'
)
#: Anything that could plausibly be read as a number by a parser, so the F7
#: sweep cannot miss an exponent by only looking where it expects numbers.
NUMERIC_TOKEN_RE = re.compile(r"^[-+]?[0-9.][0-9.eE+-]*$")


# ---------------------------------------------------------------------------
# Fixtures: a real generated map, and a second one that also carries patches.
# ---------------------------------------------------------------------------
def _commit(name: str, blueprint, root: Path) -> str:
    project = Project.create(name, root, blueprint=blueprint)
    project.commit()
    return project.paths()["map"].read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def generated_text(tmp_path_factory) -> str:
    """The text of a brush-only map the generator actually wrote to disk."""
    root = tmp_path_factory.mktemp("tools_brushes")
    return _commit("zm_conformance", three_room_map("zm_conformance"), root)


@pytest.fixture(scope="module")
def patched_text(tmp_path_factory) -> str:
    """A generated map that also contains ``mesh`` patches, for F9.

    ``lift=0`` avoids an unrelated defect in ``blueprint/model.py``; it does not
    affect the text properties under test.
    """
    root = tmp_path_factory.mktemp("tools_patches")
    blueprint = three_room_map("zm_conformance_patch")
    blueprint.add_terrain(
        HeightField.from_rows([[0, 4, 8], [2, 6, 10], [4, 8, 12]]),
        Point(0.0, 0.0, 0.0),
        64.0,
        chunk=3,
        lift=0.0,
    )
    return _commit("zm_conformance_patch", blueprint, root)


@pytest.fixture(scope="module")
def generated_document(generated_text: str):
    return parse_map_text(generated_text)


def _lines(text: str) -> list[str]:
    body = text.split("\n")
    if body and body[-1] == "":
        body.pop()
    return body


# ---------------------------------------------------------------------------
# F1 - F2: the header and the layer table
# ---------------------------------------------------------------------------
def test_f1_header_is_iwmap_4_then_script_startingnumber(generated_text: str) -> None:
    """Radiant refuses a file whose first line is not ``iwmap 4``.

    Line 2 is the format's only quoted-key/unquoted-value line (spec 1.1);
    writing it as an ordinary pair would make the file parse as a map with a
    stray worldspawn key and no starting number.
    """
    lines = _lines(generated_text)
    assert lines[0] == "iwmap 4"
    assert lines[1] == '"script_startingnumber" 0'
    assert check_map_text(generated_text).ok


def test_f2_only_layer_declarations_precede_the_first_entity(
    generated_text: str,
) -> None:
    """Anything else before the first entity is a line Radiant will drop.

    The header region is not free-form: a stray key/value or comment there is
    silently lost on the editor's next save, taking whatever it meant with it.
    """
    lines = _lines(generated_text)
    first_entity = next(
        index for index, line in enumerate(lines) if ENTITY_COMMENT_RE.match(line)
    )
    assert first_entity > 2, "the generator must emit a layer table (spec 1.1)"
    for index in range(2, first_entity):
        line = lines[index]
        assert not line or LAYER_LINE_RE.match(line), (
            f"line {index + 1} is not a layer declaration: {line!r}"
        )
    assert "F2" not in check_map_text(generated_text).codes()


# ---------------------------------------------------------------------------
# F3 - F4: block numbering and entity 0
# ---------------------------------------------------------------------------
def test_f3_entities_and_brushes_are_numbered_consecutively(
    generated_text: str,
) -> None:
    """Gapped numbering is the signature of an append-per-call generator.

    The design this replaces reopened the file for every helper and appended,
    so counters drifted.  The writer renumbers from the document on every save;
    this asserts it actually does, per entity for brushes (spec 1.2).
    """
    expected_entity = 0
    expected_brush = 0
    seen_entities = 0
    for line in _lines(generated_text):
        entity = ENTITY_COMMENT_RE.match(line)
        if entity:
            assert int(entity.group(1)) == expected_entity
            expected_entity += 1
            expected_brush = 0
            seen_entities += 1
            continue
        brush = BRUSH_COMMENT_RE.match(line)
        if brush:
            assert int(brush.group(1)) == expected_brush
            expected_brush += 1
    assert seen_entities > 1
    assert "F3" not in check_map_text(generated_text).codes()


def test_f4_entity_zero_is_the_worldspawn(generated_text, generated_document) -> None:
    """Entity 0 owns the static geometry; the compiler assumes it is worldspawn.

    A map whose first entity is something else compiles into a world with no
    sealed hull, which leaks and fails with no useful diagnostic (spec 1.2).
    """
    first = generated_document.entities[0]
    assert first.classname == "worldspawn"
    assert first.pairs[0][0] == "classname", "classname is conventionally first"
    assert "F4" not in check_map_text(generated_text).codes()


# ---------------------------------------------------------------------------
# F5: guids
# ---------------------------------------------------------------------------
def test_f5_every_entity_and_brush_opens_with_a_unique_upper_case_guid(
    generated_text, generated_document
) -> None:
    """Duplicate or lower-case guids make Radiant merge or reject blocks.

    ``guid`` must be the first line inside the braces of every entity and every
    brush, braced 8-4-4-4-12 upper-case hex (spec 1.2), and unique across the
    file: two blocks sharing one is how a generator that reuses a UUID loses
    geometry in the editor.
    """
    guids: list[str] = []
    for entity in generated_document.entities:
        guids.append(entity.guid)
        guids.extend(solid.guid for solid in entity.solids)
    assert guids, "the map has no blocks to check"
    duplicates = [guid for guid, count in Counter(guids).items() if count > 1]
    assert not duplicates, f"guids used more than once: {duplicates[:5]}"

    lines = _lines(generated_text)
    opened = 0
    for index, line in enumerate(lines):
        if line.strip() != "{":
            continue
        opened += 1
        following = lines[index + 1]
        assert GUID_LINE_RE.match(following), (
            f"block opened at line {index + 1} does not start with a guid: "
            f"{following!r}"
        )
    assert opened == len(guids)
    assert "F5" not in check_map_text(generated_text).codes()


# ---------------------------------------------------------------------------
# F6: key/value lines
# ---------------------------------------------------------------------------
def test_f6_key_value_lines_are_two_quoted_strings(generated_text: str) -> None:
    """Values are always strings, even numeric ones (spec 1.2).

    Emitting ``"zombie_cost" 950`` unquoted is the natural mistake when the
    model holds an int; the entity then loads with the key missing and the
    script reads a default at runtime instead of failing at compile time.
    """
    lines = _lines(generated_text)
    for index, line in enumerate(lines):
        if index == 1 or not line.startswith('"'):
            continue
        if LAYER_LINE_RE.match(line):
            continue
        assert PAIR_LINE_RE.match(line), f"line {index + 1} is not a pair: {line!r}"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("guid ", "layer ")):
            assert TAGGED_LINE_RE.match(stripped), (
                f"guid/layer take an unquoted key and a quoted value: {stripped!r}"
            )
    assert "F6" not in check_map_text(generated_text).codes()


# ---------------------------------------------------------------------------
# F7: number formatting
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fixture_name", ["generated_text", "patched_text"])
def test_f7_no_exponent_notation_anywhere(fixture_name, request) -> None:
    """No real BO3 map contains an exponent, and nobody knows if one parses.

    ``%g``-style formatting produces both ``1e-05`` and six-significant-digit
    rounding (``65536.25`` -> ``65536.2``), so a single careless format string
    silently moves geometry *and* risks a token the compiler may reject with no
    diagnostic (spec 1.9 rule 3).  ``-0`` is the other trap: it is what
    ``sin(pi) * 100`` formats to on any wall built on a zero coordinate.
    """
    text = request.getfixturevalue(fixture_name)
    for index, line in enumerate(text.split("\n")):
        if line.startswith("//"):
            continue
        for raw in line.replace("(", " ").replace(")", " ").split():
            token = raw.strip('"')
            if not token or not NUMERIC_TOKEN_RE.match(token):
                continue
            assert "e" not in token and "E" not in token, (
                f"exponent notation at line {index + 1}: {token!r}"
            )
            assert NUMBER_RE.match(token), (
                f"not a plain decimal at line {index + 1}: {token!r}"
            )
            assert token != "-0", f"negative zero at line {index + 1}"


def test_f7_decimal_token_follows_the_spec_cases() -> None:
    """The writer's number rule, checked on the exact cases spec 1.9 names.

    Each of these is a defect the reference implementation shipped: ``%g``
    turning ``65536.25`` into ``65536.2``, ``repr`` writing ``1e-05``, and
    trigonometric noise landing in the file as ``-0`` or ``1.22e-14``.
    """
    assert decimal_token(16.0) == "16"
    assert decimal_token(65536.25) == "65536.25"
    assert decimal_token(math.sin(math.pi) * 100) == "0"
    assert decimal_token(-0.0) == "0"

    tiny = decimal_token(1e-5)
    assert "e" not in tiny and "E" not in tiny
    assert NUMBER_RE.match(tiny), tiny
    assert float(tiny) == pytest.approx(1e-5)

    # Integers must survive byte-identically (spec 1.9 rule 4).
    for value in (-1536, 0, 1, 65536, -1):
        assert decimal_token(float(value)) == str(value)
    assert decimal_token(-71.964066) == "-71.964066"


def test_f7_parsed_exponents_survive_untouched_but_are_never_generated() -> None:
    """A foreign file's exponent token must come back out spelled the same way.

    ``zm_alien_isolation.map`` really does contain ``-5.5670738e-005``.
    Reformatting a number the caller never touched would rewrite a mapper's
    file; the source text is kept for exactly that reason (spec 1.11).
    """
    kept = mapsource.parse_scalar("-5.5670738e-005")
    assert decimal_token(kept) == "-5.5670738e-005"

    # The same magnitude arrived at by arithmetic has no source text, so it goes
    # out under the generator rule instead: plain decimal, never an exponent.
    computed = decimal_token(float(kept))
    assert "e" not in computed and "E" not in computed
    assert NUMBER_RE.match(computed), computed


# ---------------------------------------------------------------------------
# F8: face lines
# ---------------------------------------------------------------------------
def test_f8_face_lines_are_three_points_a_material_and_twelve_numbers(
    generated_text: str,
) -> None:
    """A short or malformed texture block is a face the compiler skips.

    The tail is positional (spec 1.5): material, six projection numbers,
    ``lightmap_gray``, six more.  Dropping one number shifts every field after
    it, which shows up as untextured geometry rather than as an error.
    """
    faces = 0
    for index, line in enumerate(generated_text.split("\n")):
        stripped = line.strip()
        if not stripped.startswith("(") or stripped == "(":
            continue
        match = FACE_LINE_RE.match(line)
        assert match, f"malformed face line {index + 1}: {stripped!r}"
        assert match.group("lightmap") == "lightmap_gray"
        assert len(match.group("projection").split()) == 6
        assert len(match.group("lightmap_projection").split()) == 6
        trailing = match.group("trailing").strip()
        assert KNOWN_TRAILING_RE.match(trailing), (
            f"the writer must not invent trailing tokens: {trailing!r}"
        )
        faces += 1
    assert faces > 0
    assert "F8" not in check_map_text(generated_text).codes()


def test_f8_default_projection_is_what_radiant_writes(generated_document) -> None:
    """Untouched faces carry ``64 64 0 0 0 0`` / ``16384 16384 0 0 0 0``.

    Spec 1.5's generator rule: keep the numeric tail fixed unless the caller
    supplies all six, so a diff against a Radiant-saved file stays reviewable.
    """
    brushes = [
        solid
        for entity in generated_document.entities
        for solid in entity.solids
        if isinstance(solid, BrushSolid)
    ]
    assert brushes
    for brush in brushes:
        for facet in brush.facets:
            assert facet.projection.as_tuple() == (64, 64, 0, 0, 0, 0)
            assert facet.lightmap_projection.as_tuple() == (16384, 16384, 0, 0, 0, 0)
            assert facet.lightmap == "lightmap_gray"


def test_f8_a_material_scale_reaches_the_first_two_projection_numbers() -> None:
    """A picture is one rectangle laid once, so its two axes differ.

    A photographed wall tiles and one number repeats it.  A poster or a sign is
    a rectangle W x H units that must show its image exactly once, which is the
    projection pair (W, H) -- unsayable while the material carried a single
    scale, because the picture then repeated on whichever axis was longer.
    """
    from zmforge.emit.mapfile import _brush_of
    from zmforge.materials import FaceMaterials, Material
    from zmforge.mapsource.document import Document, Entity
    from zmforge.solids.forms import block
    from zmforge.spatial import Span

    guid = "{00000000-0000-0000-0000-000000000001}"
    picture = Material("t7_concrete_trowelled", 96.0, 48.0)
    brush = _brush_of(
        block(Span(Point(0, 0, 0), Point(96, 8, 48)), FaceMaterials.uniform(picture)),
        guid,
    )
    entity = Entity(guid=guid, pairs=[("classname", "worldspawn")], solids=[brush])
    text = render_map_text(Document(entities=[entity]))

    faces = 0
    for line in text.split("\n"):
        match = FACE_LINE_RE.match(line)
        if not match:
            continue
        assert match.group("projection").split()[:2] == ["96", "48"]
        faces += 1
    assert faces == 6


def test_f8_one_scale_is_still_written_on_both_axes() -> None:
    """``sized(64)`` is the square case and must not have changed shape."""
    from zmforge.emit.mapfile import _surface_projection
    from zmforge.materials import Material

    square = Material("t7_concrete_trowelled").sized(64)
    assert (square.scale, square.scale_v) == (64.0, 64.0)
    assert _surface_projection(square).as_tuple() == (64, 64, 0, 0, 0, 0)
    # a scale set at construction falls back the same way
    assert Material("t7_concrete_trowelled", 20.0).scale_v == 20.0
    assert _surface_projection(Material("t7_concrete_trowelled", 20.0)).as_tuple() == (
        20.0,
        20.0,
        0,
        0,
        0,
        0,
    )
    # and an untouched material still gets Radiant's own default
    assert _surface_projection(Material("t7_concrete_trowelled")).as_tuple() == (
        64,
        64,
        0,
        0,
        0,
        0,
    )
    with pytest.raises(ValueError, match="v scale needs a u scale"):
        Material("t7_concrete_trowelled", scale_v=48.0)


# ---------------------------------------------------------------------------
# A picture is placed, not just sized: the shift pair
# ---------------------------------------------------------------------------
#: One hung picture per wall direction, at positions that are deliberately not
#: a whole number of images from the world origin, with the four numbers each
#: one has to carry worked out by hand.
#:
#: A vertex's texture coordinate is ``(P . axis - shift) / size``, measured by
#: compiling probe faces and reading the coordinates back out of the compiled
#: map (``docs/mapsource-format-reference.md`` 1.4).  The axes belong to the
#: world: across the face ``+X`` for a wall on the Y axis and ``+Y`` for one on
#: the X axis, and **down** the face ``-Z``.  So the shift is the world
#: coordinate of the corner the image's own top-left has to sit on, and the
#: size is the face's extent along that axis.
#:
#: Two of the four directions share their axis with the wall opposite and so
#: run it backwards for anyone standing in front: a picture there is mirrored
#: unless its width is written negative, and then the corner the image starts
#: at is the far one.  Facing north a player has east on his right, so the
#: south-looking wall is the right way round and the north-looking one is not.
#:
#: Worked, for the first row: the face runs x 772 to 828 and z 364 to 476, so
#: the image's top-left is at x 772, z 476, which along ``-Z`` is -476.  Before
#: this, every picture face was written ``0 0`` and that one showed its seam 12
#: units across itself (772 is 44 units into a 56-unit image).
PICTURE_PLACEMENTS = (
    # side, box mins, box maxs, (u size, v size), (size u, size v, shift u, shift v)
    ("SOUTH", (772.0, 942.0, 364.0), (828.0, 944.0, 476.0), (56.0, 112.0),
     (56.0, 112.0, 772.0, -476.0)),
    ("NORTH", (133.0, 640.0, 51.0), (189.0, 642.0, 163.0), (56.0, 112.0),
     (-56.0, 112.0, 189.0, -163.0)),
    ("EAST", (-304.0, 305.0, 20.0), (-302.0, 361.0, 132.0), (56.0, 112.0),
     (56.0, 112.0, 305.0, -132.0)),
    ("WEST", (2336.0, 1422.5, 94.5), (2338.0, 1478.5, 206.5), (56.0, 112.0),
     (-56.0, 112.0, 1478.5, -206.5)),
)


def _hung_picture(side_name: str, mins, maxs, size) -> tuple:
    """The projection numbers of the one art face of a hung picture."""
    from zmforge.emit.mapfile import _brush_of
    from zmforge.materials import FaceMaterials, Material
    from zmforge.solids.forms import block
    from zmforge.spatial import Side, Span

    side = getattr(Side, side_name)
    picture = Material("zmf_art_example_poster", size[0], size[1])
    solid = block(
        Span(Point(*mins), Point(*maxs)),
        FaceMaterials.only_visible_on(side, picture),
    )
    brush = _brush_of(solid, "{00000000-0000-0000-0000-000000000001}")
    art = [f for f in brush.facets if f.material == picture.name]
    assert len(art) == 1, "a hung picture shows on one face and caulks the other five"
    return art[0].projection.as_tuple()


@pytest.mark.parametrize("side,mins,maxs,size,expected", PICTURE_PLACEMENTS)
def test_a_picture_is_anchored_to_its_own_face_in_every_wall_direction(
    side, mins, maxs, size, expected
) -> None:
    """One image, its top-left on the face's top-left, wherever the face is.

    Four wall directions and four positions that are not image-aligned, because
    the defect only shows on a face the world grid does not happen to agree
    with -- and none of a generated map's forty-three picture faces did.
    """
    projection = _hung_picture(side, mins, maxs, size)
    assert projection[:4] == expected
    assert abs(projection[0]) == size[0] and projection[1] == size[1], (
        "the image's own size still reaches the file"
    )
    assert projection[4:] == (0.0, 0.0), "no rotation, and the sixth stays untouched"


@pytest.mark.parametrize("side,mins,maxs,size,expected", PICTURE_PLACEMENTS)
def test_one_image_spans_a_picture_face_with_no_seam_inside_it(
    side, mins, maxs, size, expected
) -> None:
    """The check the player makes: walk the face's own corners through the
    projection the file carries and see whole numbers.

    A texture coordinate of a whole number is an edge of the image.  Zero at
    one end of the face and one at the other is a single copy of the image
    filling it; anything else shows a seam.  Computed
    from the emitted numbers through the compiler's own formula rather than
    from the code that wrote them, so it fails on the old ``0 0`` shift.

    ``u`` is read at the corner a player in front of the wall sees on his
    left, which is the low world coordinate on two of the walls and the high
    one on the other two: it has to be 0 there, or the image is mirrored.
    """
    size_u, size_v, shift_u, shift_v = _hung_picture(side, mins, maxs, size)[:4]
    across = 1 if side in ("EAST", "WEST") else 0  # +Y for an east/west wall, else +X
    left, right = (
        (maxs[across], mins[across]) if side in ("NORTH", "WEST")
        else (mins[across], maxs[across])
    )
    coordinates = {
        "left": (left - shift_u) / size_u,
        "right": (right - shift_u) / size_u,
        "top": (-maxs[2] - shift_v) / size_v,
        "bottom": (-mins[2] - shift_v) / size_v,
    }
    for where, coordinate in coordinates.items():
        assert coordinate == pytest.approx(round(coordinate), abs=1e-9), (
            f"the face's {where} edge must land on an edge of the image"
        )
    assert coordinates["left"] == pytest.approx(0.0), "the image starts where the face does"
    assert coordinates["top"] == pytest.approx(0.0), "and it starts at its own top"
    assert coordinates["right"] == pytest.approx(1.0), "exactly one image across"
    assert coordinates["bottom"] == pytest.approx(1.0), "exactly one image up"


def test_the_world_anchored_shift_is_what_put_the_seam_inside_the_face() -> None:
    """The regression, stated as numbers.

    With ``0 0`` a hung poster's 56-unit face at x 772 showed its own
    left edge 12 units in -- 21% across -- with the tail of its right-hand side
    wrapped round to the left of it and the headline running off the right;
    and its top 112 units at z 476 showed the bottom quarter of the image
    above the picture, 476 being 28 units into an image.
    """
    side, mins, maxs, size, expected = PICTURE_PLACEMENTS[0]
    across_seam = (-mins[0]) % size[0]
    down_seam = maxs[2] % size[1]
    assert (across_seam, down_seam) == (12.0, 28.0), "where the old file's two seams fell"
    assert 0.0 < across_seam < size[0] and 0.0 < down_seam < size[1]
    assert _hung_picture(side, mins, maxs, size)[:4] != (size[0], size[1], 0.0, 0.0)
    assert _hung_picture(side, mins, maxs, size)[:4] == expected


def test_a_tiling_surface_keeps_the_world_anchor_it_had() -> None:
    """Two things that are not pictures, and must be written as they were.

    A photographed wall is laid at 20 units and a wall is longer than that, so
    the pattern runs on across the join between two brushes of the same wall
    and a shift would put a step in it.  A box painted one material all over
    is a crate, not a hung picture, however its sides happen to measure -- the
    second solid here is exactly one tile across two of its faces.  Both keep
    ``0 0``, which is the path the shared document's ``texture_scales`` feeds.
    """
    from zmforge.emit.mapfile import _brush_of, _surface_projection
    from zmforge.materials import FaceMaterials, Material
    from zmforge.solids.forms import block
    from zmforge.spatial import Span

    wall = Material("rs_bed_wall", 20.0)
    crate = Material("t7_concrete_trowelled", 96.0, 48.0)
    solids = (
        block(Span(Point(133, 640, 51), Point(389, 642, 179)), FaceMaterials.uniform(wall)),
        block(Span(Point(5, 7, 11), Point(101, 15, 59)), FaceMaterials.uniform(crate)),
    )
    for solid, material in zip(solids, (wall, crate)):
        brush = _brush_of(solid, "{00000000-0000-0000-0000-000000000002}")
        for facet in brush.facets:
            assert facet.projection.as_tuple() == (
                material.scale, material.scale_v, 0.0, 0.0, 0.0, 0.0
            )
    # and the material-only call, which nothing has to hand a face to
    assert _surface_projection(wall).as_tuple() == (20.0, 20.0, 0.0, 0.0, 0.0, 0.0)


def test_f8_patch_group_parenthesis_is_not_a_face_line(patched_text: str) -> None:
    """A valid map with terrain patches must not raise F8.

    The group-opening ``(`` of a patch control grid is structure, not a face
    line; flagging it makes ``commit`` report errors on a map that is correct,
    which trains callers to ignore the report.
    """
    report = check_map_text(patched_text)
    assert [f for f in report.findings if f.code == "F8"] == []


# ---------------------------------------------------------------------------
# F9: patch blocks
# ---------------------------------------------------------------------------
def _scan_patches(text: str) -> list[dict]:
    """Walk the raw text and pull out each patch body's structure.

    Deliberately textual: F9 is a property of the emitted file's line order,
    and going through the reader would hide a writer that emits the inner block
    in the wrong sequence but is forgiving enough to read back.
    """
    lines = [line.strip() for line in text.split("\n")]
    found: list[dict] = []
    for index, line in enumerate(lines):
        if line not in ("mesh", "curve"):
            continue
        at = index + 1
        assert lines[at] == "{", "a patch keyword must open an inner brace"
        at += 1
        layer = None
        if lines[at].startswith("layer "):
            # Where Radiant puts a patch's layer: first line of the inner
            # block (328/328 layered patches in the shipped map_source).
            layer = lines[at]
            at += 1
        contents = None
        if lines[at].startswith("contents "):
            assert lines[at].endswith(";"), "a contents line ends in a semicolon"
            contents = lines[at]
            at += 1
        assert lines[at] == "toolFlags;", f"expected toolFlags;, got {lines[at]!r}"
        at += 1
        material, lightmap, dimensions = lines[at], lines[at + 1], lines[at + 2].split()
        at += 3
        groups: list[int] = []
        while lines[at] == "(":
            at += 1
            count = 0
            while lines[at] != ")":
                assert lines[at].startswith("v "), (
                    f"expected a vertex line, got {lines[at]!r}"
                )
                count += 1
                at += 1
            groups.append(count)
            at += 1
        assert lines[at] == "}", "a patch body must close its inner brace"
        found.append(
            {
                "kind": line,
                "layer": layer,
                "contents": contents,
                "material": material,
                "lightmap": lightmap,
                "dimensions": dimensions,
                "groups": groups,
                "vertices": [
                    lines[position]
                    for position in range(index, at)
                    if lines[position].startswith("v ")
                ],
            }
        )
    return found


def test_f9_patch_blocks_have_the_fixed_inner_order_and_full_grid(
    patched_text: str,
) -> None:
    """The patch inner block order is fixed and a short grid is unrecoverable.

    Spec 1.8: optional ``contents ...;``, ``toolFlags;``, material, lightmap,
    ``W H T1 T2``, then exactly W groups of exactly H ``v`` lines.  W/H that
    disagree with the grid makes Radiant read past the block into the next
    brush, which corrupts everything after it in the file.
    """
    patches = _scan_patches(patched_text)
    assert patches, "the patched fixture emitted no patch at all"
    for patch in patches:
        assert len(patch["dimensions"]) == 4
        width, height, subdivision, flavour = (int(n) for n in patch["dimensions"])
        assert width >= 1 and height >= 1
        assert len(patch["groups"]) == width, (
            f"declared {width} groups, found {len(patch['groups'])}"
        )
        assert all(count == height for count in patch["groups"]), (
            f"declared {height} vertices per group, found {patch['groups']}"
        )
        assert subdivision == (0 if patch["kind"] == "mesh" else 16)
        assert flavour == 8
        assert patch["lightmap"] == "lightmap_gray"
        assert patch["material"] != "caulk", (
            "caulk on a patch makes the compiler print its terrain-caulk banner "
            "and the surface render black (spec 1.8)"
        )
        for vertex in patch["vertices"]:
            tokens = vertex.split()
            assert tokens[0] == "v"
            if tokens[4] == "c":
                assert tokens[9] == "t", "colour is four numbers, then the t marker"
                numbers = tokens[1:4] + tokens[5:9] + tokens[10:14]
            else:
                assert tokens[4] == "t", f"vertex without its t marker: {vertex!r}"
                numbers = tokens[1:4] + tokens[5:9]
            assert len(numbers) in (7, 11)
            for token in numbers:
                assert NUMBER_RE.match(token), f"bad vertex number {token!r}"
    assert "F9" not in check_map_text(patched_text).codes()


def test_f9_patch_survives_the_reader(patched_text: str) -> None:
    """The reader must find the patch's end despite its nested brace.

    A brace-depth counter is the only way out of the container (spec 1.11); a
    reader that stops at the first ``}`` swallows the rest of the entity, and
    the loss is silent.
    """
    document = parse_map_text(patched_text)
    patches = [
        solid
        for entity in document.entities
        for solid in entity.solids
        if isinstance(solid, PatchSolid)
    ]
    assert len(patches) == len(_scan_patches(patched_text))
    assert not any(
        isinstance(solid, OpaqueSolid)
        for entity in document.entities
        for solid in entity.solids
    ), f"geometry fell back to opaque text: {document.notes[:3]}"
    for patch in patches:
        assert patch.width * patch.height == sum(len(g) for g in patch.grid)


# ---------------------------------------------------------------------------
# F10: round trip on generated text
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fixture_name", ["generated_text", "patched_text"])
def test_f10_round_trip_is_byte_identical(fixture_name, request) -> None:
    """``render(parse(render(doc)))`` must equal ``render(doc)`` byte for byte.

    Callers read maps they generated earlier, change one entity and write back.
    If the pair is not a fixed point, every such edit produces a diff full of
    reformatted numbers and reindented brushes, and a real change becomes
    impossible to review (spec 1.11).
    """
    once = request.getfixturevalue(fixture_name)
    twice = render_map_text(parse_map_text(once))
    assert twice == once
    assert render_map_text(parse_map_text(twice)) == once


# ---------------------------------------------------------------------------
# F11: round trip on real BO3 files
# ---------------------------------------------------------------------------
def _profile(document) -> dict:
    """Everything F11 says must survive a read/write/read cycle."""
    per_entity: list[tuple[str | None, Counter]] = []
    brushes = faces = patches = opaque = 0
    trailing: list[str] = []
    dimensions: list[tuple[int, int, int, int]] = []
    control_points: list[int] = []
    for entity in document.entities:
        per_entity.append((entity.classname, Counter(entity.pairs)))
        for solid in entity.solids:
            if isinstance(solid, BrushSolid):
                brushes += 1
                faces += len(solid.facets)
                trailing.extend(facet.trailing for facet in solid.facets)
            elif isinstance(solid, PatchSolid):
                patches += 1
                dimensions.append(
                    (solid.width, solid.height, solid.subdivision, solid.flavour)
                )
                control_points.append(sum(len(group) for group in solid.grid))
            else:
                opaque += 1
    return {
        "entities": len(document.entities),
        "pairs": per_entity,
        "brushes": brushes,
        "faces": faces,
        "patches": patches,
        "opaque": opaque,
        "trailing": Counter(trailing),
        "dimensions": dimensions,
        "control_points": control_points,
    }


def test_the_corpus_is_present() -> None:
    """Four real BO3/CoD map files by other mappers, if present; F11 is
    meaningless without them.

    They are other authors' maps and gitignored, so a clone without them
    skips.  Once any are present all four must be: a partial set fails rather
    than passing on fewer maps than the round trip was written against.
    """
    if not CORPUS:
        pytest.skip("tests/corpus/*.map not present (third-party maps, not in the repository)")
    assert len(CORPUS) == 4, [path.name for path in CORPUS]


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.name)
def test_f11_foreign_round_trip_preserves_every_structure(path: Path) -> None:
    """A mapper's own file must come back with nothing lost.

    Whitespace and block numbering may be normalised (spec 1.11), so this
    compares structure between the first and the second parse rather than bytes
    against the original.  Trailing face tokens such as
    ``decalLayerSort "..." decalEditorSort N`` are included because a reader
    that drops what it does not recognise destroys per-face data the mapper set
    by hand and cannot get back.
    """
    first = mapsource.read(path)
    rendered = render_map_text(first)
    second = parse_map_text(rendered, newline=first.newline)

    before, after = _profile(first), _profile(second)
    assert before["entities"] == after["entities"] > 0
    assert before["pairs"] == after["pairs"]
    assert before["brushes"] == after["brushes"]
    assert before["faces"] == after["faces"] > 0
    assert before["patches"] == after["patches"]
    assert before["dimensions"] == after["dimensions"]
    assert before["control_points"] == after["control_points"]
    assert before["trailing"] == after["trailing"]
    assert before["opaque"] == after["opaque"]

    # Nothing may be quietly reclassified as text the reader gave up on.
    assert before["opaque"] == 0, (
        f"{path.name}: {before['opaque']} solids kept as opaque text; "
        f"first note: {first.notes[:1]}"
    )
    # And the second render must be a fixed point, as for generated text.
    assert render_map_text(second) == rendered


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.name)
def test_f11_foreign_round_trip_keeps_the_header_and_layers(path: Path) -> None:
    """Layer paths and flags are the mapper's organisation of the file.

    Losing them does not break the compile, so it would go unnoticed until the
    mapper reopened a map whose every brush had landed in one flat layer.
    """
    first = mapsource.read(path)
    second = parse_map_text(render_map_text(first), newline=first.newline)
    assert [(l.path, l.flags) for l in first.layers] == [
        (l.path, l.flags) for l in second.layers
    ]
    assert first.starting_number == second.starting_number
    assert render_map_text(second).startswith("iwmap 4")


# ---------------------------------------------------------------------------
# F12: line endings
# ---------------------------------------------------------------------------
def test_f12_generated_files_are_lf(tmp_path) -> None:
    """New ``.map`` files are LF and UTF-8 (spec 1.10).

    A CRLF file from a generator run on Windows produces a diff against every
    LF file in the same map_source tree, and reviewing a map is already hard
    enough.
    """
    project = Project.create(
        "zm_endings", tmp_path, blueprint=three_room_map("zm_endings")
    )
    project.commit()
    raw = project.paths()["map"].read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    raw.decode("utf-8")  # must not raise: the file is UTF-8


def test_f12_a_crlf_file_is_written_back_as_crlf(tmp_path) -> None:
    """Editing a mapper's CRLF file must not rewrite every line of it.

    Normalising endings on save turns a one-key change into a diff touching the
    whole file, and on a shared map that is a merge conflict per line
    (spec 1.10).
    """
    source = tmp_path / "crlf.map"
    body = (
        "iwmap 4\n"
        '"script_startingnumber" 0\n'
        '"000_Global" flags expanded active\n'
        "// entity 0\n"
        "{\n"
        'guid "{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}"\n'
        '"classname" "worldspawn"\n'
        "// brush 0\n"
        "{\n"
        ' guid "{11111111-2222-3333-4444-555555555555}"\n'
        " ( 0 0 16 ) ( 0 1 16 ) ( 1 0 16 ) caulk 64 64 0 0 0 0"
        " lightmap_gray 16384 16384 0 0 0 0\n"
        "}\n"
        "}\n"
    ).replace("\n", "\r\n")
    source.write_bytes(body.encode("utf-8"))

    document = mapsource.read(source)
    assert document.newline == "\r\n"

    target = tmp_path / "out.map"
    mapsource.write(target, document)
    raw = target.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n"), "a line went out as bare LF"
    assert raw.count(b"\r\n") == body.count("\r\n")
    assert b"\r\r" not in raw

    # Re-reading the written file must give the same document and ending.
    again = mapsource.read(target)
    assert again.newline == "\r\n"
    assert _profile(again) == _profile(document)


# ---------------------------------------------------------------------------
# F13: every emitted solid has a shape a shipped map uses
# ---------------------------------------------------------------------------
#: Shapes measured over the mod tools' own ``map_source``.  Counts and file names only, no
#: content: the game's data stays out of the repository (docs/licensing.md).
SHIPPED_SHAPES = Path(__file__).parent / "corpus" / "shipped-solid-shapes.json"
_FACE_START_RE = re.compile(r"^\( -?[\d.]+ ")
_DIMS_RE = re.compile(r"^-?\d+ -?\d+ -?\d+ -?\d+$")
_WORD_RE = re.compile(r"^[A-Za-z0-9_]+$")
_GRID_RE = re.compile(r"(\( v \) ?)+")


def _line_kind(stripped: str) -> str | None:
    """One token per line, the same classification the ledger script uses."""
    if stripped == "{" or stripped == "}":
        return stripped
    if stripped.startswith("guid "):
        return "guid"
    if stripped.startswith("layer "):
        return "layer"
    if stripped.startswith("contents "):
        return "contents"
    if stripped.startswith("toolFlags"):
        return "toolFlags"
    if stripped in ("mesh", "curve"):
        return "kw"
    if _FACE_START_RE.match(stripped):
        return "face"
    if stripped in ("(", ")"):
        return stripped
    if stripped.startswith("v "):
        return "v"
    if _DIMS_RE.match(stripped):
        return "dims"
    if _WORD_RE.match(stripped):
        return "word"
    if not stripped:
        return None
    return "OTHER:" + stripped.split()[0]


def _solid_shapes(text: str) -> list[tuple[str, int]]:
    """``(shape, line)`` for every ``// brush`` container in ``text``.

    A shape is the container's line kinds in order, consecutive repeats
    collapsed and the control-point groups reduced to one ``grid`` token, so
    ``guid kw { layer contents toolFlags word dims grid }`` is one layered
    collision patch whatever its size.
    """
    lines = text.split("\n")
    found: list[tuple[str, int]] = []
    at = 0
    while at < len(lines):
        if not BRUSH_COMMENT_RE.match(lines[at].strip()):
            at += 1
            continue
        opened = at + 1
        at += 1
        if at >= len(lines) or lines[at].strip() != "{":
            continue
        at += 1
        sequence: list[str] = []
        depth = 1
        while at < len(lines) and depth > 0:
            stripped = lines[at].strip()
            kind = _line_kind(stripped)
            if stripped == "{":
                depth += 1
            elif stripped == "}":
                depth -= 1
            if kind is not None and (not sequence or sequence[-1] != kind):
                sequence.append(kind)
            at += 1
        found.append((_GRID_RE.sub("grid ", " ".join(sequence)).strip(), opened))
    return found


def _shipped_shapes() -> dict[str, int]:
    ledger = json.loads(SHIPPED_SHAPES.read_text(encoding="utf-8"))
    return ledger["shapes"]


def _corpus_shapes() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in CORPUS:
        for shape, _ in _solid_shapes(path.read_text(encoding="utf-8", errors="replace")):
            counts[shape] = counts.get(shape, 0) + 1
    return counts


def test_f13_the_shape_ledger_is_present_and_large() -> None:
    """The ledger must describe the shipped tools, not a handful of files."""
    ledger = json.loads(SHIPPED_SHAPES.read_text(encoding="utf-8"))
    assert ledger["files"] >= 700, ledger["files"]
    assert ledger["patch_containers"] >= 20000, ledger["patch_containers"]
    assert ledger["brush_containers"] >= 20000, ledger["brush_containers"]
    # The two things this test exists for, stated as facts of the ledger.
    assert not any(
        shape.startswith("guid layer kw") for shape in ledger["shapes"]
    ), "no shipped patch carries a layer line before its keyword"
    assert any(
        shape.startswith("guid kw { layer") for shape in ledger["shapes"]
    ), "shipped patches carry their layer line first inside the inner block"


def test_f13_the_public_corpus_agrees_with_the_shipped_ledger() -> None:
    """The four public maps and the shipped ledger must not contradict.

    A shape seen in the corpus but absent from 700+ shipped files would mean
    the two classifiers have drifted apart, and the check below would then
    be measuring the wrong grammar.
    """
    shipped = _shipped_shapes()
    unknown = {shape for shape in _corpus_shapes() if shape not in shipped}
    assert not unknown, sorted(unknown)


@pytest.mark.parametrize("fixture_name", ["generated_text", "patched_text"])
def test_f13_every_generated_solid_has_a_shape_a_shipped_map_uses(
    fixture_name, request
) -> None:
    """A ``layer`` line between a patch container's guid and its keyword is caught.

    cod2map64 stops on it with ``MatchToken: got 'mesh', expected '('``: the
    writer had put a patch's ``layer`` line between the container's guid and
    the keyword, a shape no shipped file has (22,795 patch containers, none).
    F9 only looked inside the keyword's inner block, F10 round-tripped through
    our own reader, which tolerated the line, and nothing compared what we
    emit with what Radiant emits.  This does: every solid the generator writes
    must have a shape found in the shipped ``map_source`` or the public
    corpus, so a new invention fails here before it reaches the compiler.
    """
    text = request.getfixturevalue(fixture_name)
    allowed = set(_shipped_shapes()) | set(_corpus_shapes())
    shapes = _solid_shapes(text)
    assert shapes, "the fixture emitted no solid at all"
    if fixture_name == "patched_text":
        assert any("kw" in shape for shape, _ in shapes), "no patch in the patched fixture"
    unknown = [(shape, line) for shape, line in shapes if shape not in allowed]
    assert not unknown, (
        f"{len(unknown)} solid(s) with a shape no shipped map uses; first at "
        f"line {unknown[0][1]}: {unknown[0][0]!r}"
    )


def test_f13_a_layer_line_before_the_patch_keyword_is_refused() -> None:
    """The exact defect, kept as a regression: writer, reader and commit check.

    The writer must put a patch's layer first inside the inner block; the
    reader must not quietly accept it before the keyword; and the commit-time
    check must report the container so ``commit`` refuses to write it.
    """
    from zmforge.mapsource.document import ControlVertex, Document, Entity

    grid = tuple(
        tuple(ControlVertex(Point(float(x), float(y), 0.0)) for y in (0, 64))
        for x in (0, 64)
    )
    patch = PatchSolid(
        guid="{00000000-0000-0000-0000-000000000001}",
        kind="mesh",
        material="t7_dirt_grassy_forest_ground",
        grid=grid,
        layer="The Map",
    )
    world = Entity(guid="{00000000-0000-0000-0000-000000000000}")
    world.pairs.append(("classname", "worldspawn"))
    world.solids.append(patch)
    good = render_map_text(Document(entities=[world]))
    good_lines = [line.strip() for line in good.split("\n")]
    keyword = good_lines.index("mesh")
    assert good_lines[keyword - 1].startswith("guid "), "only guid precedes the keyword"
    assert good_lines[keyword + 1] == "{"
    assert good_lines[keyword + 2] == 'layer "The Map"', "layer is the first inner line"
    assert [shape for shape, _ in _solid_shapes(good)] == [
        "guid kw { layer toolFlags word dims grid }"
    ]
    assert "F9" not in check_map_text(good).codes()

    # What the writer used to emit: the same lines with layer moved up.
    lines = good.split("\n")
    layer_at = next(i for i, line in enumerate(lines) if line.startswith("layer "))
    keyword_at = next(i for i, line in enumerate(lines) if line.strip() == "mesh")
    bad_lines = lines[:keyword_at] + ["  " + lines[layer_at].strip()] + lines[keyword_at:layer_at] + lines[layer_at + 1 :]
    bad = "\n".join(bad_lines)
    assert [shape for shape, _ in _solid_shapes(bad)] == [
        "guid layer kw { toolFlags word dims grid }"
    ]
    assert "guid layer kw { toolFlags word dims grid }" not in _shipped_shapes()
    document = parse_map_text(bad)
    assert any(isinstance(s, OpaqueSolid) for e in document.entities for s in e.solids), (
        "the reader must not parse a layer line before the keyword as a patch"
    )
    report = check_map_text(bad)
    assert "F9" in report.codes(), "commit must refuse what the compiler refuses"
