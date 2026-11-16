"""雷达台账：SQLite 是查询索引，Markdown 是给人和 git 的账本。

为什么这样分：数据库便于「这期还有几条没分析」「哪些借鉴已落地」这类查询，
但二进制文件无法 review、无法跨机器追溯。所以结论、证据、变更理由一律写进
radar/analyses|applied/*.md 并进 git；这里只存路径、结论、证据坐标。

提交纪律（借鉴 OpenClaw 的 design.md:125）：候选状态、分析/变更记录、审计事件
必须在同一个事务里提交；写不进去就整体回滚。审计不是事后补的日志。

解析两种简报格式：
  1. tech-radar 自动生成：`### 标题` + `- 核心：` / `- 创新点：` / `- 谁该看：` / `- 链接：`
  2. 人手工粘贴：`1. 标题` + `核心　...` / `创新　...` / `[原文](url)`
同一天可能有多期（实测 11:00 与 15:00 内容不同），用 slot 区分，靠内容 sha 去重。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

SKILL_ROOT = Path(__file__).resolve().parent.parent
RADAR_DIR = SKILL_ROOT / "radar"
SCHEMA_PATH = RADAR_DIR / "schema.sql"
DEFAULT_STATE = RADAR_DIR / "state"
LEDGER_PATH = RADAR_DIR / "LEDGER.md"

VERDICT_WORDS = ("adopt", "adapt", "skip")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def state_root() -> Path:
    return Path(os.environ.get("RADAR_HOME", str(DEFAULT_STATE))).expanduser()


def cache_root() -> Path:
    return Path(os.environ.get("RADAR_CACHE",
                               str(state_root() / "cache"))).expanduser()


def db_path() -> Path:
    return Path(os.environ.get("RADAR_DB",
                               str(state_root() / "radar.db"))).expanduser()


def connect(db: Path | None = None) -> sqlite3.Connection:
    path = Path(db) if db else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    # 只加列的轻量迁移：早期台账没有 slot 列。
    cols = {r[1] for r in conn.execute("PRAGMA table_info(briefs)")}
    if "slot" not in cols:
        conn.execute("ALTER TABLE briefs ADD COLUMN slot TEXT NOT NULL DEFAULT ''")
    conn.commit()


def rel(path: Path) -> str:
    """对外一律用相对 skill 根的路径，方便换机器后仍可定位。"""
    try:
        return str(Path(path).resolve().relative_to(SKILL_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------- 事务与审计

@contextmanager
def tx(conn: sqlite3.Connection):
    """显式事务：状态变更与审计事件必须一起提交。

    sqlite3 默认在第一次 DML 时隐式开事务，直接 `BEGIN IMMEDIATE` 会报
    "cannot start a transaction within a transaction"，所以先 commit 收尾再开写锁。
    """
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def _event_row(conn: sqlite3.Connection, kind: str, detail: dict,
               ts: str | None = None) -> str:
    """只写事件行，不提交、不落文件——由调用方放在同一个事务里。"""
    ts = ts or now_str()
    conn.execute("INSERT INTO events(ts, kind, detail) VALUES(?,?,?)",
                 (ts, kind, json.dumps(detail, ensure_ascii=False)))
    return ts


def _audit_file(ts: str, kind: str, detail: dict) -> None:
    """事务提交成功后追加审计流；best effort，失败不影响已提交的事实。"""
    log = state_root() / "audit.jsonl"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": ts, "kind": kind, "detail": detail},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass


def audit(conn: sqlite3.Connection, kind: str, detail: dict) -> None:
    ts = now_str()
    with tx(conn):
        _event_row(conn, kind, detail, ts)
    _audit_file(ts, kind, detail)


# ---------------------------------------------------------------- 简报解析

def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _kind(url: str, title: str) -> str:
    host = _host(url)
    if host.endswith("github.com") or host.endswith("gitlab.com"):
        return "repo"
    if host or url:
        return "article"
    if title.lower().startswith("github"):
        return "repo"
    return "other"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _strip_md(text: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    return _clean(text).strip("*` ")


def parse_brief(text: str) -> list[dict]:
    """解析简报正文，返回候选列表。两种格式都试，取解析出更多条的那次。"""
    blocks = _parse_hash_blocks(text)
    numbered = _parse_numbered_blocks(text)
    return blocks if len(blocks) >= len(numbered) else numbered


def _parse_hash_blocks(text: str) -> list[dict]:
    lines = text.splitlines()
    items: list[dict] = []
    cur: dict | None = None
    for raw in lines:
        line = raw.rstrip()
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m and not line.startswith("#### "):
            if cur:
                items.append(cur)
            cur = {"title": _strip_md(m.group(1)), "url": "", "core": "",
                   "innovation": "", "audience": ""}
            continue
        if cur is None:
            continue
        for key, label in (("core", "核心"), ("innovation", "创新点"),
                           ("audience", "谁该看")):
            mm = re.match(r"^[-*]\s*%s\s*[：:]\s*(.*)$" % label, line)
            if mm:
                cur[key] = _clean(mm.group(1))
        mm = re.match(r"^[-*]\s*(?:链接|原文)\s*[：:]\s*(\S+)", line)
        if mm:
            cur["url"] = mm.group(1)
    if cur:
        items.append(cur)
    return _finish(items)


def _parse_numbered_blocks(text: str) -> list[dict]:
    lines = text.splitlines()
    items: list[dict] = []
    cur: dict | None = None
    for raw in lines:
        line = raw.rstrip()
        m = re.match(r"^\s*(\d{1,3})[.、]\s+(.+?)\s*$", line)
        if m and not re.match(r"^\s*\d{1,3}[.、]\s*\[", line):
            if cur:
                items.append(cur)
            cur = {"title": _strip_md(m.group(2)), "url": "", "core": "",
                   "innovation": "", "audience": ""}
            continue
        if cur is None:
            continue
        for key, label in (("core", "核心"), ("innovation", "创新")):
            mm = re.match(r"^\s*%s[\s　]+(.+)$" % label, line)
            if mm:
                cur[key] = _clean(mm.group(1))
        mm = re.search(r"\[[^\]]*\]\((https?://[^)\s]+)\)", line)
        if mm and not cur["url"]:
            cur["url"] = mm.group(1)
        mm = re.match(r"^\s*(?:链接|原文)[\s　]*[：:]\s*(\S+)", line)
        if mm:
            cur["url"] = mm.group(1)
    if cur:
        items.append(cur)
    return _finish(items)


def _finish(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        title = _clean(it.get("title", ""))
        url = _clean(it.get("url", ""))
        if not title or title in ("查看完整简报",):
            continue
        it.update(seq=len(out) + 1, title=title, url=url, host=_host(url),
                  kind=_kind(url, title))
        out.append(it)
    return out


def ingest_brief(conn: sqlite3.Connection, text: str, *, brief_date: str,
                 slot: str = "", title: str = "", source: str = "",
                 source_path: str = "",
                 items: list[dict] | None = None) -> dict:
    items = items if items is not None else parse_brief(text)
    if not items:
        raise ValueError("没有解析出任何候选条目：请检查简报格式，"
                         "或用 intake --json-file 显式给出条目")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    title = title or next((l[2:].strip() for l in text.splitlines()
                           if l.startswith("# ")), "未命名简报")
    row = conn.execute(
        "SELECT id FROM briefs WHERE brief_date=? AND raw_sha256=?",
        (brief_date, sha)).fetchone()
    if row:
        return {"brief_id": row["id"], "inserted": 0, "duplicate": True,
                "item_count": len(items)}
    ts = now_str()
    detail = {"brief_id": 0, "date": brief_date, "items": len(items),
              "source": source, "slot": slot}
    try:
        with tx(conn):
            cur = conn.execute(
                "INSERT INTO briefs(brief_date,slot,title,source,source_path,"
                "raw_sha256,item_count,ingested_at) VALUES(?,?,?,?,?,?,?,?)",
                (brief_date, slot, _clean(title), source, source_path, sha,
                 len(items), ts))
            brief_id = int(cur.lastrowid)
            for it in items:
                conn.execute(
                    "INSERT INTO candidates(brief_id,seq,title,url,host,kind,"
                    "core,innovation,audience,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (brief_id, it["seq"], it["title"], it.get("url", ""),
                     it.get("host", ""), it.get("kind", "other"),
                     it.get("core", ""), it.get("innovation", ""),
                     it.get("audience", ""), ts, ts))
            detail["brief_id"] = brief_id
            _event_row(conn, "intake", detail, ts)
    except sqlite3.IntegrityError:
        # 并发下另一个进程刚插入同一期：按 duplicate 处理，不报错。
        row = conn.execute(
            "SELECT id FROM briefs WHERE brief_date=? AND raw_sha256=?",
            (brief_date, sha)).fetchone()
        return {"brief_id": row["id"] if row else 0, "inserted": 0,
                "duplicate": True, "item_count": len(items)}
    _audit_file(ts, "intake", detail)
    return {"brief_id": brief_id, "inserted": len(items), "duplicate": False,
            "item_count": len(items), "title": title}


# ---------------------------------------------------------------- 查询与写入

def list_candidates(conn: sqlite3.Connection, status: str | None = None,
                    brief: str | None = None) -> list[dict]:
    sql = ("SELECT c.*, b.brief_date FROM candidates c "
           "JOIN briefs b ON b.id=c.brief_id")
    where, args = [], []
    if status:
        where.append("c.status=?")
        args.append(status)
    if brief:
        where.append("b.brief_date=?")
        args.append(brief)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY b.brief_date DESC, c.seq"
    return [dict(r) for r in conn.execute(sql, args)]


def take_next(conn: sqlite3.Connection) -> dict | None:
    """原子领取一条待分析候选。两个 agent 同时跑也只会有一条被拿走。"""
    ts = now_str()
    row = None
    detail = None
    with tx(conn):
        row = conn.execute(
            "SELECT * FROM candidates WHERE status='new' ORDER BY id LIMIT 1"
        ).fetchone()
        if row:
            conn.execute("UPDATE candidates SET status='screened', updated_at=? "
                         "WHERE id=? AND status='new'", (ts, row["id"]))
            # 领取与领取证据同事务（OpenClaw postgres-work-queue.ts:62 的 claim+audit）：
            # 没有这条事件，事后无法回答「这条是谁在什么时候领走的」。
            detail = {"candidate_id": row["id"]}
            _event_row(conn, "claim", detail, ts)
    if detail:
        _audit_file(ts, "claim", detail)
    return dict(row) if row else None


def _set_status_row(conn: sqlite3.Connection, candidate_id: int, status: str,
                    *, relevance: int | None = None,
                    verdict: str | None = None, reason: str = "",
                    ts: str | None = None) -> None:
    """只更新行，不提交；供事务内部复用。"""
    conn.execute(
        "UPDATE candidates SET status=?, relevance=COALESCE(?,relevance), "
        "verdict=COALESCE(?,verdict), reason=?, updated_at=? WHERE id=?",
        (status, relevance, verdict, reason, ts or now_str(), candidate_id))


def set_status(conn: sqlite3.Connection, candidate_id: int, status: str,
               *, relevance: int | None = None, verdict: str | None = None,
               reason: str = "") -> None:
    with tx(conn):
        _set_status_row(conn, candidate_id, status, relevance=relevance,
                        verdict=verdict, reason=reason)


def record_analysis(conn: sqlite3.Connection, candidate_id: int, *,
                    report_path: str, verdict: str, mechanisms: list[str],
                    evidence: list[str], cost: str = "", risk: str = "",
                    relevance: int | None = None, reason: str = "") -> None:
    if verdict not in VERDICT_WORDS:
        raise ValueError("verdict 只能是 adopt/adapt/skip")
    ts = now_str()
    detail = {"candidate_id": candidate_id, "verdict": verdict,
              "report": report_path}
    # 分析、候选状态、审计事件一次提交：任何一步失败都整体回滚，
    # 不留下「报告已入账但候选仍是 new」这类自相矛盾的台账。
    with tx(conn):
        conn.execute(
            "INSERT INTO analyses(candidate_id,report_path,verdict,mechanisms,"
            "evidence,cost,risk,created_at) VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(candidate_id) DO UPDATE SET "
            "report_path=excluded.report_path,verdict=excluded.verdict,"
            "mechanisms=excluded.mechanisms,evidence=excluded.evidence,"
            "cost=excluded.cost,risk=excluded.risk",
            (candidate_id, report_path, verdict,
             json.dumps(mechanisms, ensure_ascii=False),
             json.dumps(evidence, ensure_ascii=False), cost, risk, ts))
        _set_status_row(conn, candidate_id, "analyzed", relevance=relevance,
                        verdict=verdict, reason=reason, ts=ts)
        _event_row(conn, "analysis", detail, ts)
    _audit_file(ts, "analysis", detail)


def record_change(conn: sqlite3.Connection, candidate_id: int, *,
                  files: list[str], summary: str, rationale: str,
                  diffstat: str = "", gate: dict | None = None,
                  commit_sha: str = "") -> None:
    ts = now_str()
    detail = {"candidate_id": candidate_id, "files": files,
              "commit": commit_sha}
    with tx(conn):
        conn.execute(
            "INSERT INTO changes(candidate_id,files,summary,rationale,diffstat,"
            "gate,commit_sha,applied_at) VALUES(?,?,?,?,?,?,?,?)",
            (candidate_id, json.dumps(files, ensure_ascii=False), summary,
             rationale, diffstat, json.dumps(gate or {}, ensure_ascii=False),
             commit_sha, ts))
        _set_status_row(conn, candidate_id, "applied", ts=ts)
        _event_row(conn, "applied", detail, ts)
    _audit_file(ts, "applied", detail)


def record_workspace(conn: sqlite3.Connection, candidate_id: int, *,
                     path: str, commit_sha: str, nbytes: int) -> None:
    ts = now_str()
    with tx(conn):
        conn.execute(
            "INSERT INTO workspaces(candidate_id,path,commit_sha,bytes,cloned_at,"
            "last_seen_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET candidate_id=excluded.candidate_id,"
            "commit_sha=excluded.commit_sha,bytes=excluded.bytes,"
            "last_seen_at=excluded.last_seen_at,cleaned_at=NULL",
            (candidate_id, path, commit_sha, nbytes, ts, ts))


def mark_cleaned(conn: sqlite3.Connection, paths: list[str]) -> None:
    ts = now_str()
    detail = {"paths": paths}
    with tx(conn):
        for p in paths:
            conn.execute("UPDATE workspaces SET cleaned_at=? WHERE path=?",
                         (ts, p))
        _event_row(conn, "clean", detail, ts)
    _audit_file(ts, "clean", detail)


# ---------------------------------------------------------------- 渲染台账

def _fmt_verdict(v: str | None) -> str:
    return {"adopt": "采纳", "adapt": "改造", "skip": "不抄",
            None: "待判"}.get(v, v or "待判")


def stats(conn: sqlite3.Connection) -> dict:
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    ws_bytes = one("SELECT COALESCE(SUM(bytes),0) FROM workspaces "
                   "WHERE cleaned_at IS NULL")
    return {
        "briefs": one("SELECT COUNT(*) FROM briefs"),
        "candidates": one("SELECT COUNT(*) FROM candidates"),
        "new": one("SELECT COUNT(*) FROM candidates WHERE status='new'"),
        "analyzed": one("SELECT COUNT(*) FROM analyses"),
        "adopt": one("SELECT COUNT(*) FROM candidates WHERE verdict='adopt'"),
        "adapt": one("SELECT COUNT(*) FROM candidates WHERE verdict='adapt'"),
        "skip": one("SELECT COUNT(*) FROM candidates WHERE verdict='skip'"),
        "applied": one("SELECT COUNT(*) FROM changes"),
        "workspace_bytes": ws_bytes,
        "workspace_mb": round(ws_bytes / 1048576, 1),
    }


def render_ledger(conn: sqlite3.Connection, out: Path = LEDGER_PATH) -> str:
    s = stats(conn)
    lines = [
        "# 技术雷达借鉴台账",
        "",
        "> 自动生成，请勿手改：数据在 `radar/state/radar.db`，",
        "> 审计流在 `radar/state/audit.jsonl`，正文在 `radar/intake|analyses|applied/`。",
        "> 重新渲染：`python3 scripts/radar_cli.py ledger`",
        "",
        "## 汇总",
        "",
        "| 期数 | 候选 | 待分析 | 已分析 | 采纳 | 改造 | 不抄 | 已落地变更 | 缓存占用 |",
        "|---|---|---|---|---|---|---|---|---|",
        "| %(briefs)d | %(candidates)d | %(new)d | %(analyzed)d | "
        "%(adopt)d | %(adapt)d | %(skip)d | %(applied)d | %(workspace_mb)s MB |" % s,
        "",
    ]
    briefs = [dict(r) for r in conn.execute(
        "SELECT * FROM briefs ORDER BY brief_date DESC, id DESC")]
    for b in briefs:
        rows = [dict(r) for r in conn.execute(
            "SELECT c.*, a.report_path FROM candidates c "
            "LEFT JOIN analyses a ON a.candidate_id=c.id "
            "WHERE c.brief_id=? ORDER BY c.seq", (b["id"],))]
        head = "%s %s" % (b["brief_date"], b["title"])
        if b.get("slot"):
            head += "（%s 批次）" % b["slot"]
        lines += ["## %s" % head, "",
                  "来源：%s%s；候选 %d 条。" %
                  (b["source"] or "未标注",
                   "（%s）" % b["source_path"] if b["source_path"] else "",
                   len(rows)), "",
                  "| # | 条目 | 类型 | 相关 | 结论 | 理由 / 报告 |",
                  "|---|---|---|---|---|---|"]
        for r in rows:
            link = "`%s`" % r["report_path"] if r["report_path"] else ""
            reason = (r["reason"] or "").replace("|", "\\|")
            if len(reason) > 80:
                reason = reason[:77] + "..."
            lines.append("| %d | [%s](%s) | %s | %s | %s | %s |" % (
                r["seq"], r["title"].replace("|", "\\|"), r["url"] or "#",
                r["kind"], r["relevance"] if r["relevance"] is not None else "-",
                _fmt_verdict(r["verdict"]),
                " ".join(x for x in (reason, link) if x) or "-"))
        changes = [dict(r) for r in conn.execute(
            "SELECT ch.*, c.title FROM changes ch JOIN candidates c "
            "ON c.id=ch.candidate_id JOIN briefs b2 ON b2.id=c.brief_id "
            "WHERE b2.id=? ORDER BY ch.id", (b["id"],))]
        if changes:
            lines += ["", "**已落地变更**", ""]
            for ch in changes:
                files = ", ".join(json.loads(ch["files"]))
                lines.append("- `%s` ← %s（%s）%s" % (
                    ch["commit_sha"] or "未提交", ch["title"], files,
                    "：" + ch["summary"]))
        lines.append("")
    text = "\n".join(lines) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


def recent_events(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]


def clean_candidates(conn: sqlite3.Connection, days: int) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    return [dict(r) for r in conn.execute(
        "SELECT * FROM workspaces WHERE cleaned_at IS NULL AND last_seen_at < ? "
        "ORDER BY last_seen_at", (cutoff,))]
