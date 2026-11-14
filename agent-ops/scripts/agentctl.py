#!/usr/bin/env python3
"""agentctl —— 用一个 agent 调度多个 CLI 子 agent（codebuddy / knot），并看护它们。

核心能力：
  dispatch  起一个后台子任务，自己指定 session id，记录会话文件绝对路径
  status    读注册表 + 进程存活 + 会话文件，输出每个子任务的状态
  locate    打印某个任务的会话文件、输出目录、日志的绝对路径
  resume    用 --resume（codebuddy）/ --sessionId（knot）续接原会话
  watch     检查挂了且未超重启上限的任务，自动 resume（可挂 cron）
  reap      清理已结束任务的 pid/exit 残留

注册表：~/.codebuddy/agentctl/registry.json
任务目录：~/.codebuddy/agentctl/<name>/{prompt.md,run.log,exit,pid,out/}

设计约束（都是实测踩过的）：
- codebuddy 必须带 `--port 0`，否则复用旧端口会 EADDRINUSE 起不来。
- 长 prompt 必须以 `--` 分隔，否则以 `-` 开头的行被当成选项（exit 1 秒退）。
- 无人值守必须 `-y`，否则权限弹窗卡死。
- 只允许 x0.00 / ≤0.15 credits 的模型（用户红线，用量太大）。
- knot 的 429 没有恢复时间通知，撞了降并发/切模型，不要原地长退避。
"""
from __future__ import annotations

import platform_util as util
import model_policy as policy

import platform_util as util

import argparse
import fcntl
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path(os.environ.get("AGENTCTL_HOME", Path.home() / ".codebuddy/agentctl"))
REGISTRY = HOME / "registry.json"
LOCK = HOME / "registry.lock"

CB_BIN = util.resolve_bin("codebuddy", "CODEBUDDY_CLI_BIN",
                       ("/usr/local/bin/codebuddy", "/opt/homebrew/bin/codebuddy"))
KNOT_BIN = util.resolve_bin("knot-cli", "KNOT_CLI_BIN",
                         ("<knot-cli 路径>",))
CB_PROJECTS = Path.home() / ".codebuddy/projects"

# 模型红线唯一权威源见 model_policy.py（与 taskctl 共用）
ALLOWED_MODELS = policy.CB_ALLOWED
DEFAULT_MAX_RESTARTS = int(os.environ.get("AGENTCTL_MAX_RESTARTS", "5"))
COOLDOWN = int(os.environ.get("AGENTCTL_COOLDOWN", "60"))


# ── 注册表 ──────────────────────────────────────────────────────────────
def _ensure_home() -> None:
    HOME.mkdir(parents=True, exist_ok=True)


def load_registry() -> dict:
    _ensure_home()
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {"tasks": {}}


def save_registry(data: dict) -> None:
    _ensure_home()
    tmp = REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, REGISTRY)


class locked_registry:
    """跨进程读写注册表，避免 watch 和 dispatch 互相覆盖。"""

    def __enter__(self):
        _ensure_home()
        self.f = open(LOCK, "a+")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        self.data = load_registry()
        return self.data

    def __exit__(self, *exc):
        save_registry(self.data)
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


# ── Stored work（借 dsh-superagent 的 Effects 设计）──────────────────
# 决策后要做的动作先写进注册表，提交后才执行；失败按 2s 起指数退避，
# 连续 3 次才转「需人工」，不因一次抖动就永久失败。
MAX_EFFECT_ATTEMPTS = 3
EFFECT_BACKOFF = (2, 4, 8, 16, 32, 60)


def enqueue(reg: dict, kind: str, name: str, payload: dict | None = None,
            seq: float | None = None) -> str:
    """把一个待执行动作写进 effects；同 kind+name 只保留一行（幂等）。"""
    # send 必须每条消息一行：用 kind:name 会把同任务的第二条覆盖掉，
    # 导致「发了 a 再发 b，b 把 a 顶掉」。launch 仍按任务唯一（幂等）。
    seq = seq if seq is not None else time.time()
    key = f"send:{name}:{int(seq * 1e6)}" if kind == "send" else f"{kind}:{name}"
    eff = reg.setdefault("effects", {}).get(key, {})
    eff.update({"kind": kind, "name": name,
                "payload": payload or {},
                "attempts": eff.get("attempts", 0),
                "next_at": 0,
                "seq": seq if seq is not None else eff.get("seq", time.time())})
    reg["effects"][key] = eff
    return key


