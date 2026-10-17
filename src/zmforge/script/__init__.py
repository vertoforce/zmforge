"""Custom gameplay script: the model, the checker and the stock symbols.

``zmforge`` generates a map's ``.gsc`` and ``.csc`` whole, every commit
(spec 5.3).  That rules out the obvious way to add gameplay logic -- opening
the file and typing -- because the next commit would erase it.  This package
is the supported way in instead: a caller hands the engine a
:class:`~zmforge.script.custom.CustomScript`, the emitter weaves it into the
generated file at the places the framework's ordering allows, and
:mod:`zmforge.script.gsc` checks the result before it can reach a build.

The three modules, in the order a caller meets them:

:mod:`~zmforge.script.custom`
    what a caller writes: functions, statements, and where they go;
:mod:`~zmforge.script.symbols`
    the stock engine and script functions the checker will accept, each with
    the file it was read out of;
:mod:`~zmforge.script.gsc`
    the checker: brackets, terminators, and calls to things nothing defines.
"""

from __future__ import annotations

from .custom import (
    CustomFunction,
    CustomScript,
    Slot,
    merge,
)
from . import tricks
from .gsc import Issue, ScriptSource, scan

__all__ = [
    "CustomFunction",
    "CustomScript",
    "Slot",
    "merge",
    "Issue",
    "ScriptSource",
    "scan",
    "tricks",
]
