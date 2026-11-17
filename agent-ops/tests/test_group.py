#!/usr/bin/env python3
"""任务组三通道回归：感知(peers) / 通讯(send→inbox) / 留痕(events.jsonl)。

对应双 AI 协作场景（实现 AI 与调研 AI 互相反馈）：
- 同组任务 spawn 时的 prompt 必须带队友状态与新消息；
- send 的幂等语义（重复投递拒绝，--force 放行）；
- peers.md 必须反映成员状态变化（tick/事件驱动刷新）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))


@pytest.fixture()
def tenv(tmp_path, monkeypatch):
    monkeypatch.setenv("TASKCTL_DB", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("AGENTCTL_HOME", str(tmp_path / "home"))
    for mod in ("taskctl", "task_group", "manager"):
        sys.modules.pop(mod, None)
    import taskctl as t
    import task_group as TG
    monkeypatch.setattr(t, "HOME", tmp_path / "home")
    monkeypatch.setattr(t, "DB", tmp_path / "tasks.db")
    return t, TG, tmp_path


def _add(t, name, goal, group="gtest"):
    ns = argparse.Namespace(kind="generic", input=None, input_file=None,
                            goal=goal, repo=None, name=name,
                            backend="codebuddy", model="free-model",
                            workdir="/tmp", priority=100, max_attempts=3,
                            group=group, quiet=True)
    assert t.cmd_add(ns) == 0


def test_add_registers_member_and_group(tenv):
    t, TG, tmp = tenv
    _add(t, "impl", "实现MVP并验证")
    _add(t, "research", "调研方案")
    gid = TG.group_dir(tmp / "home", "gtest")
    ctx = (gid / "context.md").read_text(encoding="utf-8")
    assert "`impl`" in ctx and "`research`" in ctx
    kinds = [json.loads(l)["kind"]
             for l in (gid / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert kinds.count("member_added") == 2


def test_send_is_idempotent_and_writes_inbox(tenv):
    t, TG, tmp = tenv
    _add(t, "impl", "实现")
    _add(t, "research", "调研")
    a = TG.send(t.db(), tmp / "home", "impl", "research", "先看方案")
    assert a["sent"] is True
    b = TG.send(t.db(), tmp / "home", "impl", "research", "先看方案")
    assert b["duplicate"] is True and b["sent"] is False
    c = TG.send(t.db(), tmp / "home", "impl", "research", "先看方案", force=True)
    assert c["sent"] is True
    inbox = (tmp / "home" / "tasks" / "impl" / "out" / "inbox.md").read_text(encoding="utf-8")
    assert inbox.count("先看方案") == 2  # 首次 + force，重复投递那次没有写入


def test_inbox_pending_and_consume(tenv):
    t, TG, tmp = tenv
    _add(t, "impl", "实现")
    outdir = tmp / "home" / "tasks" / "impl" / "out"
    TG.send(t.db(), tmp / "home", "impl", "user", "第一条")
    TG.send(t.db(), tmp / "home", "impl", "user", "第二条")
    pend = TG.pending_inbox(outdir)
    assert "第一条" in pend and "第二条" in pend
    TG.mark_consumed(outdir)
    assert TG.pending_inbox(outdir) == ""
    TG.send(t.db(), tmp / "home", "impl", "user", "第三条")
    assert "第三条" in TG.pending_inbox(outdir)


def test_peers_reflect_state_change(tenv):
    t, TG, tmp = tenv
    _add(t, "impl", "实现")
    _add(t, "research", "调研")
    conn = t.db()
    conn.execute("UPDATE tasks SET status='finished', result_json=? WHERE name='impl'",
                 (json.dumps({"status": "done", "summary": "MVP 验证通过"}),))
    conn.commit()
    TG.refresh_peers(conn, tmp / "home", "gtest")
    peers = (TG.group_dir(tmp / "home", "gtest") / "peers.md").read_text(encoding="utf-8")
    assert "impl" in peers and "MVP 验证通过" in peers and "finished" in peers


def test_spawn_prompt_injects_peers_and_inbox(tenv):
    t, TG, tmp = tenv
    _add(t, "impl", "实现")
    _add(t, "research", "调研")
    TG.send(t.db(), tmp / "home", "impl", "research", "方案已就绪，先实现 A")
    conn = t.db()
    task = conn.execute("SELECT * FROM tasks WHERE name='impl'").fetchone()
    prompt = t.ensure_task_dir(task)
    assert "组内队友状态" in prompt
    assert "research" in prompt
    assert "方案已就绪" in prompt
    # 已消费：再次渲染不再重复注入消息；peers 投影每轮都在
    prompt2 = t.ensure_task_dir(task)
    assert prompt2.count("方案已就绪") == 0, "收件箱消费后不应重复注入"
    assert "组内队友状态" in prompt2


def test_group_status_lists_members(tenv):
    t, TG, tmp = tenv
    _add(t, "impl", "实现")
    _add(t, "research", "调研")
    rows = TG.group_status(t.db(), "gtest")
    assert [r["name"] for r in rows] == ["impl", "research"]
