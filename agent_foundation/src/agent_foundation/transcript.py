"""Append-only transcript storage, redaction, and opaque identity helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Iterator

from .events import Event

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*(?:bearer\s+)?\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{16,}"),
)


def redact_text(text: str, *, replacement: str = "***REDACTED***") -> str:
    """Best-effort redaction for common secret-bearing text before persistence."""
    result = text or ""
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def hmac_digest(value: str, key: str) -> str:
    """Create a stable opaque identifier without storing the original value."""
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


class TranscriptWriter:
    """Writes one redacted event object per JSONL line."""

    def __init__(self, path: str | Path, *, redact: bool = True) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._redact = redact

    def append(self, event: Event) -> None:
        payload = event.to_dict()
        if self._redact:
            payload["message"] = redact_text(payload["message"])
            payload["data"] = _redact_value(payload["data"])
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


class TranscriptReader:
    """Tolerates interrupted or malformed trailing lines while reading a transcript."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def events(self) -> Iterator[Event]:
        try:
            with self.path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        yield Event.from_dict(value)
        except FileNotFoundError:
            return


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    """Append one JSON record to a .jsonl file, tolerating OSError.

    Abstracted from three hand-rolled copies in the parent system (self-heal
    log, canary trend, ledger): each was open-append + dumps + silent-OSError,
    and each forgot a different detail. Centralized so the details live once.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a lost log line must never take down the main flow
