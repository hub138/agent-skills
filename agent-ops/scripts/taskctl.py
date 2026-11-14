#!/usr/bin/env python3
"""taskctl —— 面向几十万任务的调度器（SQLite 队列 + 有限 worker 池）。

设计要点（为什么能到几十万）：
1. 任务本体是数据库里的一行，不是进程。几十万任务 = 几十万行，不是几十万进程。
2. 并发由 worker 池限制（默认 2，用户口径），队列深度无上限。
3. 每次操作只碰索引命中的少量行，不做全表扫描、不 glob 目录。
4. 租约（lease）代替 pid：worker 崩溃后租约过期自动回收，跨重启有效。
5. 提示词由任务类型模板渲染，用户只给类型和输入，不写 prompt。

命令：
  add       加任务（--goal 一句话即可，--kind 决定模板）
  plan      一句话自动拆成多个任务（用户完全不用写提示词）
  add-file  从文件批量导入（每行一个 JSON）
  list      按状态分页列出
  stats     按状态/类型聚合（SQL，不读全表）
  tick      调度一轮：回收过期租约 → 取任务 → 起进程 → 执行 outbox
  brief     只读某任务的结果摘要（给主 agent 控上下文）
  retry     手动重试
  cancel    取消
  daemon    常驻循环（替代 cron，间隔可调）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import shlex
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path(os.environ.get("AGENTCTL_HOME", Path.home() / ".codebuddy/agentctl"))
DB = Path(os.environ.get("TASKCTL_DB", HOME / "tasks.db"))
TEMPLATES = Path(__file__).resolve().parent.parent / "templates/tasks"
CB_BIN = os.environ.get("CODEBUDDY_CLI_BIN", "/usr/local/bin/codebuddy")
KNOT_BIN = os.environ.get("KNOT_CLI_BIN", "<knot-cli 路径>")
CB_PROJECTS = Path.home() / ".codebuddy/projects"

DEFAULT_CONCURRENCY = int(os.environ.get("TASKCTL_CONCURRENCY", "2"))
LEASE_SECONDS = int(os.environ.get("TASKCTL_LEASE", "1800"))
MAX_ATTEMPTS = int(os.environ.get("TASKCTL_MAX_ATTEMPTS", "3"))
# 假死判定：会话 jsonl / progress.md / run.log 全部超过这个秒数没增长，
# 且 CLI 进程还活着 → 判卡住，杀掉重排。设 0 关闭。
# 默认 900s 是保守值：reasoning 阶段本来就不产生新事件（实测思考 20s
# 期间 jsonl 不动是正常的），阈值太小会误杀正在干活的长任务。
STALE_SECONDS = int(os.environ.get("TASKCTL_STALE", "900"))


# 全局重写（compaction）留痕与阈值。借鉴：prime-agent 的百分比参数校验、
# deer-flow 的 CompactionEvent（压缩是破坏性的，必须留可回溯统计与副本）。
def _valid_percent(v, default: float) -> float:
    """1~100 之间的有限数才合法，否则回退默认。"""
    try:
        f = float(v)
        return f if math.isfinite(f) and 1.0 <= f <= 100.0 else default
    except (TypeError, ValueError):
        return default


# progress 行数比上次记录下降 ≥ 该百分比 → 视为发生全局重写，写 compaction 事件
COMPACT_DROP_PCT = _valid_percent(os.environ.get("TASKCTL_COMPACT_DROP_PCT"), 30.0)
# progress 超过该行数 → supervisor 快照标 needs_compaction，提醒模型做全局重写
COMPACT_MAX_LINES = max(100, int(os.environ.get("TASKCTL_COMPACT_MAX_LINES", "2000")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT UNIQUE NOT NULL,
  kind         TEXT NOT NULL,
  input_json   TEXT NOT NULL DEFAULT '{}',
  prompt_path  TEXT,
  status       TEXT NOT NULL DEFAULT 'queued',
  priority     INTEGER NOT NULL DEFAULT 100,
  attempts     INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  lease_until  REAL NOT NULL DEFAULT 0,
  worker_id    TEXT,
  session_id   TEXT,
  outdir       TEXT,
  backend      TEXT NOT NULL DEFAULT 'codebuddy',
  model        TEXT NOT NULL DEFAULT 'free-model',
  workdir      TEXT,
  result_json  TEXT,
  error        TEXT,
  created_at   REAL NOT NULL,
  started_at   REAL,
  ended_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_ready ON tasks(status, priority, id);
CREATE INDEX IF NOT EXISTS idx_tasks_lease ON tasks(status, lease_until);
CREATE INDEX IF NOT EXISTS idx_tasks_kind  ON tasks(kind, status);

CREATE TABLE IF NOT EXISTS task_events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  at      REAL NOT NULL,
  kind    TEXT NOT NULL,
  payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, id);

CREATE TABLE IF NOT EXISTS outbox (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id  INTEGER NOT NULL,
  kind     TEXT NOT NULL,
  payload  TEXT,
  status   TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_at  REAL NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outbox_ready ON outbox(status, next_at);

CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT
);
"""

BACKOFF = (2, 4, 8, 16, 32, 60, 120, 300)

# 用户硬红线：只允许 x0.00 或 ≤0.15 credits。
ALLOWED_MODELS = {
    "free-model", "free-model-flash", "small-model", "echo", "small-model", "free-model", "free-model-preview",
    "gpt-6-luna", "glm-5.3-flash-ioa", "minimax-m3.1-flash",
    "deepseek-v4.1-flash", "mimo-v2.6-pro", "gpt-5.6-luna",
}


