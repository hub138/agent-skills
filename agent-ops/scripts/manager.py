#!/usr/bin/env python3
"""管理者：任务主人的化身（2026-11-13 由"监督者"升级）。

主人发起任务时并不确定多复杂、要多久；管理者让这件事被持续做好：
读全部进度与改动 → 纠正/判断/推进 → 可微调目标（refine）→ 全部决策留痕可追溯。
定时(1800s)/事件(120s 无增长或 error) 触发；每任务独立调用（并发 2 路）。

设计来源（原 watchdog（旧版） skill，2026-11-12 用户纠正后恢复）：
  watchdog.sh 的做法是 `--resume <sid>` + 一条固定提示词，
  **由模型读进度、自己判断从哪继续**，脚本只管「什么时候拉起」。
  我一度把它换成纯脚本 mtime 判活，丢掉了最关键的灵活性：
  脚本不会应对「进度文件在涨但内容全是重复报错」「该换方向」
  「该追加一条指令」这类情况。

这里的分工：
  脚本：收集状态快照、决定何时该问、执行模型给出的结构化决策、防呆
  模型：读快照 → 判断每个任务是正常/卡住/该改方向/该重来/需人看
  人  ：只读 stats / brief，只有 escalate 才需要介入

输出契约（监督者只输出 JSON 数组，不写别的）：
  [{"task":"名字","action":"continue|nudge|restart|escalate|finish",
    "reason":"≤80字","guidance":"给被监督 agent 的指令（nudge/restart 用）"}]

用法：
  python3 supervisor.py once          # 跑一次（cron / daemon 调）
  python3 supervisor.py daemon        # 常驻，每 --interval 秒一次
  python3 supervisor.py snapshot      # 只看快照，不调模型（调试）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taskctl as T  # noqa: E402  复用 SQLite 与任务目录约定

CB_BIN = os.environ.get("CODEBUDDY_CLI_BIN", "/usr/local/bin/codebuddy")
# 用户 2026-11-12 最终口径：监督者默认 free-model（codebuddy 侧写 free-model），不再用偏弱的 small-model。
# 要换模型设 SUPERVISOR_MODEL 即可（如 SUPERVISOR_MODEL=small-model）。
SUPERVISOR_MODEL = os.environ.get("SUPERVISOR_MODEL", "free-model")
# 管理者读 progress 全文，上下文比旧监督者大，180s 实测不够（2026-11-13）
# 实测：管理者读全文+refine 人设下单次调用可达 ~420s（2026-11-13 通道慢时段）
SUPERVISOR_TIMEOUT = int(os.environ.get("SUPERVISOR_TIMEOUT", "420"))
INTERVAL = int(os.environ.get("SUPERVISOR_INTERVAL", "300"))
# 低于这个 idle 不打扰监督者，避免频繁调用烧额度
MIN_IDLE_TO_ASK = int(os.environ.get("SUPERVISOR_MIN_IDLE", "120"))
# 监督调用并发：与 worker 同语义（每模型 2 路），排队不超发
SUPERVISOR_CONCURRENCY = int(os.environ.get("SUPERVISOR_CONCURRENCY", "2"))
# 即使没有异常，也每这么久问一次（定时监督，对齐原 watchdog）
FORCE_ASK_EVERY = int(os.environ.get("SUPERVISOR_FORCE_EVERY", "1800"))
LAST_ASK_FILE = Path(os.environ.get(
    "SUPERVISOR_LAST_ASK", "/tmp/taskctl_supervisor_last_ask.json"))

PROMPT = """你是多 agent 任务队列的**监督者**。下面是从数据库和文件里取出的状态快照，
不是让你去执行任务，而是让你判断每个任务现在该不该干预。

判断要点：
- 「正常」：进度在增长、或进程刚启动、或模型正在 reasoning（此时文件不动是正常的）
- 「卡住」：文件长时间无增长且没有合理解释，或进度里反复出现同一条报错
- 「该改方向」：进度显示它走错了、反复重试同一失败动作、或输出契约一直不合格
- 「需人看」：重试耗尽、缺输入、需要人做决策
- 「已完成」：result.json 有效但状态还没收尾
- 「需要压缩」：needs_compaction=True（progress 超行数上限）且模型一直只追加不重写
  → nudge：先读 progress 全文做全局重写（保留所有关键决策/未完成项/下一步），重写前先归档原文

