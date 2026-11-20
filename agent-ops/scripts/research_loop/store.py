"""研究状态存储：SQLite 事务、事件流、摘要登记（方案 9.2/9.3）。"""
from __future__ import annotations

import json
import sqlite3
import pathlib

from .core_types import now_ts

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS experiments(
        experiment_id TEXT PRIMARY KEY, created_ts REAL NOT NULL,
        stage TEXT NOT NULL, objective_version TEXT NOT NULL,
        data_version TEXT NOT NULL, evaluator_digest TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS attempts(
        attempt_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
        stage TEXT NOT NULL, task_id TEXT,
        exec_status TEXT NOT NULL DEFAULT 'queued',
        evidence_status TEXT NOT NULL DEFAULT 'pending',
        trial_status TEXT NOT NULL DEFAULT 'untested',
        started_ts REAL, finished_ts REAL,
        inputs_digest TEXT, outputs_digest TEXT, result_path TEXT)""",
    """CREATE TABLE IF NOT EXISTS metrics(
        attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
        metric_id TEXT NOT NULL, value REAL, numerator REAL,
        denominator REAL, unknown_count INTEGER DEFAULT 0,
        lower_bound REAL, stat_method TEXT, stat_params TEXT,
        PRIMARY KEY(attempt_id, metric_id))""",
    """CREATE TABLE IF NOT EXISTS artifacts(
        artifact_id TEXT PRIMARY KEY,
        attempt_id TEXT REFERENCES attempts(attempt_id),
        role TEXT NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS decisions(
        decision_id TEXT PRIMARY KEY,
        attempt_id TEXT REFERENCES attempts(attempt_id),
        decision TEXT NOT NULL, reason TEXT, ts REAL NOT NULL,
        actor TEXT NOT NULL DEFAULT 'machine_gate')""",
    """CREATE TABLE IF NOT EXISTS ideas(
        idea_id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
        direction TEXT, source TEXT, prerequisites TEXT, falsify_plan TEXT,
        status TEXT NOT NULL DEFAULT 'queued',
        tries INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0,
        created_ts REAL NOT NULL, updated_ts REAL NOT NULL)""",
]


def open_db(db_path: str) -> sqlite3.Connection:
    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    for ddl in SCHEMA:
        conn.execute(ddl)
    conn.commit()
    return conn


def tx_ctx(conn: sqlite3.Connection):
    class _Tx:
        def __enter__(self):
            conn.execute("BEGIN IMMEDIATE")
            return conn
        def __exit__(self, et, ev, tb):
            if et is None:
                conn.commit()
            else:
                conn.rollback()
            return False
    return _Tx()


def append_event(conn: sqlite3.Connection, kind: str, data: dict) -> int:
    cur = conn.execute(
        "INSERT INTO events(ts, kind, data) VALUES(?,?,?)",
        (now_ts(), kind, json.dumps(data, ensure_ascii=False, sort_keys=True)))
    return cur.lastrowid


def replay_events(conn: sqlite3.Connection) -> list:
    """按序返回事件（审计链；权威是各表）。"""
    rows = conn.execute(
        "SELECT id, ts, kind, data FROM events ORDER BY id").fetchall()
    return [{"id": r["id"], "ts": r["ts"], "kind": r["kind"],
             "data": json.loads(r["data"])} for r in rows]
