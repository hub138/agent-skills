"""Provider-neutral document retrieval and context-packing primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Document:
    """A source document supplied by the application."""

    document_id: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    """A stable, attributable segment of a document."""

    chunk_id: str
    document_id: str
    index: int
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalHit:
    """A retrieval result whose score is meaningful only within its source."""

    chunk: Chunk
    score: float
    source: str = ""


class Retriever(Protocol):
    """Application-owned retrieval adapter, whether lexical, vector, or remote."""

    def search(self, query: str, *, limit: int) -> Sequence[RetrievalHit]: ...


class ChunkIndex(Retriever, Protocol):
    """Optional write-capable adapter for any caller-selected retrieval index."""

    def upsert(self, chunks: Sequence[Chunk]) -> None: ...

    def delete(self, chunk_ids: Sequence[str]) -> None: ...


@dataclass(frozen=True)
class ContextBudget:
    max_chars: int = 8_000
    max_chunks: int = 8
    max_chars_per_chunk: int | None = None


@dataclass(frozen=True)
class Citation:
    number: int
    document_id: str
    chunk_id: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextPacket:
    text: str
    citations: tuple[Citation, ...]
    hits: tuple[RetrievalHit, ...]


def chunk_document(document: Document, *, max_chars: int = 1_200, overlap_chars: int = 0) -> list[Chunk]:
    """Split text on paragraph boundaries before using fixed-size windows."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

    pieces: list[str] = []
    for paragraph in _paragraph_windows(document.text):
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
        else:
            pieces.extend(_fixed_windows(paragraph, max_chars, overlap_chars))

    return [
        Chunk(
            chunk_id=_chunk_id(document.document_id, index, text),
            document_id=document.document_id,
            index=index,
            text=text,
            metadata=dict(document.metadata),
        )
        for index, text in enumerate(pieces)
        if text
    ]


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[RetrievalHit]], *, rank_constant: int = 60
) -> list[RetrievalHit]:
    """Fuse independently ranked result lists without comparing raw scores."""
    if rank_constant < 0:
        raise ValueError("rank_constant must be non-negative")

    totals: dict[str, float] = {}
    representatives: dict[str, RetrievalHit] = {}
    for ranked_hits in ranked_lists:
        seen: set[str] = set()
        for rank, hit in enumerate(ranked_hits, start=1):
            chunk_id = hit.chunk.chunk_id
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            totals[chunk_id] = totals.get(chunk_id, 0.0) + 1.0 / (rank_constant + rank)
            current = representatives.get(chunk_id)
            if current is None or hit.score > current.score:
                representatives[chunk_id] = hit

    return [
        RetrievalHit(representatives[chunk_id].chunk, score, representatives[chunk_id].source)
        for chunk_id, score in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def deduplicate_hits(hits: Sequence[RetrievalHit]) -> list[RetrievalHit]:
    """Keep the highest-ranked version of each normalized text segment."""
    unique: dict[str, RetrievalHit] = {}
    for hit in hits:
        fingerprint = _text_fingerprint(hit.chunk.text)
        current = unique.get(fingerprint)
        if current is None or hit.score > current.score:
            unique[fingerprint] = hit
    return sorted(unique.values(), key=lambda hit: (-hit.score, hit.chunk.chunk_id))


def pack_context(hits: Sequence[RetrievalHit], budget: ContextBudget = ContextBudget()) -> ContextPacket:
    """Produce a bounded, cited context string from ranked retrieval results."""
    if budget.max_chars <= 0 or budget.max_chunks <= 0:
        return ContextPacket("", (), ())
    if budget.max_chars_per_chunk is not None and budget.max_chars_per_chunk <= 0:
        raise ValueError("max_chars_per_chunk must be positive when provided")

    selected: list[RetrievalHit] = []
    citations: list[Citation] = []
    parts: list[str] = []
    used_chars = 0
    for hit in deduplicate_hits(hits):
        if len(selected) >= budget.max_chunks:
            break
        content = hit.chunk.text.strip()
        if budget.max_chars_per_chunk is not None:
            content = content[: budget.max_chars_per_chunk].rstrip()
        marker = f"[{len(selected) + 1}] "
        available = budget.max_chars - used_chars - (1 if parts else 0) - len(marker)
        if available <= 0:
            break
        content = content[:available].rstrip()
        if not content:
            continue
        rendered = marker + content
        parts.append(rendered)
        used_chars += len(rendered) + (1 if len(parts) > 1 else 0)
        selected.append(hit)
        citations.append(
            Citation(
                number=len(selected),
                document_id=hit.chunk.document_id,
                chunk_id=hit.chunk.chunk_id,
                metadata=dict(hit.chunk.metadata),
            )
        )

    return ContextPacket("\n".join(parts), tuple(citations), tuple(selected))


def _paragraph_windows(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.replace("\r\n", "\n").split("\n\n") if paragraph.strip()]


def _fixed_windows(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    step = max_chars - overlap_chars
    return [text[start : start + max_chars] for start in range(0, len(text), step)]


def _chunk_id(document_id: str, index: int, text: str) -> str:
    digest = sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{document_id}:{index}:{digest}"


def _text_fingerprint(text: str) -> str:
    normalized = " ".join(text.split()).casefold()
    return sha256(normalized.encode("utf-8")).hexdigest()


def _pack_bounded(items: list[tuple[str, str]], max_chars: int,
                  max_items: int) -> list[str]:
    """Greedy budget packing shared by context and memory assembly.

    Abstracted from two line-identical loops (context.pack_context and
    memory.pack_memory_context) that had already drifted in one detail.
    """
    parts: list[str] = []
    used = 0
    for i, (marker, content) in enumerate(items[:max_items]):
        available = max_chars - used - (1 if parts else 0) - len(marker)
        if available <= 0:
            break
        rendered = f"{marker}{content[:available].rstrip()}"
        parts.append(rendered)
        used += len(rendered) + 1
    return parts
