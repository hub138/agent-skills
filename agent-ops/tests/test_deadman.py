#!/usr/bin/env python3
"""死士检查通用件回归测试。

运行：python3 -m pytest tests/test_deadman.py -q
全部用 sqlite 内存库 + 临时文件，不碰真实 DB、不发真实通知。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
import deadman as D  # noqa: E402


@pytest.fixture()
def sqldb(tmp_path):
    import sqlite3
    p = tmp_path / "t.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, updated_at TEXT, ok INTEGER)")
    conn.commit()
    yield {"kind": "sqlite", "path": str(p)}, conn
    conn.close()


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# ── db_freshness：新鲜 / 超龄 / gate 放行 / 演练模式 ───────────────────
def test_db_freshness(sqldb, tmp_path):
    cfg, conn = sqldb
    now = datetime.now()
    dbs = {"m": D.DB(cfg)}

    conn.execute("INSERT INTO t(updated_at) VALUES(?)", (ts(now - timedelta(hours=1)),))
    conn.commit()
    c = {"type": "db_freshness", "name": "心跳", "db": "m",
         "freshness_sql": "SELECT MAX(updated_at) FROM t", "max_age_hours": 6}
    r = D.check_db_freshness(c, now, dbs, {})[0]
    assert r["ok"] is True

    conn.execute("UPDATE t SET updated_at=?", (ts(now - timedelta(hours=20)),))
    conn.commit()
    r = D.check_db_freshness(c, now, dbs, {})[0]
    assert r["ok"] is False and "20" in r["evidence"] or "阈值" in r["evidence"]

    # gate=可判定队列>0 才报异常；gate=0 → 视为正常空闲（防「没输入≠停摆」误报）
    c2 = dict(c, gate_sql="SELECT COUNT(*) FROM t WHERE ok=1", gate_min=1)
    r = D.check_db_freshness(c2, now, dbs, {})[0]
    assert r["ok"] is True  # ok=1 的行 0 条 → gate=0 → 不报

    # 演练模式：阈值 0 强制报
    c3 = dict(c, max_age_hours=0)
    r = D.check_db_freshness(c3, now, dbs, {})[0]
    assert r["ok"] is False
    dbs["m"].close()


# ── queue_stall：有输入无产出才停摆 ───────────────────────────────────
def test_queue_stall(sqldb):
    cfg, conn = sqldb
    now = datetime.now()
    dbs = {"m": D.DB(cfg)}
    c = {"type": "queue_stall", "name": "队列", "db": "m",
         "pending_sql": "SELECT COUNT(*) FROM t WHERE ok IS NULL",
         "judged_sql": "SELECT COUNT(*) FROM t WHERE ok IS NOT NULL AND updated_at >= ?",
         "window_hours": 12}
    # 有 pending、窗口内无判定 → 停摆
    conn.execute("INSERT INTO t(updated_at,ok) VALUES(?,NULL)", (ts(now - timedelta(hours=2)),))
    conn.commit()
    assert D.check_queue_stall(c, now, dbs, {})[0]["ok"] is False
    # 窗口内有判定 → 正常
    conn.execute("INSERT INTO t(updated_at,ok) VALUES(?,1)", (ts(now - timedelta(hours=1)),))
    conn.commit()
    assert D.check_queue_stall(c, now, dbs, {})[0]["ok"] is True
    # 无 pending（没输入）→ 正常，不误报
    conn.execute("DELETE FROM t WHERE ok IS NULL")
    conn.commit()
    assert D.check_queue_stall(c, now, dbs, {})[0]["ok"] is True
    dbs["m"].close()


# ── log_freshness：超龄 + 进程存活才判空转 ────────────────────────────
def test_log_freshness(tmp_path):
    now = datetime.now()
    log = tmp_path / "app.log"
    log.write_text("x", encoding="utf-8")
    old = time.time() - 10 * 3600
    os.utime(log, (old, old))
    c = {"type": "log_freshness", "name": "日志", "glob": str(tmp_path / "*.log"),
         "max_age_hours": 2, "require_process": "definitely-not-running-xyz-proc"}
    # 进程不存在 → 只判进程异常路径？此处 require_process 只用于"进程活但日志停"判空转
    r = D.check_log_freshness(c, now, {}, {})[0]
    # 进程不活 → 不判空转（进程死了是 process_alive 的职责）
    assert r["ok"] is True
    # 用当前 python 进程当"存活进程"
    c2 = dict(c, require_process="python")
    r = D.check_log_freshness(c2, now, {}, {})[0]
    assert r["ok"] is False and "空转" in r["name"]


# ── notify_silence：有记录/无记录/超龄 ────────────────────────────────
def test_notify_silence(tmp_path):
    now = datetime.now()
    nl = tmp_path / "notify_send.log"
    c = {"type": "notify_silence", "name": "通知", "notify_log": str(nl),
         "max_age_hours": 48}
    # 无记录
    r = D.check_notify_silence(c, now, {}, {})[0]
    assert r["ok"] is False and "无发送记录" in r["name"]
    # 新鲜记录
    nl.write_text(f"{ts(now - timedelta(hours=1))} | sent | 通知发送成功\n", encoding="utf-8")
    r = D.check_notify_silence(c, now, {}, {})[0]
    assert r["ok"] is True
    # 超龄记录
    nl.write_text(f"{ts(now - timedelta(hours=100))} | sent | 通知发送成功\n", encoding="utf-8")
    r = D.check_notify_silence(c, now, {}, {})[0]
    assert r["ok"] is False and "长时间无通知" in r["name"]


# ── notify：stdin 零转义管道 ──────────────────────────────────────────
def test_notify_stdin():
    cfg = {"notify_cmd": "cat"}
    out = D.notify(cfg, "中文内容【告警】test")
    assert "RC=0" in out
    assert "中文内容【告警】test" in out  # cat 原样回显，证明零转义


# ── run_checks：单项失败不拖垮整轮 ────────────────────────────────────
def test_run_checks_isolation(tmp_path):
    cfg = {
        "databases": {"m": {"kind": "sqlite", "path": str(tmp_path / "x.db")}},
        "checks": [
            {"type": "db_freshness", "name": "会炸的", "db": "m",
             "freshness_sql": "SELECT * FROM 不存在的表", "max_age_hours": 6},
            {"type": "process_alive", "name": "进程", "pattern": "python"},
        ],
    }
    r = D.run_checks(cfg)
    names = {a["name"] for a in r["anomalies"]}
    assert any("会炸的" in n for n in names)          # 第一项炸 → 记异常
    assert any("进程" in n for n in r["normals"])  # 第二项照常执行


# ── render / main：演练模式标注 ───────────────────────────────────────
def test_render_and_main(tmp_path, capsys):
    result = {"now": datetime.now(),
              "anomalies": [{"name": "X", "evidence": "e", "duration": "1 小时"}],
              "normals": ["Y：ok"]}
    text = D.render(result)
    assert "1 项异常" in text and "X" in text and "Y：ok" in text

    cfg = {"notify_cmd": "cat", "log_file": str(tmp_path / "d.log"),
           "checks": [{"type": "db_freshness", "name": "a", "db": "m",
                       "freshness_sql": "SELECT 1", "max_age_hours": 0}],
           "databases": {"m": {"kind": "sqlite", "path": ":memory:"}}}
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    # sqlite :memory: 每次连接独立，SELECT 1 标量恒真 → 无 MAX 行 → age None → 演练报异常
    rc = D.main(["--config", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "异常" in out
