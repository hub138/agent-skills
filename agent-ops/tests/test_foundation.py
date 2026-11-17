#!/usr/bin/env python3
"""agent_foundation 桥接回归：接线必须真实生效，缺库必须优雅回退。

对应 2026-11-17 夜 <审查项目> 232 条实测缺口里本轮接入的四个：
prompt 截断、失败分类+冷却、证据校验、三级解析回退。
recovery/iteration_loop/resource_pool 明确不迁移（理由见 SKILL.md 桥接表）。
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import evidence_gate as EG  # noqa: E402
import foundation_bridge as FB  # noqa: E402
import prompt_transport as PT  # noqa: E402
import provider_events as PE  # noqa: E402


def test_bridge_locates_real_library():
    assert FB.src_dir() is not None
    assert FB.load("agent_foundation.protocol") is not None


def test_bridge_returns_none_when_missing(tmp_path, monkeypatch):
    # 安装副本布局：旁无 agent_foundation，环境变量也没给 → 必须优雅返回 None
    monkeypatch.setattr(FB, "SKILL_ROOT", tmp_path)
    monkeypatch.delenv("AGENT_FOUNDATION_SRC", raising=False)
    assert FB.src_dir() is None
    assert FB.load("agent_foundation.protocol") is None


def test_bridge_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(FB, "SKILL_ROOT", tmp_path)
    # 内部布局与公开仓库布局都能命中（agent-ops 与 agent_foundation 相对位置不同）
    cands = [ROOT.parent / "agent_foundation" / "src",
             ROOT.parent / "agent-skills" / "agent_foundation" / "src"]
    src = next((str(c) for c in cands if (c / "agent_foundation").is_dir()), None)
    assert src, "测试机应至少存在一份 agent_foundation"
    monkeypatch.setenv("AGENT_FOUNDATION_SRC", src)
    assert FB.src_dir() is not None
    assert FB.load("agent_foundation.evidence") is not None


def test_cap_prompt_within_limit_untouched():
    text = "x" * PT.ARG_LIMIT
    assert PT.cap_prompt(text, log=None) is text


def test_cap_prompt_keeps_head_and_tail():
    text = "HEAD" + "m" * (PT.ARG_LIMIT + 1000) + "TAIL"
    out = PT.cap_prompt(text, log=None)
    assert len(out) <= PT.ARG_LIMIT + 300
    assert out.startswith("HEAD") and out.endswith("TAIL") and "已截断" in out


def test_classify_fake_green_light():
    info = PE.classify_output(
        '{"type":"error","error":"Plugin runtime refresh timeout"}')
    assert info["kind"] == "provider_unavailable"
    assert info["retry_same_session"] is True


def test_classify_rate_limit_and_auth_and_transient():
    assert PE.classify_output("usage limit exceeded")["kind"] == "rate_limited"
    assert PE.classify_output("http 401 unauthorized")["kind"] == "authentication_failed"
    assert PE.classify_output("upstream connect error")["kind"] == "provider_unavailable"


def test_classify_clean_output_is_none():
    assert PE.classify_output("正常输出，没有任何失败形态") is None


def test_cooldown_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_HOME", str(tmp_path))
    assert PE.in_cooldown() is None
    PE.note_cooldown("rate_limited", 3600, "限流")
    cd = PE.in_cooldown()
    assert cd and cd["kind"] == "rate_limited" and cd["remaining_seconds"] > 0


def test_handle_output_cooldowns_only_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCHDOG_HOME", str(tmp_path))
    info = PE.handle_output('{"type":"error"}')
    assert info["retry_same_session"] is True
    assert PE.in_cooldown() is None
    PE.handle_output("too many requests")
    assert PE.in_cooldown() is not None


def test_evidence_gate_valid_coord(tmp_path):
    d = tmp_path / "task"
    d.mkdir()
    (d.parent / "src.py").write_text(
        "\n".join("line%d" % i for i in range(1, 51)), encoding="utf-8")
    assert EG.check(d, ["src.py:10"]) == []


def test_evidence_gate_flags_fabricated_line(tmp_path):
    d = tmp_path / "task"
    d.mkdir()
    (d.parent / "src.py").write_text(
        "\n".join("line%d" % i for i in range(1, 51)), encoding="utf-8")
    problems = EG.check(d, ["src.py:999"])
    assert len(problems) == 1 and "行号越界" in problems[0]


def test_evidence_gate_flags_missing_file(tmp_path):
    d = tmp_path / "task"
    d.mkdir()
    problems = EG.check(d, ["no_such_file.py:3"])
    assert len(problems) == 1 and "不存在" in problems[0]


def test_evidence_gate_quote_vs_progress(tmp_path):
    d = tmp_path / "task"
    d.mkdir()
    (d / "progress.md").write_text("核心结论：租约用 lease_until 守护", encoding="utf-8")
    ok = EG.check(d, ["租约用 lease_until 守护"])
    bad = EG.check(d, ["这句引文根本没有出现过在进度里啊"])
    assert ok == [] and len(bad) == 1


def test_manager_uses_protocol_then_fallback(tmp_path, monkeypatch):
    """manager 解析：EMBEDDED 级可采；缺库回退手写正则；失败形态先拦。"""
    for mod in ("manager", "taskctl", "prompt_transport",
                "provider_events", "foundation_bridge"):
        sys.modules.pop(mod, None)
    monkeypatch.setenv("TASKCTL_DB", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("AGENTCTL_HOME", str(tmp_path / "home"))
    import manager as M
    monkeypatch.setattr(M, "SUPERVISOR_TIMEOUT", 5)

    fake_out = '前缀 {"action":"continue","reason":"在推进"} 后缀'
    monkeypatch.setattr(M.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=fake_out,
                                                        returncode=0))
    monkeypatch.setattr(M.PE, "in_cooldown", lambda: None)
    monkeypatch.setattr(M.PE, "handle_output", lambda out: None)
    d = M.ask_model_single("快照", "总览", "t1")
    assert d and d["action"] == "continue"

    monkeypatch.setattr(M.FB, "load", lambda name: None)
    d2 = M.ask_model_single("快照", "总览", "t2")
    assert d2 and d2["action"] == "continue"

    fake_fail = '{"type":"error","error":"boom"}'
    monkeypatch.setattr(M.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=fake_fail,
                                                        returncode=0))
    assert M.ask_model_single("快照", "总览", "t3") is None
