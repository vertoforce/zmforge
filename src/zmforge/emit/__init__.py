"""Turning a blueprint into the files the tools read.

Four outputs, all derived from the same model on every commit and never
patched in place: the map source, the two GSC scripts, the linker's asset
manifest, and the plan view that becomes the map's loading screen.  Nothing in here runs a tool or touches the filesystem -- callers
get text back and :class:`~zmforge.project.Project` decides where it lands.
"""

from __future__ import annotations

from .manifest import display_title, render_localisation_manifest, render_manifest
from .planview import PLAN_PALETTE, PlanPalette, PlanView, render_plan
from .mapfile import build_document, world_solids_of
from .scripts import render_client_script, render_server_script

__all__ = [
    "build_document",
    "world_solids_of",
    "render_server_script",
    "render_client_script",
    "render_manifest",
    "render_localisation_manifest",
    "display_title",
    "render_plan",
    "PlanView",
    "PlanPalette",
    "PLAN_PALETTE",
]