对每个任务给一个动作，`task` 字段**必须原样填快照里的 `task_name:` 值**（纯名字，
不要带 #id、类型或任何装饰）。只输出 JSON 数组，不要解释、不要 markdown 围栏：
[{"task":"名字","action":"continue|nudge|restart|escalate|finish",
  "reason":"≤80字","guidance":"给被监督 agent 的一句话指令（nudge/restart 时必填）"}]

动作含义：
- continue : 正常，什么都不做
- nudge    : 还在跑，但把 guidance 写进任务目录，供下次重排/续接时注入提示词
- restart  : 杀掉当前进程并重排，guidance 会写进下一轮提示词
- escalate : 标为需人工，写清 reason
- finish   : 按已有产出收尾

重要约束：
- 拿不准就 continue，**不要随意 restart**；误杀正在干活的长任务比晚发现更糟。
- reason 必须基于快照里的事实，不要编造。
- 不同任务可以给不同动作，不要一刀切。

=== 状态快照 ===
{snapshot}
"""


def _tail(path: Path, n: int = 6, width: int = 160) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return [x[:width] for x in lines[-n:]]
    except Exception:
        return []


def _session_tail(sid: str, n: int = 3) -> list[str]:
    """会话 jsonl 是边跑边写的，取最后几条事件的类型+文本摘要。"""
    if not sid:
        return []
    out: list[str] = []
    for p in sorted(T.CB_PROJECTS.glob(f"*/{sid}.jsonl"),
                    key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
        for ln in _tail(p, n=n * 2, width=400):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            kind = r.get("type") or r.get("role") or "?"
            c = r.get("content")
            txt = ""
            if isinstance(c, list):
                txt = " ".join(str(x.get("text", ""))[:70]
                               for x in c if isinstance(x, dict))
            out.append(f"{kind}:{txt[:80]}")
    return out[-n:]


MANAGER_PROMPT_SINGLE = """你是任务「{name}」的**管理者**——任务主人的化身。
主人发起任务时并不确定它有多复杂、要多久；你的职责是让这件事被**持续做好**：
理解目标、读全部进度与改动、纠正方向、判断推进、允许加深加强优化改进修复，
甚至可以**微调任务目标**（refine）——目标服务于价值，不是死的条文。

判断要点：
- 「正常」：进度在增长、或刚启动、或模型正在 reasoning（文件不动是正常的）
- 「卡住」：文件长时间无增长且没有合理解释，或反复出现同一条报错
- 「该改方向」：走错了、反复重试同一失败动作、或输出契约一直不合格
- 「需人看」：重试耗尽、缺输入、需要主人决策
- 「已完成」：result.json 有效但状态还没收尾
- 「需要压缩」：needs_compaction=True 且一直只追加不重写
  → nudge：先读 progress 全文做全局重写，重写前把原文复制到 progress-archive/
- 「目标该调」：进展揭示了原目标的部分内容已无价值、或发现了更值得做的方向
  → refine：给出调整后的完整目标（new_goal），旧目标会自动归档留痕

只输出一个 JSON 对象，不要数组、不要解释、不要 markdown 围栏：
{"action":"continue|nudge|restart|escalate|finish|refine",
 "reason":"≤80字","guidance":"给 worker 的一句话指令（nudge/restart/refine 时必填）",
 "new_goal":"refine 时的完整新目标文本（其余动作填 null）"}

动作含义：
- continue : 正常，什么都不做
- nudge    : 把 guidance 写进任务目录，供下次重排/续接时注入提示词
- restart  : 杀掉当前进程并重排，guidance 会写进下一轮提示词
- escalate : 标为需人工（主人），写清 reason
- finish   : 按已有产出收尾
- refine   : 微调/重写任务目标；旧目标自动归档到 goal-archive/，全程留痕

重要约束：
- 拿不准就 continue，**不要随意 restart**；误杀正在干活的长任务比晚发现更糟。
- reason 必须基于快照事实，不要编造；refine 必须保留原目标中仍然有效的部分。
- 全局摘要仅供判断"是不是系统性问题"，你的决策只针对目标任务。
- 所有决策（含 continue）都会被记录到 decisions.jsonl，主人和任何 AI 都可追溯。

=== 全局摘要 ===
{overview}

=== 当前任务目标（goal.md，可能已被你上次 refine 调整） ===
{goal}

