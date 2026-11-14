#!/usr/bin/env python3
"""模型监督模型 · agentctl 后端。

为什么单独一个文件而不是改 supervisor.py：
  supervisor.py 的 rows 是 taskctl 的 sqlite Row，决策执行依赖那些字段；
  而 agentctl 的任务只存在于目录 + 会话 jsonl 里，没有数据库。
  硬塞进去会把两套模型混在一起，改坏现有 taskctl 监督。
  所以：**复用** supervisor 的提示词与模型调用，**只换**快照来源和动作执行。

快照来源：~/.codebuddy/agentctl/<name>/
  pid / exit / prompt.md / progress.md / run.log / out/
  会话 jsonl（事件数与最后事件时间）

动作执行：
  continue  : 不动
  nudge     : 写 <taskdir>/guidance.md（供下轮续接注入；运行中的任务不能插话）
  restart   : 进程已死且无 exit 才 resume；活着不动
  escalate  : 写 <taskdir>/escalate.md，等人工
  finish    : 不动，仅在日志记录

用法：
  python3 supervise_agents.py snapshot     # 只看快照，不调模型
  python3 supervise_agents.py once         # 跑一次
  python3 supervise_agents.py daemon --interval 1800
"""
from __future__ import annotations

import platform_util as util

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import supervisor as S          # 复用 PROMPT / ask_model / SUPERVISOR_MODEL
import agentctl as A            # 复用 registry 与 session_file，避免自己猜会话路径

AGENT_ROOT = Path(os.environ.get('AGENTCTL_ROOT', Path.home() / '.codebuddy/agentctl'))
CB_BIN = util.resolve_bin('codebuddy', 'CODEBUDDY_CLI_BIN',
                       ('/usr/local/bin/codebuddy', '/opt/homebrew/bin/codebuddy'))
PROJ_ROOT = Path(os.environ.get('CODEBUDDY_PROJECTS',
                                Path.home() / '.codebuddy/projects'))
LAST_ASK = Path('/tmp/agentctl_supervisor_last_ask.json')
FORCE_ASK_EVERY = int(os.environ.get('SUPERVISOR_FORCE_ASK', '1800'))
MIN_IDLE_TO_ASK = int(os.environ.get('SUPERVISOR_MIN_IDLE', '600'))


def _tail(p, n=4):
    try:
        ls = Path(p).read_text(encoding='utf-8', errors='replace').splitlines()
        return [x[:200] for x in ls[-n:]]
    except OSError:
        return []


def _session_stats(task, taskdir):
    """用 agentctl 官方 session_file 定位会话，统计事件数与最近工具调用。

    自己按前缀 glob 会全部指到最新那个 jsonl（实测四个任务都显示 118 事件），
    必须走 registry 里的 session_id。
    """
    f = A.session_file(task)
    if not f or not Path(f).exists():
        return 0, -1, ''
    n = 0
    last_tool = ''
    last_ts = 0
    try:
        for line in Path(f).open(encoding='utf-8', errors='ignore'):
            n += 1
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get('type') == 'function_call':
                a = d.get('arguments')
                if isinstance(a, str):
                    try:
                        a = json.loads(a)
                    except Exception:
                        a = {}
                brief = ''
                if isinstance(a, dict):
                    for k in ('command', 'file_path', 'path', 'pattern'):
                        if k in a:
                            brief = f"{k}={str(a[k])[:60]}"
                            break
                last_tool = f"{d.get('name')}({brief})"
            ts = d.get('timestamp')
            if isinstance(ts, (int, float)) and ts > 1e12:
                last_ts = max(last_ts, ts / 1000)
    except OSError:
        pass
    idle = int(time.time() - last_ts) if last_ts else -1
    return n, idle, last_tool


