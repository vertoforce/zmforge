"""Numbers that remember how they were written.

A ``.map`` file is round-tripped, not just generated: a caller may read a
Radiant file, change one entity and write it back.  Reformatting numbers that
nobody touched would produce a huge, unreviewable diff and — worse — would
quietly rewrite values Radiant wrote in exponent notation.  So a number parsed
out of a file is a :class:`Scalar`: a ``float`` for arithmetic that also carries
the exact token text it came from.  Numbers the generator invents have no source
text and are formatted by the rule in spec section 1.9.
"""

from __future__ import annotations

import re

from ..errors import MapTextError

__all__ = ["Scalar", "NUMBER_RE", "decimal_token", "parse_scalar"]


#: The shape every *generated* number has: optional sign, digits, optional
#: fractional part.  Never an exponent (spec 1.9, conformance check F7).
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")

#: How many fractional digits the fixed-point format starts from before the
#: trailing zeros are stripped (spec 1.9 rule 1).
_FRACTION_DIGITS = 8


class Scalar(float):
    """A ``float`` that remembers the token text it was parsed from.

    ``source`` is ``None`` for computed values, which is what makes
    :func:`decimal_token` fall through to the formatting rule.
    """

    __slots__ = ("source",)

    source: str | None

    def __new__(cls, value: float | str, source: str | None = None) -> "Scalar":
        self = super().__new__(cls, value)
        self.source = source
        return self

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.source is None:
            return f"Scalar({float(self)!r})"
        return f"Scalar({float(self)!r}, {self.source!r})"


def decimal_token(value: float) -> str:
    """Render ``value`` the way Radiant writes numbers (spec 1.9).

    A scalar that came from a file is written back byte-identically.  Anything
    else is fixed-point at eight fractional digits with trailing zeros and a
    trailing dot removed, and floating-point noise that formats as ``-0`` (or as
    nothing at all) collapsed to ``0``.  Exponent notation can never come out of
    here, and integers survive unchanged.
    """
    if isinstance(value, Scalar) and value.source is not None:
        return value.source
    text = f"{float(value):.{_FRACTION_DIGITS}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        return "0"
    return text


def parse_scalar(text: str) -> Scalar:
    """Read one numeric token, keeping its spelling for the writer.

    Tolerant on input on purpose: shipped BO3 maps do contain exponent tokens
    (``-5.5670738e-005`` in ``zm_alien_isolation.map``) even though the writer
    never produces one.  Keeping the source text is what lets such a file come
    back out unchanged.
    """
    try:
        value = float(text)
    except (TypeError, ValueError) as exc:
        raise MapTextError(f"expected a number, found {text!r}") from exc
    return Scalar(value, text)
