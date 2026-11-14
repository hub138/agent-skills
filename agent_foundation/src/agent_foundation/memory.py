"""Provider-neutral conversation and long-term memory primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, Sequence


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRecord:
    """An application-owned fact, preference, or other reusable note."""

    memory_id: str
    content: str
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    importance: float = 0.5
    tags: frozenset[str] = field(default_factory=frozenset)
    metadata: dict[str, object] = field(default_factory=dict)

    def is_active(self, now: datetime | None = None) -> bool:
        current = _as_utc(now or utc_now())
        return self.expires_at is None or _as_utc(self.expires_at) > current


@dataclass(frozen=True)
class MemoryMatch:
    memory: MemoryRecord
    relevance: float


class MemoryStore(Protocol):
    """Application-owned storage adapter for semantic or keyword memory search."""

    def search(self, query: str, *, limit: int) -> Sequence[MemoryMatch]: ...

    def upsert(self, memory: MemoryRecord) -> None: ...


class MemoryDistiller(Protocol):
    """Optional adapter that turns a transcript into caller-defined memory records."""

    def distill(self, messages: Sequence[ConversationMessage]) -> Sequence[MemoryRecord]: ...


@dataclass(frozen=True)
class MemoryBudget:
    max_chars: int = 4_000
    max_records: int = 8
    decay_half_life_days: float = 30.0


def conversation_window(
    messages: Sequence[ConversationMessage], *, max_messages: int = 20, max_chars: int = 12_000
) -> list[ConversationMessage]:
    """Return the newest whole messages that fit, truncating only a sole oversized message."""
    if max_messages <= 0 or max_chars <= 0:
        return []

    selected: list[ConversationMessage] = []
    used_chars = 0
    for message in reversed(messages):
        content = message.content.strip()
        if not content:
            continue
        if len(selected) >= max_messages:
            break
        if used_chars + len(content) <= max_chars:
            selected.append(
                ConversationMessage(message.role, content, message.created_at, dict(message.metadata))
            )
            used_chars += len(content)
            continue
        if not selected:
            selected.append(
                ConversationMessage(message.role, content[-max_chars:], message.created_at, dict(message.metadata))
            )
        break
    selected.reverse()
    return selected


def rank_memories(
    matches: Sequence[MemoryMatch], budget: MemoryBudget = MemoryBudget(), *, now: datetime | None = None
) -> list[MemoryMatch]:
    """Filter expired entries and combine relevance, importance, and time decay."""
    if budget.max_records <= 0 or budget.max_chars <= 0:
        return []
    if budget.decay_half_life_days <= 0:
        raise ValueError("decay_half_life_days must be positive")

    current = _as_utc(now or utc_now())
    scored: list[tuple[float, MemoryMatch]] = []
    for match in matches:
        memory = match.memory
        if not memory.content.strip() or not memory.is_active(current):
            continue
        age_days = max(0.0, (current - _as_utc(memory.created_at)).total_seconds() / 86_400)
        freshness = 0.5 ** (age_days / budget.decay_half_life_days)
        score = 0.75 * _bounded(match.relevance) + 0.15 * _bounded(memory.importance) + 0.10 * freshness
        scored.append((score, match))
    ranked = sorted(scored, key=lambda item: (-item[0], item[1].memory.memory_id))
    return [match for _, match in ranked[: budget.max_records]]


def pack_memory_context(
    matches: Sequence[MemoryMatch], budget: MemoryBudget = MemoryBudget(), *, now: datetime | None = None
) -> str:
    """Format ranked memories into a bounded, provider-neutral context string."""
    parts: list[str] = []
    used_chars = 0
    for match in rank_memories(matches, budget, now=now):
        if len(parts) >= budget.max_records:
            break
        marker = f"[{len(parts) + 1}] "
        available = budget.max_chars - used_chars - (1 if parts else 0) - len(marker)
        if available <= 0:
            break
        content = match.memory.content.strip()[:available].rstrip()
        if not content:
            continue
        rendered = marker + content
        parts.append(rendered)
        used_chars += len(rendered) + (1 if len(parts) > 1 else 0)
    return "\n".join(parts)


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
