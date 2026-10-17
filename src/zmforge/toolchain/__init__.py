"""Running the compiler, the lighting baker and the linker, and judging them.

Every verdict here comes from **evidence in a stage's log**, never from its
exit code (spec 7.3, item K3).  The compiler exits 0 on an unsealed map and on
missing materials; the linker never exits 0 at all -- 2000 and 154000 have both
been measured on successful links.  A chain that read exit codes would call a
leaking map a success and a good link a failure, in that order.

Runners are the only place that knows how a process is started: natively on
this machine, or under Wine in a container on this machine.  Both hand back
the same :class:`~.stages.StageOutcome`; :func:`~.targets.select_target` checks
that the Wine one is usable.
"""

from __future__ import annotations

from .evidence import (
    StageEvidence,
    decode_tool_output,
    read_bake_log,
    read_compile_log,
    read_link_log,
    read_refresh_log,
    strip_colour,
)
from .layout import ToolsLayout, resolve_layout, stage_environment
from .runner import LocalRunner, RunResult
from .stages import ChainOutcome, StageOutcome, Toolchain
from .targets import Target, select_target
from .wine import WineRunner

__all__ = [
    "ToolsLayout",
    "resolve_layout",
    "stage_environment",
    "StageEvidence",
    "decode_tool_output",
    "strip_colour",
    "read_compile_log",
    "read_link_log",
    "read_refresh_log",
    "read_bake_log",
    "RunResult",
    "LocalRunner",
    "WineRunner",
    "Target",
    "select_target",
    "StageOutcome",
    "ChainOutcome",
    "Toolchain",
]
