"""派单适配层：outbox 幂等登记、taskctl 派单、崩溃对账、结果验收（方案 3.2/9.3/1.2）。"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from .core_types import EXEC_BLOCKED, EXEC_FAILED, EXEC_SUCCEEDED, now_ts, sha256_text
from .store import append_event, tx_ctx

DISPATCH_TIMEOUT = 60

OUTBOX_DDL = """CREATE TABLE IF NOT EXISTS outbox(
    outbox_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    task_id TEXT,
    dispatch_status TEXT NOT NULL DEFAULT 'pending',
    payload TEXT,
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL,
    UNIQUE(experiment_id, stage, attempt_id))"""

# dispatch_status 生命周期：pending(登记未派) → dispatching(已调 taskctl 未写回执)
# → dispatched(有 task_id)；taskctl 不可用 → blocked；崩溃窗口 → needs_reconcile。
_DISPATCHING = "dispatching"
_DISPATCHED = "dispatched"
_BLOCKED = "blocked"
_NEEDS_RECONCILE = "needs_reconcile"


def _ensure_outbox_table(db: sqlite3.Connection) -> None:
    db.execute(OUTBOX_DDL)


def ensure_outbox(db: sqlite3.Connection, experiment_id: str, stage: str,
                  attempt_id: str) -> str:
    """幂等键 experiment_id+stage+attempt_id；同键已登记返回现有 outbox_id。"""
    _ensure_outbox_table(db)
    existing = db.execute(
        "SELECT outbox_id FROM outbox WHERE experiment_id = ? AND stage = ?"
        " AND attempt_id = ?", (experiment_id, stage, attempt_id)).fetchone()
    if existing:
        return existing["outbox_id"]
    outbox_id = "obx-" + sha256_text(
        "%s|%s|%s" % (experiment_id, stage, attempt_id))[:16]
    ts = now_ts()
    with tx_ctx(db):
        db.execute(
            "INSERT INTO outbox(outbox_id, experiment_id, stage, attempt_id,"
            " task_id, dispatch_status, created_ts, updated_ts)"
            " VALUES(?,?,?,?,NULL,?,?,?)",
            (outbox_id, experiment_id, stage, attempt_id, "pending", ts, ts))
        append_event(db, "outbox_registered",
                     {"outbox_id": outbox_id, "experiment_id": experiment_id,
                      "stage": stage, "attempt_id": attempt_id})
    return outbox_id


def _parse_task_id(stdout: str):
    """解析 taskctl 回执：优先 JSON，回退 task-* 正则。"""
    text = (stdout or "").strip()
    if text:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                tid = data.get("task_id") or data.get("id")
                if tid:
                    return str(tid)
        except ValueError:
            pass
    m = re.search(r"task-[A-Za-z0-9_-]+", text)
    return m.group(0) if m else None


def _set_outbox(db: sqlite3.Connection, outbox_id: str, **fields) -> None:
    sets = ", ".join("%s = ?" % k for k in fields)
    args = list(fields.values()) + [now_ts(), outbox_id]
    db.execute("UPDATE outbox SET %s, updated_ts = ? WHERE outbox_id = ?" % sets,
               args)


def dispatch_attempt(taskctl_cli: str, db: sqlite3.Connection,
                     experiment_id: str, stage: str, attempt_id: str,
                     prompt_file: str, workdir: str, project: dict) -> dict:
    """派单：outbox 先登记，已有 task_id 直接复用不重派（崩溃对账）；
    taskctl 不可用/超时 → exec_status=blocked，不做失败重试。"""
    outbox_id = ensure_outbox(db, experiment_id, stage, attempt_id)
    row = db.execute("SELECT * FROM outbox WHERE outbox_id = ?",
                     (outbox_id,)).fetchone()
    if row["task_id"]:
        return {"exec_status": "dispatched", "task_id": row["task_id"],
                "outbox_id": outbox_id, "reused": True}
    if not taskctl_cli or not os.path.exists(taskctl_cli):
        with tx_ctx(db):
            _set_outbox(db, outbox_id, dispatch_status=_BLOCKED)
        return {"exec_status": EXEC_BLOCKED, "task_id": None,
                "outbox_id": outbox_id, "reason": "taskctl 不可用"}
    with tx_ctx(db):
        _set_outbox(db, outbox_id, dispatch_status=_DISPATCHING,
                    payload=json.dumps(
                        {"prompt_file": prompt_file, "workdir": workdir,
                         "project_id": (project or {}).get("project_id")},
                        ensure_ascii=False, sort_keys=True))
    argv = [sys.executable, taskctl_cli, "add",
            "--experiment-id", experiment_id, "--stage", stage,
            "--attempt-id", attempt_id, "--prompt-file", prompt_file,
            "--workdir", workdir]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=DISPATCH_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError) as e:
        with tx_ctx(db):
            _set_outbox(db, outbox_id, dispatch_status=_BLOCKED,
                        payload=str(e))
        return {"exec_status": EXEC_BLOCKED, "task_id": None,
                "outbox_id": outbox_id, "reason": "taskctl 调用失败: %s" % e}
    task_id = _parse_task_id(proc.stdout)
    if not task_id:
        with tx_ctx(db):
            _set_outbox(db, outbox_id, dispatch_status=_BLOCKED,
                        payload="回执无 task_id: %r" % proc.stdout[:200])
        return {"exec_status": EXEC_BLOCKED, "task_id": None,
                "outbox_id": outbox_id, "reason": "taskctl 回执无 task_id"}
    with tx_ctx(db):
        _set_outbox(db, outbox_id, task_id=task_id,
                    dispatch_status=_DISPATCHED)
        append_event(db, "attempt_dispatched",
                     {"outbox_id": outbox_id, "task_id": task_id,
                      "experiment_id": experiment_id, "stage": stage,
                      "attempt_id": attempt_id})
    return {"exec_status": "dispatched", "task_id": task_id,
            "outbox_id": outbox_id, "reused": False}


def reconcile(db, taskctl_cli: str) -> dict:
    """对账：dispatching/needs_reconcile 的行按幂等键回查 taskctl。

    查到 task_id → 回填 dispatched；确认不存在 → 允许重派（清 dispatching）。
    """
    reconciled, missing = 0, 0
    rows = db.execute(
        "SELECT * FROM outbox WHERE dispatch_status IN "
        "('dispatching', 'needs_reconcile')").fetchall()
    for row in rows:
        try:
            r = subprocess.run(
                [sys.executable, taskctl_cli, "list", "--json"],
                capture_output=True, text=True, timeout=60)
            tasks = json.loads(r.stdout or "[]")
            found = None
            for t in tasks if isinstance(tasks, list) else []:
                if str(t.get("goal") or "").find(row["attempt_id"]) >= 0:
                    found = t.get("task_id") or t.get("id")
                    break
            if found:
                db.execute("UPDATE outbox SET task_id=?, "
                           "dispatch_status='dispatched' WHERE outbox_id=?",
                           (str(found), row["outbox_id"]))
                reconciled += 1
            else:
                db.execute("UPDATE outbox SET dispatch_status='pending', "
                           "task_id=NULL WHERE outbox_id=?", (row["outbox_id"],))
                missing += 1
        except Exception:
            # 回查失败也要解锁行（不卡 dispatching）；下轮再试
            db.execute("UPDATE outbox SET dispatch_status='pending' "
                       "WHERE outbox_id=? AND dispatch_status='dispatching'",
                       (row["outbox_id"],))
            missing += 1
    return {"reconciled": reconciled, "missing": missing}


def check_execution_result(result_path: str) -> dict:
    """严格校验 result.json（方案 3.2 字段 + cases 逐条结构）。

    兼容 exec_status/execution_status 两种字段名；缺文件/坏 JSON/缺字段/
    cases 结构非法 → {valid: False, reason}。
    """
    p = Path(result_path)
    if not p.is_file():
        return {"valid": False, "reason": "missing"}
    try:
        result = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"valid": False, "reason": "malformed: %s" % str(e)[:100]}
    if not isinstance(result, dict):
        return {"valid": False, "reason": "not an object"}
    status = result.get("execution_status") or result.get("exec_status")
    for k in ("started_at", "finished_at", "cases"):
        if k not in result:
            return {"valid": False, "reason": "missing field: %s" % k}
    if status != "succeeded":
        return {"valid": False,
                "reason": "exec_status=%s 不允许进实验" % status}
    cases = result["cases"]
    if not isinstance(cases, list):
        return {"valid": False, "reason": "cases 必须是数组"}
    seen = set()
    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            return {"valid": False, "reason": "cases[%d] 不是对象" % i}
        cid = c.get("case_id")
        if not cid or not isinstance(cid, str):
            return {"valid": False, "reason": "cases[%d] 缺 case_id" % i}
        if cid in seen:
            return {"valid": False, "reason": "cases[%d] case_id 重复: %s"
                    % (i, cid)}
        seen.add(cid)
        for m in c.get("metrics", []) if isinstance(c.get("metrics"), list) else []:
            if not isinstance(m, dict) or "metric_id" not in m:
                return {"valid": False,
                        "reason": "cases[%s] metrics 结构非法" % cid}
    return {"valid": True, "case_count": len(cases)}


def run_stage_cmd(argv: list, cwd=None, timeout: int = 1800) -> dict:
    """阶段命令执行：argv 数组不拼 shell；超时转 failed + timeout 标记。"""
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv 必须是字符串数组（不拼 shell）")
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as e:
        return {"exec_status": EXEC_FAILED, "timeout": True, "argv": argv,
                "rc": None,
                "stdout": e.stdout if isinstance(e.stdout, str) else "",
                "stderr": e.stderr if isinstance(e.stderr, str) else ""}
    return {"exec_status": EXEC_SUCCEEDED if proc.returncode == 0 else EXEC_FAILED,
            "timeout": False, "rc": proc.returncode, "argv": argv,
            "stdout": proc.stdout, "stderr": proc.stderr}
