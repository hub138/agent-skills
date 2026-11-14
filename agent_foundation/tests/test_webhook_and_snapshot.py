"""Tests aligned with the rewritten webhook (fail-stop, retries, instance
dedupe state) and snapshot (entry-format manifest with sha256/existed)."""

import json
import io
import urllib.request

import pytest

from agent_foundation.webhook import WebhookClient, utf8_chunks
from agent_foundation.snapshot import FileSnapshot


class FakeUrlopen:
    """Patch urllib.request.urlopen. errcode!=0 simulates HTTP-200-with-error."""

    def __init__(self, errcode: int | None = None):
        self.errcode = errcode
        self.payloads: list[dict] = []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data.decode("utf-8"))
        self.payloads.append(body)
        resp_body = json.dumps({"errcode": self.errcode} if self.errcode
                               else {"errcode": 0}).encode("utf-8")
        return _FakeResp(resp_body)


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_business_error_is_reported_as_failure(monkeypatch):
    server = FakeUrlopen(errcode=40058)
    monkeypatch.setattr(urllib.request, "urlopen", server)
    client = WebhookClient("http://hook")
    r = client.send("hello")
    assert r.ok is False
    assert any("40058" in f for f in r.failures)


def test_oversized_message_splits_and_delivers_all(monkeypatch):
    server = FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", server)
    client = WebhookClient("http://hook")
    msg = ("· 条目：这是一个足够长的通知条目，用来撑起字节数，验证分片语义。\n" * 120)
    r = client.send(msg)
    assert r.ok is True
    assert len(server.payloads) >= 2
    joined = "".join(_text(p).replace("\n", "") for p in server.payloads)
    assert msg.replace("\n", "") in joined  # lossless across chunks


def test_chunk_failure_stops_delivery(monkeypatch):
    calls = {"n": 0}

    class Flaky(FakeUrlopen):
        def __call__(self, req, timeout=None):
            calls["n"] += 1
            if calls["n"] >= 2:  # second chunk fails
                body = json.loads(req.data.decode("utf-8"))
                self.payloads.append(body)
                return _FakeResp(json.dumps({"errcode": 40058}).encode())
            return super().__call__(req, timeout)

    monkeypatch.setattr(urllib.request, "urlopen", Flaky())
    client = WebhookClient("http://hook")
    msg = "\n".join(f"· 条目{i}：内容足够长需要分片才能完整到达。" for i in range(80))
    r = client.send(msg)
    assert r.ok is False
    assert calls["n"] == 2  # stop-on-failure: chunk 3 never attempted


def test_dedupe_skips_entire_message(monkeypatch):
    server = FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", server)
    client = WebhookClient("http://hook")
    r1 = client.send("同一条状态通知", dedupe=True)
    assert r1.ok and not r1.deduped
    r2 = client.send("同一条状态通知", dedupe=True)
    assert r2.ok is True and r2.deduped is True and r2.chunks == 0
    assert len(server.payloads) == 1  # second send never hit the wire


def test_dedupe_state_is_per_instance(monkeypatch):
    server = FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", server)
    a = WebhookClient("http://hook-a")
    b = WebhookClient("http://hook-b")
    a.send("同一内容", dedupe=True)
    r = b.send("同一内容", dedupe=True)  # different URL → different dedupe space
    assert not r.deduped


def _text(payload: dict) -> str:
    return payload.get("markdown", {}).get("content", "")


# ── snapshot：新 manifest 结构（path/sha256/existed）────────────────────────

def test_rollback_deletes_files_created_during_edit(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    (repo / "a.txt").write_text("original", encoding="utf-8")

    snap = FileSnapshot(tmp_path / "snaps", "attempt-1")
    missing = snap.snapshot(["a.txt", "new-file.md"], repo)
    assert missing == ["new-file.md"]  # did not exist at snapshot time

    # The edit creates the new file
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
