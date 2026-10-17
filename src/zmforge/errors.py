"""Typed errors raised across zmforge.

The hierarchy is deliberately shallow: every failure a caller can cause is a
``ForgeError``, and the leaf type names the constraint that was violated so a
facade can map it onto an error code without string matching.
"""

from __future__ import annotations


class ForgeError(Exception):
    """Base class for every error this library raises on purpose."""


class BlueprintError(ForgeError):
    """A caller asked the blueprint for something it cannot represent."""


class InvalidBounds(BlueprintError):
    """A box has a non-positive extent on some axis."""


class OpeningDoesNotFit(BlueprintError):
    """A doorway or window does not lie inside the wall it was asked to cut."""


class UnknownMaterial(BlueprintError):
    """A material name is not in the known-clean catalogue (strict mode only)."""


class UnknownZone(BlueprintError):
    """A zone handle was used that this blueprint never issued."""


class DuplicateId(BlueprintError):
    """Two elements were given the same stable id."""


class NotOnFloor(BlueprintError):
    """A placement sits too far above (or inside) the surface beneath it."""


class InteractiveBlocked(BlueprintError):
    """An interactive item was placed where another one stops it being used.

    An item you cannot reach is an item that does not exist, so this is
    raised at placement time rather than reported afterwards.  The volumes
    and the measurements behind them are :mod:`zmforge.blueprint.reach`; the
    same question asked of a finished map is check ``Z42``.
    """

    def __init__(self, message: str, clash=None) -> None:
        #: The :class:`zmforge.blueprint.reach.Clash` that was refused, so a
        #: caller can read the two ids and the overlap off it rather than out
        #: of the message.
        self.clash = clash
        super().__init__(message)


class MapExists(ForgeError):
    """A map of this name is already in the tools root and nothing said replace it.

    ``path`` is the existing .map, so a front end can word its own way out
    (the CLI says ``pass --overwrite``; the library says ``overwrite=True``).
    """

    def __init__(self, path) -> None:
        self.path = path
        super().__init__(
            f"{path} already exists; pass overwrite=True to replace it, or "
            "use Project.open to keep what is there"
        )


class RegenerateWouldDiscard(ForgeError):
    """A recipe was asked to rewrite editor work it cannot carry forward.

    ``origin.edited_since_generate`` is set when a map editor saves the
    document.  A regenerate
    normally merges that work into its own output -- a three-way merge by
    element id against the last generated document
    (:mod:`zmforge.docmerge`) -- and this is raised only when there is no such
    ancestor beside the map, which leaves nothing to attribute the differences
    to and makes a merge a guess.  A caller that means to lose the edits passes
    ``discard_edits=True``.  Raised rather than reported, because the
    alternative is a person's work disappearing with a warning nobody reads.
    """


class MapTextError(ForgeError):
    """A ``.map`` file could not be parsed."""

    def __init__(self, message: str, line_number: int | None = None) -> None:
        self.line_number = line_number
        if line_number is not None:
            message = f"line {line_number}: {message}"
        super().__init__(message)


class ToolchainError(ForgeError):
    """A build stage could not be started."""


class NoInteractiveDesktop(ToolchainError):
    """The lighting bake was requested where no interactive desktop exists."""
