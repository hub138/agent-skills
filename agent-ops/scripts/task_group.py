"""任务组：同一次 plan 拆出的任务互相感知与通讯（文件即协议，零依赖）。

三条通道（对应用户场景：双 AI 协作，实现 AI 与调研 AI 互相反馈）：
  感知 = groups/<gid>/peers.md（事件驱动刷新；spawn 时注入 prompt）
  通讯 = 任务 outdir/inbox.md（taskctl send 追加；下一轮 prompt 注入；偏移量防重放）
  留痕 = groups/<gid>/events.jsonl（schema 对齐 foundation.events.Event：ts/kind/source/payload）

单写者纪律：inbox.md 只由 send() 追加（append-only，不截断，偏移量防重放）；
events.jsonl 只由 group_event() 追加；peers.md 只由 refresh_peers() 原子覆盖
（它是派生视图）。消息幂等：同一 (from,message) 的 sha 已在组事件里则拒绝，
--force 才允许重发——foundation.idempotency 的语义，本地实现（无库依赖）。
idle 口径与 taskctl.last_activity 同源（session jsonl > progress > result > runlog）。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

# 状态变化类事件：触发 peers 刷新（taskctl.event 的 hook 用）
REFRESH_KINDS = {"finished_by_result", "bad_result_requeue", "queued",
                 "lease_expired_requeue", "lease_expired_final",
                 "inbox_message", "added", "need_supervision", "requeued",
                 "suspended", "resumed"}


def group_dir(home, gid: str) -> Path:
    return Path(home) / "groups" / gid


def group_event(home, gid: str, kind: str, source: str,
                payload: dict) -> dict:
    d = group_dir(home, gid)
    d.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind,
           "source": source, "payload": payload}
    with (d / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def message_sha(source: str, message: str) -> str:
    return hashlib.sha256(f"{source}\n{message}".encode("utf-8")).hexdigest()[:16]


def _sent_shas(home, gid: str) -> set[str]:
    p = group_dir(home, gid) / "events.jsonl"
    if not p.exists():
        return set()
    shas = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # 行容错：半行不影响其余
        pay = rec.get("payload") or {}
        if rec.get("kind") == "message_sent" and pay.get("sha"):
            shas.add(pay["sha"])
    return shas


def register_member(home, gid: str, name: str, kind: str, goal: str) -> None:
    d = group_dir(home, gid)
    d.mkdir(parents=True, exist_ok=True)
    ctx = d / "context.md"
    if not ctx.exists():
        ctx.write_text(f"# 组 {gid}\n\n## 成员\n", encoding="utf-8")
    text = ctx.read_text(encoding="utf-8")
    if f"`{name}`" not in text:
        with ctx.open("a", encoding="utf-8") as fh:
            fh.write(f"- `{name}`（{kind}）：{(goal or '')[:200]}\n")
    group_event(home, gid, "member_added", name, {"goal": (goal or "")[:200]})


def _idle_seconds(task_row) -> int:
    """与 taskctl.last_activity 同源口径的简化版（session jsonl 之外的三类）。"""
    outdir = Path(task_row["outdir"])
    candidates = []
    for f in (outdir / "progress.md", outdir / "result.json",
              outdir.parent / "run.log"):
        if f.exists():
            candidates.append(f.stat().st_mtime)
    if candidates:
        return int(time.time() - max(candidates))
    started = float(task_row["started_at"] or 0)
    return int(time.time() - started) if started else -1


def refresh_peers(conn, home, gid: str) -> int:
    rows = conn.execute(
        "SELECT * FROM tasks WHERE group_id=? ORDER BY id", (gid,)).fetchall()
    if not rows:
        return 0
    lines = ["# 组内成员快照（tick/事件自动刷新，勿手改）", ""]
    for t in rows:
        summary = ""
        if t["result_json"]:
            try:
                summary = str(json.loads(t["result_json"]).get("summary", ""))[:120]
            except json.JSONDecodeError:
                summary = ""
        lines.append(f"- `{t['name']}` [{t['status']}] "
                     f"attempts={t['attempts']} idle={_idle_seconds(t)}s")
        if summary:
            lines.append(f"  summary: {summary}")
        lines.append(f"  outdir: {t['outdir']}")
    d = group_dir(home, gid)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "peers.md.tmp"
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(d / "peers.md")
    return len(rows)


def send(conn, home, to_name: str, from_name: str, message: str,
         force: bool = False) -> dict:
    """给队友发消息：append 到对方 inbox + 组事件留痕 + 刷新 peers。

    同一 (from, message) 已发过且未 force → duplicate=True 不重复投递。
    """
    to = conn.execute("SELECT * FROM tasks WHERE name=?",
                      (to_name,)).fetchone()
    if not to:
        raise ValueError(f"目标任务 {to_name} 不存在")
    gid = to["group_id"] or ""
    sha = message_sha(from_name, message)
    if gid and sha in _sent_shas(home, gid) and not force:
        return {"sent": False, "duplicate": True, "sha": sha,
                "to": to_name, "to_id": to["id"], "gid": gid}
    outdir = Path(to["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with (outdir / "inbox.md").open("a", encoding="utf-8") as fh:
        fh.write(f"- [{ts}][from={from_name}] {message.strip()}\n")
    if gid:
        group_event(home, gid, "message_sent", from_name,
                    {"to": to_name, "sha": sha, "bytes": len(message)})
        refresh_peers(conn, home, gid)
    return {"sent": True, "duplicate": False, "sha": sha, "to": to_name,
            "to_id": to["id"], "gid": gid, "bytes": len(message)}


def pending_inbox(outdir) -> str:
    """返回 inbox.md 中尚未消费的新内容；消费后调 mark_consumed。"""
    outdir = Path(outdir)
    inbox = outdir / "inbox.md"
    if not inbox.exists():
        return ""
    data = inbox.read_bytes()
    off_file = outdir / ".inbox_offset"
    try:
        off = int(off_file.read_text(encoding="utf-8")) if off_file.exists() else 0
    except (OSError, ValueError):
        off = 0
    if len(data) <= off:
        return ""
    return data[off:].decode("utf-8", "replace")


def mark_consumed(outdir) -> None:
    outdir = Path(outdir)
    inbox = outdir / "inbox.md"
    size = inbox.stat().st_size if inbox.exists() else 0
    (outdir / ".inbox_offset").write_text(str(size), encoding="utf-8")


def group_status(conn, gid: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT name,status,attempts,priority,outdir,error FROM tasks "
        "WHERE group_id=? ORDER BY id", (gid,))]
