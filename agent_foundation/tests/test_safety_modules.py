"""Tests for webhook / evidence / atomic_json / snapshot modules.

Every test traces back to a production incident in the knowledge-base
self-evolution system (see docs/benchmark-tasks.md incident archive).
"""

import json

from agent_foundation.atomic_json import AtomicJsonStore
from agent_foundation.evidence import repair_quote, verify_quote
from agent_foundation.snapshot import FileSnapshot
from agent_foundation.webhook import utf8_chunks


# ── webhook: HTTP 200 is not success ──────────────────────────────────────

def test_oversized_message_is_split_by_utf8_bytes():
    # 4096 Chinese characters = 12KB: character-based truncation still overflows
    msg = "很长的中文通知内容" * 500
    chunks = utf8_chunks(msg, limit=3500)
    assert all(len(c.encode("utf-8")) <= 3500 for c in chunks)
    # 硬切处会引入换行（markdown 通知里无语义）；字符级无损才是承诺
    assert "".join(c.replace("\n", "") for c in chunks) == msg


# ── evidence: fabricated quotes must fail, honest ones must pass ──────────

BODY = ('上一轮压测持续了 300 秒，错误率保持稳定。设计上他说“先定义判定条件再跑工具”，'
        '这句话是全文的锚点，后面的章节都围绕它展开。重复段落在文末。重复段落在文末。')


def test_exact_quote_passes():
    assert verify_quote(BODY, "这句话是全文的锚点")


def test_fabricated_quote_fails():
    assert not verify_quote(BODY, "这句话根本不在原文里，是编造的引文内容")


def test_one_char_off_fails():
    assert not verify_quote(BODY, "这句话是全文的锚店")  # 锚点→锚店


def test_invisible_differences_are_tolerated():
    assert verify_quote(BODY, "这句话是全文的锚点，\n 后面的章节都围绕它展开。")
    assert verify_quote(BODY, "设计上他说\"先定义判定条件再跑工具\"，这句话是全文的锚点")


def test_repair_recovers_honest_copies():
    r = repair_quote(BODY, "压测持续了 300 秒，错误率保持稳定")
    assert r == "压测持续了 300 秒，错误率保持稳定"  # 原文片段（不含上下文前缀）


def test_repair_rejects_ambiguous_hits():
    assert repair_quote(BODY + BODY, "重复段落在文末") is None  # twice in body


def test_repair_rejects_unknown():
    assert repair_quote(BODY, "这句话完全不存在于原文之中任何位置") is None


def test_repair_rejects_short_quotes():
    assert repair_quote(BODY, "锚点") is None  # below min length


# ── atomic_json: kill -9 must never lose data ─────────────────────────────

def test_save_creates_backup(tmp_path):
    store = AtomicJsonStore(tmp_path / "db.json")
    store.save({"n": 1})
    store.save({"n": 2})
    assert (tmp_path / "db.json.bak").exists()
    assert json.loads((tmp_path / "db.json.bak").read_text())["n"] == 1
    assert json.loads((tmp_path / "db.json").read_text())["n"] == 2


def test_truncated_main_file_falls_back_to_backup(tmp_path):
    store = AtomicJsonStore(tmp_path / "db.json")
    store.save({"items": [1]})
    store.save({"items": [1, 2, 3]})
    # tmp+replace 保证主文件要么完整旧版要么完整新版——"写一半截断"只可能
    # 来自外部破坏。此时 .bak 提供的是上一份完整状态，永不静默当空。
    (tmp_path / "db.json").write_text('{"items": [1, 2, ', encoding="utf-8")
    r = store.load()
    assert r.ok and r.recovered_from == "backup"
    assert r.data["items"] == [1]  # 上一份好文件


def test_validation_rejects_wrong_shape(tmp_path):
    store = AtomicJsonStore(tmp_path / "db.json",
                            validate=lambda d: isinstance(d, dict) and "missions" in d)
    store.save({"missions": []})
    store.save({"missions": [1]})
    (tmp_path / "db.json").write_text('{"wrong": true}', encoding="utf-8")
    r = store.load()
    assert r.recovered_from == "backup"  # wrong shape treated as corruption


def test_missing_file_returns_default(tmp_path):
    r = AtomicJsonStore(tmp_path / "none.json").load()
    assert r.ok and r.data is None


def test_backup_alone_corrupt_is_not_silent_empty(tmp_path):
    """主文件缺失 + 备份损坏 = 数据事故，必须报错而不是静默返回空。"""
    store = AtomicJsonStore(tmp_path / "db.json")
    store.save({"n": 1})
    (tmp_path / "db.json").unlink()          # main gone
    (tmp_path / "db.json.bak").write_text("{broken", encoding="utf-8")
    r = store.load()
    assert not r.ok and r.error  # never ok=True with empty default here


# ── snapshot: restore must be verifiable ──────────────────────────────────

def test_snapshot_and_verified_restore(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    (repo / "a.txt").write_text("original A", encoding="utf-8")
    (repo / "sub" / "b.txt").write_text("original B", encoding="utf-8")

    snap = FileSnapshot(tmp_path / "snaps", "attempt-1")
    missing = snap.snapshot(["a.txt", "sub/b.txt"], repo)
    assert missing == []

    (repo / "a.txt").write_text("edited A", encoding="utf-8")
    (repo / "sub" / "b.txt").write_text("edited B", encoding="utf-8")

    ok, why = snap.restore(repo)
    assert ok, why
    assert (repo / "a.txt").read_text() == "original A"
    assert (repo / "sub" / "b.txt").read_text() == "original B"


def test_rollback_deletes_files_created_during_edit(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    (repo / "a.txt").write_text("original", encoding="utf-8")

    snap = FileSnapshot(tmp_path / "snaps", "attempt-1")
    missing = snap.snapshot(["a.txt", "new-file.md"], repo)
    assert missing == ["new-file.md"]

    (repo / "new-file.md").write_text("AI created this", encoding="utf-8")
    ok, why = snap.restore(repo)
    assert ok, why
    assert (repo / "a.txt").read_text() == "original"
    assert not (repo / "new-file.md").exists()  # created-by-edit is rolled back


def test_restore_verifies_against_snapshot_time_hash(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "a.txt").write_text("v1", encoding="utf-8")
    snap = FileSnapshot(tmp_path / "snaps", "attempt-2")
    snap.snapshot(["a.txt"], repo)

    # Tamper with the SNAPSHOT copy after the fact. Restore must catch this
    # by comparing against the hash recorded in the manifest — the old
    # implementation compared snapshot-copy vs restored-copy and was blind
    # to exactly this corruption.
    snap._dir.joinpath("a.txt").write_text("corrupted-after-snapshot", encoding="utf-8")
    ok, why = snap.restore(repo)
    assert not ok and "hash" in why


def test_manifest_unreadable_is_structured_failure(tmp_path):
    snap = FileSnapshot(tmp_path / "snaps", "attempt-3")
    snap._dir.mkdir(parents=True, exist_ok=True)
    snap._dir.joinpath("manifest.json").write_text("{broken", encoding="utf-8")
    ok, why = snap.restore(tmp_path)
    assert not ok and "manifest unreadable" in why