def flush_effects(reg: dict, verbose: bool = True) -> list[str]:
    """按 seq 顺序执行到期 effect。send 保序：同一任务有未完成的 send 时跳过。

    返回本轮完成的 key 列表。调用方负责持有 registry 锁。
    """
    effects = reg.get("effects", {})
    done: list[str] = []
    # 每个任务本轮最多执行一个 send，保证「前一条没完成不投下一条」
    sent_this_round: set[str] = set()
    for key, e in sorted(effects.items(), key=lambda kv: kv[1].get("seq", 0)):
        if e.get("next_at", 0) > time.time():
            continue
        t = reg.get("tasks", {}).get(e["name"])
        if not t:
            done.append(key)
            continue
        if e["kind"] == "send":
            if e["name"] in sent_this_round:
                continue
            if alive(t.get("pid")):
                # 还在跑：并发 resume 不会被处理，30s 后再看
                e["next_at"] = time.time() + 30
                continue
        try:
            if e["kind"] == "launch":
                ok = launch_task(t, e["payload"].get("prompt", ""))
            elif e["kind"] == "send":
                ok = resume_task(t, e["payload"].get("message"))
                sent_this_round.add(e["name"])
            else:
                ok = False
        except Exception as exc:
            if verbose:
                print(f"[effect] {key} 异常: {exc}", file=sys.stderr)
            ok = False
        if ok:
            done.append(key)
            continue
        e["attempts"] = int(e.get("attempts", 0)) + 1
        if e["attempts"] >= MAX_EFFECT_ATTEMPTS:
            e["failed"] = True
            done.append(key)
            t["status"] = "awaiting-person"
            if verbose:
                print(f"[effect] {key} 连续 {e['attempts']} 次失败，转人工处理",
                      file=sys.stderr)
        else:
            wait = EFFECT_BACKOFF[min(e["attempts"] - 1, len(EFFECT_BACKOFF) - 1)]
            e["next_at"] = time.time() + wait
    for k in done:
        effects.pop(k, None)
    return done


def pending_effects_for(reg: dict, name: str) -> int:
    return sum(1 for e in reg.get("effects", {}).values() if e.get("name") == name)


# ── 基础工具 ────────────────────────────────────────────────────────────
def task_dir(name: str) -> Path:
    d = HOME / name
    (d / "out").mkdir(parents=True, exist_ok=True)
    return d


def alive(pid: int | None) -> bool:
    """平台差异统一由 platform_util.pid_exists 处理。"""
    return util.pid_exists(pid)


