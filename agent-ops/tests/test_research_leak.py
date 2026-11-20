"""research_loop.leak 工程回归(方案 8.1、13.1 隔离项)。"""
import os
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from research_loop import leak  # noqa: E402


def _mk(path, content="secret-label-content\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------- scan_workspace ----------

def test_scan_clean_workspace_passes(tmp_path):
    ws = tmp_path / "ws"
    _mk(ws / "src/a.py", "print('hello')\n")
    deny = _mk(tmp_path / "vault/labels.json")
    res = leak.scan_workspace(str(ws), [str(deny)],
                              ["CANARY-ZZTOP"])
    assert res["verdict"] == "pass"
    assert res["violations"] == []


def test_scan_copied_deny_file_hash_match(tmp_path):
    ws = tmp_path / "ws"
    deny = _mk(tmp_path / "vault/labels.json", "secret-label-content\n")
    _mk(ws / "data/labels_copy.json", "secret-label-content\n")  # 换名拷贝
    _mk(ws / "src/ok.py", "fine\n")
    res = leak.scan_workspace(str(ws), [str(deny)], [])
    types = {v["type"] for v in res["violations"]}
    assert types == {"hash-match"}
    assert res["verdict"] == "fail"


def test_scan_canary_found(tmp_path):
    ws = tmp_path / "ws"
    deny = _mk(tmp_path / "vault/labels.json")
    _mk(ws / "notes.md", "review note mentions CANARY-ZZTOP leak\n")
    res = leak.scan_workspace(str(ws), [str(deny)], ["CANARY-ZZTOP"])
    types = {v["type"] for v in res["violations"]}
    assert types == {"canary-found"}
    assert res["verdict"] == "fail"


def test_scan_deny_path_mounted_into_workspace(tmp_path):
    ws = tmp_path / "ws"
    deny = _mk(ws / "vault/labels.json")  # 禁止源直接挂进工作区
    _mk(ws / "src/ok.py", "fine\n")
    res = leak.scan_workspace(str(ws), [str(deny)], [])
    types = {v["type"] for v in res["violations"]}
    assert types == {"path-in-deny"}
    assert res["verdict"] == "fail"


def test_scan_symlink_to_deny_file_hit(tmp_path):
    ws = tmp_path / "ws"
    deny = _mk(tmp_path / "vault/labels.json")
    link = ws / "link.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(deny), str(link))
    res = leak.scan_workspace(str(ws), [str(deny)], [])
    types = {v["type"] for v in res["violations"]}
    assert types == {"path-in-deny"}
    assert res["verdict"] == "fail"


def test_scan_symlink_into_deny_directory(tmp_path):
    ws = tmp_path / "ws"
    _mk(tmp_path / "vault/labels.json")   # vault 整目录禁入
    link = ws / "link.json"               # symlink 解析后落进禁目录
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(tmp_path / "vault" / "labels.json"), str(link))
    res = leak.scan_workspace(str(ws), [str(tmp_path / "vault")], [])
    assert {v["type"] for v in res["violations"]} == {"path-in-deny"}


def test_scan_oversized_files_skipped(tmp_path):
    ws = tmp_path / "ws"
    deny = _mk(tmp_path / "vault/labels.json", "A" * 64 + "\n")
    big = ws / "big.bin"
    big.parent.mkdir(parents=True, exist_ok=True)
    big.write_text("A" * 64 + "\n" + "B" * (1 << 21), encoding="utf-8")
    res = leak.scan_workspace(str(ws), [str(deny)], [],
                              max_file_bytes=1 << 20)
    assert res["verdict"] == "pass"


# ---------- probe_reverse_read ----------

def test_probe_readable_deny_path_fails(tmp_path):
    deny = _mk(tmp_path / "vault/labels.json", "labels\n")
    res = leak.probe_reverse_read([str(deny)])
    assert res["attempts"][0]["readable"] is True
    assert res["attempts"][0]["bytes"] > 0
    assert res["verdict"] == "fail"


def test_probe_unreadable_path_passes(tmp_path):
    missing = tmp_path / "vault" / "nope.json"
    res = leak.probe_reverse_read([str(missing)])
    assert res["attempts"][0]["readable"] is False
    assert res["verdict"] == "pass"


# ---------- isolation_gate ----------

def _scan(v):
    return {"violations": [], "verdict": v}


def _probe(readable=False):
    return {"attempts": [{"path": "x", "readable": readable, "bytes": 1}],
            "verdict": "fail" if readable else "pass"}


def test_gate_full_requires_scan_and_probe_clean():
    assert leak.isolation_gate("full", _scan("pass"), _probe(False))[
        "verdict"] == "pass"
    assert leak.isolation_gate("full", _scan("pass"), _probe(True))[
        "verdict"] == "fail"
    assert leak.isolation_gate("full", _scan("fail"), _probe(False))[
        "verdict"] == "fail"


def test_gate_limited_only_needs_scan():
    assert leak.isolation_gate("limited", _scan("pass"), _probe(True))[
        "verdict"] == "pass"  # 无阻断能力也不 fail,但进不了终验
    assert leak.isolation_gate("limited", _scan("fail"), _probe(False))[
        "verdict"] == "fail"


def test_gate_blocked_mode():
    assert leak.isolation_gate("blocked", _scan("pass"), _probe(False))[
        "verdict"] == "blocked"
    assert leak.isolation_gate("nope", _scan("pass"), _probe(False))[
        "verdict"] == "blocked"


def test_final_only_accepts_full_pass():
    good_full = leak.isolation_gate("full", _scan("pass"), _probe(False))
    assert leak.accepts_final(good_full) is True
    assert leak.accepts_final(
        leak.isolation_gate("limited", _scan("pass"), _probe(True))) is False
    assert leak.accepts_final(
        leak.isolation_gate("blocked", _scan("pass"), _probe(False))) is False
    assert leak.accepts_final(
        leak.isolation_gate("full", _scan("fail"), _probe(False))) is False