=== 该任务全部进度与改动 ===
{progress}
"""


def build_task_snapshot(r: sqlite3.Row) -> str:
    """单任务紧凑快照：监督调用一次只看一个任务，避免混批互相干扰。"""
    out = Path(r["outdir"])
    base = out.parent
    ts, src = T.last_activity(r)
    idle = int(time.time() - ts) if ts else -1
    stale, why = T.is_stale(r)
    try:
        pid = int((base / "pid").read_text().strip())
    except Exception:
        pid = 0
    alive = bool(pid and Path(f"/proc/{pid}").exists())
    res = ["  " + x for x in _tail(out / "result.json", n=4)] or ["  (无)"]
    sess = ["  " + x for x in _session_tail(r["session_id"])] or ["  (无)"]
    # 管理者读全部进度：≤400 行全文；更长则头 30 + 尾 200（全局重写机制管着膨胀）
    prog_lines = 0
    prog_text = ""
    try:
        prog_text = (out / "progress.md").read_text(
            encoding="utf-8", errors="replace")
        prog_lines = prog_text.count("\n")
    except OSError:
        pass
    if prog_lines <= 400:
        progress_block = prog_text or "(无)"
    else:
        ls = prog_text.splitlines()
        progress_block = ("(共 %d 行，此处显示头 30 + 尾 200；已要求 worker 全局重写)\n"
                          % prog_lines
                          + "\n".join(ls[:30]) + "\n... (中间省略) ...\n"
                          + "\n".join(ls[-200:]))
    goal_md = out.parent / "goal.md"
    goal = (goal_md.read_text(encoding="utf-8", errors="replace").strip()
            if goal_md.exists() else "(无 goal.md，用发起时的 input)")
    needs_compaction = prog_lines > T.COMPACT_MAX_LINES
    judge = f"疑似卡住({why})" if stale else "无异常"
    return "\n".join([
        f"### 任务 #{r['id']} [{r['kind']}]",
        f"task_name: {r['name']}",
        f"attempts={r['attempts']}/{r['max_attempts']} "
        f"started={T.iso(r['started_at'])} 进程存活={alive}",
        f"最近进展: {src} 距今 {idle}s；脚本初判={judge}",
        f"progress_lines={prog_lines} needs_compaction={needs_compaction}"
        f"（超过 {T.COMPACT_MAX_LINES} 行应做全局重写：读全文→压成紧凑结构，"
        f"重写前把原文复制到 progress-archive/）",
        f"error: {(r['error'] or '-')[:150]}",
        "result.json:", *res,
        "会话事件尾:", *sess,
    ]) + f"\n=== goal.md ===\n{goal}\n=== progress.md（{prog_lines} 行）===\n{progress_block}"


def build_snapshot(conn) -> tuple[str, list[sqlite3.Row], dict[int, str]]:
    """总览 + running 行 + 每任务独立快照。

    overview 一行/任务，给监督模型系统性信号（如 3 个任务同时 idle——
    可能是限流而非单任务问题）；决策仍按任务独立调用。
    """
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status='running' ORDER BY id").fetchall()
    if not rows:
        return "(没有 running 任务)", [], {}
    snaps = {}
    overview = []
    for r in rows:
        snaps[r["id"]] = build_task_snapshot(r)
        ts, _ = T.last_activity(r)
        idle = int(time.time() - ts) if ts else -1
        overview.append(f"- {r['name']} idle={idle}s attempts={r['attempts']}")
    return (f"running 任务 {len(rows)} 个：\n" + "\n".join(overview),
            rows, snaps)


def should_ask(snapshot: str, rows: list[sqlite3.Row]) -> tuple[bool, str]:
    """脚本只决定「什么时候该问模型」，不判断任务死活。"""
    if not rows:
        return False, "无 running 任务"
    # 定时监督：对齐原 watchdog 的 check_interval
    try:
        last = json.loads(LAST_ASK_FILE.read_text()).get("ts", 0)
    except Exception:
        last = 0
    if time.time() - last >= FORCE_ASK_EVERY:
        return True, f"定时监督到期({FORCE_ASK_EVERY}s)"
    # 事件监督：有任务疑似无增长，且距上次询问够久
    for r in rows:
        ts, _ = T.last_activity(r)
        if time.time() - ts >= MIN_IDLE_TO_ASK:
            return True, f"{r['name']} 超过 {MIN_IDLE_TO_ASK}s 无增长，请模型判断"
        if r["error"]:
            return True, f"{r['name']} 有 error，请模型判断"
    return False, "都在正常推进"


def ask_model(snapshot: str) -> list[dict] | None:
    # 不能用 str.format：提示词里的 JSON 示例 {"task":...} 会被当成模板变量。
    prompt = PROMPT.replace("{snapshot}", snapshot)
    cmd = [CB_BIN, "-p", "--port", "0", "--output-format", "text",
           "--permission-mode", "bypassPermissions", "-y",
           "--model", SUPERVISOR_MODEL,
           "--session-id", f"sup-{int(time.time())}", "--", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=SUPERVISOR_TIMEOUT)
    except subprocess.TimeoutExpired:
        print("[supervisor] 监督者超时，本轮不做任何动作", file=sys.stderr)
        return None
    out = (r.stdout or "").strip()
    m = re.search(r"\[[\s\S]*\]", out)
    if not m:
        print(f"[manager] 输出无法解析，本轮不动: {out[:200]}", file=sys.stderr)
        return None
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, list) else None
    except Exception as exc:
        print(f"[manager] JSON 解析失败 {exc}，本轮不动", file=sys.stderr)
        return None


def ask_model_single(snapshot: str, overview: str, name: str) -> dict | None:
    """单任务独立调用：小上下文、聚焦判断、失败只影响本任务。"""
    prompt = (MANAGER_PROMPT_SINGLE.replace("{name}", name)
              .replace("{overview}", overview))
    cmd = [CB_BIN, "-p", "--port", "0", "--output-format", "text",
           "--permission-mode", "bypassPermissions", "-y",
           "--model", SUPERVISOR_MODEL,
           "--session-id", f"mgr-{name}-{int(time.time())}", "--", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=SUPERVISOR_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"[manager] {name}: 监督者超时，本任务本轮不动", file=sys.stderr)
        return None
    out = (r.stdout or "").strip()
    m = re.search(r"\{[\s\S]*\}", out)
    if not m:
        print(f"[manager] {name}: 输出无法解析: {out[:150]}", file=sys.stderr)
        return None
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) and d.get("action") else None
    except Exception as exc:
        print(f"[manager] {name}: JSON 解析失败 {exc}", file=sys.stderr)
        return None


def apply(conn, decisions: list[dict]) -> list[str]:
    """执行模型的结构化决策；脚本不做判断，但做防呆。"""
    acted = []
    for d in decisions or []:
        if not isinstance(d, dict):
            continue
        name, action = d.get("task"), d.get("action")
        reason = str(d.get("reason") or "")[:200]
        guidance = str(d.get("guidance") or "").strip()
        # 模型可能把 "s3 #1 [generic]" 整个抄进来；归一化后再查。
        raw = str(name or "")
        r = conn.execute("SELECT * FROM tasks WHERE name=?", (raw,)).fetchone()
        if not r and raw:
            cand = raw.split()[0].strip("#")
            r = conn.execute("SELECT * FROM tasks WHERE name=?", (cand,)).fetchone()
        if not r:
            m = re.search(r"#(\d+)", raw)
            if m:
                r = conn.execute("SELECT * FROM tasks WHERE id=?",
                                 (int(m.group(1)),)).fetchone()
        if not r:
            T.event(conn, 0, "supervisor_unmatched", {"task": raw[:100]})
            continue
        # 决策全留痕（含 continue 与理由）：主人/任何 AI 可追溯管理者怎么想的
        try:
            outdir = Path(r["outdir"])
            outdir.mkdir(parents=True, exist_ok=True)
            with open(outdir.parent / "decisions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": T.now(), "task": r["name"],
                                    "action": action, "reason": reason,
                                    "guidance": guidance[:300]},
                                   ensure_ascii=False) + "\n")
        except OSError:
            pass
        if action == "continue":
            continue
        if action == "refine":
            new_goal = str(d.get("new_goal") or "").strip()
            if not new_goal:
                continue
            outdir = Path(r["outdir"])
            base = outdir.parent
            goal_md = base / "goal.md"
            if goal_md.exists():
                arch = base / "goal-archive"
                arch.mkdir(parents=True, exist_ok=True)
                shutil.copy2(goal_md, arch / f"goal-{int(time.time())}.md")
            goal_md.write_text(new_goal, encoding="utf-8")
            guidance = guidance or f"任务目标已被管理者调整，以下为准：{new_goal[:300]}"
            reason = f"[goal_refined] {reason}"
            # 落到 nudge 路径：guidance.md 注入下一轮（下方统一处理）
            action = "nudge"
        # 防呆：restart 必须模型给了 guidance，且没超重试次数
        if action == "restart":
            if r["attempts"] >= r["max_attempts"]:
                action = "escalate"
                reason = f"模型要求 restart 但重试已耗尽；原由: {reason}"
            elif not guidance:
                continue  # 没给指令的重排没意义，忽略
        if action == "nudge" and not guidance:
            continue

        outdir = Path(r["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)
        if guidance:
            (outdir / "guidance.md").write_text(
                f"# 管理者指令（{T.iso(time.time())}）\n\n{guidance}\n"
                f"\n判断依据：{reason}\n", encoding="utf-8")

        if action == "restart":
            T.kill_worker(r)
            conn.execute(
                "UPDATE tasks SET status='queued', lease_until=0, error=? WHERE id=?",
                (f"监督者判定需重来：{reason}；指令已写 guidance.md", r["id"]))
        elif action == "escalate":
            conn.execute(
                "UPDATE tasks SET status='awaiting-person', error=? WHERE id=?",
                (f"需人工：{reason}", r["id"]))
        elif action == "finish":
            rj = outdir / "result.json"
            payload = None
            if rj.exists():
                try:
                    payload = json.loads(rj.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if isinstance(payload, dict) and T.validate_result(payload) is None:
                conn.execute(
                    "UPDATE tasks SET status=?, result_json=?, ended_at=? WHERE id=?",
                    (payload["status"], json.dumps(payload, ensure_ascii=False),
                     time.time(), r["id"]))
            else:
                conn.execute("UPDATE tasks SET status='done', ended_at=? WHERE id=?",
                             (time.time(), r["id"]))
        # nudge：只写 guidance.md，不动进程（等下次重排/续接注入）
        T.event(conn, r["id"], f"supervisor_{action}",
                {"reason": reason, "guidance": guidance[:200]})
        conn.commit()
        acted.append(f"{name}:{action}")
    return acted


def run_once(verbose: bool = True) -> int:
    """每任务**独立**监督调用：不混批（混批会互相干扰、一次解析失败全军覆没）。

    并发 = SUPERVISOR_CONCURRENCY（默认 2，遵守每模型 2 路的额度语义）；
    某任务调用失败/超时只影响它自己，其余照常拿到决策。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    conn = T.db()
    try:
        overview, rows, snaps = build_snapshot(conn)
        if verbose:
            print(overview[:800])
        ask, why = should_ask(overview, rows)
        if verbose:
            print(f"\n[触发] ask={ask} 原因={why}")
        if not ask or not rows:
            return 0

        decisions_all = []
        skipped = []
        with ThreadPoolExecutor(max_workers=SUPERVISOR_CONCURRENCY) as pool:
            futs = {pool.submit(ask_model_single, snaps[r["id"]], overview,
                                r["name"]): r["name"] for r in rows}
            for fut in as_completed(futs):
                name = futs[fut]
                try:
                    d = fut.result()
                except Exception as exc:
                    print(f"[manager] {name}: 监督调用异常 {exc}", file=sys.stderr)
                    d = None
                if d is None:
                    skipped.append(name)
                    continue
                decisions_all.append({"task": name, **d})

        LAST_ASK_FILE.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
        acted = apply(conn, decisions_all)
        print(f"[manager] {len(rows)} 任务独立监督: 决策 {len(decisions_all)} 条"
              f"（跳过 {len(skipped)}）执行: {acted or '(全部 continue)'}")
        return 0
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(prog="supervisor", description="模型监督模型")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("once", help="跑一次")
    a.add_argument("--quiet", action="store_true")
    a.set_defaults(func=lambda a: run_once(verbose=not a.quiet))
    s = sub.add_parser("snapshot", help="只看快照，不调模型")
    s.set_defaults(func=lambda a: (print(build_snapshot(T.db())[0]), 0)[1])
    d = sub.add_parser("daemon", help="常驻")
    d.add_argument("--interval", type=int, default=INTERVAL)
    def loop(a):
        print(f"supervisor daemon: 每 {a.interval}s 一轮，model={SUPERVISOR_MODEL}")
        while True:
            try:
                run_once(verbose=False)
            except Exception as exc:
                print(f"[manager] 异常 {exc}", file=sys.stderr)
            time.sleep(a.interval)
    d.set_defaults(func=loop)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
