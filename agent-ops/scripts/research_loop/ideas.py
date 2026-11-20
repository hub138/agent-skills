"""研究创意池：登记、状态流转、结果记账与选向（方案 3.2/6.1/6.3）。"""
from __future__ import annotations

import json
import sqlite3

from .core_types import KINDS, now_ts, sha256_text
from .store import append_event, tx_ctx


def _as_text(value) -> str:
    """list/dict 序列化为 JSON 文本，其余转 str。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

# 创意状态（方案 6.1）
IDEA_QUEUED = "queued"; IDEA_TESTING = "testing"; IDEA_WON = "won"
IDEA_RETIRED = "retired"; IDEA_PAUSED = "paused"
IDEA_STATUSES = {IDEA_QUEUED, IDEA_TESTING, IDEA_WON, IDEA_RETIRED, IDEA_PAUSED}

# 未尝试探索加成：让零尝试的创意优先于已有战绩的创意（探索优先，方案 6.3）
EXPLORE_BONUS = 1.0
# 连续无收益方向降权（方案 6.3 stall_dirs）：必须压过探索加成，让 stall 方向沉底
STALL_PENALTY = 2.0


def _fingerprint(title: str, direction) -> str:
    return sha256_text("%s|%s" % (title, "" if direction is None else direction))


def add_idea(db: sqlite3.Connection, title: str, kind: str, direction,
             source: str, prerequisites, falsify_plan,
             idea_id: str = None) -> str:
    """登记创意；指纹（title+direction）去重，已存在返回现有 idea_id。"""
    if kind not in KINDS:
        raise ValueError("kind 必须是 %s，收到 %r" % (sorted(KINDS), kind))
    existing = db.execute(
        "SELECT idea_id FROM ideas WHERE title = ? AND direction IS ?",
        (title, direction)).fetchone()
    if existing:
        return existing["idea_id"]
    if not idea_id:
        idea_id = "idea-" + _fingerprint(title, direction)[:12]
        n = 2
        while db.execute("SELECT 1 FROM ideas WHERE idea_id = ?",
                         (idea_id,)).fetchone():
            idea_id = "idea-" + _fingerprint(title, direction)[:12] + "-%d" % n
            n += 1
    ts = now_ts()
    with tx_ctx(db):
        db.execute(
            "INSERT INTO ideas(idea_id, title, kind, direction, source,"
            " prerequisites, falsify_plan, status, tries, wins,"
            " created_ts, updated_ts) VALUES(?,?,?,?,?,?,?,?,0,0,?,?)",
            (idea_id, title, kind, direction, source,
             _as_text(prerequisites), _as_text(falsify_plan),
             IDEA_QUEUED, ts, ts))
        append_event(db, "idea_added", {"idea_id": idea_id, "title": title,
                                        "kind": kind, "direction": direction})
    return idea_id


def update_idea_status(db: sqlite3.Connection, idea_id: str, status: str) -> None:
    if status not in IDEA_STATUSES:
        raise ValueError("status 必须是 %s，收到 %r" % (sorted(IDEA_STATUSES), status))
    with tx_ctx(db):
        cur = db.execute(
            "UPDATE ideas SET status = ?, updated_ts = ? WHERE idea_id = ?",
            (status, now_ts(), idea_id))
        if cur.rowcount == 0:
            raise ValueError("idea 不存在: %s" % idea_id)
        append_event(db, "idea_status", {"idea_id": idea_id, "status": status})


def record_outcome(db: sqlite3.Connection, idea_id: str, win: bool,
                   experiment_id: str) -> None:
    """记账一次实验结果：tries+1；win 则 wins+1 并标 won。"""
    with tx_ctx(db):
        row = db.execute("SELECT status FROM ideas WHERE idea_id = ?",
                         (idea_id,)).fetchone()
        if not row:
            raise ValueError("idea 不存在: %s" % idea_id)
        if win:
            db.execute(
                "UPDATE ideas SET tries = tries + 1, wins = wins + 1,"
                " status = ?, updated_ts = ? WHERE idea_id = ?",
                (IDEA_WON, now_ts(), idea_id))
        else:
            db.execute(
                "UPDATE ideas SET tries = tries + 1, updated_ts = ?"
                " WHERE idea_id = ?", (now_ts(), idea_id))
        append_event(db, "idea_outcome", {"idea_id": idea_id, "win": bool(win),
                                          "experiment_id": experiment_id})


def _score(row: sqlite3.Row, stall_dirs) -> float:
    """期望收益 = wins/(tries+1)；零尝试探索加成；stall 方向降权。确定性。"""
    score = row["wins"] / (row["tries"] + 1)
    if row["tries"] == 0:
        score += EXPLORE_BONUS
    if stall_dirs and row["direction"] in stall_dirs:
        score -= STALL_PENALTY
    return score


def next_ideas(db: sqlite3.Connection, limit: int = 3,
               stall_dirs: list = None) -> list:
    """选向：queued 优先，retired 不出，stall_dirs 降权，确定性排序。"""
    rows = db.execute(
        "SELECT * FROM ideas WHERE status != ? ORDER BY idea_id",
        (IDEA_RETIRED,)).fetchall()
    ranked = sorted(rows, key=lambda r: (
        0 if r["status"] == IDEA_QUEUED else 1,
        -_score(r, stall_dirs or []),
        r["idea_id"]))
    return [{"idea_id": r["idea_id"], "title": r["title"], "kind": r["kind"],
             "tries": r["tries"], "wins": r["wins"]}
            for r in ranked[:max(0, limit)]]
