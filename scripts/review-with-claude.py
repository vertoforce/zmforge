#!/usr/bin/env python3
"""Example runner: answer a zmforge review packet with the ``claude`` CLI.

    scripts/review-with-claude.py <recipe> [zmforge review options]
        [--model M] [--claude-bin PATH] [--jobs N]

This is one way to follow ``docs/workflows/review-a-map.md``, not part of
zmforge.  It builds the packet (``zmforge review <recipe> ...``), makes one
headless ``claude -p`` call per room (images attached) and one for the map,
each with tools off, from an empty temporary directory and with the call's
schema passed as ``--json-schema``, writes each answer as
``<call>.findings.json`` (and cost/time as ``<call>.meta.json``), then runs
``zmforge review --import <packet> --partial``.  A failed call becomes an
error in the report rather than stopping the run.

Use it as the template for your own runner: anything that reads each
``<call>.prompt.md``, looks at the listed images and writes findings that
match ``<call>.schema.json`` works the same way.

Needs the Claude Code CLI installed and signed in; ``ZMFORGE_REVIEW_CLAUDE``
or ``--claude-bin`` picks the binary.  No API key is read or passed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zmforge.review import ai, packet as packets  # noqa: E402
from zmforge.review.ai import ReviewError  # noqa: E402

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class ClaudeCLI:
    """One headless Claude Code call per :meth:`__call__`; returns the review JSON."""

    binary: str = field(default_factory=lambda: os.environ.get("ZMFORGE_REVIEW_CLAUDE", "claude"))
    model: str = DEFAULT_MODEL
    timeout: float = 1200.0
    retries: int = 1
    system: str = ai.REVIEWER_ROLE

    def argv(self, schema: Mapping) -> list[str]:
        return [
            self.binary, "-p",
            "--model", self.model,
            "--output-format", "json",
            "--tools", "",
            "--no-session-persistence",
            "--setting-sources", "project",
            "--system-prompt", self.system,
            "--json-schema", json.dumps(schema, separators=(",", ":")),
        ]

    def __call__(self, prompt: str, schema: Mapping,
                 images: Sequence[Path] = ()) -> tuple[dict, dict]:
        """``(review, meta)``; raises :class:`ReviewError` after the retries.

        With *images* the prompt goes in as one stream-json user message
        carrying the PNGs as image blocks (``-p`` text input cannot carry
        images) and the answer is the stream's final ``result`` event, which
        has the same fields as ``--output-format json``.
        """
        last = None
        argv, stdin = self.argv(schema), prompt
        if images:
            argv = [a for a in argv if a not in ("--output-format", "json")]
            argv[2:2] = ["--input-format", "stream-json", "--output-format", "stream-json",
                         "--verbose"]
            stdin = image_message(prompt, images)
        for attempt in range(self.retries + 1):
            # A neutral working directory, so no project instructions or hooks
            # from this repository ride along with the prompt.
            with tempfile.TemporaryDirectory(prefix="zmforge-review-cli-") as cwd:
                started = time.time()
                try:
                    done = subprocess.run(argv, input=stdin, text=True,
                                          capture_output=True, timeout=self.timeout, cwd=cwd)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    last = ReviewError(f"claude CLI did not finish: {exc}")
                    continue
            if done.returncode != 0 and not done.stdout.strip():
                last = ReviewError(f"claude CLI exit {done.returncode}: {done.stderr.strip()[:300]}")
                continue
            try:
                review, meta = parse_cli_output(
                    stream_result(done.stdout) if images else done.stdout)
            except ReviewError as exc:
                last = exc
                continue
            meta["seconds"] = round(time.time() - started, 1)
            meta["attempt"] = attempt + 1
            meta["model"] = self.model
            return review, meta
        raise last or ReviewError("claude CLI failed")


def image_message(prompt: str, images: Sequence[Path]) -> str:
    """One stream-json user message: the PNGs as image blocks, then the text."""
    content: list[dict] = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(Path(p).read_bytes()).decode()}}
        for p in images
    ]
    content.append({"type": "text", "text": prompt})
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"


def stream_result(stdout: str) -> str:
    """The final ``result`` event of a stream-json run, as a JSON string."""
    for line in reversed(stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            return line
    raise ReviewError(f"claude CLI stream has no result event: {stdout[-200:]!r}")


def parse_cli_output(stdout: str) -> tuple[dict, dict]:
    """The review object and the call's metadata from ``--output-format json``."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"claude CLI output is not JSON: {stdout[:200]!r}") from exc
    if not isinstance(envelope, dict):
        raise ReviewError("claude CLI output is not a JSON object")
    if envelope.get("is_error") or envelope.get("subtype") not in (None, "success"):
        raise ReviewError(f"claude CLI reported an error: {str(envelope.get('result'))[:300]}")
    meta = {k: envelope.get(k) for k in ("total_cost_usd", "num_turns", "duration_ms",
                                         "session_id") if k in envelope}
    structured = envelope.get("structured_output")
    if isinstance(structured, dict):
        return structured, meta
    result = envelope.get("result")
    if isinstance(result, dict):
        return result, meta
    if not isinstance(result, str):
        raise ReviewError("claude CLI output has no result")
    return ai.extract_json(result), meta


