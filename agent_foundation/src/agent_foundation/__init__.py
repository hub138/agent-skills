"""Framework-neutral building blocks for agent sessions, context, and memory."""

from .cli_session import (
    ProcessResult,
    ProcessSpec,
    ProcessSupervisor,
    Termination,
    decode_json_lines,
    normalize_stream_line,
)
from .content import extract_json_object, extract_text, json_pointer_values
from .context import (
    Chunk,
    ChunkIndex,
    Citation,
    ContextBudget,
    ContextPacket,
    Document,
    RetrievalHit,
    Retriever,
    chunk_document,
    deduplicate_hits,
    pack_context,
    reciprocal_rank_fusion,
)
from .events import Event, EventKind
from .memory import (
    ConversationMessage,
    MemoryBudget,
    MemoryDistiller,
    MemoryMatch,
    MemoryRecord,
    MemoryStore,
    conversation_window,
    pack_memory_context,
    rank_memories,
    utc_now,
)
from .probe import CommandProbe, probe_command
from .recovery import Checkpoint, FileCheckpointStore, RetryPolicy, retry
from .transcript import TranscriptReader, TranscriptWriter, hmac_digest, redact_text

__all__ = [
    "Checkpoint",
    "Chunk",
    "ChunkIndex",
    "Citation",
    "CommandProbe",
    "ContextBudget",
    "ContextPacket",
    "ConversationMessage",
    "Document",
    "Event",
    "EventKind",
    "FileCheckpointStore",
    "MemoryBudget",
    "MemoryDistiller",
    "MemoryMatch",
    "MemoryRecord",
    "MemoryStore",
    "ProcessResult",
    "ProcessSpec",
    "ProcessSupervisor",
    "RetryPolicy",
    "RetrievalHit",
    "Retriever",
    "Termination",
    "TranscriptReader",
    "TranscriptWriter",
    "decode_json_lines",
    "deduplicate_hits",
    "extract_json_object",
    "extract_text",
    "hmac_digest",
    "json_pointer_values",
    "normalize_stream_line",
    "chunk_document",
    "conversation_window",
    "pack_context",
    "pack_memory_context",
    "probe_command",
    "redact_text",
    "rank_memories",
    "reciprocal_rank_fusion",
    "retry",
    "utc_now",
]

# Safety modules (from production incidents — see README "已提取能力")
from .atomic_json import AtomicJsonStore, LoadResult  # noqa: E402
from .evidence import repair_quote, verify_quote  # noqa: E402
from .snapshot import FileSnapshot  # noqa: E402
from .webhook import SendResult, WebhookClient  # noqa: E402