def assert_model(model: str, backend: str = "codebuddy") -> None:
    m = (model or "").strip()
    # knot 侧这些 ID 走免费额度，不受 codebuddy credits 红线约束
    if backend == "knot":
        if m not in ("free-model", "small-model", "free-model-preview", "glm-5.3", "glm-5.3-flash",
                     "deepseek-v4-flash", "deepseek-v4-pro"):
            raise SystemExit(f"knot 模型 {m!r} 不在允许清单")
        return
    if m not in ALLOWED_MODELS:
        raise SystemExit(f"拒绝：模型 {m!r} 超出 0.15 credits 红线。允许 {sorted(ALLOWED_MODELS)}")


def validate_result(d) -> str | None:
    """校验子任务写的 result.json；返回错误说明，合格返回 None。"""
    if not isinstance(d, dict):
        return "不是 JSON 对象"
    if d.get("status") not in ("done", "blocked", "failed"):
        return "status 不是 done/blocked/failed"
    summary = d.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return "summary 缺失或不是字符串"
    if len(summary) > 400:
        return f"summary 过长({len(summary)}字)，上限 200 字左右"
    ev = d.get("evidence", [])
    if not isinstance(ev, list) or len(ev) > 10:
        return "evidence 不是数组或超过 10 条"
    q = d.get("question")
    if q is not None and (not isinstance(q, str) or len(q) > 300):
        return "question 不是字符串或过长"
    return None


def now() -> float:
    return time.time()


def iso(ts: float | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def db() -> sqlite3.Connection:
    HOME.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    return conn


def event(conn, task_id: int, kind: str, payload: dict | None = None) -> None:
    conn.execute("INSERT INTO task_events(task_id, at, kind, payload) VALUES(?,?,?,?)",
                 (task_id, now(), kind, json.dumps(payload or {}, ensure_ascii=False)))


# ── 提示词模板 ──────────────────────────────────────────────────────────
def list_kinds() -> list[str]:
    if not TEMPLATES.is_dir():
        return []
    return sorted(p.stem for p in TEMPLATES.glob("*.md"))


def render_prompt(kind: str, inp: dict, outdir: Path, name: str) -> str:
    """按任务类型渲染提示词。用户永远不需要手写 prompt。"""
    tpl = TEMPLATES / f"{kind}.md"
    if not tpl.exists():
        avail = ", ".join(list_kinds()) or "(无)"
        raise SystemExit(f"未知任务类型 {kind!r}。可用类型：{avail}")
    text = tpl.read_text(encoding="utf-8")
    values = {
        "name": name,
        "outdir": str(outdir),
        "progress": str(outdir / "progress.md"),
        "result": str(outdir / "result.json"),
        "done_file": str(outdir / "DONE"),
        "input_json": json.dumps(inp, ensure_ascii=False, indent=2),
    }
    for k, v in inp.items():
        values[f"input_{k}"] = str(v)
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    missing = [m for m in ("{outdir}", "{result}", "{progress}") if m in text]
    if missing:
        raise SystemExit(f"模板 {kind} 渲染后仍有占位符 {missing}，检查模板变量")
    return text


# ── add / import ────────────────────────────────────────────────────────
KIND_FIELDS = {
    "generic":        "topic（想让它干什么，自由文本）",
    "compare-commit": "commit, repo, file, diff, upstream_code（缺的跳过）",
    "reproduce-bug":  "bug_id, repo, test_case, workdir",
    "fix-bug":        "bug_id, repo, symptom, workdir",
    "research":       "topic, questions（数组）, sources（可选）",
}


def cmd_kinds(args) -> int:
    """列出可用的任务类型和每个类型要什么输入（不懂 AI 的人照着填）。"""
    print("可用任务类型（add --kind 后面填这些）：")
    for k in list_kinds():
        print(f"  {k:<18} 输入: {KIND_FIELDS.get(k, '见模板')}")
    print("\n示例：taskctl add --kind generic --input '{\"topic\":\"检查这个仓库的构建脚本\"}'")
    print("批量：每行一个 JSON，字段 kind/input/name/priority，用 taskctl add-file tasks.txt")
    return 0


PLANNER_PROMPT = """你是任务拆解器。把用户的目标拆成不超过 {max_tasks} 个可以独立执行的子任务。

可用的任务类型：{kinds}
（generic=任意工作；compare-commit=代码合入判定；reproduce-bug=缺陷复现；
 fix-bug=缺陷修复；research=调研）

规则：
- 每个子任务必须能单独交给一个 agent 完成，不依赖其它子任务的中间对话。
- 每个 goal 用一句自然语言说清「做什么、在哪个路径、交付什么」。
- 不要写实现计划、不要写提示词、不要解释。
- 只输出一个 JSON 数组，不要 markdown 围栏。
每项格式：{{"kind":"类型","goal":"一句话","priority":100}}

用户目标：
{goal}
"""


def cmd_add(args) -> int:
    inp = json.loads(args.input) if args.input else {}
    if args.input_file:
        inp.update(json.loads(Path(args.input_file).read_text(encoding="utf-8")))
    # 自然语言入口：--goal "一句话" 就够了，用户不需要懂 JSON / 提示词 / 任务类型。
    if args.goal:
        inp.setdefault("topic", args.goal)
        inp.setdefault("goal", args.goal)
    if args.repo:
        inp.setdefault("repo", args.repo)
    kind = args.kind or "generic"
    name = args.name or f"{kind}-{int(now() * 1000)}"
    assert_model(args.model, args.backend)
    if not args.goal and not inp:
        print("提示：用 --goal \"一句话说明要做什么\" 最简单；"
              "也可用 --kind/--input 精确指定", file=sys.stderr)
    # 惰性：几十万任务时绝不能给每个任务建目录 + 写 prompt.md。
    # 目录和提示词只在 tick 真正要拉起它时才创建（见 ensure_task_dir）。
    outdir = HOME / "tasks" / name / "out"
    conn = db()
    try:
        conn.execute(
            "INSERT INTO tasks(name,kind,input_json,prompt_path,status,priority,"
            "max_attempts,outdir,backend,model,workdir,session_id,created_at) "
            "VALUES(?,?,?,?, 'queued',?,?,?,?,?,?,?,?)",
            (name, kind, json.dumps(inp, ensure_ascii=False), "",
             args.priority, args.max_attempts, str(outdir),
             args.backend, args.model, args.workdir,
             f"{name}-{int(now())}", now()))
        tid = conn.execute("SELECT id FROM tasks WHERE name=?", (name,)).fetchone()["id"]
        event(conn, tid, "added", {"kind": kind})
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"任务名 {name} 已存在（幂等）", file=sys.stderr)
        return 2
    finally:
        conn.close()
    # goal.md：发起时的原始目标；管理者可 refine（旧版自动归档 goal-archive/）
    try:
        _g = (inp.get("goal") or inp.get("topic") or "").strip()
        if _g:
            Path(outdir).parent.mkdir(parents=True, exist_ok=True)
            (Path(outdir).parent / "goal.md").write_text(_g, encoding="utf-8")
    except Exception:
        pass

    if not args.quiet:
        print(f"已加入队列 #{tid} {name} [{kind}] priority={args.priority}")
    return 0