def read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def session_file(task: dict) -> Path | None:
    """按 session_id 找到会话文件绝对路径。

    codebuddy 的命名规则实测：~/.codebuddy/projects/<workspace-slug>/<session-id>.jsonl
    （`--session-id` 指定什么，文件名就是什么）。
    knot 没有对应的 jsonl，只能靠任务目录里的 run.log。
    """
    sid = task.get("session_id")
    backend = task.get("backend")
    if not sid:
        return None
    if backend == "codebuddy":
        hits = sorted(CB_PROJECTS.glob(f"*/{sid}.jsonl"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        return hits[0] if hits else None
    return None


def session_events(path: Path | None) -> tuple[int, str | None, str | None]:
    """会话文件是**边跑边写**的（实测 6 秒内出现，消息逐条追加），
    比 stdout 重定向可靠：后者是块缓冲，进程结束才 flush。
    返回 (事件数, 最后事件时间, 最后事件类型)。
    """
    if not path or not path.exists():
        return 0, None, None
    n = 0
    last = None
    kind = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        n += 1
        try:
            r = json.loads(line)
        except Exception:
            continue
        kind = r.get("type") or r.get("subtype") or kind
        ts = r.get("timestamp") or r.get("__timestamp")
        if isinstance(ts, (int, float)):
            last = datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts).strftime("%H:%M:%S")
        elif isinstance(ts, str):
            last = ts[11:19] if len(ts) >= 19 else ts
    return n, last, kind


def tail_session(path: Path | None, n: int = 3) -> list[str]:
    if not path or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return [ln[:200] for ln in lines[-n:]]
    except Exception:
        return []


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dur(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m}m" if h else (f"{m}m{s}s" if m else f"{s}s")


# ── dispatch ────────────────────────────────────────────────────────────
def build_cmd(task: dict, prompt: str, resume: bool) -> list[str]:
    backend = task["backend"]
    model = task["model"]
    sid = task["session_id"]
    if backend == "codebuddy":
        cmd = [CB_BIN, "-p", "--port", "0", "--output-format", "text",
               "--permission-mode", "bypassPermissions", "-y",
               "--model", model]
        if resume:
            # 2.132.0 没有 --resume-create-missing（那是 2.183.0 的参数），
            # 会话不存在时会秒退；由 do_resume 检测后降级新建。
            cmd += ["--resume", sid]
        else:
            cmd += ["--session-id", sid]
        # `--` 必须保留：长 prompt 中以 - 开头的行会被当成选项。
        cmd += ["--", prompt]
        return cmd
    # knot：--sessionId 指定会话，续接也用它
    return [KNOT_BIN, "chat", "--no-update", "--output-format", "text",
            "--model", model, "--sessionId", sid, "-p", prompt]


def spawn(task: dict, prompt: str, resume: bool, save_prompt: bool = True) -> int:
    d = task_dir(task["name"])
    prompt_file = d / "prompt.md"
    # send 追加的临时消息不能覆盖原任务 prompt，否则下次 resume 会发错内容。
    if save_prompt:
        prompt_file.write_text(prompt, encoding="utf-8")
    log = d / "run.log"
    pidf = d / "pid"
    exitf = d / "exit"
    # 不能 unlink：本机沙箱的「安全删除」shim 会尝试跨设备移入 Trash，
    # 报 Invalid cross-device link 并递归到 RecursionError。清空即可。
    for f in (pidf, exitf):
        f.write_text("", encoding="utf-8")

    cmd = build_cmd(task, prompt, resume)
    # 用 bash 包一层写 pid / exit：父进程退出后仍能拿到退出码。
    # 记录死因：被信号杀时 bash 不会走到 echo $?，用 trap 把信号写进 exit，
    # 否则只能看到「run.log 空、exit 空、状态 queued」，无从判断是崩溃还是被杀。
    inner = (f"echo $$ > {shlex.quote(str(pidf))}; "
             f"trap 'rc=$?; echo \"signal-or-exit:$rc\" > {shlex.quote(str(exitf))}' EXIT; "
             f"{' '.join(shlex.quote(c) for c in cmd)} "
             f">> {shlex.quote(str(log))} 2>&1; "
             f"echo $? > {shlex.quote(str(exitf))}")
    with open(log, "a", encoding="utf-8") as lf:
        lf.write(f"\n===== {'resume' if resume else 'start'} {now_iso()} =====\n")
    proc = subprocess.Popen(
        ["bash", "-c", inner],
        cwd=task.get("workdir") or str(Path.home()),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=dict(os.environ, AGENTCTL_TASK=task["name"]),
    )
    return proc.pid


def launch_task(task: dict, prompt: str) -> bool:
    """真正起一个任务（供 effect 调用）。成功返回 True。

    秒退自愈：新建时若复用旧 session_id，而磁盘上已有同名会话文件，
    codebuddy 会直接退出（rc=0、run.log 无内容），状态停在 queued，
    形成「watch 反复续接但永远起不来」的死锁（实测三个任务卡 13 分钟）。
    这里 spawn 后等 3 秒探活，不活就换新 session_id 重试一次。
    """
    if not (prompt or "").strip():
        return False
    pid = spawn(task, prompt, resume=False)
    task["pid"] = pid
    task["started_at"] = now_iso()
    task["status"] = "working"
    time.sleep(3)
    if alive(pid):
        return True
    old_sid = task.get("session_id")
    task["session_id"] = f"{task['name']}-{int(time.time())}"
    print(f"[launch] {task['name']} 秒退，session_id {old_sid} → {task['session_id']}，重试",
          file=sys.stderr)
    pid = spawn(task, prompt, resume=False)
    task["pid"] = pid
    time.sleep(2)
    if alive(pid):
        return True
    print(f"[launch] {task['name']} 换 id 后仍秒退，交回 effect 退避重试", file=sys.stderr)
    task["status"] = "queued"
    return False


def resume_task(task: dict, message: str | None = None) -> bool:
    """续接任务（供 effect 调用）。message 为空则用原 prompt。"""
    return do_resume(task, extra_prompt=message) == 0


def cmd_dispatch(args) -> int:
    if args.model not in ALLOWED_MODELS:
        print(f"拒绝：模型 {args.model!r} 超出红线（只允许 {sorted(ALLOWED_MODELS)}）",
              file=sys.stderr)
        return 2
    prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file \
        else (args.prompt or "")
    if not prompt.strip():
        print("拒绝：prompt 为空", file=sys.stderr)
        return 2

    sid = args.session_id or f"{args.name}-{int(time.time())}"
    task = {
        "name": args.name,
        "backend": args.backend,
        "model": args.model,
        "session_id": sid,
        "workdir": str(Path(args.workdir).expanduser().resolve()),
        "outdir": str(task_dir(args.name) / "out"),
        "status": "running",
        "restarts": 0,
        "max_restarts": args.max_restarts,
        "created_at": now_iso(),
        "started_at": now_iso(),
        "pid": None,
    }
    with locked_registry() as reg:
        old = reg["tasks"].get(args.name)
        # 幂等：同名任务还活着就拒绝，避免两个进程抢同一目录/会话。
        if old and alive(old.get("pid")):
            print(f"拒绝：{args.name} 已在跑（pid={old['pid']}）。"
                  f"要追加指令用 send，要重跑先 stop。", file=sys.stderr)
            return 4
        reg["tasks"][args.name] = task
        # stored work：先入库，提交后才真正拉起。
        enqueue(reg, "launch", args.name, {"prompt": prompt})
        flush_effects(reg)
        t = reg["tasks"][args.name]
        left = pending_effects_for(reg, args.name)
    print(f"已派发 {args.name} | {args.backend}/{args.model} | pid={t.get('pid')}")
    if left:
        print(f"（{left} 个动作待重试，watch 会继续）")
    print(f"会话: {sid}")
    print(f"目录: {task_dir(args.name)}")
    return 0


# ── status / locate / logs ──────────────────────────────────────────────
def inspect(task: dict, effects: int = 0) -> dict:
    pid = task.get("pid")
    d = task_dir(task["name"])
    exit_code = read_int(d / "exit")
    sf = session_file(task)
    running = alive(pid) and exit_code is None
    # 状态从「存了什么」推导，不只看 pid（借 dsh Ticket stages 的思路）：
    #   queued          还有待执行动作
    #   working         进程活着
    #   done            正常退出且有结论事件
    #   idle            正常退出但还没结论（等下一条消息）
    #   failed          异常退出且重试未耗尽
    #   awaiting-person 重试耗尽，需要人看
    if task.get("status") == "awaiting-person":
        status = "awaiting-person"
    elif effects:
        status = "queued"
    elif running:
        status = "working"
    elif exit_code == 0:
        status = "done"
    elif exit_code is None:
        status = "queued"
    else:
        status = "failed"
    started = task.get("started_at")
    try:
        elapsed = time.time() - datetime.fromisoformat(started).timestamp()
    except Exception:
        elapsed = 0
    log = d / "run.log"
    events, last_event, last_kind = session_events(sf)
    if status == "done" and last_kind not in ("result", "message"):
        status = "idle"
    return {
        **task,
        "status": status,
        "elapsed": dur(elapsed),
        "session_path": str(sf) if sf else (str(log) if task["backend"] == "knot" else None),
        "session_events": events,
        "last_event_at": last_event,
        "last_event_type": last_kind,
        "log": str(log),
        "log_size": log.stat().st_size if log.exists() else 0,
        "exit_code": exit_code,
    }


def cmd_status(args) -> int:
    reg = load_registry()
    tasks = reg.get("tasks", {})
    if not tasks:
        print("没有已注册的任务。用 dispatch 起一个。")
        return 0
    rows = [inspect(t, pending_effects_for(reg, t["name"])) for t in tasks.values()]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"{'任务':<18}{'后端/模型':<20}{'状态':<9}{'运行':<8}"
          f"{'事件/最后事件':<18}{'会话文件'}")
    for r in rows:
        ev = f"{r['session_events']}/{r['last_event_at'] or '-'}"
        print(f"{r['name']:<18}{r['backend']+'/'+r['model']:<20}{r['status']:<9}"
              f"{r['elapsed']:<8}{ev:<18}{r.get('session_path') or '-'}")
    return 0


