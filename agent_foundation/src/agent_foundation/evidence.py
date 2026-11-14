"""Verify that an LLM-produced quote actually exists verbatim in a source text.

Real-world failure this abstracts: models asked to report document problems
invent quotes that look plausible but cannot be found in the source —
fabricated findings then consume real repair work. Conversely, models that DO
copy honestly introduce invisible differences (whitespace, full/half-width
punctuation, quote style) that a naive ``quote in body`` check rejects.

Two operations, both deliberately conservative:

- ``verify_quote`` — exact match after normalization; any hit passes.
- ``repair_quote`` — when the raw match fails, normalize both sides
  (NFC, strip whitespace, unify quotes/brackets) and require the normalized
  quote to hit **exactly once** in the normalized body; return the original
  text span. Zero or multiple hits return None: a repair that could land on
  the wrong position is worse than no repair.

A length guard rejects pathological matches where the repaired span is far
larger than the original quote (a symptom of matching inside repeated boilerplate).
"""

from __future__ import annotations

import re
import unicodedata

_TRANSLATION = str.maketrans({
    "\u201c": '"', "\u201d": '"',   # curly double quotes
    "\u2018": "'", "\u2019": "'",   # curly single quotes
    "\uff08": "(", "\uff09": ")",   # full-width parentheses
    "\uff1a": ":", "\uff0c": ",",   # full-width colon/comma
})


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", "", s)
    return s.translate(_TRANSLATION)


def verify_quote(body: str, quote: str) -> bool:
    """True when quote exists verbatim (post-normalization) in body."""
    n_body = _norm(body)
    n_quote = _norm(quote)
    return bool(n_quote) and n_quote in n_body


def repair_quote(body: str, quote: str, *, min_norm_len: int = 8,
                 max_expand: int = 20) -> str | None:
    """Return the original span that the quote (with invisible differences)
    refers to, or None.

    Requirements for a repair:
    - normalized quote is at least ``min_norm_len`` chars (short strings can
      accidentally match boilerplate)
    - normalized quote hits exactly once (0 or 2+ → None)
    - repaired span is not pathologically larger than the quote
    """
    n_quote = _norm(quote)
    if len(n_quote) < min_norm_len:
        return None

    chars: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(body):
        if ch.isspace():
            continue
        chars.append(_norm(ch))
        index_map.append(i)
    n_body = "".join(chars)

    if n_body.count(n_quote) != 1:
        return None
    start = n_body.find(n_quote)
    end = start + len(n_quote) - 1
    span = body[index_map[start]:index_map[end] + 1]
    if len(span) > len(quote) * 2 + max_expand:
        return None
    return span