def collect():
    """从 agentctl registry 取任务，只保留未收尾的（有 pid 或无 exit）。"""
    reg = A.load_registry()
    out = []
    for name, task in (reg.get('tasks') or {}).items():
        d = A.task_dir(name)
        pid = A.read_int(d / 'pid') or 0
        alive = A.alive(pid)
        exitc = (d / 'exit').read_text().strip() if (d / 'exit').exists() else ''
        finished = (d / 'finished.md').exists()
        # 已收尾 / 已转人工的跳过：awaiting-person 是 agentctl 的终态，
        # 再让监督模型判一次是浪费调用，且会反复给同一任务发指令。
        if finished or (d / 'escalate.md').exists():
            continue
        if task.get('status') == 'awaiting-person':
            continue
        # 已退出且已收尾的跳过；退出了但没 finish 的仍要看（可能异常退出）
        if not alive and exitc and finished:
            continue
        # 一行式探针/测试任务不监督：它们没有产出契约，监督只会反复报「无新事件」
        if name.startswith('probe') or name.startswith('demo'):
            continue
        # 已正常退出（exit 非空且为 0）且会话超过 5 分钟无新事件 → 视为完成，
        # 不再触发「无新事件」告警（此前 probe 因此反复触发、模型输出 null）。
        if not alive and exitc.strip() and 'signal-or-exit:0' in exitc and idle > 300:
            continue
        n_ev, idle, last_tool = _session_stats(task, d)
        prog = d / 'progress.md'
        prog_lines = 0
        if prog.exists():
            prog_lines = prog.read_text(encoding='utf-8', errors='replace').count('\n')
        out.append({
            'name': name, 'dir': str(d), 'pid': pid, 'alive': alive,
            'exit': exitc, 'events': n_ev, 'idle': idle,
            'last_tool': last_tool, 'prog_lines': prog_lines,
            'missing_progress': prog_lines == 0,
            'backend': task.get('backend', ''),
        })
    return out


def build_snapshot(items):
    if not items:
        return '(没有 agentctl 任务)'
    blocks = []
    for t in items:
        prog = ['  ' + x for x in _tail(Path(t['dir']) / 'progress.md')] or ['  (无 progress.md)']
        blocks.append('\n'.join([
            f"### agentctl 任务 [{Path(t['dir']).name}]",
            f"task_name: {t['name']}",
            f"进程存活={t['alive']} exit={t['exit'] or '-'} 会话事件={t['events']} "
            f"最后事件距今={t['idle']}s",
            f"最近工具调用: {t['last_tool'] or '-'}",
            f"progress_lines={t['prog_lines']}"
            + ('（**缺失：上下文压缩后无法恢复，必须要求它先落盘**）'
               if t['missing_progress'] else ''),
            'progress.md 尾:', *prog,
        ]))
    return '\n\n'.join(blocks)


PROMPT = S.PROMPT + """

【硬规则 · 优先于上面的判断要点】
快照里某任务出现「**缺失：上下文压缩后无法恢复**」，且 `会话事件` ≥ 20：
- action **必须是 `nudge`**，不能判 continue；
- guidance 必须明确要求它「立刻把已确认的现状写进 progress.md」，
  内容至少包含：已读到哪些文件、已核对出哪些数据、已排除哪些路径、下一步要做什么；
- 理由：跑了几十个事件仍不落盘，上下文一压缩后续会话只能重新探查，
  实测三个任务各浪费 30~50 个事件在还原上下文。这不是「推理中正常表现」，
  是必须纠正的浪费。

同理，`progress_lines` 超过 300 行的任务，nudge 要求它做全局重写（先归档原文）。
"""