def cmd_locate(args) -> int:
    reg = load_registry()
    t = reg.get("tasks", {}).get(args.name)
    if not t:
        print(f"没有任务 {args.name}", file=sys.stderr)
        return 1
    r = inspect(t, pending_effects_for(reg, t["name"]))
    print(f"任务      : {r['name']}")
    print(f"会话 ID   : {r['session_id']}")
    print(f"会话文件  : {r.get('session_path') or '(knot 无 jsonl，看 run.log)'}")
    print(f"输出目录  : {r['outdir']}")
    print(f"日志      : {r['log']}")
    print(f"工作目录  : {r['workdir']}")
    print(f"状态      : {r['status']}  pid={r.get('pid')}  运行 {r['elapsed']}")
    print(f"会话事件  : {r['session_events']} 条，最后 {r['last_event_at'] or '-'}"
          f"（{r['last_event_type'] or '-'}）")
    return 0


def cmd_brief(args) -> int:
    """只读 result.json 的摘要字段；没有就回退最后 20 行 run.log。

    这是给主 agent 控制上下文用的：一个子任务跑半小时能产出几千行日志，
    主 agent 只需要 status/summary/evidence/question 这几个字段。
    """
    reg = load_registry()
    t = reg.get("tasks", {}).get(args.name)
    if not t:
        print(f"没有任务 {args.name}", file=sys.stderr)
        return 1
    outdir = Path(t.get("outdir") or (task_dir(args.name) / "out"))
    rj = outdir / "result.json"
    if rj.exists():
        try:
            d = json.loads(rj.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"result.json 解析失败: {exc}", file=sys.stderr)
            d = None
        if isinstance(d, dict):
            print(f"任务     : {t['name']}")
            print(f"状态     : {d.get('status')}")
            print(f"摘要     : {d.get('summary')}")
            for e in (d.get("evidence") or [])[:5]:
                print(f"证据     : {e}")
            if d.get("question"):
                print(f"待决策   : {d['question']}")
            if d.get("next"):
                print(f"下一步   : {d['next']}")
            return 0
    # 还没写 result.json：只给最后 20 行，不给全文
    log = task_dir(args.name) / "run.log"
    print(f"任务 {args.name}: 还没有 result.json，回退最后 {args.n} 行日志")
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n".join(lines[-args.n:]))
    return 0


