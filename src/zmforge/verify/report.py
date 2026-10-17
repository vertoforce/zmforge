"""Findings and reports: what every check hands back.

A finding carries a stable ``code`` so a facade, a test or a future CI job can
assert on it without matching prose.  Codes are the spec's own check labels
(``F7``, ``G9``, ``Z10``) wherever a check implements one, so a failure points
straight at the paragraph that explains it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

__all__ = ["Finding", "Report", "error", "note", "warning"]


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing a check objects to."""

    severity: str
    code: str
    message: str
    element_id: str | None = None
    position: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def __str__(self) -> str:
        where = f" [{self.element_id}]" if self.element_id else ""
        spot = f" at {self.position}" if self.position else ""
        return f"{self.severity.upper()} {self.code}{where}{spot}: {self.message}"


def error(code: str, message: str, element_id: str | None = None, position: str | None = None) -> Finding:
    return Finding("error", code, message, element_id, position)


def warning(code: str, message: str, element_id: str | None = None, position: str | None = None) -> Finding:
    return Finding("warning", code, message, element_id, position)


def note(code: str, message: str, element_id: str | None = None, position: str | None = None) -> Finding:
    """An advisory that is expected on a healthy map (severity ``info``).

    Counted with the warnings (``Report.warnings`` is everything that is not
    an error), but the CLI shows it only with ``-v``: it records a deliberate
    choice, not something the map's author has to act on.
    """
    return Finding("info", code, message, element_id, position)


@dataclass
class Report:
    """A list of findings, plus the questions callers actually ask of it."""

    findings: list[Finding] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.is_error]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if not f.is_error]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}

    def __iter__(self) -> Iterator[Finding]:
        return iter(self.findings)

    def __len__(self) -> int:
        return len(self.findings)

    def __add__(self, other: "Report") -> "Report":
        return Report(self.findings + other.findings)

    def summary(self) -> str:
        if not self.findings:
            return "no findings"
        return (
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s): "
            + "; ".join(str(f) for f in self.findings[:10])
            + ("; ..." if len(self.findings) > 10 else "")
        )
