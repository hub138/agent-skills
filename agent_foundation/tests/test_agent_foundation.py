from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from agent_foundation import (
    Checkpoint,
    ContextBudget,
    ConversationMessage,
    Document,
    Event,
    EventKind,
    FileCheckpointStore,
    MemoryBudget,
    MemoryMatch,
    MemoryRecord,
    ProcessSpec,
    ProcessSupervisor,
    RetrievalHit,
    RetryPolicy,
    Termination,
    TranscriptReader,
    TranscriptWriter,
    chunk_document,
    conversation_window,
    decode_json_lines,
    extract_json_object,
    extract_text,
    json_pointer_values,
    normalize_stream_line,
    pack_context,
    pack_memory_context,
    rank_memories,
    reciprocal_rank_fusion,
    retry,
)


def test_stream_normalization_and_json_lines_are_schema_free():
    assert normalize_stream_line("\x1b]0;title\x07data: {\"any\": 1}") == '{"any": 1}'
    decoded, rejected = decode_json_lines(['data: {"x": 1}\nnot-json\n[1, 2]'])
    assert decoded == [{"x": 1}, [1, 2]]
    assert rejected == ["not-json"]


def test_content_extraction_needs_no_provider_shape():
    document = {"arbitrary": {"answer": "hello"}, "items": [{"value": 3}]}
    assert json_pointer_values(document, ["/arbitrary/answer", "/items/0/value"]) == ["hello", 3]
    assert extract_text(document, pointers=["/arbitrary/answer"]) == "hello"
    assert extract_json_object("notes\n```json\n{\"free\": true}\n```") == {"free": True}
    assert extract_json_object('before ["a", {"b": "}"}] after') == ["a", {"b": "}"}]


def test_context_chunking_fusion_and_budget_have_no_backend_dependency():
    chunks = chunk_document(Document("guide", "first paragraph\n\nsecond paragraph\n\nthird paragraph"), max_chars=18)
    assert [chunk.text for chunk in chunks] == ["first paragraph", "second paragraph", "third paragraph"]

    first = [RetrievalHit(chunks[0], 0.8), RetrievalHit(chunks[1], 0.7)]
    second = [RetrievalHit(chunks[1], 0.2), RetrievalHit(chunks[2], 0.9)]
    fused = reciprocal_rank_fusion([first, second])
    assert fused[0].chunk == chunks[1]

    packet = pack_context(fused, ContextBudget(max_chars=50, max_chunks=2))
    assert len(packet.citations) == 2
    assert [citation.document_id for citation in packet.citations] == ["guide", "guide"]
    assert len(packet.text) <= 50


def test_memory_window_ranking_and_budget_are_generic():
    now = datetime(2026, 7, 26, tzinfo=UTC)
    messages = [
        ConversationMessage("system", "one"),
        ConversationMessage("user", "two"),
        ConversationMessage("assistant", "three"),
    ]
    assert [message.content for message in conversation_window(messages, max_messages=2, max_chars=20)] == ["two", "three"]

    active = MemoryRecord("active", "useful memory", created_at=now - timedelta(days=1), importance=1.0)
    expired = MemoryRecord("expired", "do not include", expires_at=now - timedelta(seconds=1))
    packed = pack_memory_context(
        [MemoryMatch(expired, 1.0), MemoryMatch(active, 0.8)],
        MemoryBudget(max_chars=30, max_records=2),
        now=now,
    )
    assert packed == "[1] useful memory"
    naive = MemoryRecord("naive", "another memory", created_at=datetime(2026, 7, 25), importance=0.1)
    assert rank_memories(
        [MemoryMatch(naive, 0.2), MemoryMatch(active, 0.8)],
        MemoryBudget(max_chars=30, max_records=1),
        now=now,
    ) == [MemoryMatch(active, 0.8)]


def test_checkpoint_and_transcript_are_restart_safe(tmp_path):
    store = FileCheckpointStore(tmp_path / "checkpoints")
    checkpoint = Checkpoint(key="conversation/one", continuation="opaque-token", data={"state": "sample"})
    store.save(checkpoint)
    restored = store.load("conversation/one")
    assert restored is not None
    assert restored.continuation == "opaque-token"

    path = tmp_path / "transcript.jsonl"
    writer = TranscriptWriter(path)
    writer.append(Event(EventKind.OUTPUT, "Authorization: top-secret"))
    assert list(TranscriptReader(path).events())[0].message == "***REDACTED***"
    writer.append(Event(EventKind.OUTPUT, "Authorization: Bearer top-secret"))
    private_block = "-----BEGIN " + "PRIVATE KEY-----\nsample\n-----END " + "PRIVATE KEY-----"
    writer.append(Event(EventKind.OUTPUT, private_block))
    events = list(TranscriptReader(path).events())
    assert events[1].message == "***REDACTED***"
    assert events[2].message == "***REDACTED***"


def test_supervisor_reports_output_heartbeat_and_idle_timeout():
    command = [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(0.3)"]
    completed = ProcessSupervisor().run(
        ProcessSpec(command, hard_timeout_seconds=2, idle_timeout_seconds=1, heartbeat_interval_seconds=0.05)
    )
    assert completed.termination == Termination.EXITED
    assert completed.stdout == "ready\n"
    assert any(event.kind == EventKind.HEARTBEAT for event in completed.events)
    start_event = next(event for event in completed.events if event.kind == EventKind.START)
    assert start_event.data == {"executable": sys.executable, "argument_count": 2}

    idle = ProcessSupervisor().run(
        ProcessSpec([sys.executable, "-c", "import time; time.sleep(2)"], idle_timeout_seconds=0.1)
    )
    assert idle.termination == Termination.IDLE_TIMEOUT

    output_then_idle = ProcessSupervisor().run(
        ProcessSpec(
            [sys.executable, "-c", "import time; print('one', flush=True); time.sleep(2)"],
            idle_timeout_seconds=0.1,
        )
    )
    assert output_then_idle.termination == Termination.IDLE_TIMEOUT
    assert output_then_idle.stdout == "one\n"


def test_retry_uses_caller_defined_transient_boundary():
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("temporary")
        return "done"

    result = retry(
        operation,
        policy=RetryPolicy(max_attempts=4, initial_delay_seconds=0.1, multiplier=2),
        is_retryable=lambda error: isinstance(error, ConnectionError),
        on_retry=lambda _attempt, _error, delay: delays.append(delay),
        sleep=lambda _delay: None,
    )
    assert result == "done"
    assert delays == [0.1, 0.2]
