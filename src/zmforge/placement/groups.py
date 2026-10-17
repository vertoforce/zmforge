"""Groups: a family of models placed and judged as one thing.

A shelving unit is a frame and its planks.  A desk is a desk and the chair
tucked under it.  A staircase prop is a stringer and its treads.  The placer
this package replaces deals those out as independent models from independent
list entries, and the result is the "one part of a set" pitfall:
frames standing where their planks did not fit, a chair almost wholly inside
a plant while its desk sits inside a bench.  On a densely dressed map dozens
of solid props can interpenetrate something, and the pairs that hurt most are
the ones where half a set landed and half of it did not.

ProcTHOR (allenai/procthor, Apache-2.0) answers this in
``asset_groups.py``: the family is instantiated at one position and one yaw,
every member is checked, and *the group* is rejected if any member intersects.
Not the member.  The group.  That is the rule here, and the consequence worth
stating plainly is that a room gets a whole desk-and-chair or no desk at all,
never a chair facing nothing.

Two things follow from "judged as one thing" and both are in
:func:`try_group`:

* a member must not interpenetrate a **non**-member, which is the ordinary
  :class:`~zmforge.placement.relations.NoOverlap` check run against every
  obstacle and every keep-clear zone;
* members are expected to touch *each other*, because that is what a set is.
  A chair tucked under a desk shares floor with it on purpose.  So the
  internal check is the same relation with an explicit allowance: the pairs
  the group itself declares in :attr:`Group.touching` are exempt, and every
  other pair is held to the same tolerance as a stranger.  A group that gets
  that list wrong fails its own check at definition time rather than shipping
  two models through each other.

Heights are relative to the group's base, so a tread at ``z_low=64`` is 64
above wherever the group is standing.  Nothing here reads a model's measured
box; a caller builds :class:`Member` from one (see
:meth:`~zmforge.placement.relations.Placed.from_model`) and this module works
in the group's own frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeAlias

from .geometry import Poly2, rotate
from .relations import NoOverlap, Placed, Violation
from .scatter import Candidate, KeepClear, Negatives

__all__ = [
    "Member",
    "Group",
    "GroupPlacement",
    "GroupAttempt",
    "instantiate",
    "internal_violations",
    "try_group",
    "place_group",
    "first_fit",
    "Spot",
    "GROUP_RELATION",
]

#: The relation a group is held to unless a caller says otherwise.  The
#: tolerance is :class:`~zmforge.placement.relations.NoOverlap`'s own default
#: of 0.05, which is the current placer's number and is small on purpose: the
#: shipped maps are full of props touching, and the layout check's threshold
#: for calling an overlap a fault is 25% of the smaller footprint, so anything
#: between the two is already worse than the shipped maps and better than the
#: 89 props this is meant to stop.
GROUP_RELATION = NoOverlap()


@dataclass(frozen=True, slots=True)
class Member:
    """One model in a family, positioned in the family's own frame.

    ``dx``/``dy`` are the offset from the group's origin before the group is
    turned, ``yaw`` the model's own turn on top of the group's, and ``hx``/
    ``hy`` its plan half extents.  ``z_low``/``z_high`` are heights above the
    group's base, so a group is defined once and stands on a floor, a plinth
    or a gallery without being redefined.

    ``part`` is the label the group uses to talk about this member, and it
    exists because a family has repeats: a frame with four treads has five
    members and four of them are the same model.  It defaults to the model
    name, which is right for the common case of one of each.
    """

    name: str
    dx: float = 0.0
    dy: float = 0.0
    yaw: float = 0.0
    hx: float = 0.0
    hy: float = 0.0
    z_low: float = 0.0
    z_high: float = 0.0
    solid: bool = True
    part: str = ""

    @property
    def label(self) -> str:
        """What :attr:`Group.touching` calls this member."""
        return self.part or self.name

    @property
    def height(self) -> float:
        return self.z_high - self.z_low


@dataclass(frozen=True, slots=True)
class Group:
    """A named family of members, plus the pairs of them meant to touch.

    ``touching`` is a list of label pairs, in either order, and it is the
    group's own declaration that two of its members share floor on purpose:
    ``("desk", "chair")`` for a chair tucked under, ``("frame", "tread_1")``
    for a tread carried on a frame.  Everything not on that list is held apart
    exactly as a stranger would be, which is what catches a family whose
    offsets were typed wrong.
    """

    name: str
    members: tuple[Member, ...] = ()
    touching: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        labels = [member.label for member in self.members]
        repeated = sorted({label for label in labels if labels.count(label) > 1})
        if repeated:
            raise ValueError(
                f"group {self.name!r} has more than one member labelled "
                f"{', '.join(repeated)}; give the repeats a `part`"
            )
        known = set(labels)
        for first, second in self.touching:
            missing = [label for label in (first, second) if label not in known]
            if missing:
                raise ValueError(
                    f"group {self.name!r} declares touching {first!r} and "
                    f"{second!r}, but {', '.join(missing)} is not a member"
                )

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(member.label for member in self.members)

    def may_touch(self, first: str, second: str) -> bool:
        """Did the group declare this pair as touching, in either order?"""
        return any(
            (first, second) == pair or (second, first) == pair
            for pair in self.touching
        )


@dataclass(frozen=True, slots=True)
class GroupPlacement:
    """A group standing somewhere: every member already turned into a ``Placed``.

    Held as a value even when the placement was rejected, because the reason a
    group did not fit is a sentence about where its members would have been,
    and that sentence cannot be written after the members are thrown away.
    """

    group: str
    x: float
    y: float
    yaw: float
    base_z: float
    members: tuple[Placed, ...] = ()

    @property
    def footprint(self) -> Poly2:
        """The convex hull of every member's footprint: the family's own plan."""
        return Poly2.of(
            point for member in self.members for point in member.footprint.points
        )

    @property
    def z_low(self) -> float:
        return min((member.z_low for member in self.members), default=self.base_z)

    @property
    def z_high(self) -> float:
        return max((member.z_high for member in self.members), default=self.base_z)

    def member(self, label: str) -> Placed:
        """One member by its ``ident`` label, for a caller checking one piece."""
        for placed in self.members:
            if placed.ident.rsplit(":", 1)[-1] == label:
                return placed
        raise KeyError(f"{self.group} has no member {label!r}")


@dataclass(frozen=True, slots=True)
class GroupAttempt:
    """A placement and the violations it collected, which may be none.

    ``bool(attempt)`` is "did it fit".  The violations are kept whether it fit
    or not, so a caller that wants to report the near misses can, and a caller
    that only wants the answer writes ``if attempt:``.
    """

    placement: GroupPlacement
    violations: tuple[Violation, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations

    def __bool__(self) -> bool:
        return self.ok

    def why(self) -> str:
        """One line naming what stopped this group, for a log or a finding."""
        if self.ok:
            return f"{self.placement.group} fits"
        return f"{self.placement.group} rejected: " + "; ".join(
            str(violation) for violation in self.violations
        )


def instantiate(
    group: Group,
    at: tuple[float, float],
    yaw: float = 0.0,
    *,
    base_z: float = 0.0,
    room: str = "",
) -> GroupPlacement:
    """Put the whole family down at one position and one yaw.

    Every member's offset is turned by the group's yaw before it is added, so
    a desk-and-chair rotated 90 degrees is still a desk with a chair tucked
    under it and not a desk with a chair beside it.  This never rejects
    anything; :func:`try_group` does the judging.
    """
    x, y = at
    placed: list[Placed] = []
    for member in group.members:
        offset_x, offset_y = rotate(member.dx, member.dy, yaw)
        placed.append(Placed(
            name=member.name,
            x=x + offset_x,
            y=y + offset_y,
            hx=member.hx,
            hy=member.hy,
            yaw=yaw + member.yaw,
            z_low=base_z + member.z_low,
            z_high=base_z + member.z_high,
            solid=member.solid,
            room=room,
            ident=f"{group.name}:{member.label}",
        ))
    return GroupPlacement(group.name, x, y, yaw, base_z, tuple(placed))


def internal_violations(
    group: Group,
    placement: GroupPlacement,
    relation: NoOverlap = GROUP_RELATION,
) -> tuple[Violation, ...]:
    """Members of one group drawn through each other, minus the declared pairs.

    The exemption is by label pair and nothing else.  It is not "members of the
    same group may overlap", because that is the rule that lets a mistyped
    offset ship: a tread declared to rest on its frame is allowed to share that
    frame's floor, and a second tread in the same place as the first is not.
    """
    labels = group.labels
    out: list[Violation] = []
    for i in range(len(placement.members)):
        for j in range(i + 1, len(placement.members)):
            if group.may_touch(labels[i], labels[j]):
                continue
            clash = relation.check(placement.members[i], placement.members[j])
            if clash is not None:
                out.append(Violation(
                    "GroupInternal",
                    f"{clash.detail} (both are part of {group.name})",
                    clash.amount, clash.subject, clash.target,
                ))
    return tuple(out)


def try_group(
    group: Group,
    at: tuple[float, float],
    yaw: float = 0.0,
    *,
    base_z: float = 0.0,
    obstacles: Iterable[Placed] = (),
    negatives: Negatives | Iterable[KeepClear] = (),
    relation: NoOverlap = GROUP_RELATION,
    room: str = "",
) -> GroupAttempt:
    """Place the family, then collect every reason it should not be there.

    All the reasons, not the first one.  A group that fails is usually going
    to be retried somewhere else (:func:`first_fit`), and when every position
    fails the useful output is "the chair hit the bench at all eight of them",
    which needs the whole list.
    """
    placement = instantiate(group, at, yaw, base_z=base_z, room=room)
    # Materialised, because this walks the obstacles once per member and a
    # caller handing over a generator would otherwise have every member after
    # the first checked against an empty room.
    obstacles = tuple(obstacles)
    zones = negatives if isinstance(negatives, Negatives) else Negatives.of(negatives)
    violations: list[Violation] = []

    for placed in placement.members:
        for obstacle in obstacles:
            clash = relation.check(placed, obstacle)
            if clash is not None:
                violations.append(clash)
        zone = zones.blocks(
            placed.footprint, z_low=placed.z_low, z_high=placed.z_high
        )
        if zone is not None:
            violations.append(Violation(
                "KeepClear",
                f"is inside the keep-clear zone for {zone.reason}",
                zone.poly.overlap_area(placed.footprint),
                placed.name,
                zone.reason,
            ))

    violations.extend(internal_violations(group, placement, relation))
    return GroupAttempt(placement, tuple(violations))


def place_group(
    group: Group,
    at: tuple[float, float],
    yaw: float = 0.0,
    *,
    base_z: float = 0.0,
    obstacles: Iterable[Placed] = (),
    negatives: Negatives | Iterable[KeepClear] = (),
    relation: NoOverlap = GROUP_RELATION,
    room: str = "",
) -> GroupPlacement | None:
    """The whole family here, or nothing.  ``None`` means it did not fit.

    :func:`try_group` is the same call with the violations attached, for a
    caller that has to say why.
    """
    attempt = try_group(
        group, at, yaw, base_z=base_z, obstacles=obstacles,
        negatives=negatives, relation=relation, room=room,
    )
    return attempt.placement if attempt.ok else None


#: A position a group may be tried at: a pair, a triple with a yaw, or
#: anything carrying ``x``, ``y`` and ``yaw`` -- which is what a
#: :class:`~zmforge.placement.scatter.Candidate` carries, so the output of a
#: scatter stack is the input of :func:`first_fit` with nothing in between.
Spot: TypeAlias = "tuple[float, ...] | Candidate"


def _spot(item: object) -> tuple[float, float, float, float | None]:
    """Read a position, a yaw and an optional base height off whatever this is."""
    if isinstance(item, (tuple, list)):
        if len(item) == 2:
            return (float(item[0]), float(item[1]), 0.0, None)
        if len(item) == 3:
            return (float(item[0]), float(item[1]), float(item[2]), None)
        raise ValueError(f"a spot is a pair or a triple, not {len(item)} numbers")
    x = getattr(item, "x", None)
    y = getattr(item, "y", None)
    if x is None or y is None:
        raise TypeError(f"{item!r} is not a spot: it has no x and y")
    z = getattr(item, "z", None)
    return (float(x), float(y), float(getattr(item, "yaw", 0.0) or 0.0),
            None if z is None else float(z))


def first_fit(
    group: Group,
    spots: Iterable[Spot],
    *,
    base_z: float = 0.0,
    obstacles: Iterable[Placed] = (),
    negatives: Negatives | Iterable[KeepClear] = (),
    relation: NoOverlap = GROUP_RELATION,
    room: str = "",
) -> GroupPlacement | None:
    """The first of these positions the whole family fits at, else ``None``.

    First rather than best, and in the order given.  A scatter stack has
    already decided what a good position looks like -- along a wall, out of the
    doorways, jittered off the lattice -- so a second opinion here would be
    scoring the same points twice with less information.  The order is the
    caller's, so a caller that wants the best position sorts before it calls.

    A spot that carries its own height, as a snapped
    :class:`~zmforge.placement.scatter.Candidate` does, stands the group at
    that height; one that does not uses ``base_z``.
    """
    obstacles = tuple(obstacles)
    zones = negatives if isinstance(negatives, Negatives) else Negatives.of(negatives)
    for item in spots:
        x, y, yaw, z = _spot(item)
        attempt = try_group(
            group, (x, y), yaw,
            base_z=base_z if z is None else z,
            obstacles=obstacles, negatives=zones, relation=relation, room=room,
        )
        if attempt.ok:
            return attempt.placement
    return None
