"""platform_util 回归：跨平台分支不靠「在当前机器上碰巧跑通」证明。

2026-11-15：此前只在 macOS 手测过，Linux / other 分支与
「Linux 但 /proc 未挂载」都没有覆盖。这里用 monkeypatch 模拟。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import platform_util as u  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_caches():
    u.os_kind.cache_clear()
    u.resolve_bin.cache_clear()
    yield
    u.os_kind.cache_clear()
    u.resolve_bin.cache_clear()



def test_os_kind_returns_known_values(monkeypatch):
    import platform
    u.os_kind.cache_clear()
    for raw, want in [("Linux", "linux"), ("Darwin", "macos"),
                      ("Windows", "other"), ("FreeBSD", "other")]:
        monkeypatch.setattr(platform, "system", lambda r=raw: r)
        u.os_kind.cache_clear()
        assert u.os_kind() == want
    u.os_kind.cache_clear()


def test_pid_exists_own_and_bogus():
    assert u.pid_exists(os.getpid()) is True
    assert u.pid_exists(999999) is False
    assert u.pid_exists(None) is False
    assert u.pid_exists("not-a-pid") is False
    assert u.pid_exists(0) is False


def test_pid_exists_macos_uses_kill(monkeypatch):
    monkeypatch.setattr(u, "os_kind", lambda: "macos")
    assert u.pid_exists(os.getpid()) is True


def test_pid_exists_linux_without_proc_falls_back(monkeypatch):
    """容器没挂 /proc 时，不能把活进程误判成死了。"""
    u.os_kind.cache_clear()
    monkeypatch.setattr(u, "os_kind", lambda: "linux")
    monkeypatch.setattr(os.path, "isdir", lambda p: False)
    assert u.pid_exists(os.getpid()) is True


def test_pid_exists_linux_with_proc(monkeypatch):
    u.os_kind.cache_clear()
    monkeypatch.setattr(u, "os_kind", lambda: "linux")
    monkeypatch.setattr(os.path, "isdir",
                        lambda p: True if p == "/proc" else p == f"/proc/{os.getpid()}")
    assert u.pid_exists(os.getpid()) is True
    assert u.pid_exists(999999) is False


def test_process_alive_other_platform_uses_ps(monkeypatch):
    u.os_kind.cache_clear()
    monkeypatch.setattr(u, "os_kind", lambda: "other")
    monkeypatch.setattr(u, "_ps_rows", lambda: [(1, "python my-worker --flag"),
                                                (2, "grep my-worker")])
    assert u.process_alive("my-worker") is True
    assert u.process_alive("absent-xyz") is False


def test_process_alive_empty_pattern_is_false():
    assert u.process_alive("") is False


def test_probe_available_when_ps_fails(monkeypatch):
    u.os_kind.cache_clear()
    monkeypatch.setattr(u, "os_kind", lambda: "macos")
    monkeypatch.setattr(u, "_ps_rows", lambda: [])
    assert u.probe_available() is False


def test_resolve_bin_env_wins(monkeypatch):
    u.resolve_bin.cache_clear()
    monkeypatch.setenv("TEST_BIN_PATH", "/custom/bin/tool")
    assert u.resolve_bin("tool", "TEST_BIN_PATH", ()) == "/custom/bin/tool"


def test_resolve_bin_candidate_then_path(monkeypatch, tmp_path):
    u.resolve_bin.cache_clear()
    fake = tmp_path / "tool"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    assert u.resolve_bin("definitely-absent-xyz", None, (str(fake),)) == str(fake)
    # 候选不存在时退回 PATH 查找；找不到就返回原名，让调用方报清晰错误
    assert u.resolve_bin("definitely-absent-xyz", None,
                         ("/nonexistent/xyz",)) == "definitely-absent-xyz"


def test_resolve_bin_finds_codebuddy_on_this_machine(monkeypatch):
    u.resolve_bin.cache_clear()
    monkeypatch.delenv("CODEBUDDY_CLI_BIN", raising=False)
    got = u.resolve_bin("codebuddy", "CODEBUDDY_CLI_BIN",
                        ("/usr/local/bin/codebuddy", "/opt/homebrew/bin/codebuddy"))
    assert got != "codebuddy", "本机应能找到 codebuddy"
    assert os.path.isabs(got)
