#!/usr/bin/env python3
"""管理者（manager）回归：refine 目标演化、决策留痕、prompt 重渲染、history。

不调真实模型——决策由测试注入 apply()；ask_model_single 的解析逻辑单测覆盖。
运行：python3 -m pytest tests/test_manager.py -q
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TASKCTL_DB", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("AGENTCTL_HOME", str(tmp_path / "home"))
    for mod in ("taskctl", "manager"):
        sys.modules.pop(mod, None)
    import taskctl as t
    import manager as M
    monkeypatch.setattr(t, "HOME", tmp_path / "home")
    monkeypatch.setattr(t, "DB", tmp_path / "tasks.db")
    return t, M, tmp_path


def _add_running(t, tmp_path, name="m1"):
    ns = argparse.Namespace(kind="generic", input='{"topic":"初始目标"}', input_file=None,
                            goal="初始目标：对比两版实现差异", repo=None, name=name,
                            backend="codebuddy", model="free-model", workdir="/tmp",
                            priority=100, max_attempts=3, quiet=True)
    t.cmd_add(ns)
    base = tmp_path / "home" / "tasks" / name
    out = base / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "progress.md").write_text("- [步骤1] 初步对比 → 3 处差异\n", encoding="utf-8")
    c = t.db()
    c.execute("UPDATE tasks SET status='running',attempts=1,started_at=?,lease_until=?,"
              "worker_id=? WHERE name=?",
              (time.time() - 100, time.time() + 1000, "w1:999999", name))
    c.commit()
    r = c.execute("SELECT * FROM tasks WHERE name=?", (name,)).fetchone()
    c.close()
    return r, base


# ── goal.md 生命周期：add 生成 → refine 归档+更新 ─────────────────────
def test_goal_lifecycle(env, tmp_path):
    t, M, tp = env
    r, base = _add_running(t, tp)
    assert (base / "goal.md").exists()
    assert "初始目标" in (base / "goal.md").read_text(encoding="utf-8")

    c = t.db()
    acted = M.apply(c, [{"task": "m1", "action": "refine",
                         "reason": "差异集中在 sort 模块",
                         "new_goal": "深入对比 sort 模块 ORDER BY：逐差异给影响与建议",
                         "guidance": "聚焦 sort"}])
    c.close()
    assert acted == ["m1:nudge"]                       # refine 落 nudge 路径
    assert "sort 模块" in (base / "goal.md").read_text(encoding="utf-8")
    arch = list((base / "goal-archive").glob("goal-*.md"))
    assert len(arch) == 1 and "初始目标" in arch[0].read_text(encoding="utf-8")


# ── 决策全留痕：continue 也记，含理由 ─────────────────────────────────
def test_decisions_provenance(env, tmp_path):
    t, M, tp = env
    r, base = _add_running(t, tp)
    c = t.db()
    M.apply(c, [{"task": "m1", "action": "continue",
                 "reason": "idle=209s 符合刚启动形态", "guidance": ""}])
    M.apply(c, [{"task": "m1", "action": "nudge", "reason": "重复报错",
                 "guidance": "先诊断根因"}])
    c.close()
    lines = [json.loads(x) for x in
             (base / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [d["action"] for d in lines] == ["continue", "nudge"]
    assert lines[0]["reason"]                          # continue 的理由也在
    assert all(d.get("ts") for d in lines)


# ── prompt.md 每轮重渲染：guidance/goal 真的会注入（回归旧 bug）──────
def test_prompt_rerender(env, tmp_path):
    t, M, tp = env
    r, base = _add_running(t, tp)
    c = t.db()
    full = c.execute("SELECT * FROM tasks WHERE name='m1'").fetchone()
    t.ensure_task_dir(full)                            # 第一轮
    pp = base / "prompt.md"
    assert "管理者给你的最新指令" not in pp.read_text(encoding="utf-8")
    # 管理者 nudge → guidance.md 落盘 → 重渲染必须出现（旧版永不重渲染 = 死回灌）
    M.apply(c, [{"task": "m1", "action": "nudge", "reason": "跑偏",
                 "guidance": "聚焦 sort 模块"}])
    text = t.ensure_task_dir(full)
    assert "聚焦 sort 模块" in text
    assert "当前任务目标" in text and "初始目标" in text    # goal.md 注入
    c.close()


# ── history：一屏全史 ────────────────────────────────────────────────
def test_history(env, tmp_path, capsys):
    t, M, tp = env
    r, base = _add_running(t, tp)
    c = t.db()
    M.apply(c, [{"task": "m1", "action": "refine", "reason": "聚焦 sort",
                 "new_goal": "sort 模块深入对比", "guidance": "x"}])
    c.close()
    ns = argparse.Namespace(task="m1")
    rc = t.cmd_history(ns)
    out = capsys.readouterr().out
    assert rc == 0
    assert "原始目标" in out and "当前目标(goal.md)" in out
    assert "时间线" in out and "管理者决策" in out
    assert "refine" in out


# ── ask_model_single 输出解析：单对象 / 围栏 / 坏输出 ─────────────────
def test_ask_model_single_parse(env, tmp_path, monkeypatch):
    t, M, tp = env
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        out = calls and json.dumps({"action": "nudge", "reason": "r", "guidance": "g"})
        class R:
            returncode = 0
            stdout = out
            stderr = ""
        return R()
    monkeypatch.setattr(M.subprocess, "run", fake_run)
    d = M.ask_model_single("快照", "总览", "m1")
    assert d and d["action"] == "nudge"
    # 会话名带任务名，便于审计
    assert any("mgr-m1-" in " ".join(c) for c in [calls[-1]])

    def fake_run_bad(cmd, **kw):
        class R:
            returncode = 0
            stdout = "模型说了一堆没有 JSON 的话"
            stderr = ""
        return R()
    monkeypatch.setattr(M.subprocess, "run", fake_run_bad)
    assert M.ask_model_single("s", "o", "m1") is None   # 坏输出 → None，本轮不动
