"""A map on disk: one blueprint, one commit, every file derived.

The reference design this replaces opened the map file, appended a few
entities and saved it once per helper call, so nothing ever saw the whole map
and a failure halfway through left a half-written one.  Here the model is
built in memory, validated as a unit, and every file is written in a single
``commit`` -- each one through a temporary file and a rename, so an
interrupted write cannot leave a mapper with half a map (spec 8.1, 8.4).

``commit`` also refuses to clobber a file it did not produce: it stores a
hash of everything it writes and compares before overwriting, because the
mapper's hand edits are not the generator's to discard (spec 5.3).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Mapping, Sequence

from . import docmerge, mapdoc, verify
from .blueprint.model import Blueprint
from .blueprint.script_plan import ScriptPlan, ZoneEdge
from .emit.manifest import display_title, render_localisation_manifest, render_manifest
from .emit.sound import (
    COMPANION_SUFFIXES,
    read_alias_header,
    render_alias_bank,
    render_companions,
    render_localised_bank,
)
from .emit.mapfile import build_document
from .emit.strings import render_str_file
from .emit.weapons import weapon_table_text
from .emit.planview import render_plan
from .emit.scripts import render_client_script, render_server_script
from .errors import ForgeError, MapExists, RegenerateWouldDiscard
from .images.png import ImageError, read_png_header
from . import mapsource, progress
from .mapsource import read as read_map
from .mapsource import render_map_text
from .surfaces.ground import TerrainRecord
from .toolchain.layout import (
    LOADING_IMAGE_SIZE,
    MAP_NAME_RE,
    PREVIEW_IMAGE_SIZE,
    ToolsLayout,
    resolve_layout,
    validate_map_name,
)
from .verify.report import Report

#: Beside the collmaps this project generates, the list of names it wrote,
#: so a rebuild refreshes its own files and never one the install shipped.
GENERATED_COLLMAPS = ".zmforge-collmaps.json"

__all__ = ["Project", "CommitResult", "MAP_NAME_RE"]


_RECORD_VERSION = 1


@dataclass
class CommitResult:
    """What a commit wrote, and what the checks thought of it."""

    written: list[Path] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)
    report: Report = field(default_factory=Report)
    skipped: list[str] = field(default_factory=list)
    #: What the three-way merge carried forward from the document on disk,
    #: or ``None`` when there was nothing to merge -- no editor edit, or the
    #: caller asked for them to be discarded (:mod:`zmforge.docmerge`).
    #: ``merge.notes`` is empty when the merge was a no-op.
    merge: "docmerge.MergeResult | None" = None
    #: Z46's fix passes on this commit: (tops given a zombie traversal,
    #: tops capped with clip).
    camping: tuple[int, int] = (0, 0)

    @property
    def ok(self) -> bool:
        return self.report.ok


class Project:
    """A named map, its blueprint and every path it owns under the tools root.

    ``tools_root`` is the mod-tools installation for a real build, or any
    directory shaped like one for a dry run on a machine without the tools:
    nothing in this class runs an executable, it only writes files where the
    tools will look for them.
    """

    def __init__(self, name: str, layout: ToolsLayout, blueprint: Blueprint) -> None:
        self.name = name
        self.layout = layout
        self.blueprint = blueprint
        self._committed: dict[str, str] = {}
        #: The document revision this project last saw on disk -- read by
        #: :meth:`open`, refreshed by every commit.  ``None`` means this project
        #: has never seen one, which is a fresh :meth:`create`.
        self._doc_revision: str | None = None
        #: Whether this project has looked at the document's place on disk at
        #: all.  A commit compares only when it has; a brand new project is not
        #: in a race with a document nobody went looking for.  Looking and
        #: finding nothing counts: "there was no document when I started" is an
        #: expectation like any other, and a document that appeared since is
        #: somebody else's work (:meth:`_refuse_stale_document`).
        self._document_seen = False
        #: The hash of the ``.map`` this project's document describes, which is
        #: the hash of the file that is actually on disk -- not of the text a
        #: commit rendered, because a commit that keeps a hand-edited ``.map``
        #: does not write that text anywhere.
        self._geometry_sha: str | None = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        name: str,
        tools_root: str | PurePath | ToolsLayout,
        *,
        seed: str | None = None,
        overwrite: bool = False,
        blueprint: Blueprint | None = None,
        title: str | None = None,
    ) -> "Project":
        """A new project, empty or around a blueprint a recipe already built.

        ``title`` is the display name menus show; leaving it ``None`` derives
        one from the map name.  Fails if the map already exists, unless
        ``overwrite``.
        """
        layout = resolve_layout(tools_root)
        validate_map_name(name, layout)
        if blueprint is None:
            blueprint = Blueprint(name, seed=seed, title=title)
        elif blueprint.name != name:
            raise ForgeError(
                f"blueprint is named {blueprint.name!r} but the project is {name!r}"
            )
        if title is not None:
            blueprint.title = title
        project = cls(name, layout, blueprint)
        existing = Path(str(layout.map_source(name)))
        if existing.exists() and not overwrite:
            raise MapExists(existing)
        if overwrite:
            # Replacing a map this tool generated before must actually replace
            # it.  With no memory of what was written last time every existing
            # file looks hand-edited and commit keeps all of them, which once
            # left a rebuild shipping the previous script.  Adopt the
            # old document's hashes and revision so files we wrote are
            # rewritten, files somebody edited by hand are still kept, and the
            # revision guard sees the document it is replacing.
            model_path = cls._model_path_for(layout, name)
            if model_path.exists():
                try:
                    stored = json.loads(model_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    stored = {}
                hashes = stored.get("hashes")
                if isinstance(hashes, Mapping):
                    project._committed = {str(k): str(v) for k, v in hashes.items()}
                revision = stored.get("revision")
                if isinstance(revision, Mapping) and revision.get("id"):
                    project._doc_revision = str(revision["id"])
                if stored:
                    # A revision was read, so there is something to be stale
                    # against: arm the compare.  Reading the revision and then
                    # never comparing it is how two regenerates from the same
                    # document were both accepted, the second replacing the
                    # first without a word.
                    project._document_seen = True
        return project

    @classmethod
    def open(
        cls,
        name: str,
        tools_root: str | PurePath | ToolsLayout,
        *,
        repair_geometry: bool = False,
    ) -> "Project":
        """Reopen a project from what is on disk.

        With a stored model file the map's identity, script plan and commit
        hashes come back.  The geometry in the ``.map`` is adopted as an
        imported element and preserved verbatim: blueprint operations add to
        it but cannot edit what is already there.  A foreign Radiant map with
        no model file loads the same way.

        ``repair_geometry`` is the way out of the one window a commit cannot
        close.  A commit renames the ``.map`` and then, a few files later, the
        document; a crash in between leaves a document describing the previous
        geometry, and the refusal below then applies to every later open,
        compile and editor save.  Opening with ``repair_geometry=True`` says
        "the ``.map`` on disk is the geometry": the document is re-anchored to
        it through :func:`zmforge.mapdoc.save` and the project opens.  It is
        never the default, because a silent re-anchor is exactly the drift
        ``geometry.sha256`` exists to catch, and the refusal names both hashes
        so the person can decide which file is the one they meant.
        """
        layout = resolve_layout(tools_root)
        validate_map_name(name, layout)
        map_path = Path(str(layout.map_source(name)))
        if not map_path.exists():
            raise ForgeError(f"no map source at {map_path}")

        model_path = cls._model_path_for(layout, name)
        stored: Mapping[str, object] = {}
        if model_path.exists():
            stored = json.loads(model_path.read_text(encoding="utf-8"))
            if repair_geometry:
                stored = mapdoc.save(
                    model_path,
                    stored,
                    written_by=f"repair:{name}",
                    expect=mapdoc.read_revision(model_path),
                    reanchor_geometry=True,
                )
            else:
                # The document names the geometry it describes and records its
                # hash.  Reading a document against a ``.map`` that is no longer
                # that one is how a sidecar format goes quietly wrong -- the
                # script plan, the prop list and the hashes would all be about a
                # map that is not on disk any more -- so the disagreement is a
                # refusal here, naming both hashes, rather than a surprise three
                # stages later.
                mapdoc.verify_geometry(model_path, stored)

        stored_title = stored.get("title")
        blueprint = Blueprint(
            name,
            seed=str(stored.get("seed", name)),
            title=str(stored_title) if stored_title else None,
        )
        plan = stored.get("script")
        if isinstance(plan, Mapping):
            blueprint.script = _plan_from_dict(name, plan)
        project = cls(name, layout, blueprint)
        project._committed = dict(stored.get("hashes", {}))  # type: ignore[arg-type]
        # What this project read, so a commit can tell whether the document
        # moved under it while the map was being worked on.
        project._doc_revision = (
            str((stored.get("revision") or {}).get("id") or "") or None  # type: ignore[union-attr]
        )
        # An open looked at the document's place on disk, so the compare is
        # armed whatever it found there.  Finding nothing is an expectation
        # too: a document that exists by the time this project commits is one
        # another session wrote, and writing over it blind is the loss this
        # guard is for.  ``_doc_revision`` is then ``None``, which is exactly
        # "I expect no document", and the conflict says so.
        project._document_seen = True
        project._geometry_sha = (
            str((stored.get("geometry") or {}).get("sha256") or "") or None  # type: ignore[union-attr]
        )

        document = read_map(map_path)
        blueprint.adopt(document, source_path=str(map_path), id="imported_source")
        return project

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    @staticmethod
    def _model_path_for(layout: ToolsLayout, name: str) -> Path:
        return Path(str(layout.map_source_dir)) / f"{name}.blueprint.json"

    @staticmethod
    def _base_path_for(layout: ToolsLayout, name: str) -> Path:
        """The last generated document, kept as the merge's common ancestor.

        A regenerate has to tell "the recipe changed this" from "somebody
        changed this in an editor", and the document on disk alone cannot say
        which: only a comparison against what the last generate wrote can.  So
        every commit leaves a byte-identical copy of the document it wrote
        beside it, and the next one merges against that
        (:mod:`zmforge.docmerge`).  Beside the map, named for it, because an
        ancestor stored anywhere else is an ancestor that can be separated from
        the document it belongs to.
        """
        return Path(str(layout.map_source_dir)) / f"{name}{docmerge.BASE_SUFFIX}"

    def paths(self) -> dict[str, Path]:
        """Every file this project owns, keyed by role.

        A map carrying its own sound owns three more kinds of file: the
        alias bank, its English companion, and one wave file per alias
        (``sound_wav:<alias>``).  They are absent from the dictionary when
        the map carries no sound, so nothing downstream checks for a bank
        that was never meant to exist.
        """
        layout, name = self.layout, self.name
        sounds: dict[str, Path] = {}
        if self.blueprint.custom_sounds:
            sounds["sound_bank"] = Path(str(layout.sound_bank(name)))
            sounds["localised_sound_bank"] = Path(str(layout.localised_sound_bank(name)))
            for suffix in COMPANION_SUFFIXES:
                sounds[f"sound_table:{suffix}"] = Path(
                    str(layout.sound_companion(name, suffix))
                )
            for sound in self.blueprint.custom_sounds:
                sounds[f"sound_wav:{sound.alias.name}"] = Path(
                    str(layout.sound_wav(name, sound.alias.wav_windows))
                )
        hud: dict[str, Path] = {}
        if getattr(self.blueprint, "hud_images", None):
            from .texture import hud_icons

            root = Path(str(layout.root))
            hud["hud_gdt"] = root / hud_icons.gdt_relative(name)
            for image in self.blueprint.hud_images:
                hud[f"hud_image:{image}"] = root / hud_icons.image_relative(name, image)
        return {
            **sounds,
            **hud,
            "map": Path(str(layout.map_source(name))),
            "server_script": Path(str(layout.server_script(name))),
            "client_script": Path(str(layout.client_script(name))),
            "manifest": Path(str(layout.manifest(name))),
            "localisation_manifest": Path(str(layout.localisation_manifest(name))),
            "loading_image": Path(str(layout.loading_image(name))),
            "preview_image": Path(str(layout.preview_image(name))),
            "workshop_json": Path(str(layout.workshop_json(name))),
            "workshop_thumbnail": Path(str(layout.workshop_thumbnail(name))),
            "weapon_table": Path(str(layout.weapon_table(name))),
            "localized_strings": Path(str(layout.localized_strings(name))),
            "props_gdt": Path(str(layout.props_gdt(name))),
            "model_export_dir": Path(str(layout.model_export_dir)),
            "collmap_dir": Path(str(layout.collmap_dir)),
            "terrain_record": Path(str(layout.map_source_dir))
            / f"{name}.terrain-record.json",
            "model": self._model_path_for(layout, name),
            "model_base": self._base_path_for(layout, name),
        }

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    def commit(
        self, *, force: bool = False, discard_edits: bool = False, **options
    ) -> CommitResult:
        """Write the map, refusing to write anything over a document that moved.

        The guard, and only the guard, is here; the writing is
        :meth:`_commit_locked` below, unchanged.  Two things are checked before
        a single file is touched, and both are answered by refusing rather than
        by writing and warning:

        * the document on disk is still the revision this project read (or last
          wrote).  A commit writes every file the map owns from one model -- the
          ``.map``, both scripts, the manifest, the images, the collmaps and the
          document -- so "write most of them and report a conflict" would leave a
          map half from each of two sessions, which is the failure this whole
          format exists to stop.
        * a document an editor has edited can be **merged** -- that is, the
          last generated document is still beside it to merge against.  A
          recipe is a generator and re-running it replaces the document, so
          the editor's work is carried across by a three-way merge rather
          than thrown away (:mod:`zmforge.docmerge`); the refusal is only
          for the one case a merge cannot be done at all, which is a document
          edited in an editor with no recorded ancestor.

        ``force=True`` overrides the first, because a regenerate that means it
        is a legitimate thing to want; it is just never the default.  It does
        **not** mean "discard": a forced regenerate still merges.
        ``discard_edits=True`` is the one flag that throws editor work away:
        it skips the merge entirely and writes the recipe's own document.  A
        document that moved under the project is a different session's map and
        is still refused, because nobody asked for that one to be discarded.

        The whole commit runs under the document's lock (:func:`zmforge.mapdoc.
        locked`), so the compare and the writes cannot interleave with another
        writer's, and the document's rename -- the last write of the commit -- is
        the point at which the new map becomes the committed one.  The ``.map``
        is renamed inside the same lock, so no reader can see a document whose
        ``geometry.sha256`` names geometry that is not there yet.

        ``**options`` is forwarded verbatim; the parameters are
        :meth:`_commit_locked`'s and are documented there.
        """
        target = self.paths()["model"]
        with mapdoc.locked(target):
            # ``discard_edits`` answers the editor-edit flag and nothing else.
            # A document whose revision moved is another session's regenerate,
            # not editor work this caller is choosing to throw away, so the
            # revision compare still refuses; only ``force`` overrides that.
            # ``force`` also still means "write despite model-level errors".
            self._refuse_stale_document(
                target, force=force, discard_edits=discard_edits
            )
            result = self._commit_locked(
                force=force, discard_edits=discard_edits, **options
            )
            # What this commit left on disk, so the next one on this project
            # compares against what it actually wrote.
            self._doc_revision = mapdoc.read_revision(target)
            self._document_seen = True
        return result

    def _refuse_stale_document(
        self, target: Path, *, force: bool, discard_edits: bool = False
    ) -> None:
        """Refuse to start a commit that would overwrite someone else's work.

        Called with the document's lock already held, so what it reads is what
        the commit will replace.  Nothing has been written when this raises.

        The two guards are answered by different flags on purpose.  The
        revision compare is about *another session*: the document on disk is no
        longer the one this project read, so somebody else generated or saved
        over it, and their work is not this caller's to discard.  Only ``force``
        skips it.  ``discard_edits`` is about *this map's editor edits*, which
        is the one thing the caller can knowingly throw away, so it skips that
        check alone.  Answering both with one flag let a second session say
        ``discard_edits=True`` and silently overwrite a regenerate it had never
        seen.

        The edit guard refuses only the one document a merge cannot be
        attempted on: editor work is
        carried across by a three-way merge against the last generated
        document (:meth:`_base_path_for`), and with no such ancestor on disk
        there is nothing to merge against -- the differences between the file
        and the recipe's output cannot be attributed to either side.
        """
        if force:
            return
        found = mapdoc.read_revision(target)
        if self._document_seen and found != self._doc_revision:
            raise mapdoc.MapDocConflict(target, self._doc_revision, found)
        if discard_edits:
            return
        if target.is_file():
            try:
                stored = json.loads(target.read_text(encoding="utf-8"))
            except ValueError:
                return  # not a document this project wrote; the checks above hold
            edited = bool((stored.get("origin") or {}).get("edited_since_generate"))
            if edited and not self.paths()["model_base"].is_file():
                raise RegenerateWouldDiscard(
                    f"{target} has been edited in a map editor since it was "
                    "generated (origin.edited_since_generate is set), and there "
                    "is no "
                    f"{self.paths()['model_base'].name} beside it to merge "
                    "against, so those edits cannot be carried forward; nothing "
                    "was written. Every generate from now on leaves that file, "
                    "so this is once per map: pass discard_edits=True "
                    "(--discard-edits on the CLI) to regenerate over the edits "
                    "and establish the ancestor."
                )

    def _commit_locked(
        self,
        *,
        force: bool = False,
        discard_edits: bool = False,
        strict_materials: bool = False,
        localisation_manifest: bool = False,
        sound_bank: bool = False,
        newline: str = "\n",
        worldspawn_overrides: Sequence[tuple[str, str]] = (),
        loading_screen: bool = True,
        loading_image: bytes | str | PurePath | None = None,
        preview_image: bytes | str | PurePath | None = None,
        render_root: str | PurePath | None = None,
    ) -> CommitResult:
        """Validate the model, then write every file it implies.

        Refuses to write while the model-level report has errors, unless
        ``force``: a map that fails these checks is one the game loads and
        then kills the player on, and finding that out costs a build plus a
        session.

        ``loading_screen`` also writes the two presentation images of
        Section 6.1 into the map's zone folder.  Left to itself it draws the
        map's own plan; ``loading_image`` / ``preview_image`` take PNG bytes
        or a path to a PNG instead, and are checked for the sizes the mod
        tools' template uses rather than resized.

        It also writes the Workshop publish settings (``zone/workshop.json``)
        and a 512 x 512 Workshop thumbnail beside them (:mod:`zmforge.workshop`).
        When *render_root* is given and holds a ``zmforge render`` run of this
        map, the thumbnail and (unless *preview_image* is supplied) the preview
        card are cut from its hero shot; otherwise both are the plan.
        """
        result = CommitResult()
        # P17's one wayfinding exception: bolts beside the doors on the
        # cheapest way to power (idempotent; ``bp.power_bolts = False`` opts out).
        from .dressing.power_bolts import paint_power_bolts

        progress.stage("placing power bolts and the gamble machine")
        paint_power_bolts(self.blueprint)
        # P22: the gamble machine at the map's farthest walk
        # (idempotent; ``bp.signature_gamble = False`` opts out; Z87).
        from .dressing.gamble import place_gamble_machine

        place_gamble_machine(self.blueprint)
        # Z46 (zm_cemetery): every top a player jumps
        # onto and no walker reaches gets a stock zombie traversal, or an
        # invisible clip cap where none fits.  Here, the last thing before the
        # verdict, so every caller (the CLI, review, scripts) and every late
        # dressing step (the power bolts above) is covered; idempotent.
        from .verify.camping import clip_camping_tops, reach_camping_tops

        progress.stage("fixing camping tops (Z46)")
        climbs, _left = reach_camping_tops(self.blueprint)
        result.camping = (climbs, clip_camping_tops(self.blueprint))
        progress.stage("model checks 1/4: zones, doors, spawns, materials")
        result.report = verify.blueprint(
            self.blueprint, strict_materials=strict_materials
        )
        if not result.report.ok and not force:
            return result
        progress.stage("writing the map, scripts and images")

        document = build_document(
            self.blueprint, worldspawn_overrides=worldspawn_overrides
        )
        document.newline = newline
        payloads: dict[str, str] = {
            "map": render_map_text(document),
            "server_script": render_server_script(self.blueprint.script, newline=newline),
            "client_script": render_client_script(self.blueprint.script, newline=newline),
            "manifest": render_manifest(
                self.name,
                title=display_title(self.name, self.blueprint.title),
                sound_bank=sound_bank,
                assets=tuple(getattr(self.blueprint, "assets", ())),
                newline=newline,
            ),
        }
        if localisation_manifest:
            payloads["localisation_manifest"] = render_localisation_manifest(
                self.name, newline=newline
            )
        if self.blueprint.ships_weapon_table():
            payloads["weapon_table"] = self._weapon_table_text(newline=newline)
        if self.blueprint.ships_localized_strings():
            payloads["localized_strings"] = self._localized_strings_text()
        if self.blueprint.custom_sounds:
            payloads.update(self._sound_bank_text())
        hud_images = getattr(self.blueprint, "hud_images", None) or {}
        if hud_images:
            from .texture.hud_icons import hud_gdt_document

            payloads["hud_gdt"] = hud_gdt_document(self.name, tuple(hud_images))

        images: dict[str, bytes] = {}
        if loading_screen:
            images["loading_image"] = self._presentation_image(
                loading_image, LOADING_IMAGE_SIZE, "loading_image", result.report
            )
            images.update(self._workshop_images(preview_image, render_root, result.report))

        for sound in self.blueprint.custom_sounds:
            images[f"sound_wav:{sound.alias.name}"] = sound.wav_bytes
        for image, png in hud_images.items():
            images[f"hud_image:{image}"] = png

        paths = self.paths()
        for directory in self.layout.directories_to_create(self.name):
            Path(str(directory)).mkdir(parents=True, exist_ok=True)
        if localisation_manifest:
            paths["localisation_manifest"].parent.mkdir(parents=True, exist_ok=True)
        if "weapon_table" in payloads:
            paths["weapon_table"].parent.mkdir(parents=True, exist_ok=True)
        if "localized_strings" in payloads:
            paths["localized_strings"].parent.mkdir(parents=True, exist_ok=True)
        for role, target in paths.items():
            if role.startswith(("sound_bank", "localised_sound_bank", "sound_table:")):
                target.parent.mkdir(parents=True, exist_ok=True)
        for role in images:
            if role.startswith(("sound_wav:", "hud_image:")):
                paths[role].parent.mkdir(parents=True, exist_ok=True)
        if "hud_gdt" in payloads:
            paths["hud_gdt"].parent.mkdir(parents=True, exist_ok=True)

        # Every file of the map is written to a temporary beside its target
        # first and only renamed into place at the end, all together: a rename
        # that fails part way (Windows refuses one over a file another program
        # holds open, WinError 5/32) is rolled back, so the map on disk is
        # never half from this commit and half from the last one.
        staged = _StagedWrites()
        committed_before = dict(self._committed)
        try:
            self._stage_map_files(
                result, staged, paths, payloads, images, force=force, discard_edits=discard_edits
            )
            staged.commit()
        except BaseException:
            staged.discard()
            self._committed = committed_before
            raise

        for terrain in self.blueprint.elements(_terrain_type()):
            record: TerrainRecord = terrain.record
            record.write_json(paths["terrain_record"])
            result.written.append(paths["terrain_record"])
            break

        result.written.extend(self._write_prop_collmaps())

        progress.stage("file checks")
        result.report.extend(
            verify.files(
                self, strict_materials=strict_materials, presentation=loading_screen
            ).findings
        )
        return result

    def _stage_map_files(
        self,
        result: CommitResult,
        staged: "_StagedWrites",
        paths: Mapping[str, Path],
        payloads: Mapping[str, str],
        images: Mapping[str, bytes],
        *,
        force: bool,
        discard_edits: bool,
    ) -> None:
        """Stage every file :meth:`_commit_locked` owns into *staged*, document last."""
        for role, text in payloads.items():
            target = paths[role]
            if not force and self._would_clobber(role, target):
                result.skipped.append(str(target))
                result.report.add(
                    verify.warning(
                        "hand_edited",
                        f"{target} has changed since this project last wrote it, so "
                        "it was left alone; pass force=True to overwrite it",
                    )
                )
                continue
            staged.stage(target, text.encode("utf-8"))
            digest = _digest(text)
            self._committed[role] = digest
            result.hashes[role] = digest
            result.written.append(target)

        for role, blob in images.items():
            target = paths[role]
            if not force and self._would_clobber_bytes(role, target):
                result.skipped.append(str(target))
                result.report.add(
                    verify.warning(
                        "hand_edited",
                        f"{target} has changed since this project last wrote it, so "
                        "it was left alone; pass force=True to overwrite it",
                    )
                )
                continue
            staged.stage(target, blob)
            digest = _digest_bytes(blob)
            self._committed[role] = digest
            result.hashes[role] = digest
            result.written.append(target)

        # The document describes the ``.map`` that is on disk, so the hash is
        # taken from the file rather than from the text this commit rendered.
        # They differ in exactly the case that matters: a ``.map`` somebody
        # hand-edited is kept (the ``hand_edited`` warning above), and recording
        # the hash of the text that was *not* written left a document naming
        # geometry nobody had -- which :meth:`open`, ``mapdoc.save`` and the
        # compile all then refused, so the mapper's only way forward was
        # ``force``, which threw the hand edit away.
        # The ``.map`` this commit will rename into place is still a temporary.
        staged_map = staged.digest_of(paths["map"])
        if staged_map is not None:
            self._geometry_sha = staged_map
        elif paths["map"].is_file():
            self._geometry_sha = mapdoc.file_digest(paths["map"])

        # Stamped with a content revision on the way out, so the document can be
        # handed between this generator and an editor without either
        # overwriting the other blind: a writer says which revision it read, and
        # a write against a stale one is refused rather than merged
        # (:mod:`zmforge.mapdoc`).  Written through the same canonical speller
        # both sides use, so a re-run of the same model produces the same bytes
        # and a diff shows a real change.
        #
        # The document this commit replaces is named as the new revision's
        # parent, which is both the history the format promises and what makes
        # a regenerate a new revision at all: with no parent, re-running the
        # same recipe over its own output hashed to the identical id, so a
        # second session holding the first's revision saw no change and
        # replaced it without a conflict.
        state = self._model_state()
        if self._doc_revision:
            state["revision"] = {"id": self._doc_revision}
        # Carry the editor's work across, unless the caller said to drop it.
        # Done here, on the state about to be stamped, so what gets a revision
        # id is the merged document -- a merge applied after the stamp would
        # leave a document whose recorded revision is the hash of a different
        # one, which every later compare would then call a conflict.
        # The recipe's own document for this run, before anything is merged
        # into it.  This, and not the file that ends up on disk, is the
        # ancestor the next regenerate compares against: the base has to answer
        # "what would the generator have written", so that an edit carried
        # forward last time still reads as the user's edit next time.  Storing
        # the *merged* document instead made every carried edit look like a
        # change the recipe had made, so the regenerate after a merge reported
        # a conflict on every edit it had just carried -- measured, and the
        # reason this is written from a separate stamp.
        recipe_text = mapdoc.canonical_text(
            mapdoc.stamp(state, written_by=f"recipe:{self.name}")
        )
        if not discard_edits:
            result.merge = self._merge_editor_edits(
                paths["model"], paths["model_base"], state
            )
            if result.merge is not None:
                state = result.merge.document
        model_text = mapdoc.canonical_text(
            mapdoc.stamp(
                state,
                written_by=f"recipe:{self.name}",
            )
        )
        # Written on every commit, discard included: discarding resets the
        # ancestor to the recipe's own output, which is what "start clean"
        # means.  With nothing to merge the two files are byte-identical.
        staged.stage(paths["model_base"], recipe_text.encode("utf-8"))
        # The document is renamed last: it is the commit point.
        staged.stage(paths["model"], model_text.encode("utf-8"))
        result.written.append(paths["model"])
        result.written.append(paths["model_base"])

    # ------------------------------------------------------------------
    def _merge_editor_edits(
        self, target: Path, base_path: Path, state: dict
    ) -> "docmerge.MergeResult | None":
        """Merge what an editor saved into the document this commit will write.

        Returns ``None`` when there is nothing to merge -- no document on disk,
        no recorded ancestor, or an on-disk document identical to that ancestor
        in the two halves that describe the map.  ``None`` and "a merge with no
        notes" are different answers on purpose: the first says no merge
        happened, the second says one ran and found nothing to carry, and only
        the second is worth a line in a report.

        Called with the document's lock held, from inside the commit, so the
        file read here is the file about to be replaced.  A base or a document
        that will not parse is treated as absent rather than as an error: the
        commit's job is to write a map, and an unreadable ancestor makes the
        merge impossible, not the generate.
        """
        if not target.is_file() or not base_path.is_file():
            return None
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
            base = json.loads(base_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(current, Mapping) or not isinstance(base, Mapping):
            return None
        if all(
            current.get(section) == base.get(section)
            for section in docmerge.MERGED_SECTIONS
        ):
            # The document on disk is exactly what the last generate produced:
            # nobody has edited it, so the regenerate is the whole answer and
            # the merge would be the identity.  Skipping it keeps an untouched
            # map's output byte-identical to a plain regenerate, and keeps
            # ``result.merge is None`` meaning "no editor work was involved".
            return None
        return docmerge.merge_document(base, current, state)

    # ------------------------------------------------------------------
    def _write_prop_collmaps(self) -> list[Path]:
        r"""Collision for the solid props whose stock model ships none.

        ``cod2map64`` bakes a ``misc_model``'s collision when the entity says
        ``use_collmap "1"`` **and** ``share\raw\collmaps\<model>.map``
        exists; the lookup is by filename, at compile time.  Measured on the mod tools
        install: 26 of the 123 stock models this map dresses with
        ship such a file and 97 do not, so without this step the flag would be
        a no-op on three quarters of the furniture and the map would still be
        walk-through.  See :func:`zmforge.props.collision.stock_collmap_document`
        for the two probe compiles that establish it.

        **Treyarch's own files are never touched.**  A model that already has
        a collmap keeps it -- theirs is authored to the shape of the art,
        ours is a box -- and the names this wrote are remembered in
        ``.zmforge-collmaps.json`` beside them so a rebuild refreshes its own
        files and only its own.
        """
        from .blueprint.elements import PropScatter
        from .props.collision import STOCK_COLLMAPS, kit_collmap_document, stock_collmap_document
        from .props.origins import drawn_box

        boxes: dict[str, tuple] = {}
        for scatter in self.blueprint.elements(PropScatter):
            for prop in scatter.props:
                if prop.solid and prop.collision_box is not None:
                    # A recipe copies the catalogue box, which for a model
                    # with a moved root bone is not where it draws.
                    boxes.setdefault(prop.model, drawn_box(prop.model, prop.collision_box))
                elif prop.solid and prop.model.startswith("zmf_prop_"):
                    # A solid kit prop placed without a box (a Prop built
                    # directly, e.g. dressing/gamble.py's ATM) still gets its
                    # one collmap: kit_collmap_document reads the recorded box
                    # itself.  Without this, use_collmap named a file nobody
                    # wrote and Z21 stopped the map.
                    boxes.setdefault(prop.model, None)
        if not boxes:
            return []
        directory = Path(str(self.layout.collmap_dir))
        directory.mkdir(parents=True, exist_ok=True)
        ledger = directory / GENERATED_COLLMAPS
        try:
            ours = set(json.loads(ledger.read_text(encoding="utf-8")))
        except Exception:
            ours = set()
        written: list[Path] = []
        for model in sorted(boxes):
            if model in STOCK_COLLMAPS:
                continue  # the install authored one; theirs is the better shape
            target = directory / f"{model}.map"
            if target.exists() and model not in ours:
                continue
            # A zmforge kit prop has one collmap, the same file the props
            # converter writes (props/collision.py kit_collmap_document).
            document = (kit_collmap_document(model) if model.startswith("zmf_prop_")
                        else stock_collmap_document(model, boxes[model]))
            mapsource.write(target, document)
            ours.add(model)
            written.append(target)
        ledger.write_text(json.dumps(sorted(ours), indent=1) + "\n", encoding="utf-8")
        return written

    # ------------------------------------------------------------------
    def _sound_bank_text(self) -> dict[str, str]:
        r"""The map's alias bank and its English companion, as text.

        The 102 column names come from the install's own
        ``share\raw\sound\aliases\user_aliases.csv`` rather than from a copy
        in this repository: it is Treyarch's data, and a bank whose columns
        disagree with the install's would load every value into the wrong
        field.  A root without that file is a hard error for the same reason
        the weapon table is: a bank built from guessed columns links, loads
        and plays the wrong thing, and nothing downstream says so.

        The bank is always written under the map's own name.  Anything else
        is a bank the linker does not open (spec 6.2, measured).
        """
        header = read_alias_header(self.layout.alias_template)
        aliases = [sound.alias for sound in self.blueprint.custom_sounds]
        payloads = {
            "sound_bank": render_alias_bank(aliases, header),
            "localised_sound_bank": render_localised_bank(header),
        }
        for suffix, text in render_companions(self.layout.sound_raw_dir).items():
            payloads[f"sound_table:{suffix}"] = text
        return payloads

    # ------------------------------------------------------------------
    def _localized_strings_text(self) -> str:
        r"""The map's own ``<map>.str``, the words on its wall-buy prompts.

        Written with CRLF whatever line ending the rest of the commit uses,
        which is the one payload here that does not follow the document.  A
        ``.str`` is not a file this generator round-trips: it is written for
        StringEd's reader, and the format is copied from a shipped map whose
        own file is CRLF (``ohm-nabar/zm_building``,
        ``english/localizedstrings/zm_abbey.str``).  Nothing has been
        measured about an LF ``.str``, so the shipped shape is what is
        emitted.
        """
        return render_str_file(self.blueprint.localized_strings())

    # ------------------------------------------------------------------
    def _weapon_table_text(self, *, newline: str = "\n") -> str:
        """The map's own weapon table, built over the install's own.

        The stock table is **read**, never carried in this repository: it is
        Treyarch's data, and a copy here would go stale against the install
        it has to agree with.  A re-priced row is that install's row with the
        cost column replaced, so everything else about the weapon -- its
        upgrade, its voice-over, whether the box may offer it -- survives.

        A map that asks for a price on a root with no stock table is a hard
        error rather than a table built from defaults: the defaults would
        link, load and hand the player a stripped weapon, and nothing
        downstream would say so.
        """
        stock_path = Path(str(self.layout.stock_weapon_table))
        try:
            stock_text = stock_path.read_text(encoding="utf-8", errors="replace")
        except OSError as problem:
            raise ForgeError(
                f"this map prices its own weapons, so it needs the install's own "
                f"weapon table to overlay, and {stock_path} could not be read "
                f"({problem}). A table built without it would quietly drop every "
                "column but the cost"
            ) from None
        return weapon_table_text(
            self.blueprint.weapon_price_table(),
            [weapon.table_row() for weapon in self.blueprint.custom_weapons],
            stock_text,
            newline=newline,
        )

    # ------------------------------------------------------------------
    def _workshop_images(
        self,
        preview_image: bytes | str | PurePath | None,
        render_root: str | PurePath | None,
        report: Report,
    ) -> dict[str, bytes]:
        """The preview card, the Workshop thumbnail and ``workshop.json``.

        A hero render (:func:`zmforge.workshop.hero_shot`) beats the plan for
        both pictures; a supplied *preview_image* still wins the card.
        """
        import io

        from PIL import Image

        from . import workshop

        title = display_title(self.name, self.blueprint.title)
        hero = None
        if render_root is not None:
            hero = workshop.hero_shot(self.name, Path(str(render_root)))
        out: dict[str, bytes] = {}
        if preview_image is None and hero is not None:
            out["preview_image"] = workshop.preview_png(
                workshop.compose(hero, title, PREVIEW_IMAGE_SIZE)
            )
        else:
            out["preview_image"] = self._presentation_image(
                preview_image,
                PREVIEW_IMAGE_SIZE,
                "preview_image",
                report,
                size_is_required=False,
            )
        # ``zmforge loadscreen``'s finished thumbnail (baked-lit photo + title)
        # wins over re-cutting one here.
        from .render.presentation import THUMBNAIL_NAME, presentation_file

        ready = presentation_file(self.name, THUMBNAIL_NAME) if render_root is not None else None
        if ready is not None:
            out["workshop_thumbnail"] = ready.read_bytes()
        else:
            if hero is not None:
                thumb = workshop.compose(hero, title, workshop.THUMBNAIL_SIZE)
            else:
                width, height = workshop.THUMBNAIL_SIZE
                plan = render_plan(self.blueprint, width=width, height=height,
                                   title=self.blueprint.title).png()
                thumb = Image.open(io.BytesIO(plan)).convert("RGB")
            out["workshop_thumbnail"] = workshop.thumbnail_jpeg(thumb)
        out["workshop_json"] = workshop.workshop_json(
            workshop.workshop_fields(self.name, title)
        )
        return out

    def _presentation_image(
        self,
        supplied: bytes | str | PurePath | None,
        expected: tuple[int, int],
        role: str,
        report: Report,
        *,
        size_is_required: bool = True,
    ) -> bytes:
        """PNG bytes for one presentation image, drawn or taken as given.

        *expected* is always the size a generated image is drawn at.  Whether
        a *supplied* image is expected to match it is a separate question,
        and ``size_is_required`` is the answer: true for the loading screen,
        where all 38 published examples are 1920 x 1080, and false for the
        preview, where 16 of 39 published maps are not the template's
        600 x 340 and are published and playable anyway
        (measured).  Same reasoning as
        :func:`~zmforge.verify.files.check_presentation`.
        """
        if supplied is None:
            width, height = expected
            return render_plan(
                self.blueprint,
                width=width,
                height=height,
                title=self.blueprint.title,
            ).png()

        blob = (
            bytes(supplied)
            if isinstance(supplied, (bytes, bytearray))
            else Path(str(supplied)).read_bytes()
        )
        try:
            header = read_png_header(blob)
        except ImageError as problem:
            raise ForgeError(f"{role}: {problem}") from None
        if size_is_required and header.size != expected:
            report.add(
                verify.warning(
                    "P1" if role == "loading_image" else "P2",
                    f"{role} is {header.width}x{header.height}. All 38 published "
                    f"Workshop maps that ship this file are "
                    f"{expected[0]}x{expected[1]}, as is the mod tools' own "
                    "template, with no exception measured",
                )
            )
        return blob

    def _would_clobber_bytes(self, role: str, target: Path) -> bool:
        if not target.exists():
            return False
        previous = self._committed.get(role)
        if previous is None:
            return True
        return _digest_bytes(target.read_bytes()) != previous

    def _would_clobber(self, role: str, target: Path) -> bool:
        if not target.exists():
            return False
        previous = self._committed.get(role)
        if previous is None:
            return True
        # newline="" keeps CRLF as written: the sound tables end their rows
        # with \r\n, and universal-newline reading turned every one of them
        # into a false "hand edited" on the next generate.
        with target.open(encoding="utf-8", errors="replace", newline="") as handle:
            return _digest(handle.read()) != previous

    def _model_state(self) -> dict:
        plan = self.blueprint.script
        return {
            "version": _RECORD_VERSION,
            "name": self.name,
            "seed": self.blueprint.seed,
            "title": display_title(self.name, self.blueprint.title),
            "hashes": dict(self._committed),
            "script": {
                "zone_hook": plan.zone_hook,
                "dog_rounds": plan.dog_rounds,
                "zones": list(plan.zones),
                "edges": [
                    {"zone_a": e.zone_a, "zone_b": e.zone_b, "flag": e.flag}
                    for e in plan.edges
                ],
                "perk_modules": plan.module_set(),
                "precache_fx": list(plan.precache_fx),
                "chest_name": plan.chest_name,
                "repeat_game_mode": plan.repeat_game_mode,
                "lift_player_cap": plan.lift_player_cap,
                "weapon_table": plan.weapon_table,
                "weapon_hints": [list(pair) for pair in plan.weapon_hints],
                "perk_hints": list(plan.perk_hints),
            },
            "elements": [
                {"id": element.id, "kind": element.kind}
                for element in self.blueprint.elements()
            ],
            # The half of the map the editor's document has no field for, so
            # that opening a generated map in an editor stops being a
            # reconstruction.  ``zmforge-map/2`` (see :mod:`zmforge.mapdoc`):
            # the geometry stays in the ``.map``, which round-trips
            # byte-for-byte, and the intent lives here in diffable text.  The
            # keys above are unchanged and still what :meth:`Project.open`
            # reads, so an older companion still loads and a newer one still
            # opens in the older code.
            "format": mapdoc.FORMAT,
            # The half a map editor draws: rooms, the holes in them, the boxes,
            # the zones, the doors, the gameplay items, the lights and the
            # props, as the recipe authored them.  Without it an editor would
            # have to rebuild the geometry from the `.map` text, which guesses wall
            # thickness, sniffs the floor-slab convention and infers which
            # storey an entity is on; none of that is a guess here, because
            # every number is on the blueprint (:mod:`zmforge.editordoc`).
            "editor": mapdoc.editor_document(self.blueprint),
            "engine": mapdoc.engine_sections(self.blueprint),
            "origin": {
                "kind": "recipe",
                "seed": self.blueprint.seed,
                "regenerable": True,
                # A regenerate replaces this file.  The editor sets this true
                # when it saves, and a regenerate refuses rather than throwing
                # an editor's edit away unnoticed.
                "edited_since_generate": False,
                **getattr(self.blueprint, "origin_args", {}),
            },
            "geometry": {
                "map_file": f"{self.name}.map",
                # The ``.map`` on disk, not the one a commit would have
                # written; ``hashes["map"]`` stays the generator's own last
                # write, which is what tells a hand edit from our own text.
                "sha256": self._geometry_sha or self._committed.get("map", ""),
                # Every GUID in the .map is sha256(seed, element id, ordinal),
                # so seed plus ids re-derive them all; nothing needs storing.
                "guid_seed": self.blueprint.seed,
            },
        }


def _terrain_type():
    from .blueprint.elements import Terrain

    return Terrain


def _plan_from_dict(name: str, data: Mapping) -> ScriptPlan:
    plan = ScriptPlan(map_name=name)
    plan.zone_hook = str(data.get("zone_hook", plan.zone_hook))
    plan.dog_rounds = bool(data.get("dog_rounds", False))
    plan.zones = list(data.get("zones", []))
    plan.edges = [
        ZoneEdge(edge["zone_a"], edge["zone_b"], edge["flag"])
        for edge in data.get("edges", [])
    ]
    plan.perk_modules = list(data.get("perk_modules", []))
    plan.precache_fx = list(data.get("precache_fx", []))
    chest = data.get("chest_name")
    plan.chest_name = str(chest) if chest else None
    plan.repeat_game_mode = bool(data.get("repeat_game_mode", False))
    plan.lift_player_cap = bool(data.get("lift_player_cap", False))
    table = data.get("weapon_table")
    plan.weapon_table = str(table) if table else None
    plan.weapon_hints = [
        (str(weapon), str(asset)) for weapon, asset in data.get("weapon_hints", [])
    ]
    plan.perk_hints = [str(asset) for asset in data.get("perk_hints", [])]
    return plan


def _digest(text: str) -> str:
    return _digest_bytes(text.encode("utf-8"))


def _digest_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


class FileHeldOpen(ForgeError):
    """A map file could not be replaced; nothing of the commit was kept."""


class _StagedWrites:
    """Write files to temporaries now, rename them all into place later.

    :meth:`commit` renames in staging order and, if any rename fails, puts back
    every file it had already replaced (from a copy taken just before), so a
    failed commit leaves the previous map whole.
    """

    def __init__(self) -> None:
        self._staged: list[tuple[Path, str, str]] = []  # target, temporary, sha256

    def stage(self, target: Path, blob: bytes) -> None:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            dir=str(target.parent), prefix=target.name, suffix=".part"
        )
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            _unlink_quietly(temporary)
            raise
        self._staged.append((target, temporary, _digest_bytes(blob)))

    def digest_of(self, target: Path) -> str | None:
        for staged_target, _temporary, digest in self._staged:
            if staged_target == Path(target):
                return digest
        return None

    def discard(self) -> None:
        for _target, temporary, _digest in self._staged:
            _unlink_quietly(temporary)
        self._staged = []

    def commit(self) -> None:
        import shutil

        done: list[tuple[Path, str | None]] = []
        try:
            for target, temporary, _digest in self._staged:
                backup = None
                if target.exists():
                    # A copy, not a hard link: on Windows a link to a file
                    # another program holds open cannot be deleted afterwards.
                    backup = f"{temporary}.old"
                    shutil.copy2(target, backup)
                try:
                    os.replace(temporary, target)
                except BaseException:
                    if backup is not None:
                        _unlink_quietly(backup)
                    raise
                done.append((target, backup))
        except BaseException as exc:
            for replaced, backup in reversed(done):
                try:
                    if backup is None:
                        os.unlink(replaced)
                    else:
                        os.replace(backup, replaced)
                except OSError:
                    pass
            self.discard()
            failed = target  # the loop variable: the rename that failed
            if isinstance(exc, PermissionError):
                if os.name == "nt":
                    raise FileHeldOpen(
                        f"close {failed} (held open by another program) and retry"
                    ) from exc
                raise FileHeldOpen(
                    f"cannot replace {failed} ({exc.strerror}); nothing was changed"
                ) from exc
            raise
        for _target, backup in done:
            if backup is not None:
                _unlink_quietly(backup)
        self._staged = []


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _write_atomically(target: Path, text: str) -> None:
    _write_bytes_atomically(target, text.encode("utf-8"))


def _write_bytes_atomically(target: Path, blob: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        dir=str(target.parent), prefix=target.name, suffix=".part"
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
