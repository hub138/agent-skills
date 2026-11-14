#!/usr/bin/env python3
"""模型监督模型 · 脚本任务后端。

为什么需要第三个后端：
  - `supervisor.py`  只认 taskctl 的 sqlite tasks 表
  - `supervise_agents.py` 只认 agentctl 的 agent 目录
  - 但项目里真正在跑的往往是一堆 **cron 脚本**（批量审判、补输入、巡检），
    它们没有 agent、没有 taskctl 记录，前两个后端都看不见 → 完全盲区。

  脚本任务的失败形态和 agent 不同：不是「进程死了」，而是
    「进程活着但产出为零」「连续几批全是限流失败」「成功数卡住不涨」。
  这些只能靠读日志 + 库指标判断，正是模型该做的活。

配置：jobs.yaml（或 --config 指定），每项描述一个脚本任务怎么观测。
输出：ALERTS.md（有异常时写）+ 退出码 0/1（1=发现需处理的问题）。

用法:
  python3 supervise_jobs.py --config jobs.yaml
  python3 supervise_jobs.py --config jobs.yaml --dry   # 只看快照不调模型
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# 监督类调用必须走 knot，不走 codebuddy：
# 实测 codebuddy -p 光启动就 58 秒，多实例并发时直接卡死（>5 分钟无输出）；
# knot-cli 同样一句话 8 秒。差 7 倍，且 knot 是免费池。
KNOT_BIN = os.environ.get('KNOT_CLI_BIN',
                          '<knot-cli 路径>')
SUPERVISOR_MODEL = os.environ.get('SUPERVISOR_MODEL_KNOT') or os.environ.get('SUPERVISOR_MODEL') or os.environ.get('WORKER_MODEL', 'default')
TIMEOUT = int(os.environ.get('SUPERVISOR_TIMEOUT', '180'))

PROMPT = '''你是批量脚本任务的**监督者**。

**重要：下面的快照已经包含全部所需信息。不要发起任何工具调用、不要查找文件、
不要读日志——直接基于快照文本判断并输出 JSON。**
（实测：不加这句，模型会输出「我需要先找到这些 cron 脚本的状态快照」「让我搜索包含
 task_name 的文件」，然后被截断，一行 JSON 都没有。）

下面是几个 cron 脚本的最新状态快照。
它们不是 agent，失败形态也不同：进程可能活着但**产出为零**、连续几批全是限流失败、
成功数卡住不涨。请判断每个任务是否正常。

判断要点：
- 「正常」：产出数在涨、成功率稳定、日志末尾有新的判定/结果行
- 「限流恶化」：最近几批失败占比明显上升（如 >30%），吞吐下降
- 「产出停滞」：进程活着但产出数连续多批不涨
- 「卡在同一处」：日志末尾反复同样报错或同一条记录
- 「已完成」：**产出计数已达总数**（快照里会标「已完成」）。
  此时日志末尾可能是历史空结果行（如 `[p1_trial] {}`），**不要因此判 alert**——
  那是任务收尾后 cron 反复空跑留下的，不是卡住。

对每个任务给一个动作。**`task` 必须原样照抄快照里的 `task_name:` 值，
不许自己编任务名、不许新增快照里没有的任务**（实测模型会编出 daily-report-cron 这种
不存在的任务，导致决策无法执行）：
[{"task":"名字","action":"ok|warn|alert|done",
  "reason":"≤80字，必须引用快照里的具体数字",
  "advice":"给运维/开发者的一句话建议，ok 时留空"}]

纪律：
- 拿不准就 ok，不要凭感觉报警。
- reason 必须有数字，不许写「看起来正常」。
只输出 JSON 数组。不许输出任何解释文字。

=== 状态快照（全部信息都在这里，task_name 必须照抄以下值）===
{snapshot}'''
if '{snapshot}' not in PROMPT:
    raise SystemExit('PROMPT 缺 {snapshot} 占位符：快照不会被插入，模型会凭空编造任务')

# 默认任务定义：怎么从日志/库里取「产出」指标
DEFAULT_JOBS = {
    'p1_trial': {
        'log': 'p1_trial.log',
        'grep': r'^\[p1_trial\]',
        'db': "SELECT count(*) FROM p1_trial",
        'total': "SELECT count(DISTINCT sha) FROM commit_verdict WHERE level='P1'",
        'expect': 'P1 审判逐批产出结论',
    },
    'reach_refine': {
        'log': 'reach_refine.log',
        'grep': r'→',
        'db': "SELECT count(*) FROM judge_condition",
        'total': ("SELECT count(*) FROM deep_reach WHERE reachability LIKE '已建立%'"),
        'expect': '补可达已建立条目的端到端输入',
    },
    'deep_all': {
        'log': 'deep_all.log',
        'grep': r'→',
        'db': "SELECT count(*) FROM deep_reach",
        'total': "SELECT count(DISTINCT sha) FROM commit_verdict WHERE level='P0'",
        'expect': '深度可达分析',
    },
}


def tail_grep(path, pattern, n=6):
    """取日志里匹配 pattern 的最后 n 行。"""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    try:
        for line in p.open(encoding='utf-8', errors='ignore'):
            if re.search(pattern, line):
                out.append(line.rstrip()[:200])
    except OSError:
        pass
    return out[-n:]


def db_count(sql, dbfile):
    try:
        c = sqlite3.connect(dbfile, timeout=30)
        r = c.execute(sql).fetchone()
        c.close()
        return r[0] if r else None
    except Exception:
        return None


def proc_alive(pattern):
    try:
        r = subprocess.run(['pgrep', '-f', pattern], capture_output=True, text=True, timeout=8)
        return bool(r.stdout.strip())
    except Exception:
        return False


def build_snapshot(jobs, base):
    blocks = []
    for name, cfg in jobs.items():
        if not cfg.get('enabled', True):
            continue
        log = os.path.join(base, cfg.get('log', ''))
        have_log = os.path.exists(log)
        mtime = ''
        if have_log:
            mtime = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(log)))
        cnt = db_count(cfg['db'], cfg['db_file']) if cfg.get('db') else None
        tot = db_count(cfg['total'], cfg['db_file']) if cfg.get('total') else None
        done = (cnt is not None and tot is not None and tot > 0 and cnt >= tot)
        lines = tail_grep(log, cfg.get('grep', '.')) if have_log else []
        alive = proc_alive(cfg.get('proc', '')) if cfg.get('proc') else None
        body = [f"### 脚本任务 [{name}]",
                f"task_name: {name}",
                f"作用: {cfg.get('expect', '')}",
                f"日志: {cfg.get('log')} 最后更新 {mtime or '不存在'}",
                f"产出计数: {cnt if cnt is not None else '（未配置）'}"
            + (f" / 总数 {tot}" if tot is not None else '')
            + ('  ← **已完成**（产出达总数，日志末尾可能是历史空行，不要当异常）' if done else ''),
                f"进程存活: {alive if alive is not None else '（不检查）'}",
                '日志末尾:']
        body += [f'  {x}' for x in lines] if lines else ['  （无匹配行）']
        blocks.append('\n'.join(body))
    return '\n\n'.join(blocks)


def ask(snapshot):
    prompt = PROMPT.replace('{snapshot}', snapshot)
    cmd = [KNOT_BIN, 'chat', '--no-update', '--output-format', 'text',
           '--model', SUPERVISOR_MODEL, '-p', prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        print('[supervise_jobs] 监督者超时', file=sys.stderr)
        return None
    out = (r.stdout or '').strip()
    # knot 会附加 requestID/sessionID 行，解析前剔掉
    out = re.sub(r'^(requestID|sessionID):.*$', '', out, flags=re.M).strip()
    if not out or 'too many requests' in out.lower() or '"code":429' in out:
        print(f'[supervise_jobs] 无有效输出: {out[:120]}', file=sys.stderr)
        return None
    # knot 会在前面加 [任务规划中] 之类的中文方括号标签，直接 re.search(r'\[.*\]')
    # 会先匹配到它。改为找所有 [...] 片段，取第一个含 "task" 字段的。
    # 必须括号配对扫描，不能用正则：
    # reason 文本里可能含「[76/76]」这种方括号，非贪婪 \[.*?\] 会提前截断，
    # 贪婪 \[.*\] 又会吞掉后面的内容。实测就栽在这里。
    frag = ''
    for st in [i for i, ch in enumerate(out) if ch == '[']:
        depth = 0
        for j in range(st, len(out)):
            if out[j] == '[':
                depth += 1
            elif out[j] == ']':
                depth -= 1
                if depth == 0:
                    cand = out[st:j + 1]
                    if '"task"' in cand or "'task'" in cand:
                        frag = cand
                    break
        if frag:
            break
    if not frag:
        print(f'[supervise_jobs] 无含 task 字段的 JSON 数组: {out[:150]}', file=sys.stderr)
        return None
    try:
        return json.loads(frag)
    except Exception:
        pass
    # 模型常输出 Python 字面量（单引号）。deep_reach 已踩过同一个坑，
    # 这里再踩一次说明这个兜底该做成公共函数而不是每个脚本各写一遍。
    try:
        v = ast.literal_eval(frag)
        if isinstance(v, list):
            return v
    except Exception:
        pass
    print(f'[supervise_jobs] JSON 解析失败: {frag[:120]}', file=sys.stderr)
    return None


def load_jobs(path, base):
    """读 jobs.yaml（极简 YAML 子集）或返回默认配置。"""
    if not path or not os.path.exists(path):
        jobs = {}
        for k, v in DEFAULT_JOBS.items():
            jobs[k] = dict(v, db_file=os.path.join(base, 'oss.sqlite'))
        return jobs
    jobs = {}
    cur = None
    for line in open(path, encoding='utf-8'):
        s = line.rstrip()
        if not s or s.lstrip().startswith('#'):
            continue
        m = re.match(r'^(\w[\w-]*):\s*$', s)
        if m:
            cur = m.group(1)
            jobs[cur] = {}
            continue
        m = re.match(r'^\s+(\w+):\s*(.+?)\s*$', s)
        if m and cur:
            k, v = m.group(1), m.group(2).strip('"\'')
            if k == 'enabled':
                jobs[cur][k] = v.lower() not in ('false', '0', 'no')
            else:
                jobs[cur][k] = v
    for v in jobs.values():
        v.setdefault('db_file', os.path.join(base, 'oss.sqlite'))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='')
    ap.add_argument('--base', default=os.environ.get(
        'SUPERVISE_BASE',
        '<skill 安装目录>/<示例项目路径>'))
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--out', default='ALERTS.md')
    a = ap.parse_args()

    base = os.path.abspath(a.base)
    jobs = load_jobs(a.config, base)
    snap = build_snapshot(jobs, base)
    if a.dry:
        print(snap)
        return 0

    dec = ask(snap)
    if not dec:
        print('[supervise_jobs] 本轮无决策，不做动作')
        return 0

    bad = [d for d in dec if str(d.get('action')) in ('warn', 'alert')]
    print(f'  {len(dec)} 个任务，异常 {len(bad)} 个')
    for d in dec:
        print(f"  {d.get('action','?'):5s} {d.get('task',''):14s} {str(d.get('reason',''))[:70]}")

    if bad:
        lines = [f'# 脚本任务告警 {time.strftime("%Y-%m-%d %H:%M")}', '',
                 f'共 {len(dec)} 个任务，{len(bad)} 个异常。', '']
        for d in bad:
            lines.append(f"## {d.get('task')} — {d.get('action')}")
            lines.append('')
            lines.append(f"- 判断：{d.get('reason','')}")
            if d.get('advice'):
                lines.append(f"- 建议：{d.get('advice')}")
            lines.append('')
        Path(os.path.join(base, a.out)).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'  已写 {a.out}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
