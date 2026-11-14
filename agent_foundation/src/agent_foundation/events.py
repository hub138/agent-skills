"""Small, transport-neutral event records for an agent session."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventKind(StrEnum):
    START = "start"
    OUTPUT = "output"
    DIAGNOSTIC = "diagnostic"
    HEARTBEAT = "heartbeat"
    CHECKPOINT = "checkpoint"
    RECOVERY = "recovery"
    ERROR = "error"
    END = "end"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Event:
    """An append-only session event with no application-specific fields."""

    kind: EventKind | str
    message: str = ""
    timestamp: str = field(default_factory=utc_now_iso)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Event":
        return cls(
            kind=str(value.get("kind") or EventKind.DIAGNOSTIC),
            message=str(value.get("message") or ""),
            timestamp=str(value.get("timestamp") or utc_now_iso()),
            data=dict(value.get("data") or {}),
        )

from datetime import UTC, datetime as _dt


def utc_now() -> _dt:
    """datetime 版本：需要做时间运算的调用方用这个；落盘用 utc_now_iso。"""
    return _dt.now(UTC)
