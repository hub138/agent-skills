"""Persist opaque continuations and retry caller-defined transient failures."""

from __future__ import annotations

import json
import os
import random
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from .events import utc_now_iso
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Checkpoint:
    """Opaque continuation data owned by the caller and persisted atomically."""

    key: str
    continuation: str | None = None
    attempt: int = 0
    status: str = "active"
    updated_at: str = field(default_factory=utc_now_iso)
    data: dict[str, Any] = field(default_factory=dict)

    def next_attempt(self, *, continuation: str | None = None, data: dict[str, Any] | None = None) -> "Checkpoint":
        return Checkpoint(
            key=self.key,
            continuation=self.continuation if continuation is None else continuation,
            attempt=self.attempt + 1,
            status="active",
            data=self.data if data is None else data,
        )


class FileCheckpointStore:
    """One JSON checkpoint per caller key, with no continuation decisions."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def load(self, key: str) -> Checkpoint | None:
        try:
            raw = json.loads(self._path_for(key).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return Checkpoint(
                key=str(raw["key"]),
                continuation=raw.get("continuation"),
                attempt=int(raw.get("attempt") or 0),
                status=str(raw.get("status") or "active"),
                updated_at=str(raw.get("updated_at") or utc_now_iso()),
                data=dict(raw.get("data") or {}),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def save(self, checkpoint: Checkpoint) -> Path:
        target = self._path_for(checkpoint.key)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp", dir=self._directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(asdict(checkpoint), handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return target

    def delete(self, key: str) -> None:
        try:
            self._path_for(key).unlink()
        except FileNotFoundError:
            return

    def _path_for(self, key: str) -> Path:
        safe = "".join(character if character.isalnum() or character in "._-" else "_" for character in key)[:160]
        if not safe:
            raise ValueError("checkpoint key must contain at least one safe character")
        return self._directory / f"{safe}.json"


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff with optional jitter."""

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    multiplier: float = 2.0
    jitter_ratio: float = 0.0

    def delay_for(self, failed_attempt: int) -> float:
        if failed_attempt < 1:
            raise ValueError("failed_attempt must be positive")
        delay = min(self.initial_delay_seconds * (self.multiplier ** (failed_attempt - 1)), self.max_delay_seconds)
        if self.jitter_ratio:
            delay *= 1 + random.uniform(-self.jitter_ratio, self.jitter_ratio)
        return max(0.0, delay)


Retryable = Callable[[Exception], bool]
RetryObserver = Callable[[int, Exception, float], None]


def retry(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy = RetryPolicy(),
    is_retryable: Retryable | None = None,
    on_retry: RetryObserver | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``operation`` until it succeeds or a caller-defined retry boundary ends."""
    if policy.max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == policy.max_attempts or (is_retryable is not None and not is_retryable(exc)):
                raise
            delay = policy.delay_for(attempt)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep(delay)
    raise RuntimeError("unreachable")
