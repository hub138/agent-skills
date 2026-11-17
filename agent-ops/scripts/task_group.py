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
import re
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


def plan_head(home, gid: str, goal: str) -> None:
    """plan 拆解时先写组上下文头：全局目标一次装配，成员随后追加投影。"""
    d = group_dir(home, gid)
    d.mkdir(parents=True, exist_ok=True)
    ctx = d / "context.md"
    if not ctx.exists():
        ctx.write_text(f"# 组 {gid}\n\n## 全局目标\n{(goal or '')[:500]}\n\n"
                       "## 成员\n", encoding="utf-8")
        group_event(home, gid, "group_created", "plan",
                    {"goal": (goal or "")[:500]})


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


# 安静模式：这些状态视为「正常推进」，不值得打扰正在干活的队友
QUIET_STATUSES = {"running", "queued"}
PEER_MEMBER_CAP = 8
_MEM_RE = re.compile(r"^- `([^`]+)` \[([a-z_]+)\]")
DISCIPLINE_LINE = ("以上是感知信息，不是你的任务：除非收件箱有明确给你的消息，"
                   "否则继续专注当前工作，不要转向队友的工作。")


def peer_brief(home, gid: str, *, cap: int = 4000) -> str:
    """注入 prompt 的队友摘要：安静模式，防止感知稀释专注度。

    - 队友都在正常推进（running/queued）→ 只给一行，近乎零噪音；
    - 有状态变化（finished/blocked/failed/suspended）→ 只列变化的成员；
    - 尾部固定纪律行：感知不等于任务，不许主动转向队友的工作。
    全量投影仍在 groups/<gid>/peers.md，需要时随取，不占上下文。
    """
    fp = group_dir(home, gid) / "peers.md"
    if not fp.exists():
        return ""
    blocks, cur = [], None
    for l in fp.read_text(encoding="utf-8").splitlines():
        if l.startswith("- `"):
            if cur:
                blocks.append(cur)
            cur = [l]
        elif cur is not None and l.startswith("  "):
            cur.append(l)  # summary/outdir 续行归入同一成员块
    if cur:
        blocks.append(cur)
    if not blocks:
        return ""
    notable, busy = [], 0
    for b in blocks:
        m = _MEM_RE.match(b[0])
        if m and m.group(2) in QUIET_STATUSES:
            busy += 1
        else:
            notable.extend(b)
    lines = []
    if not notable:
        lines.append(f"队友 {len(blocks)} 人均在推进中，无需要你关注的变动。")
    else:
        lines.extend(notable[:PEER_MEMBER_CAP])
        rest = len(notable) - PEER_MEMBER_CAP
        if rest > 0:
            lines.append(f"- （另有 {rest} 名队友状态变化，全文见 peers.md）")
        if busy:
            lines.append(f"- 其余 {busy} 名队友推进中（不响应他们的进度）")
    lines.append(DISCIPLINE_LINE)
    return "\n".join(lines)[:cap]


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
