"""Thin adapters: a command line now, an MCP server later.

Adapters convert arguments and print results.  They hold no geometry, no
naming rules and no build logic, so a second adapter costs nothing and the
library stays usable without either.
"""

from __future__ import annotations

from .cli import main

__all__ = ["main"]
