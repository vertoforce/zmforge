"""A small, conservative reader for the GSC the engine emits.

Why this exists: a script error in Black Ops III is *fatal*.  The game does
not skip the bad line, it drops to an ``UNRECOVERABLE ERROR`` and the map
dies on load or mid-round, which is how the reference project's maps failed
(spec 7.4).  The compiler is the only authority on GSC, and it lives on
Windows behind a linker that never exits zero, so a mistake found there
costs a whole build cycle.  This module catches the cheap classes of mistake
-- unbalanced braces, an unterminated string, a statement with no semicolon,
a call to a function that nothing defines -- in the same process that wrote
the text.

It is deliberately **not** a GSC parser.  It answers one question, "could
this text possibly be the script I meant", and it errs towards silence: every
check here either points at a specific line or says nothing.  Anything it
cannot be sure about is left to the compiler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "Issue",
    "ScriptSource",
    "strip_noise",
    "scan",
    "DEV_ONLY_BUILTINS",
    "dev_only_calls",
    "OPEN_CLOSE",
]

#: Bracket pairs GSC uses.  ``<`` / ``>`` are comparisons, never brackets.
OPEN_CLOSE = {"{": "}", "(": ")", "[": "]"}

#: Keywords that may head a line with no trailing semicolon.
_BLOCK_HEADS = (
    "if",
    "else",
    "for",
    "foreach",
    "while",
    "switch",
    "do",
    "case",
    "default",
    "function",
    "class",
    "autoexec",
    "private",
)

#: Directives, which are their own statement form and take no semicolon in
#: the ``REGISTER_SYSTEM`` case.  ``#using`` / ``#insert`` do take one.
_DIRECTIVE = re.compile(r"^\s*#\s*(using|insert|define|namespace|precache)\b")

_FUNCTION_DEF = re.compile(
    r"^\s*(?:autoexec\s+|private\s+)*function\s+(?:autoexec\s+|private\s+)*"
    r"([A-Za-z_]\w*)\s*\("
)
#: ``ns::name`` in a call or a function pointer.
_QUALIFIED = re.compile(r"\b([A-Za-z_]\w*)::([A-Za-z_]\w*)")
#: A bare ``name(`` call that is not a keyword and not qualified.
_BARE_CALL = re.compile(r"(?<![\w:.&])([A-Za-z_]\w*)\s*\(")
#: ``&name`` / ``&ns::name`` -- a function pointer, which GSC checks at load.
#: The lookarounds keep the logical-and operator out of it: in ``a && b`` the
#: second ``&`` is followed by an identifier and would otherwise read as a
#: pointer to a function called ``b``.
_POINTER = re.compile(r"(?<![&\w])&(?!&)\s*(?:([A-Za-z_]\w*)::)?([A-Za-z_]\w*)")

#: Words that read like a call but are language, not a function.
_NOT_CALLS = frozenset(
    {
        "if",
        "else",
        "for",
        "foreach",
        "while",
        "switch",
        "case",
        "return",
        "wait",
        "waittill",
        "waittillframeend",
        "thread",
        "notify",
        "endon",
        "assert",
        "function",
        "REGISTER_SYSTEM",
    }
)


@dataclass(frozen=True, slots=True)
class Issue:
    """One thing wrong with a script, with the line to look at."""

    code: str
    line: int
    detail: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"line {self.line}: {self.detail}"


@dataclass
class ScriptSource:
    """What :func:`scan` could work out about a script's text."""

    using: set[str] = field(default_factory=set)
    defined: dict[str, int] = field(default_factory=dict)
    bare_calls: list[tuple[str, int]] = field(default_factory=list)
    qualified_calls: list[tuple[str, str, int]] = field(default_factory=list)
    pointers: list[tuple[str | None, str, int]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def sound(self) -> bool:
        """True when nothing structural is wrong with the text."""
        return not self.issues


def strip_noise(text: str) -> list[str]:
    """The script with comments and string bodies blanked, line for line.

    Developer blocks (``/# ... #/``) go the same way: the retail compiler
    strips them, so what is inside one cannot break a retail build.

    Blanking rather than deleting keeps every line number and every bracket
    outside a string exactly where it was, so an issue can point at the line
    the author wrote.  String *bodies* go because a brace or a semicolon
    inside ``"a{b"`` is text, not syntax; the quotes stay so an unterminated
    one is still visible.
    """
    out: list[str] = []
    in_block_comment = False
    in_dev_block = False
    for raw in text.split("\n"):
        buf: list[str] = []
        in_string = False
        index = 0
        while index < len(raw):
            two = raw[index : index + 2]
            char = raw[index]
            if in_dev_block:
                # ``/# ... #/`` is a developer block: the retail compiler
                # drops it, so its contents are not this checker's business.
                if two == "#/":
                    in_dev_block = False
                    buf.append("  ")
                    index += 2
                    continue
                buf.append(" ")
                index += 1
                continue
            if in_block_comment:
                if two == "*/":
                    in_block_comment = False
                    buf.append("  ")
                    index += 2
                    continue
                buf.append(" ")
                index += 1
                continue
            if in_string:
                if char == "\\" and index + 1 < len(raw):
                    buf.append("  ")
                    index += 2
                    continue
                if char == '"':
                    in_string = False
                    buf.append('"')
                    index += 1
                    continue
                buf.append(" ")
                index += 1
                continue
            if two == "//":
                buf.append(" " * (len(raw) - index))
                break
            if two == "/*":
                in_block_comment = True
                buf.append("  ")
                index += 2
                continue
            if two == "/#":
                in_dev_block = True
                buf.append("  ")
                index += 2
                continue
            if char == '"':
                in_string = True
                buf.append('"')
                index += 1
                continue
            buf.append(char)
            index += 1
        if in_string:
            # Report it here rather than losing it: the caller sees the line
            # with an odd number of quotes and can say so.
            pass
        out.append("".join(buf))
    return out


def _quote_balance(line: str) -> bool:
    return line.count('"') % 2 == 0


def scan(text: str) -> ScriptSource:
    """Read a script's structure and list what is wrong with it.

    The issues this raises, and the reason each is fatal in game:

    ``gsc_string``
        an unterminated string literal -- the compiler swallows the rest of
        the file looking for the closing quote;
    ``gsc_bracket``
        a bracket that never closes, or one that closes what was not open;
    ``gsc_semicolon``
        a statement with no terminator, which is a compile error;
    ``gsc_toplevel``
        a statement outside any function, where only directives may live;
    ``gsc_duplicate``
        two definitions of one function name, where the second silently wins;
    ``gsc_nested``
        a function defined inside another function's body, which GSC has no
        syntax for.
    """
    source = ScriptSource()
    lines = strip_noise(text)
    stack: list[tuple[str, int]] = []

    for number, line in enumerate(lines, start=1):
        if not _quote_balance(line):
            source.issues.append(
                Issue("gsc_string", number, "unterminated string literal")
            )
            continue

        depth_before = len([1 for opener, _ in stack if opener == "{"])
        for char in line:
            if char in OPEN_CLOSE:
                stack.append((char, number))
            elif char in OPEN_CLOSE.values():
                if not stack:
                    source.issues.append(
                        Issue("gsc_bracket", number, f"stray closing {char!r}")
                    )
                    continue
                opener, opened_at = stack.pop()
                if OPEN_CLOSE[opener] != char:
                    source.issues.append(
                        Issue(
                            "gsc_bracket",
                            number,
                            f"closing {char!r} does not match the {opener!r} "
                            f"opened on line {opened_at}",
                        )
                    )

        depth = len([1 for opener, _ in stack if opener == "{"])
        stripped = line.strip()
        match = _FUNCTION_DEF.match(line)
        if match:
            name = match.group(1)
            if depth_before > 0:
                # GSC has no nested functions.  A definition that opens while
                # another body is still open is what a multi-line custom
                # statement carrying its own ``function`` produces, and the
                # brace count alone cannot see it because the braces balance.
                source.issues.append(
                    Issue(
                        "gsc_nested",
                        number,
                        f"function {name!r} is defined inside another "
                        "function's body",
                    )
                )
            if name in source.defined:
                source.issues.append(
                    Issue(
                        "gsc_duplicate",
                        number,
                        f"function {name!r} is already defined on line "
                        f"{source.defined[name]}",
                    )
                )
            else:
                source.defined[name] = number

        directive = _DIRECTIVE.match(line)
        if directive:
            if directive.group(1) in ("using", "insert"):
                path = stripped.split(None, 1)[1].rstrip(";").strip()
                source.using.add(path)
            continue

        if stripped and depth == 0 and not match and not stripped.startswith("}"):
            # Outside a function body only directives and the client
            # script's REGISTER_SYSTEM macro are legal.
            if not stripped.startswith("REGISTER_SYSTEM"):
                source.issues.append(
                    Issue(
                        "gsc_toplevel",
                        number,
                        f"{stripped!r} is outside any function, where only "
                        "#using / #insert / #define and REGISTER_SYSTEM may live",
                    )
                )

        if stripped and depth > 0:
            _check_termination(stripped, number, source)

        for namespace, name in _QUALIFIED.findall(line):
            source.qualified_calls.append((namespace, name, number))
        for name in _BARE_CALL.findall(line):
            if name in _NOT_CALLS:
                continue
            if match and name == match.group(1):
                # The definition's own header, not a call of it.
                continue
            source.bare_calls.append((name, number))
        for namespace, name in _POINTER.findall(line):
            source.pointers.append((namespace or None, name, number))

    for opener, opened_at in stack:
        source.issues.append(
            Issue(
                "gsc_bracket",
                opened_at,
                f"{opener!r} is never closed",
            )
        )
    return source


def _check_termination(stripped: str, number: int, source: ScriptSource) -> None:
    """A statement inside a body must end in ``;``, ``{``, ``}`` or ``:``."""
    if stripped.endswith((";", "{", "}", ":", ",")):
        return
    head = re.match(r"([A-Za-z_]\w*)", stripped)
    if head and head.group(1) in _BLOCK_HEADS:
        return
    if stripped.startswith("#"):
        return
    source.issues.append(
        Issue(
            "gsc_semicolon",
            number,
            f"{stripped!r} has no statement terminator",
        )
    )


#: Builtins the game accepts only inside a ``/# ... #/`` developer block.
#: Outside one the retail loader refuses the whole script at map load:
#: ``Fatal Error: 2 script errors: Dev only calls must be wrapped in a
#: devblock /#...#/: "895B00" with 1 parameters in
#: scripts/zm/zm_<map>.gsc`` (the boss test map, two bare
#: ``PrintLn``).  The rest of the list is measured, not assumed: across the
#: mod tools tree (``share/raw/scripts``, every ``.gsc``/``.csc``)
#: each of these is called only inside developer blocks, 0 times outside.
#: Not on it, because the stock tree calls them outside developer blocks:
#: ``Assert`` (1146 times), ``AssertMsg`` (74), ``AddDebugCommand`` (1,
#: ``_zm_weap_octobomb.gsc:1074``), and the retail ``Record*`` stats calls
#: (``RecordPlayerStats`` 63, ``RecordGameEvent`` 23, ...).
DEV_ONLY_BUILTINS: frozenset[str] = frozenset({
    "println", "print3d", "line", "sphere", "box", "circle", "debugstar",
    "record3dtext", "recordcircle", "recordenttext", "recordline",
    "recordsphere", "recordstar",
})


def dev_only_calls(text: str) -> list[tuple[int, str]]:
    """Every call to a :data:`DEV_ONLY_BUILTINS` builtin outside a developer
    block, as ``(line, name as written)``.

    Comments, strings and developer blocks are blanked first
    (:func:`strip_noise`), so a call inside ``/# #/`` is not reported.  A
    name the script defines itself is its own function, not the builtin.
    """
    lines = strip_noise(text)
    defined = {
        match.group(1).lower()
        for line in lines
        if (match := _FUNCTION_DEF.match(line))
    }
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if _FUNCTION_DEF.match(line):
            continue
        for match in _BARE_CALL.finditer(line):
            name = match.group(1)
            if name.lower() in DEV_ONLY_BUILTINS and name.lower() not in defined:
                hits.append((number, name))
    return hits