def cmd_logs(args) -> int:
    reg = load_registry()
    t = reg.get("tasks", {}).get(args.name)
    if not t:
        print(f"没有任务 {args.name}", file=sys.stderr)
        return 1
    log = task_dir(args.name) / "run.log"
    if not log.exists():
        print("还没有日志")
        return 1
    text = log.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(text[-args.n:]))
    return 0


# ── resume / watch / reap ───────────────────────────────────────────────
def do_resume(task: dict, extra_prompt: str | None = None) -> int:
    d = task_dir(task["name"])
    prompt_file = d / "prompt.md"
    prompt = extra_prompt or (prompt_file.read_text(encoding="utf-8")
                              if prompt_file.exists() else task.get("prompt", ""))
    if not prompt.strip():
        print(f"{task['name']}: 没有可用的 prompt，跳过", file=sys.stderr)
        return 1
    pid = spawn(task, prompt, resume=True, save_prompt=(extra_prompt is None))
    # codebuddy 2.132.0 没有 --resume-create-missing：会话不存在会秒退。
    # 等 3 秒看是否还活着，秒退就降级为「用同一个 session_id 新建」。
    time.sleep(3)
    if not alive(pid):
        log_text = (d / "run.log").read_text(encoding="utf-8", errors="replace")[-1500:]             if (d / "run.log").exists() else ""
        if any(k in log_text for k in ("No conversation", "not found", "unknown",
                                       "Invalid session", "no session")):
            print(f"{task['name']}: 原会话不存在，降级新建", file=sys.stderr)
            pid = spawn(task, prompt, resume=False)
    task["pid"] = pid
    task["started_at"] = now_iso()
    task["restarts"] = int(task.get("restarts", 0)) + 1
    task["status"] = "running"
    return 0


def cmd_resume(args) -> int:
    with locked_registry() as reg:
        t = reg["tasks"].get(args.name)
        if not t:
            print(f"没有任务 {args.name}", file=sys.stderr)
            return 1
        if alive(t.get("pid")):
            print(f"{args.name} 还在跑（pid={t['pid']}），不重复拉起")
            return 0
        enqueue(reg, "launch", args.name, {"prompt": ""})
        flush_effects(reg)
    print(f"已续接 {args.name}")
    return 0


