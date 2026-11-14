#!/usr/bin/env python3
"""taskctl 关键行为回归测试（此前是 ad-hoc 内联验证，固化为可重复运行）。

运行：python3 -m pytest tests/test_taskctl.py -q
隔离：每个测试用独立 TASKCTL_DB / AGENTCTL_HOME（tmp_path）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("TASKCTL_DB", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("AGENTCTL_HOME", str(home))
    monkeypatch.setenv("TASKCTL_STALE", "900")
    for mod in ("taskctl", "supervisor"):
        sys.modules.pop(mod, None)
    import taskctl as t
    monkeypatch.setattr(t, "HOME", home)
    monkeypatch.setattr(t, "DB", tmp_path / "tasks.db")
    return t


# ── 阈值参数化（借鉴 prime-agent 的校验）───────────────────────────────
def test_valid_percent(env):
    t = env
    assert t.COMPACT_DROP_PCT == 30.0  # 默认
    assert t._valid_percent("abc", 30.0) == 30.0        # 非法回退
    assert t._valid_percent("150", 30.0) == 30.0        # 超界回退
    assert t._valid_percent("-5", 30.0) == 30.0         # 负数回退
    assert t._valid_percent("45", 30.0) == 45.0         # 合法生效


# ── result.json 契约校验 ───────────────────────────────────────────────
def test_validate_result(env):
    t = env
    assert t.validate_result({"status": "done", "summary": "x",
                              "evidence": ["a:1"]}) is None
    assert t.validate_result({"status": "ok"}) is not None          # 非法 status
    assert t.validate_result({"status": "done", "summary": ""}) is not None
    assert t.validate_result({"status": "done", "summary": "x" * 500}) is not None
    assert t.validate_result({"status": "done", "summary": "x",
                              "evidence": "notlist"}) is not None


# ── 假死判定：60s 不判死 / 超阈值判死 / 写新进度复活 / 0 关闭 ──────────
def test_is_stale(env, tmp_path):
    t = env
    out = tmp_path / "out"
    out.mkdir(parents=True)
    prog = out / "progress.md"
    prog.write_text("- 步骤1\n", encoding="utf-8")
    row = {"outdir": str(out), "session_id": "", "started_at": time.time() - 10}

    old = time.time() - 60
    os.utime(prog, (old, old))
    assert t.is_stale(row) == (False, "progress 60s 无增长")  # 未到阈值不判死

    older = time.time() - 1000
    os.utime(prog, (older, older))
    assert t.is_stale(row)[0] is True                          # 超阈值判死

    prog.write_text("- 步骤2\n", encoding="utf-8")             # 写新进度复活
    assert t.is_stale(row)[0] is False

    t.STALE_SECONDS = 0
    assert t.is_stale(row) == (False, "")                      # 0 关闭
    t.STALE_SECONDS = 900


# ── compaction 留痕：快照归档 + 行数骤降写事件 ─────────────────────────
def test_archive_progress_compaction(env, tmp_path):
    t = env
    out = tmp_path / "tasks" / "s1" / "out"
    out.mkdir(parents=True)
    prog = out / "progress.md"
    prog.write_text("\n".join(f"- 第{i}步" for i in range(600)) + "\n", encoding="utf-8")

    conn = t.db()
    conn.execute(
        "INSERT INTO tasks(id,name,kind,status,outdir,attempts,max_attempts,"
        "created_at) VALUES(1,'s1','generic','running',?,1,3,?)",
        (str(out), time.time()))
    # 第一次留痕：600 行基线
    t.archive_progress(conn, conn.execute("SELECT * FROM tasks WHERE id=1").fetchone())
    conn.commit()
    arch = out.parent / "progress-archive"
    assert len(list(arch.glob("snap-*.md"))) == 1
    assert c_e(conn, 1, "compaction") == 0                     # 无下降无事件

    # 模拟全局重写：600 → 49 行（drop 91.8% ≥ 30%）
    prog.write_text("# 紧凑重写版\n" * 49, encoding="utf-8")
    t.archive_progress(conn, conn.execute("SELECT * FROM tasks WHERE id=1").fetchone())
    conn.commit()

    assert c_e(conn, 1, "compaction") == 1                     # 事件已写
    ev = conn.execute(
        "SELECT payload FROM task_events WHERE kind='compaction'").fetchone()
    d = json.loads(ev["payload"])
    assert d["before_lines"] == 600 and d["after_lines"] == 49
    assert d["drop_pct"] > 30
    assert Path(d["archive"]).exists()                         # 压缩后版本归档
    # 顺序无关断言：两个 snap = 无损原文（大）+ 压缩后（小）；glob 不保证排序
    sizes = sorted(p.stat().st_size for p in arch.glob("snap-*.md"))
    assert len(sizes) == 2
    assert sizes[0] < 2000 and sizes[1] > 5000
    conn.close()


def c_e(conn, tid, kind):
    return conn.execute("SELECT COUNT(*) c FROM task_events "
                        "WHERE task_id=? AND kind=?", (tid, kind)).fetchone()["c"]


# ── 收尾后由 tick 触发同一逻辑（端到端小闭环）──────────────────────────
def test_tick_end_to_end_compaction(env, tmp_path, monkeypatch):
    t = env
    out = tmp_path / "tasks" / "e2e" / "out"
    out.mkdir(parents=True)
    base = out.parent
    (base / "prompt.md").write_text("p", encoding="utf-8")
    (out / "progress.md").write_text("\n".join(f"- 第{i}步" for i in range(500)) + "\n",
                                     encoding="utf-8")
    (out / "result.json").write_text(json.dumps(
        {"status": "done", "summary": "完成", "evidence": ["a:1"]}), encoding="utf-8")
    conn = t.db()
    conn.execute(
        "INSERT INTO tasks(id,name,kind,status,outdir,attempts,max_attempts,"
        "started_at,lease_until,created_at) "
        "VALUES(1,'e2e','generic','running',?,1,3,?,?,?)",
        (str(out), time.time() - 100, time.time() + 1000, time.time() - 100))
    # 基线：500 行
    t.archive_progress(conn, conn.execute("SELECT * FROM tasks WHERE id=1").fetchone())
    conn.commit()
    # 模型已全局重写为紧凑结构
    (out / "progress.md").write_text("# 紧凑\n" * 40, encoding="utf-8")
    t.cmd_tick(type("A", (), {"concurrency": 1, "quiet": True})())
    r = conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()
    assert r["status"] == "done"
    assert c_e(conn, 1, "compaction") == 1
    conn.close()
