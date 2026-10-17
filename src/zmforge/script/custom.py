"""The seam: gameplay logic a caller supplies, woven into a generated file.

The engine regenerates ``<map>.gsc`` from a model on every commit, so the
one thing a caller must never do is edit the emitted file.  A
:class:`CustomScript` is the supported alternative.  It is a *model* of the
logic, not a patch of the text: functions with bodies, and statements bound
to one of a small number of :class:`Slot` positions that the framework's
required ordering leaves free.

Two properties fall out of doing it this way, and both are the point:

* **Generated scaffolding cannot corrupt hand-written logic.**  Custom
  functions are appended whole, after everything the engine writes, and the
  engine never parses them back or edits around anchors.
* **Hand-written logic cannot corrupt the scaffolding.**  A slot is the only
  place a statement may land, and no slot exists between
  ``level.dog_rounds_allowed`` and the framework entry, so the ordering
  conformance check Z10 tests cannot be broken by anything a caller writes.

Names are checked here, before emission, because a collision with a
generated function is silent in GSC: the second definition wins and the map
loads with the wrong ``main``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum

__all__ = ["Slot", "CustomFunction", "CustomScript", "merge", "IDENTIFIER"]

IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")


class Slot(Enum):
    """Where a custom statement may go.

    The values are the four positions that are safe.  There is deliberately
    no slot between the dog-round assignment and ``zm_usermap::main()``:
    spec 4.12 makes that ordering load-bearing, and a slot there would let a
    caller break it.

    ``BEFORE_ENTRY``
        top of ``main``, *before* ``level.dog_rounds_allowed``.  This is
        where a level variable the framework reads at start-up belongs.
    ``AFTER_ENTRY``
        in ``main`` after the framework entry, before the zone wiring.
        Threads started here run with the framework already initialised.
    ``ZONE_HOOK``
        inside the generated zone hook, which the zone manager calls once.
    ``CLIENT_INIT``
        in the client script's ``__init__``, the system-registered callback.
    """

    BEFORE_ENTRY = "before_entry"
    AFTER_ENTRY = "after_entry"
    ZONE_HOOK = "zone_hook"
    CLIENT_INIT = "client_init"

    @property
    def client_side(self) -> bool:
        return self is Slot.CLIENT_INIT


@dataclass(frozen=True, slots=True)
class CustomFunction:
    """One function to append to the generated script.

    ``body`` is the statements between the braces, one per element, written
    without leading indentation -- the emitter indents.  ``purpose`` is
    carried into the emitted file as a comment, so a reader of the generated
    script can tell what a block of logic is for without the blueprint.
    """

    name: str
    body: tuple[str, ...]
    params: tuple[str, ...] = ()
    purpose: str = ""
    client_side: bool = False

    def __post_init__(self) -> None:
        if not IDENTIFIER.match(self.name):
            raise ValueError(f"{self.name!r} is not a usable GSC function name")
        for param in self.params:
            if not IDENTIFIER.match(param):
                raise ValueError(f"{param!r} is not a usable GSC parameter name")
        if not self.body:
            raise ValueError(
                f"custom function {self.name!r} has an empty body; an empty "
                "function is almost always a half-finished edit"
            )

    @property
    def signature(self) -> str:
        return f"function {self.name}( {', '.join(self.params)} )" if self.params \
            else f"function {self.name}()"


@dataclass(frozen=True, slots=True)
class CustomScript:
    """Everything one caller adds to a map's scripts.

    Instances are immutable and combine with :func:`merge`, so a map can be
    built from several independent mechanics without any of them knowing
    about the others.
    """

    using: tuple[str, ...] = ()
    client_using: tuple[str, ...] = ()
    functions: tuple[CustomFunction, ...] = ()
    statements: tuple[tuple[Slot, str], ...] = ()
    #: Assets this logic calls for, as ``(prefix, name)`` pairs, so a
    #: mechanic that plays a custom sound declares the bank that carries it.
    #: Calling for an undeclared asset is a runtime failure; declaring one
    #: that does not exist is a linker complaint, which is the cheaper of the
    #: two to find.
    assets: tuple[tuple[str, str], ...] = ()
    #: Free text recorded in the blueprint and in the emitted file's header:
    #: what this logic is and, where it matters, what it was read out of.
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        seen: dict[str, CustomFunction] = {}
        for function in self.functions:
            if function.name in seen:
                raise ValueError(
                    f"two custom functions are both called {function.name!r}"
                )
            seen[function.name] = function
        for slot, statement in self.statements:
            if not isinstance(slot, Slot):
                raise TypeError(f"{slot!r} is not a Slot")
            if not statement.strip():
                raise ValueError("a custom statement is empty")

    # -- reading -----------------------------------------------------------
    def in_slot(self, slot: Slot) -> tuple[str, ...]:
        """Statements bound to ``slot``, in the order they were added."""
        return tuple(text for bound, text in self.statements if bound is slot)

    def server_functions(self) -> tuple[CustomFunction, ...]:
        return tuple(f for f in self.functions if not f.client_side)

    def client_functions(self) -> tuple[CustomFunction, ...]:
        return tuple(f for f in self.functions if f.client_side)

    @property
    def empty(self) -> bool:
        return not (self.functions or self.statements or self.using
                    or self.client_using or self.assets)

    # -- building ----------------------------------------------------------
    def with_note(self, note: str) -> "CustomScript":
        return replace(self, notes=self.notes + (note,))


def merge(*parts: CustomScript) -> CustomScript:
    """One :class:`CustomScript` from several, order preserved.

    ``#using`` lines are de-duplicated because a repeated one is a compile
    error; function names are not, because two mechanics defining the same
    name is a mistake a caller wants to hear about.
    """
    using: list[str] = []
    client_using: list[str] = []
    functions: list[CustomFunction] = []
    statements: list[tuple[Slot, str]] = []
    assets: list[tuple[str, str]] = []
    notes: list[str] = []
    for part in parts:
        for module in part.using:
            if module not in using:
                using.append(module)
        for module in part.client_using:
            if module not in client_using:
                client_using.append(module)
        functions.extend(part.functions)
        statements.extend(part.statements)
        for asset in part.assets:
            if asset not in assets:
                assets.append(asset)
        notes.extend(part.notes)
    return CustomScript(
        using=tuple(using),
        client_using=tuple(client_using),
        functions=tuple(functions),
        statements=tuple(statements),
        assets=tuple(assets),
        notes=tuple(notes),
    )