def cmd_send(args) -> int:
    """给已有任务追加一条消息并续接。

    实测结论：会话**结束后** resume 追加新指令可靠（能正常返回并写入
    jsonl）；会话**还在跑**时并发 resume 只把消息 append 进 jsonl，
    原进程不会处理它。所以这里在跑就拒绝，让调用方等结束。
    """
    with locked_registry() as reg:
        t = reg["tasks"].get(args.name)
        if not t:
            print(f"没有任务 {args.name}", file=sys.stderr)
            return 1
        if alive(t.get("pid")):
            print(f"{args.name} 还在跑（pid={t['pid']}）。并发 resume 不可靠："
                  f"消息会写进会话但不会被处理。等它结束再 send，或先 kill。",
                  file=sys.stderr)
            return 3
        # stored work：消息入队，flush 按 seq 保序投递；失败会重试到 3 次。
        enqueue(reg, "send", args.name, {"message": args.message})
        flush_effects(reg)
    print(f"已追加消息并续接 {args.name}")
    return 0


def cmd_watch(args) -> int:
    acted = []
    with locked_registry() as reg:
        # 先把待重试的 launch/send 执行掉（stored work）。
        flushed = flush_effects(reg, verbose=not args.quiet)
        for name, t in reg.get("tasks", {}).items():
            if t.get("enabled") is False:
                continue
            r = inspect(t, pending_effects_for(reg, name))
            if r["status"] in ("working", "done", "queued", "awaiting-person"):
                continue
            if int(t.get("restarts", 0)) >= int(t.get("max_restarts", DEFAULT_MAX_RESTARTS)):
                continue
            last = t.get("started_at")
            try:
                since = time.time() - datetime.fromisoformat(last).timestamp()
            except Exception:
                since = COOLDOWN + 1
            if since < COOLDOWN:
                continue
            enqueue(reg, "launch", name, {"prompt": ""})
            flush_effects(reg)
            acted.append(name)
    if acted:
        print("已续接:", ", ".join(acted))
    elif not args.quiet:
        print("没有需要续接的任务")
    return 0


def cmd_reap(args) -> int:
    n = 0
    with locked_registry() as reg:
        for t in reg.get("tasks", {}).values():
            pid = t.get("pid")
            if pid and not alive(pid):
                t["pid"] = None
                n += 1
    print(f"清理 {n} 个已结束任务的 pid")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="agentctl", description="多 CLI 子 agent 编排与看护")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dispatch", help="派发一个后台子任务")
    d.add_argument("--name", required=True)
    d.add_argument("--backend", choices=["codebuddy", "knot"], default="codebuddy")
    d.add_argument("--model", default="free-model")
    d.add_argument("--prompt-file")
    d.add_argument("--prompt")
    d.add_argument("--workdir", default=str(Path.home()))
    d.add_argument("--session-id")
    d.add_argument("--max-restarts", type=int, default=DEFAULT_MAX_RESTARTS)
    d.set_defaults(func=cmd_dispatch)

    s = sub.add_parser("status", help="列出所有任务状态")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    lo = sub.add_parser("locate", help="打印会话文件/输出目录/日志绝对路径")
    lo.add_argument("name")
    lo.set_defaults(func=cmd_locate)

    bf = sub.add_parser("brief", help="只读 result.json 摘要（控制主上下文）")
    bf.add_argument("name")
    bf.add_argument("-n", type=int, default=20, help="没有 result.json 时回退多少行")
    bf.set_defaults(func=cmd_brief)

    lg = sub.add_parser("logs", help="看任务日志")
    lg.add_argument("name")
    lg.add_argument("-n", type=int, default=40)
    lg.set_defaults(func=cmd_logs)

    sd = sub.add_parser("send", help="给已结束的任务追加一条消息并续接")
    sd.add_argument("name")
    sd.add_argument("message")
    sd.set_defaults(func=cmd_send)

    r = sub.add_parser("resume", help="续接一个任务")
    r.add_argument("name")
    r.set_defaults(func=cmd_resume)

    w = sub.add_parser("watch", help="检查并续接挂掉的任务（可挂 cron）")
    w.add_argument("--quiet", action="store_true")
    w.set_defaults(func=cmd_watch)

    rp = sub.add_parser("reap", help="清理已结束任务的 pid")
    rp.set_defaults(func=cmd_reap)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
