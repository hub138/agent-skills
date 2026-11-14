#!/usr/bin/env python3
"""本 skill 自检：每个能力「有没有真的在用」。

为什么需要：skill 文档说的能力有十几个，但实际项目里可能只用了一两个。
「有没有正确用起来」不能靠回忆，要每次算一遍。

输出三类：
  在用     — 有进程/cron/数据，且在产出
  闲置     — 有能力但当前项目没有适用场景（是合理的，不是缺陷）
  不该用   — 能力存在但场景不匹配（例如用 agent 跑长批量）

用法：
  python3 scripts/selfcheck.py
  python3 scripts/selfcheck.py --base <项目目录>   # 指定被检查项目
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
AGENTCTL = HOME / '.codebuddy/agentctl'
WATCHDOG = HOME / '.codebuddy/watchdog'
SKILL = Path(__file__).resolve().parent.parent


def run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or '').strip()
    except Exception:
        return ''


def crons():
    return run('crontab -l 2>/dev/null')


def procs(pat):
    return [x for x in run(f'pgrep -f {pat}').split() if x]


def check_agentctl():
    reg = AGENTCTL / 'registry.json'
    if not reg.exists():
        return '闲置', '没有 agentctl 任务记录'
    try:
        tasks = json.loads(reg.read_text()).get('tasks', {})
    except Exception:
        return '闲置', 'registry 读取失败'
    if not tasks:
        return '闲置', 'registry 为空'
    alive = []
    for name, t in tasks.items():
        pid = t.get('pid')
        ok = False
        if pid:
            ok = os.path.exists(f'/proc/{pid}')
        if ok:
            alive.append(name)
    total = len(tasks)
    if alive:
        return '在用', f'{len(alive)}/{total} 个任务进程存活'
    return '闲置', f'{total} 个任务记录，全部已退出（无活跃 agent）'


def check_supervisor():
    """supervisor.py 面向 taskctl；常驻 daemon 或 cron 都算在用。"""
    c = crons()
    in_cron = 'supervisor.py' in c
    db = Path(os.environ.get(
        "TASKCTL_DB", str(Path.home() / ".codebuddy/agentctl/tasks.db")))
    has_lib = db.exists()
    daemon = daemon_alive() or ('supervisor.py daemon' in c)
    if daemon:
        return '在用', 'supervisor daemon 在岗' + ('（库存在）' if has_lib else '')
    if in_cron:
        return '在用', '已挂 crontab'
    if has_lib:
        return '部分', 'taskctl 库存在但 supervisor 未启动（python3 scripts/supervisor.py daemon）'
    return '闲置', '无 taskctl 库、未启动 supervisor'


def check_supervise_agents():
    c = crons()
    if 'supervise_agents.py' in c:
        # 看它是否有产出
        log = '/tmp/night/supervisor.log'
        if os.path.exists(log) and os.path.getsize(log) > 0:
            return '在用', '已挂 cron 且有输出'
        return '在用', '已挂 cron（尚无输出，可能无活跃 agent 而不触发）'
    return '闲置', '未挂 cron'


def check_supervise_jobs():
    c = crons()
    if 'supervise_jobs.py' in c:
        log = '/tmp/night/supjobs.log'
        if os.path.exists(log) and os.path.getsize(log) > 0:
            return '在用', '已挂 cron 且有输出'
        return '在用', '已挂 cron（尚无输出）'
    return '闲置', '未挂 cron'


def check_watchdog():
    jobs = WATCHDOG / 'jobs.json'
    in_cron = 'watchdog.sh' in crons()
    if not jobs.exists():
        return '闲置', '无 jobs.json'
    try:
        d = json.loads(jobs.read_text())
        enabled = [w['name'] for w in d.get('watchers', []) if w.get('enabled')]
    except Exception:
        return '闲置', 'jobs.json 读取失败'
    if in_cron and enabled:
        return '在用', f'{len(enabled)} 个 watcher 启用'
    if enabled:
        return '闲置', f'{len(enabled)} 个 watcher 启用但 cron 未挂'
    return '闲置', '所有 watcher 已停用（用户主动停）'


def daemon_alive() -> bool:
    import subprocess
    try:
        r = subprocess.run(['pgrep', '-f', 'taskctl.py daemon'],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def check_taskctl():
    # 库路径必须与 taskctl.py 的解析一致：TASKCTL_DB 优先，默认 HOME/tasks.db。
    # 旧实现 glob('**/taskctl*.db') 匹配不到 tasks.db，明明在用却报「闲置」。
    db = Path(os.environ.get(
        "TASKCTL_DB", str(Path.home() / ".codebuddy/agentctl/tasks.db")))
    if not db.exists():
        return '闲置', '无 taskctl 库（python3 scripts/taskctl.py add 启用）'
    try:
        import sqlite3
        c = sqlite3.connect(str(db))
        rows = {r[0]: r[1] for r in c.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status")}
        c.close()
    except Exception as e:
        return '部分', f'库存在但读取失败: {e}'
    if not rows:
        return '闲置', '库存在但还没有任务'
    total = sum(rows.values())
    detail = ' / '.join(f'{k} {v}' for k, v in sorted(rows.items()))
    daemon = 'daemon 在岗' if daemon_alive() else 'daemon 未启动'
    return '在用', f'{total} 个任务（{detail}），{daemon}'


def check_memory(base):
    """三层记忆：progress.md（子 agent）/ STATE.md（现状）/ NOTES.md（判断）。"""
    b = Path(base) if base else None
    if not b or not b.exists():
        return '闲置', '未指定项目目录'
    state = b / 'STATE.md'
    notes = b / 'NOTES.md'
    parts = []
    if state.exists():
        age = (__import__('time').time() - state.stat().st_mtime) / 60
        parts.append(f'STATE.md {int(age)}分钟前刷新')
    else:
        parts.append('STATE.md 缺')
    parts.append('NOTES.md 有' if notes.exists() else 'NOTES.md 缺')
    prog = list(b.glob('*/progress.md')) + [p for p in [b / 'progress.md'] if p.exists()]
    parts.append(f'progress.md {len(prog)} 个')
    if state.exists() and notes.exists():
        return '在用', '；'.join(parts)
    return '部分', '；'.join(parts)


def check_loop_scripts(base):
    """脚本 + cron 的批量作业（本项目实际主力）。"""
    b = Path(base) if base else None
    if not b or not b.exists():
        return '闲置', '未指定项目目录'
    c = crons()
    loops = [p.name for p in b.glob('*_loop.sh')]
    hooked = [x for x in loops if x in c]
    if hooked:
        return '在用', f'{len(hooked)} 个循环已挂 cron：{", ".join(hooked)}'
    if loops:
        return '闲置', f'{len(loops)} 个循环脚本存在但未挂 cron'
    return '闲置', '无循环脚本'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.environ.get('SELFCHECK_BASE', ''))
    a = ap.parse_args()

    checks = [
        ('agentctl 多 agent 派发', check_agentctl()),
        ('supervisor（taskctl 后端）', check_supervisor()),
        ('supervise_agents（agent 后端）', check_supervise_agents()),
        ('supervise_jobs（脚本后端）', check_supervise_jobs()),
        ('watchdog + jobs.json', check_watchdog()),
        ('taskctl 队列', check_taskctl()),
        ('三层记忆', check_memory(a.base)),
        ('脚本 + cron 批量作业', check_loop_scripts(a.base)),
    ]

    print(f'{"能力":32s} {"状态":6s} 说明')
    print('-' * 96)
    cnt = {}
    for name, (st, why) in checks:
        cnt[st] = cnt.get(st, 0) + 1
        icon = {'在用': '✅', '闲置': '⏸', '部分': '⚠️', '不该用': '❌'}.get(st, '?')
        print(f'{name:32s} {icon}{st:5s} {why}')

    print()
    print('  汇总: ' + ' / '.join(f'{k} {v}' for k, v in cnt.items()))
    print()
    print('  说明：「闲置」不等于缺陷——没有适用场景就不用。')
    print('       真正要警惕的是「本该在用却闲置」和「用错场景」。')

    # 一致性提示：agent 全死但 supervise_agents 还挂着 → 可以提一句
    for name, (st, why) in checks:
        if name.startswith('agentctl') and st == '闲置' and 'supervise_agents' in crons():
            print()
            print('  ⚠ 提示：agentctl 已无活跃任务，但仍挂着 supervise_agents cron。')
            print('     这不是错误（它会静默返回），只是每小时一次空跑，可按需保留或摘掉。')


if __name__ == '__main__':
    main()