def cmd_plan(args) -> int:
    """一句话 → 自动拆成多个任务并入队。全程不要求用户写提示词。"""
    import re
    prompt = PLANNER_PROMPT.format(
        max_tasks=args.max_tasks, goal=args.goal,
        kinds=", ".join(list_kinds()))
    cmd = [CB_BIN, "-p", "--port", "0", "--output-format", "text",
           "--permission-mode", "bypassPermissions", "-y",
           "--model", "free-model", "--session-id",
           f"plan-{int(now())}", "--", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
        out = (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        print("拆解超时：请改用 --goal 直接加一个任务，或把目标说小一点", file=sys.stderr)
        return 1
    # 从输出里提取 JSON 数组（模型可能带围栏或前导文字）
    m = re.search(r"\[[\s\S]*\]", out)
    if not m:
        print(f"拆解结果无法解析，原始输出：\n{out[:500]}", file=sys.stderr)
        return 1
    try:
        items = json.loads(m.group(0))
    except Exception as exc:
        print(f"拆解结果 JSON 解析失败: {exc}\n{out[:500]}", file=sys.stderr)
        return 1
    if not isinstance(items, list) or not items:
        print("拆解结果为空", file=sys.stderr)
        return 1
    added = 0
    for i, it in enumerate(items[:args.max_tasks]):
        if not isinstance(it, dict):
            continue
        ns = argparse.Namespace(
            kind=it.get("kind", "generic"), input=None, input_file=None,
            goal=it.get("goal") or args.goal, repo=args.repo,
            name=it.get("name"), priority=int(it.get("priority", 100)),
            max_attempts=args.max_attempts, backend=args.backend,
            model=args.model, workdir=args.workdir, quiet=True)
        if cmd_add(ns) == 0:
            added += 1
    print(f"目标已拆成 {added} 个任务并入队：{args.goal}")
    print("用 `taskctl stats` 看进度、`taskctl daemon` 开始跑")
    return 0


def cmd_add_file(args) -> int:
    """批量导入：每行一个 JSON，字段 kind/input/name/priority。"""
    n = 0
    path = Path(args.file)
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            ns = argparse.Namespace(
                kind=row["kind"], input=json.dumps(row.get("input", {})),
                input_file=None, name=row.get("name"),
                priority=int(row.get("priority", 100)),
                max_attempts=int(row.get("max_attempts", MAX_ATTEMPTS)),
                backend=row.get("backend", "codebuddy"),
                model=row.get("model", "free-model"),
                workdir=row.get("workdir", str(HOME)),
                goal=row.get("goal"), repo=row.get("repo"), quiet=True)
            if cmd_add(ns) == 0:
                n += 1
    print(f"批量导入完成：{n} 条")
    return 0


# ── 查询 ────────────────────────────────────────────────────────────────
def cmd_list(args) -> int:
    conn = db()
    try:
        where, params = "", []
        if args.status:
            where = "WHERE status IN (%s)" % ",".join("?" * len(args.status))
            params = args.status
        rows = conn.execute(
            f"SELECT id,name,kind,status,attempts,priority,created_at,outdir "
            f"FROM tasks {where} ORDER BY priority, id LIMIT ? OFFSET ?",
            (*params, args.limit, args.offset)).fetchall()
        total = conn.execute(f"SELECT COUNT(*) c FROM tasks {where}", params).fetchone()["c"]
    finally:
        conn.close()
    print(f"{'ID':>8} {'名称':<26} {'类型':<16} {'状态':<10} {'尝试':<4} {'加入'}")
    for r in rows:
        print(f"{r['id']:>8} {r['name'][:25]:<26} {r['kind'][:15]:<16} "
              f"{r['status']:<10} {r['attempts']}/{MAX_ATTEMPTS:<2} {iso(r['created_at'])}")
    print(f"-- 共 {total} 条，本页 {len(rows)} 条（offset={args.offset}）")
    return 0


def cmd_stats(args) -> int:
    conn = db()
    try:
        print("=== 按状态 ===")
        for r in conn.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status ORDER BY c DESC"):
            print(f"  {r['status']:<14} {r['c']}")
        print("=== 按类型 ===")
        for r in conn.execute("SELECT kind, status, COUNT(*) c FROM tasks "
                              "GROUP BY kind, status ORDER BY kind, c DESC LIMIT 30"):
            print(f"  {r['kind'][:20]:<22} {r['status']:<12} {r['c']}")
        r = conn.execute("SELECT COUNT(*) c FROM outbox WHERE status='pending'").fetchone()
        print(f"=== outbox 待执行 {r['c']} ===")
    finally:
        conn.close()
    return 0


def cmd_brief(args) -> int:
    conn = db()
    try:
        r = conn.execute("SELECT * FROM tasks WHERE id=? OR name=?",
                         (args.task, args.task)).fetchone()
        if not r:
            print(f"没有任务 {args.task}", file=sys.stderr)
            return 1
        print(f"任务     : #{r['id']} {r['name']} [{r['kind']}]")
        print(f"状态     : {r['status']}  尝试 {r['attempts']}/{r['max_attempts']}")
        if r["result_json"]:
            d = json.loads(r["result_json"])
            print(f"摘要     : {d.get('summary')}")
            for e in (d.get("evidence") or [])[:5]:
                print(f"证据     : {e}")
            if d.get("question"):
                print(f"待决策   : {d['question']}")
            if d.get("next"):
                print(f"下一步   : {d['next']}")
        elif r["error"]:
            print(f"错误     : {r['error'][:300]}")
        print(f"输出目录 : {r['outdir']}")
    finally:
        conn.close()
    return 0


# ── 调度 ────────────────────────────────────────────────────────────────
def build_cmd(task: sqlite3.Row, prompt: str) -> list[str]:
    backend = task["backend"] or "codebuddy"
    model = task["model"] or "free-model"
    sid = task["session_id"]
    if model in ("free-model", "small-model", "free-model-preview") and backend == "knot":
        return [KNOT_BIN, "chat", "--no-update", "--output-format", "text",
                "--model", model, "--sessionId", sid, "-p", prompt]
    cmd = [CB_BIN, "-p", "--port", "0", "--output-format", "text",
           "--permission-mode", "bypassPermissions", "-y", "--model", model]
    # attempts 在抢占时已经 +1，所以首次尝试时是 1：必须用 --session-id 新建，
    # 用 --resume 会报 "No conversation found" 直接退出。
    first = int(task["attempts"] or 1) <= 1
    cmd += ["--session-id", sid] if first else ["--resume", sid]
    cmd += ["--", prompt]
    return cmd


def ensure_task_dir(task: sqlite3.Row) -> str:
    """惰性创建任务目录并渲染提示词。几十万任务时只有被拉起的才占 inode。"""
    outdir = Path(task["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)
    pp = outdir.parent / "prompt.md"
    inp = json.loads(task["input_json"] or "{}")
    # 每轮重渲染（旧版只在首次生成 → 重试时 error/guidance 回灌静默失效）。
    # prompt.md 是"当前轮次的投影视图"；源状态在 goal.md/progress.md/guidance.md。
    extra = ""
    if task["error"]:
        extra = ("\n## 上一次失败原因（务必修正）\n" + task["error"][:500] + "\n")
    guidance = outdir / "guidance.md"
    if guidance.exists():
        extra += ("\n## 管理者给你的最新指令（优先级高于原计划）\n"
                  + guidance.read_text(encoding="utf-8")[:1500] + "\n")
    goal_md = outdir.parent / "goal.md"
    if goal_md.exists():
        extra += ("\n## 当前任务目标（管理者可能已调整，以此为准）\n"
                  + goal_md.read_text(encoding="utf-8")[:800] + "\n")
    pp.write_text(render_prompt(task["kind"], inp, outdir, task["name"]) + extra,
                  encoding="utf-8")
    return pp.read_text(encoding="utf-8")


def spawn_task(conn, task: sqlite3.Row, prompt: str = "") -> int | None:
    """启动一个独立的 Python worker 进程来持有 CLI 子进程。

    为什么不用 bash 包装：codebuddy 超时清理会 killpg 整个进程组，
    bash 会被连带杀掉，`exit` 永远写不出来（实测两次）。这里 worker
    自己 Popen CLI 到新会话，两层隔离，由 worker 负责写 pid 和 exit。
    """
    outdir = Path(task["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir.parent
    log = base / "run.log"
    pidf = base / "pid"
    exitf = base / "exit"
    pidf.write_text("", encoding="utf-8")
    exitf.write_text("", encoding="utf-8")
    with open(log, "a", encoding="utf-8") as lf:
        lf.write(f"\n===== attempt {task['attempts']} {datetime.now():%F %T} =====\n")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_worker",
         "--task-id", str(task["id"]), "--timeout", str(LEASE_SECONDS)],
        cwd=task["workdir"] or str(HOME),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    return proc.pid


def cmd_worker(args) -> int:
    """被 spawn_task 拉起的监督进程：跑 CLI、写 pid/exit、超时清理。"""
    conn = db()
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (args.task_id,)).fetchone()
    if not task:
        return 1
    outdir = Path(task["outdir"])
    base = outdir.parent
    prompt = ensure_task_dir(task)
    cmd = build_cmd(task, prompt)
    log = base / "run.log"
    pidf = base / "pid"
    exitf = base / "exit"
    rc = -1
    try:
        with open(log, "a", encoding="utf-8") as lf:
            cli = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        pidf.write_text(str(cli.pid), encoding="utf-8")
        try:
            rc = cli.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(cli.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            rc = -9
    except Exception as exc:
        with open(log, "a", encoding="utf-8") as lf:
            lf.write(f"worker error: {exc}\n")
        rc = -2
    exitf.write_text(str(rc), encoding="utf-8")
    conn.close()
    return 0

def last_activity(task: sqlite3.Row) -> tuple[float, str]:
    """任务最近一次「真的有进展」的时间和来源。

    优先级：会话 jsonl（codebuddy 边跑边写，最真实）> progress.md
    > result.json > run.log。全都没有时用任务 started_at。
    不用 AI 去读日志判断死活：那要额外一次模型调用、更慢更贵，
    而 mtime 是内核给的客观事实。
    """
    outdir = Path(task["outdir"])
    base = outdir.parent
    candidates: list[tuple[float, str]] = []
    sid = task["session_id"] or ""
    if sid:
        for p in CB_PROJECTS.glob(f"*/{sid}.jsonl"):
            candidates.append((p.stat().st_mtime, "session_jsonl"))
    for f, label in ((outdir / "progress.md", "progress"),
                     (outdir / "result.json", "result"),
                     (base / "run.log", "runlog")):
        if f.exists():
            candidates.append((f.stat().st_mtime, label))
    if candidates:
        return max(candidates)
    return (float(task["started_at"] or 0), "started_at")


def is_stale(task: sqlite3.Row) -> tuple[bool, str]:
    if STALE_SECONDS <= 0:
        return False, ""
    ts, src = last_activity(task)
    idle = time.time() - ts
    # 刚启动还没写任何东西的，用 started_at 兜底，别立刻判死
    if src == "started_at" and idle < STALE_SECONDS:
        return False, ""
    return (idle > STALE_SECONDS, f"{src} {int(idle)}s 无增长")


def _progress_state(prog: Path) -> dict | None:
    try:
        data = prog.read_bytes()
    except OSError:
        return None
    if not data:
        return None
    return {"size": len(data), "lines": data.count(b"\n"),
            "hash": hashlib.sha256(data).hexdigest()[:16]}


def archive_progress(conn, task: sqlite3.Row) -> None:
    """任务收尾时对 progress.md 留痕。

    - 内容有变 → 归档一份快照到 progress-archive/snap-*.md（无损原文留盘）
    - 行数比上次记录下降 ≥ COMPACT_DROP_PCT → 写 compaction 事件
      （deer-flow：压缩是破坏性的，before/after 统计必须可回溯）
    不 commit：由调用方的外层分支统一提交。
    """
    if not task["outdir"]:
        return
    prog = Path(task["outdir"]) / "progress.md"
    st = _progress_state(prog)
    if not st:
        return
    key = f"progress_state:{task['id']}"
    row = conn.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
    prev = json.loads(row["v"]) if row else None
    base = Path(task["outdir"]).parent
    arch = base / "progress-archive"
    if prev and st["lines"] < prev["lines"]:
        drop = (prev["lines"] - st["lines"]) / max(1, prev["lines"]) * 100
        if drop >= COMPACT_DROP_PCT:
            arch.mkdir(parents=True, exist_ok=True)
            dest = arch / f"compact-{len(list(arch.glob('compact-*.md'))) + 1}-{int(now())}.md"
            shutil.copy2(prog, dest)
            event(conn, task["id"], "compaction", {
                "before_lines": prev["lines"], "after_lines": st["lines"],
                "drop_pct": round(drop, 1),
                "before_size": prev["size"], "after_size": st["size"],
                "before_hash": prev.get("hash"), "after_hash": st["hash"],
                "archive": str(dest)})
    if not prev or prev.get("hash") != st["hash"]:
        arch.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prog, arch / f"snap-{len(list(arch.glob('snap-*.md'))) + 1}-{int(now())}.md")
    conn.execute("INSERT INTO kv(k,v) VALUES(?,?) "
                 "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                 (key, json.dumps(st)))


def kill_worker(task: sqlite3.Row) -> None:
    """按 pid 精确杀 CLI 所在的进程组，不 pkill -f 误伤别的项目。"""
    try:
        pid = int((Path(task["outdir"]).parent / "pid").read_text().strip())
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ValueError, OSError, ProcessLookupError, PermissionError):
        pass


def cmd_tick(args) -> int:
    conn = db()
    started = 0
    try:
        # 1) 回收租约过期：worker 崩溃/机器重启后任务自动回到队列
        expired = conn.execute(
            "SELECT id,name,attempts,max_attempts,outdir FROM tasks "
            "WHERE status='running' AND lease_until < ?", (now(),)).fetchall()
        for r in expired:
            # 只有进程真的不在了才回收；续租逻辑偶尔漏一轮也不会误杀长任务。
            try:
                wpid = int((Path(r["outdir"]).parent / "pid").read_text().strip())
            except Exception:
                wpid = 0
            if wpid and Path(f"/proc/{wpid}").exists():
                conn.execute("UPDATE tasks SET lease_until=? WHERE id=?",
                             (now() + LEASE_SECONDS, r["id"]))
                continue
            if r["attempts"] >= r["max_attempts"]:
                conn.execute("UPDATE tasks SET status='failed', error=?, ended_at=? WHERE id=?",
                             ("租约过期且重试耗尽", now(), r["id"]))
                event(conn, r["id"], "lease_expired_final")
            else:
                conn.execute("UPDATE tasks SET status='queued', lease_until=0, worker_id=NULL WHERE id=?",
                             (r["id"],))
                event(conn, r["id"], "lease_expired_requeue")
        # 2) 原子抢占。BEGIN IMMEDIATE 拿 SQLite 写锁，两个 tick 同时跑时
        #    第二个会等到第一个 commit，SELECT 时已无 queued → 不会重复拉起。
        #    实测修复前：并发=1 时两个 tick 会把同一任务 spawn 2 次。
        # 第 1 步租约回收可能已开启隐式事务，先提交再开显式事务，
        # 否则 sqlite 报 "cannot start a transaction within a transaction"。
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        try:
            running = conn.execute(
                "SELECT COUNT(*) c FROM tasks WHERE status='running'").fetchone()["c"]
            free = max(0, args.concurrency - running)
            claimed = []
            if free:
                rows = conn.execute(
                    "SELECT id FROM tasks WHERE status='queued' "
                    "ORDER BY priority, id LIMIT ?", (free,)).fetchall()
                for r in rows:
                    cur = conn.execute(
                        "UPDATE tasks SET status='running', attempts=attempts+1, "
                        "lease_until=?, worker_id=?, started_at=? "
                        "WHERE id=? AND status='queued'",
                        (now() + LEASE_SECONDS, f"w{os.getpid()}", now(), r["id"]))
                    if cur.rowcount == 1:
                        claimed.append(r["id"])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        # commit 之后才做外部副作用（起进程），崩溃时由租约/出件队列兜住。
        for tid in claimed:
            task = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            assert_model(task["model"], task["backend"])
            conn.execute(
                "INSERT INTO outbox(task_id, kind, payload, status, created_at) "
                "VALUES(?, 'spawn', '', 'pending', ?)", (tid, now()))
            conn.commit()
            try:
                pid = spawn_task(conn, task)
                conn.execute("UPDATE tasks SET worker_id=? WHERE id=?",
                             (f"w{os.getpid()}:{pid}", tid))
                conn.execute("UPDATE outbox SET status='done' WHERE task_id=? "
                             "AND kind='spawn' AND status='pending'", (tid,))
                event(conn, tid, "spawned", {"pid": pid})
                started += 1
            except Exception as exc:
                conn.execute(
                    "UPDATE tasks SET status='queued', attempts=attempts-1, "
                    "lease_until=0, error=? WHERE id=?", (str(exc)[:300], tid))
                conn.execute("UPDATE outbox SET status='failed' WHERE task_id=? "
                             "AND kind='spawn' AND status='pending'", (tid,))
                event(conn, tid, "spawn_failed", {"error": str(exc)[:200]})
            conn.commit()
        # 3) 收尾：进程已退出但状态还是 running 的，读 exit/result 判定
        for r in conn.execute(
                "SELECT id,name,outdir,attempts,max_attempts,session_id FROM tasks "
                "WHERE status='running' AND lease_until >= ?", (now(),)).fetchall():
            base = Path(r["outdir"]).parent
            # 长任务续租：进程还活着就续，避免租约过期被误判成崩溃重复拉起。
            # 实测修复前：一个跑 2 小时的任务在 30 分钟后会被重新拉起第二个进程。
            try:
                wpid = int((base / "pid").read_text().strip())
            except Exception:
                wpid = 0
            if wpid and Path(f"/proc/{wpid}").exists():
                # 进程活着 ≠ 在干活。会话文件/进度文件长时间不增长就是假死。
                full = conn.execute("SELECT * FROM tasks WHERE id=?",
                                    (r["id"],)).fetchone()
                stale, why = is_stale(full)
                if stale:
                    # 2026-11-12 用户纠正：脚本不做「是不是该杀」的判断。
                    # 原 watchdog skill 的核心是「模型读进度自己判断下一步」，
                    # 这里只把「疑似无增长」记成待监督信号，由
                    # scripts/supervisor.py 拉起监督者模型做决策。
                    # 进程继续续租、绝不误杀正在 reasoning 的长任务。
                    if not (full["error"] or "").startswith("疑似卡住"):
                        conn.execute("UPDATE tasks SET error=? WHERE id=?",
                                     (f"疑似卡住：{why}（待监督者模型判断）", r["id"]))
                        event(conn, r["id"], "need_supervision", {"why": why})
                    conn.execute("UPDATE tasks SET lease_until=? WHERE id=?",
                                 (now() + LEASE_SECONDS, r["id"]))
                    conn.commit()
                    continue
                conn.execute("UPDATE tasks SET lease_until=? WHERE id=?",
                             (now() + LEASE_SECONDS, r["id"]))
                conn.commit()
                continue
            # 收尾留痕：归档 progress 快照 + compaction 检测（在状态变更前）
            archive_progress(conn, r)
            # 结果优先：result.json 有效就直接收尾，不必等 exit
            # （进程可能在收尾、也可能被 killpg 杀掉没留下退出码）。
            rj = Path(r["outdir"]) / "result.json"
            if rj.exists():
                try:
                    payload = json.loads(rj.read_text(encoding="utf-8"))
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    err = validate_result(payload)
                    if err is None:
                        conn.execute(
                            "UPDATE tasks SET status=?, result_json=?, ended_at=? WHERE id=?",
                            (payload["status"], json.dumps(payload, ensure_ascii=False),
                             now(), r["id"]))
                        event(conn, r["id"], "finished_by_result")
                        conn.commit()
                        continue
                    # 契约不合格：不让这条污染 brief，重试并在 prompt 里带上原因
                    if r["attempts"] < r["max_attempts"]:
                        conn.execute(
                            "UPDATE tasks SET status='queued', lease_until=0, error=? WHERE id=?",
                            (f"result.json 不合格：{err}", r["id"]))
                        event(conn, r["id"], "bad_result_requeue", {"error": err})
                        conn.commit()
                        continue
            exitf = base / "exit"
            try:
                code = int(exitf.read_text().strip())
            except Exception:
                code = None
            if code is None:
                # bash 包装层可能被 codebuddy 的 killpg 连带杀掉，
                # exit 永远不落盘。用 pid 是否还存在来判断。
                try:
                    pid = int((base / "pid").read_text().strip())
                except Exception:
                    pid = 0
                if pid and not Path(f"/proc/{pid}").exists():
                    code = -9
                else:
                    continue
            result = Path(r["outdir"]) / "result.json"
            payload = None
            if result.exists():
                try:
                    payload = json.loads(result.read_text(encoding="utf-8"))
                except Exception:
                    payload = None
            if code == 0 and payload:
                conn.execute("UPDATE tasks SET status=?, result_json=?, ended_at=? WHERE id=?",
                             (payload.get("status") if payload.get("status") in
                              ("done", "blocked", "failed") else "done",
                              json.dumps(payload, ensure_ascii=False), now(), r["id"]))
                event(conn, r["id"], "finished", {"code": code})
            elif code == 0:
                conn.execute("UPDATE tasks SET status='done', ended_at=?, error=? WHERE id=?",
                             (now(), "进程正常退出但没写 result.json", r["id"]))
                event(conn, r["id"], "finished_no_result")
            else:
                log = (Path(r["outdir"]).parent / "run.log")
                lost = log.exists() and "No conversation found" in log.read_text(
                    encoding="utf-8", errors="replace")[-2000:]
                if lost and r["attempts"] < r["max_attempts"]:
                    # 会话没了：换一个新的 session_id 重新跑，避免永远 resume 失败
                    conn.execute(
                        "UPDATE tasks SET status='queued', lease_until=0, "
                        "session_id=? WHERE id=?",
                        (f'{r["name"]}-r{r["attempts"]}', r["id"]))
                    event(conn, r["id"], "session_lost_requeue")
                    conn.commit()
                    continue
                if r["attempts"] >= r["max_attempts"]:
                    conn.execute("UPDATE tasks SET status='failed', error=?, ended_at=? WHERE id=?",
                                 (f"exit={code}", now(), r["id"]))
                    event(conn, r["id"], "failed_final", {"code": code})
                else:
                    conn.execute("UPDATE tasks SET status='queued', lease_until=0 WHERE id=?",
                                 (r["id"],))
                    event(conn, r["id"], "requeue", {"code": code})
            conn.commit()
        conn.commit()
    finally:
        conn.close()
    if started and not args.quiet:
        print(f"本轮拉起 {started} 个任务")
    return 0


def cmd_retry(args) -> int:
    conn = db()
    try:
        r = conn.execute("SELECT id,attempts FROM tasks WHERE id=? OR name=?",
                         (args.task, args.task)).fetchone()
        if not r:
            print(f"没有任务 {args.task}", file=sys.stderr)
            return 1
        conn.execute("UPDATE tasks SET status='queued', attempts=0, lease_until=0, "
                     "error=NULL, ended_at=NULL WHERE id=?", (r["id"],))
        event(conn, r["id"], "manual_retry")
        conn.commit()
    finally:
        conn.close()
    print(f"已重置 {args.task} 到队列")
    return 0


def cmd_history(args) -> int:
    """任务全史：任何 AI 一屏看懂做了几次、做了什么、为什么、管理者怎么判断的。"""
    conn = db()
    try:
        r = conn.execute("SELECT * FROM tasks WHERE id=? OR name=?",
                         (args.task, args.task)).fetchone()
        if not r:
            print(f"没有任务 {args.task}", file=sys.stderr)
            return 1
        print(f"任务 #{r['id']} {r['name']} [{r['kind']}]  状态={r['status']} "
              f"尝试 {r['attempts']}/{r['max_attempts']}")
        inp = json.loads(r["input_json"] or "{}")
        g0 = (inp.get("goal") or inp.get("topic") or "")
        if g0:
            print(f"原始目标: {g0[:200]}")
        base = Path(r["outdir"]).parent if r["outdir"] else None
        gm = base / "goal.md" if base else None
        if gm and gm.exists():
            print(f"当前目标(goal.md): {gm.read_text(encoding='utf-8')[:200]}")
        if r["result_json"]:
            d = json.loads(r["result_json"])
            print(f"最终: {d.get('status')} | {d.get('summary','')[:150]}")
        elif r["error"]:
            print(f"最近 error: {r['error'][:200]}")
        print("--- 时间线 ---")
        for e in conn.execute("SELECT at, kind, payload FROM task_events "
                              "WHERE task_id=? ORDER BY id", (r["id"],)):
            pay = (e["payload"] or "")[:120]
            try:
                at = time.strftime("%m-%d %H:%M:%S", time.localtime(float(e["at"])))
            except Exception:
                at = str(e["at"])
            print(f"  {at}  {e['kind']}  {pay}")
        dj = base / "decisions.jsonl" if base else None
        if dj and dj.exists():
            print("--- 管理者决策（decisions.jsonl）---")
            for line in dj.read_text(encoding="utf-8").splitlines()[-20:]:
                try:
                    d = json.loads(line)
                    print(f"  {d.get('ts')}  {d.get('action'):<9} {str(d.get('reason'))[:110]}")
                except Exception:
                    print(" ", line[:120])
        return 0
    finally:
        conn.close()


def cmd_suspend(args) -> int:
    """主动挂起（借鉴 google/ax SuspendTask：checkpoint 后暂停）。

    与 cancel（终态不恢复）和 restart（消耗一次重试）的区别：
    - 不消耗 attempts，可无限次 resume；
    - 现场全部保留（progress.md / 会话文件），resume 后 prompt 自动带断点提示；
    - 挂起是人的显式动作，死士检查若配了 process_alive 会告警——属预期。
    """
    conn = db()
    try:
        r = conn.execute("SELECT id FROM tasks WHERE id=? OR name=?",
                         (args.task, args.task)).fetchone()
        if not r:
            print(f"没有任务 {args.task}", file=sys.stderr)
            return 1
        row = conn.execute(
            "SELECT status, worker_id, outdir FROM tasks WHERE id=?",
            (r["id"],)).fetchone()
        if row["status"] != "running":
            print(f"只有 running 任务可挂起（当前 {row['status']}）", file=sys.stderr)
            return 1
        wid = (row["worker_id"] or "")
        if ":" in wid:
            try:
                pid = int(wid.rsplit(":", 1)[1])
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, ValueError):
                pass
        outdir = Path(row["outdir"]) if row["outdir"] else None
        if outdir:
            (outdir / "SUSPENDED").write_text(
                f"{datetime.now():%Y-%m-%d %H:%M:%S} 人工挂起\n", encoding="utf-8")
        conn.execute("UPDATE tasks SET status='suspended', lease_until=0 WHERE id=?",
                     (r["id"],))
        event(conn, r["id"], "suspended")
        conn.commit()
        print(f"已挂起 {args.task}（现场保留，resume 恢复）")
        return 0
    finally:
        conn.close()


def cmd_resume(args) -> int:
    """恢复挂起的任务：回 queued，下一轮 tick 正常拉起并从断点继续。"""
    conn = db()
    try:
        r = conn.execute("SELECT id FROM tasks WHERE id=? OR name=?",
                         (args.task, args.task)).fetchone()
        if not r:
            print(f"没有任务 {args.task}", file=sys.stderr)
            return 1
        row = conn.execute("SELECT status, outdir FROM tasks WHERE id=?",
                           (r["id"],)).fetchone()
        if row["status"] != "suspended":
            print(f"只有 suspended 任务可恢复（当前 {row['status']}）", file=sys.stderr)
            return 1
        outdir = Path(row["outdir"]) if row["outdir"] else None
        if outdir:
            mark = outdir / "SUSPENDED"
            if mark.exists():
                mark.unlink()
        conn.execute("UPDATE tasks SET status='queued', lease_until=0 WHERE id=?",
                     (r["id"],))
        event(conn, r["id"], "resumed_from_suspend")
        conn.commit()
        print(f"已恢复 {args.task}（回队列，将读 progress.md 从断点继续）")
        return 0
    finally:
        conn.close()


def cmd_cancel(args) -> int:
    conn = db()
    try:
        r = conn.execute("SELECT id FROM tasks WHERE id=? OR name=?",
                         (args.task, args.task)).fetchone()
        if not r:
            print(f"没有任务 {args.task}", file=sys.stderr)
            return 1
        row = conn.execute("SELECT worker_id, outdir FROM tasks WHERE id=?",
                           (r["id"],)).fetchone()
        # 只改状态不够：进程还会继续跑、继续写产出。按 worker_id 里的 pid 精确杀。
        wid = (row["worker_id"] or "") if row else ""
        if ":" in wid:
            try:
                pid = int(wid.rsplit(":", 1)[1])
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, ValueError):
                pass
        conn.execute("UPDATE tasks SET status='cancelled', ended_at=? WHERE id=?",
                     (now(), r["id"]))
        event(conn, r["id"], "cancelled")
        conn.commit()
    finally:
        conn.close()
    print(f"已取消 {args.task}")
    return 0


def cmd_daemon(args) -> int:
    print(f"daemon 启动：db={DB} 并发={args.concurrency} 间隔={args.interval}s")
    while True:
        try:
            cmd_tick(argparse.Namespace(concurrency=args.concurrency, quiet=True))
        except Exception as exc:
            print(f"tick 异常: {exc}", file=sys.stderr)
        time.sleep(args.interval)


def main() -> int:
    p = argparse.ArgumentParser(prog="taskctl", description="几十万任务级调度器")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="加任务（--goal 一句话即可）")
    a.add_argument("--goal", help="自然语言说明要做什么（最简单）")
    a.add_argument("--repo", help="工作仓库路径")
    a.add_argument("--kind", help="任务类型，默认 generic；见 kinds")
    a.add_argument("--input", help="输入 JSON 字符串（可选）")
    a.add_argument("--input-file", help="输入 JSON 文件（可选）")
    a.add_argument("--name")
    a.add_argument("--backend", choices=["codebuddy", "knot"], default="codebuddy")
    a.add_argument("--model", default="free-model")
    a.add_argument("--workdir", default=str(HOME))
    a.add_argument("--priority", type=int, default=100)
    a.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    a.add_argument("--quiet", action="store_true")
    a.set_defaults(func=cmd_add)

    pl = sub.add_parser("plan", help="一句话自动拆成多个任务（完全不用写提示词）")
    pl.add_argument("--goal", required=True)
    pl.add_argument("--repo")
    pl.add_argument("--max-tasks", type=int, default=10)
    pl.add_argument("--timeout", type=int, default=240)
    pl.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    pl.add_argument("--backend", default="codebuddy")
    pl.add_argument("--model", default="free-model")
    pl.add_argument("--workdir", default=str(HOME))
    pl.set_defaults(func=cmd_plan)

    wk = sub.add_parser("_worker", help=argparse.SUPPRESS)
    wk.add_argument("--task-id", type=int, required=True)
    wk.add_argument("--timeout", type=int, default=LEASE_SECONDS)
    wk.set_defaults(func=cmd_worker)

    kd = sub.add_parser("kinds", help="列出可用任务类型")
    kd.set_defaults(func=cmd_kinds)

    af = sub.add_parser("add-file", help="批量导入（每行一个 JSON）")
    af.add_argument("file")
    af.set_defaults(func=cmd_add_file)

    ls = sub.add_parser("list", help="按状态分页列出")
    ls.add_argument("--status", nargs="*", default=["queued", "running"])
    ls.add_argument("--limit", type=int, default=20)
    ls.add_argument("--offset", type=int, default=0)
    ls.set_defaults(func=cmd_list)

    st = sub.add_parser("stats", help="按状态/类型聚合")
    st.set_defaults(func=cmd_stats)

    bf = sub.add_parser("brief", help="只读任务结果摘要")
    bf.add_argument("task")
    bf.set_defaults(func=cmd_brief)

    tk = sub.add_parser("tick", help="调度一轮")
    tk.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    tk.add_argument("--quiet", action="store_true")
    tk.set_defaults(func=cmd_tick)

    rt = sub.add_parser("retry")
    rt.add_argument("task")
    rt.set_defaults(func=cmd_retry)

    hh = sub.add_parser("history", help="任务全史：事件时间线 + 管理者决策")
    hh.add_argument("task")
    hh.set_defaults(func=cmd_history)

    sp = sub.add_parser("suspend", help="挂起 running 任务（不耗 attempts，现场保留）")
    sp.add_argument("task")
    sp.set_defaults(func=cmd_suspend)

    rs = sub.add_parser("resume", help="恢复挂起的任务（回队列从断点继续）")
    rs.add_argument("task")
    rs.set_defaults(func=cmd_resume)

    cc = sub.add_parser("cancel")
    cc.add_argument("task")
    cc.set_defaults(func=cmd_cancel)

    dm = sub.add_parser("daemon", help="常驻调度循环")
    dm.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    dm.add_argument("--interval", type=int, default=30)
    dm.set_defaults(func=cmd_daemon)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
