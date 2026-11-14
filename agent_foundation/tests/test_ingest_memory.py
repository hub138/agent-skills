"""测试幂等接收与文件型记忆库。"""

from pathlib import Path

from agent_foundation import (
    AcceptState,
    FileMemoryVault,
    IdempotentReceiver,
    InMemoryIdempotencyStore,
    Submission,
)


def test_receiver_accepts_duplicate_and_supersedes():
    store = InMemoryIdempotencyStore()
    receiver = IdempotentReceiver(store)

    first = receiver.receive(Submission(idempotency_key="k1", fingerprint="task:loop:#3", record={"n": 1}, version=3))
    assert first.state is AcceptState.CREATED

    replay = receiver.receive(Submission(idempotency_key="k1", fingerprint="task:loop:#3", record={"n": 2}, version=3))
    assert replay.state is AcceptState.DUPLICATE
    assert replay.record == {"n": 1}

    stale = receiver.receive(Submission(idempotency_key="k2", fingerprint="task:loop:#2", record={"n": 9}, version=2))
    assert stale.state is AcceptState.SUPERSEDED

    newer = receiver.receive(Submission(idempotency_key="k3", fingerprint="task:loop:#4", record={"n": 4}, version=4))
    assert newer.state is AcceptState.CREATED

    same_content_new_key = receiver.receive(
        Submission(idempotency_key="k4", fingerprint="task:loop:#3", record={"n": 1}, version=3)
    )
    assert same_content_new_key.state is AcceptState.DUPLICATE


def test_receiver_fingerprint_uniqueness_under_concurrent_saves():
    store = InMemoryIdempotencyStore()
    winner = store.save(Submission(idempotency_key=None, fingerprint="fp-x", record="first"))
    loser = store.save(Submission(idempotency_key=None, fingerprint="fp-x", record="second"))
    assert winner.record == "first"
    assert loser.record == "first"


def test_file_vault_write_read_entries_and_index(tmp_path: Path):
    vault = FileMemoryVault(tmp_path)
    vault.write("feedback", "verify", "# 先验证再下结论\n正文")
    vault.write("project", "layout", "# 布局审计\n")
    vault.write("project", "nav", "无标题首行时用文件名兜底")

    assert vault.read("feedback", "verify") == "# 先验证再下结论\n正文"
    assert vault.read("feedback", "missing") is None

    project_entries = vault.entries("project")
    assert [(entry.slug, entry.title) for entry in project_entries] == [
        ("layout", "布局审计"),
        ("nav", "无标题首行时用文件名兜底"),
    ]

    index = vault.rebuild_index()
    text = index.read_text(encoding="utf-8")
    assert "布局审计" in text and "project_layout.md" in text

    all_names = {entry.filename for entry in vault.entries()}
    assert all_names == {"feedback_verify.md", "project_layout.md", "project_nav.md"}
