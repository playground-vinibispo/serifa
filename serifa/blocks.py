r"""Delimited blocks -- what vim calls a text object.

This exists because GtkSourceView's visual mode has no text objects. The
library symbols say so plainly: there is ``gtk_source_vim_command_set_text_object``
and an insert-mode counterpart, but the visual state only exposes ``clone``,
``get_bounds``, ``ignore_command``, ``new`` and ``warp``. Hence ``ci{`` works
and ``vi{`` does not -- there the ``i`` is ignored and ``{`` becomes the
"previous paragraph" motion, which merely jumps the cursor.

Pure functions on purpose: this is the part that can be tested with no window,
no keyboard and no vim.
"""

from __future__ import annotations

PAIRS = {
    "{": ("{", "}"), "}": ("{", "}"), "B": ("{", "}"),
    "(": ("(", ")"), ")": ("(", ")"), "b": ("(", ")"),
    "[": ("[", "]"), "]": ("[", "]"),
    "<": ("<", ">"), ">": ("<", ">"),
}

QUOTES = {'"': '"', "'": "'", "`": "`"}


def _escaped(text: str, position: int) -> bool:
    r"""Whether the character is preceded by an odd number of backslashes.

    In LaTeX ``\{`` is a literal brace and opens no block at all -- ignoring
    that would make ``vi{`` match the wrong brace inside any ``\newcommand``.
    """
    backslashes = 0
    i = position - 1
    while i >= 0 and text[i] == "\\":
        backslashes += 1
        i -= 1
    return backslashes % 2 == 1


def block_bounds(
    text: str, position: int, opener: str, closer: str
) -> tuple[int, int] | None:
    """Find the pair surrounding `position`, as (opener index, closer index).

    Depth is counted in both directions, so nesting works: with the cursor on
    `b`, ``{a {b} c}`` returns the inner pair.
    """
    if not text:
        return None
    position = max(0, min(position, len(text) - 1))

    # Cursor sitting on the opener itself: the block is the one starting here.
    if text[position] == opener and not _escaped(text, position):
        start = position
    else:
        depth = 0
        start = -1
        for i in range(position, -1, -1):
            if _escaped(text, i):
                continue
            if text[i] == closer and i != position:
                depth += 1
            elif text[i] == opener:
                if depth == 0:
                    start = i
                    break
                depth -= 1
        if start < 0:
            return None

    depth = 0
    for j in range(start + 1, len(text)):
        if _escaped(text, j):
            continue
        if text[j] == opener:
            depth += 1
        elif text[j] == closer:
            if depth == 0:
                return start, j
            depth -= 1
    return None


def quote_bounds(text: str, position: int, quote: str) -> tuple[int, int] | None:
    """Same idea for quotes, which do not nest: parity within the line."""
    line_start = text.rfind("\n", 0, position) + 1
    line_end = text.find("\n", position)
    if line_end < 0:
        line_end = len(text)

    occurrences = [
        i
        for i in range(line_start, line_end)
        if text[i] == quote and not _escaped(text, i)
    ]
    for a, b in zip(occurrences[::2], occurrences[1::2], strict=False):
        if a <= position <= b:
            return a, b
    return None


def target(
    text: str, position: int, sign: str, inside: bool
) -> tuple[int, int] | None:
    """Turn `i{`, `a{`, `i"`... into the range to select.

    `inside` is vim's `i`; `False` is `a`, which includes the delimiters.
    Returns (start, end) as Python-style offsets: end is exclusive.
    """
    if sign in PAIRS:
        opener, closer = PAIRS[sign]
        found = block_bounds(text, position, opener, closer)
    elif sign in QUOTES:
        found = quote_bounds(text, position, sign)
    else:
        return None

    if found is None:
        return None
    start, end = found
    return (start + 1, end) if inside else (start, end + 1)