def ask_model(snapshot):
    """用扩展后的 PROMPT 调监督者（supervisor.ask_model 用的是它自己的 PROMPT）。"""
    prompt = PROMPT.replace('{snapshot}', snapshot)
    cmd = [CB_BIN, '-p', '--port', '0', '--output-format', 'text',
           '--permission-mode', 'bypassPermissions', '-y',
           '--model', S.SUPERVISOR_MODEL,
           '--session-id', f'supagent-{int(time.time())}', '--', prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print('[supervise_agents] 监督者超时，本轮不动', file=sys.stderr)
        return None
    out = (r.stdout or '').strip()
    if not out or '"type":"error"' in out or 'Plugin runtime refresh' in out:
        print(f'[supervise_agents] 监督者无有效输出: {out[:120]}', file=sys.stderr)
        return None
    import re as _re
    m = _re.search(r'\[.*\]', out, _re.S)
    if not m:
        print(f'[supervise_agents] 无 JSON 数组: {out[:120]}', file=sys.stderr)
        return None
    try:
        return json.loads(m.group(0))
    except Exception as e:
        print(f'[supervise_agents] JSON 解析失败: {e}', file=sys.stderr)
        return None


def should_ask(items):
    if not items:
        return False, '没有任务'
    last = 0
    try:
        last = json.loads(LAST_ASK.read_text()).get('ts', 0)
    except Exception:
        pass
    if time.time() - last >= FORCE_ASK_EVERY:
        return True, f'定时监督到期({FORCE_ASK_EVERY}s)'
    for t in items:
        if t['missing_progress'] and t['events'] > 20:
            return True, f"{t['name']} 已跑 {t['events']} 事件仍无 progress.md"
        if t['idle'] >= MIN_IDLE_TO_ASK:
            return True, f"{t['name']} 超过 {MIN_IDLE_TO_ASK}s 无新事件"
    return False, '都在正常推进'


def apply_actions(items, decisions):
    by_name = {t['name']: t for t in items}
    log = []
    for d in decisions or []:
        name = str(d.get('task', '')).strip()
        act = str(d.get('action', 'continue')).strip()
        reason = str(d.get('reason', ''))[:120]
        guid = str(d.get('guidance', ''))[:600]
        t = by_name.get(name)
        if not t:
            log.append(f'  跳过未知任务 {name}')
            continue
        dpath = Path(t['dir'])
        if act == 'nudge':
            old = (dpath / 'guidance.md').read_text(encoding='utf-8', errors='replace') \
                if (dpath / 'guidance.md').exists() else ''
            if guid and guid in old:
                log.append(f'  nudge {name}: 与上次相同，跳过')
                continue
            (dpath / 'guidance.md').write_text(
                f'# 监督者指令 {time.strftime("%Y-%m-%d %H:%M:%S")}\n{guid}\n', encoding='utf-8')
            log.append(f'  nudge {name}: {guid[:60]}')
        elif act == 'restart':
            if t['alive']:
                log.append(f'  restart {name}: 进程还活着，改为只写 guidance 不杀')
                (dpath / 'guidance.md').write_text(
                    f'# 监督者指令 {time.strftime("%Y-%m-%d %H:%M:%S")}\n{guid}\n',
                    encoding='utf-8')
            else:
                r = subprocess.run([sys.executable, os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), 'agentctl.py'),
                    'resume', name], capture_output=True, text=True, timeout=120,
                    env={**os.environ, 'CODEBUDDY_CLI_BIN': CB_BIN})
                log.append(f'  restart {name}: {(r.stdout or r.stderr).strip()[:60]}')
        elif act == 'escalate':
            (dpath / 'escalate.md').write_text(
                f'# 需人工 {time.strftime("%Y-%m-%d %H:%M:%S")}\n{reason}\n{guid}\n',
                encoding='utf-8')
            log.append(f'  escalate {name}: {reason}')
        elif act == 'finish':
            (dpath / 'finished.md').write_text(reason, encoding='utf-8')
            log.append(f'  finish {name}: {reason}')
        else:
            log.append(f'  continue {name}')
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['snapshot', 'once', 'daemon'], nargs='?',
                    default='once')
    ap.add_argument('--interval', type=int, default=1800)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    if a.mode == 'daemon':
        while True:
            items = collect()
            ask, why = should_ask(items)
            if ask or a.force:
                snap = build_snapshot(items)
                dec = ask_model(snap)
                print(f'[{time.strftime("%H:%M:%S")}] 触发({why}) 决策 {len(dec or [])} 条',
                      flush=True)
                for l in apply_actions(items, dec):
                    print(l, flush=True)
                LAST_ASK.write_text(json.dumps({'ts': time.time()}))
            time.sleep(a.interval)
        return

    items = collect()
    snap = build_snapshot(items)
    if a.mode == 'snapshot':
        print(snap)
        return
    ask, why = should_ask(items)
    print(f'  触发判断: ask={ask} ({why})')
    if not (ask or a.force):
        print('  不调模型')
        return
    dec = ask_model(snap)
    print(f'  监督者决策: {json.dumps(dec, ensure_ascii=False)[:400]}')
    for l in apply_actions(items, dec or []):
        print(l)
    LAST_ASK.write_text(json.dumps({'ts': time.time()}))


if __name__ == '__main__':
    main()
