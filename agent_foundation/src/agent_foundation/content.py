"""Schema-free extraction of text and embedded JSON from arbitrary content."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL | re.IGNORECASE)


def json_pointer_values(document: Any, pointers: Iterable[str]) -> list[Any]:
    """Select values by RFC 6901 JSON pointers without binding to a provider schema."""
    values: list[Any] = []
    for pointer in pointers:
        if pointer == "":
            values.append(document)
            continue
        if not pointer.startswith("/"):
            continue
        current = document
        valid = True
        for raw_part in pointer[1:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                valid = False
                break
        if valid:
            values.append(current)
    return values


def extract_text(value: Any, *, pointers: Iterable[str] | None = None) -> str:
    """Return readable text from a value or from caller-specified JSON pointers.

    With pointers, only selected values are rendered. Without pointers, strings
    are returned directly and structured values use stable JSON serialization.
    """
    selected = json_pointer_values(value, pointers) if pointers is not None else [value]
    pieces: list[str] = []
    for item in selected:
        if isinstance(item, str):
            pieces.append(item)
        elif item is not None:
            pieces.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return "\n".join(piece for piece in pieces if piece)


def extract_json_object(text: str) -> dict[str, Any] | list[Any] | None:
    """Find a JSON object or array in plain output, a fenced block, or prose.

    The function does not validate a schema. Callers decide whether a recovered
    value is meaningful for their own protocol.
    """
    source = (text or "").strip()
    if not source:
        return None
    direct = _decode_container(source)
    if direct is not None:
        return direct
    for match in reversed(_JSON_FENCE.findall(source)):
        found = _decode_container(match)
        if found is not None:
            return found
    return _first_balanced_container(source)


def _decode_container(source: str) -> dict[str, Any] | list[Any] | None:
    try:
        value = json.loads(source)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, (dict, list)) else None


def _first_balanced_container(text: str) -> dict[str, Any] | list[Any] | None:
    for start, char in enumerate(text):
        if char not in "{[":
            continue
        closing = "}" if char == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == char:
                depth += 1
            elif current == closing:
                depth -= 1
                if depth == 0:
                    found = _decode_container(text[start : index + 1])
                    if found is not None:
                        return found
                    break
    return None


def stable_fingerprint(text: str, *, mask_digits: bool = True,
                       prefix_chars: int = 60) -> str:
    """Stable identity for a noisy problem report.

    Real-world failure this abstracts: a monitor reported "first screen needs
    765,152 bytes" — the next day it was 765,153 and the dedupe saw a brand
    new problem. Same bug, different digits, dedupe silently dead (noted in
    the parent system as "accumulates for two weeks then explodes").

    Normalization: NFC → strip whitespace/punctuation → optional digit masking
    (every run of digits becomes '#') → keep a prefix → SHA-256.
    """
    import hashlib
    s = unicodedata_normalize(text)
    if mask_digits:
        s = re.sub(r"\d+", "#", s)
    s = re.sub(r"[\s，。；、：:，,（）()\[\]\[\]{}\"'`]+", "", s)
    s = s[:prefix_chars]
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def unicodedata_normalize(text: str) -> str:
    import unicodedata as _u
    return _u.normalize("NFC", text)