def answer_packet(packet_dir: Path, cli: Callable[..., tuple[dict, dict]], *, jobs: int = 4,
                  log: Callable[[str], None] = lambda s: None) -> list[str]:
    """Write ``<call>.findings.json`` for every call of the packet; the errors.

    Room calls run in parallel; the map call runs last, with the room grades
    (:func:`ai.room_digest`) appended to its prompt.  A failed call leaves a
    ``<call>.error.txt`` instead of findings.
    """
    packet_dir = Path(packet_dir)
    packet = packets.load(packet_dir)
    errors: list[str] = []

    def ask(call: Mapping, prompt: str) -> dict | None:
        schema = json.loads((packet_dir / call["schema"]).read_text(encoding="utf-8"))
        images = [Path(p) for p in call["images"]]
        log(f"{call['id']}: calling ({len(prompt) // 1000} kB, {len(images)} images)")
        for stale in (".findings.json", ".error.txt", ".meta.json"):
            (packet_dir / f"{call['id']}{stale}").unlink(missing_ok=True)
        try:
            raw, meta = cli(prompt, schema, images=images) if images else cli(prompt, schema)
        except ReviewError as exc:
            errors.append(f"{call['id']}: {exc}")
            (packet_dir / f"{call['id']}.error.txt").write_text(str(exc), encoding="utf-8")
            log(f"{call['id']}: FAILED {exc}")
            return None
        (packet_dir / call["findings"]).write_text(json.dumps(raw, indent=1), encoding="utf-8")
        (packet_dir / f"{call['id']}.meta.json").write_text(json.dumps(meta, indent=1),
                                                             encoding="utf-8")
        log(f"{call['id']}: {raw.get('grade')} ({raw.get('score')})")
        return raw

    def room(call: Mapping) -> dict:
        raw = ask(call, (packet_dir / call["prompt"]).read_text(encoding="utf-8"))
        return dict(raw or {"principles": []}, room=call["room"])

    rooms = [c for c in packet["calls"] if c["kind"] == "room"]
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        room_answers = list(pool.map(room, rooms))
    for call in packet["calls"]:
        if call["kind"] == "map":
            prompt = (packet_dir / call["prompt"]).read_text(encoding="utf-8")
            prompt = prompt.replace(ai.ROOM_REVIEWS_LATER, json.dumps(
                ai.room_digest(room_answers), separators=(",", ":"), default=str))
            ask(call, prompt)
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--claude-bin", default=None,
                        help="the claude CLI (default $ZMFORGE_REVIEW_CLAUDE or claude)")
    parser.add_argument("--jobs", type=int, default=4, help="room calls in parallel")
    ours, rest = parser.parse_known_args(argv)
    from zmforge.facade.cli import _build_parser
    from zmforge.review import run

    args = _build_parser().parse_args(["review", *rest])
    if args.import_dir or args.no_ai or not args.recipe:
        parser.error("give a recipe and zmforge review options; this runner builds, answers "
                     "and imports the packet itself")
    log = (lambda s: None) if args.quiet else (lambda s: print(s, file=sys.stderr, flush=True))
    packet_dir = run.build(args)
    cli = ClaudeCLI(model=ours.model)
    if ours.claude_bin:
        cli.binary = ours.claude_bin
    answer_packet(packet_dir, cli, jobs=ours.jobs, log=log)
    return run.import_findings(packet_dir, strict=args.strict, partial=True,
                               reviewer=f"claude CLI, {ours.model}", quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
