#!/usr/bin/env python3
"""knot-cli 批量调用的全局限流感知封装（本机免费通道，多项目共用）。

直接用法：
    from knot_batch import batch, probe, global_load, recommend
    print(global_load())            # 全局 chat 数 / 按项目 / 按模型 / 孤儿
    print(recommend())              # 当前建议本机开多少路
    ok, out = probe()               # 低频探活（启动一次即可）
    results = batch(items, lambda it: f"判定：{it}", models=MODELS, per_model=2)
    # results: [(item, model, verdict_dict|None, raw)]

设计依据（2026-11-12 凌晨实测，见本文第八节）：
- 限制的是「每模型在途并发」，不是整机总并发。按模型分桶 + 每模型 2 路，
  9 个模型共 18 路能跑；而全局 10 路不分桶时 48 条失败 32 条。
- **knot 的 429 没有恢复时间通知**（codebuddy 才有「将在 … 重置」），所以
  自动恢复靠探测式降并发/回升，见 `knot-limits.md` §4 与 `AdaptiveConcurrency`。
- 官方口径（平台官方限流文档，仅适用于 knot）修正早期结论：429 是「人+模型粒度」限频，
  **各模型相互独立，撞限流切模型有效**；旧注释写「换模型也没用」是错的。
  chat_once 单次不重试、短超时 25s、失败返回 None 交下轮断点续跑仍然成立，
  但 batch() 现在带 fallback 链：撞 rate_limit 自动切下一个模型重试一次。
- 绝不使用 <业务调用点> 的封装做批量：retries=3 / timeout=180 / 退避 45s，
  实测 18 路并发 4 分钟 0 条返回。
"""
import os, re, json, subprocess, threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

KNOT = '<knot-cli 路径>'
# 2026-11-12 用户口径：本项目只用免费 hy 系列，不用 deepseek / flash /
# glm / kimi。其它 ID 在 SKILL.md 的 ID 表里仍作为「实测扣费 0」的事实
# 保留（供别的项目按需选用），但默认批量封装不再自动回落到它们。
# 用户 2026-11-12 最终口径：默认只用 free-model（codebuddy 侧写 free-model）；small-model 偏弱、不进默认池。
# 可配置：MTR_KNOT_MODELS=free-model,small-model 显式加模型；每模型最多 2 路、全局上限 10。
# 不做全局配额推演——别的项目也在用，算不清也没必要算。
MODELS = [m.strip() for m in os.environ.get(
    "MTR_KNOT_MODELS", "free-model").split(",") if m.strip()]
# 用户 2026-11-12 口径：一个模型全局 3 并发持续跑没问题（是全局，不是单项目），
# 全局上限 10（多模型合计）；旧值「本项目总量 2」是语义误读，已作废。
PER_MODEL = 2                    # 本项目单模型并发上限
# 硬上限只在 knot_rate_budget 里定义一次，避免两个脚本改一处漏一处。
try:
    from knot_rate_budget import PROJECT_HARD_CAP, GLOBAL_PER_MODEL_CAP, PER_MODEL_CAP
except ImportError:  # 直接 `python3 knot_batch.py` 时当前目录不在 sys.path
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parent))
    from knot_rate_budget import PROJECT_HARD_CAP, GLOBAL_PER_MODEL_CAP, PER_MODEL_CAP
TIMEOUT = 25               # 单次调用超时；实测正常 6.7s
PROBE_EVERY = 10           # 每 N 批探活一次，探活本身也占额度，不要太频繁

# 429 / 假绿灯：knot RC=0、stderr 空、错误串在 stdout
ERR_PAT = re.compile(r'429|too many requests|创建异步请求失败|RateLimitError|'
                     r'"type"\s*:\s*"error"|Plugin runtime refresh settled', re.I)


def global_load():
    """读 /proc 统计全局真实 chat 数（排除 watchdog；pgrep 在 Python 子进程里会漏统计）。"""
    rows = []
    for pid in (x for x in os.listdir('/proc') if x.isdigit()):
        try:
            cmd = open(f'/proc/{pid}/cmdline', 'rb').read().decode('utf8', 'ignore').replace('\0', ' ').strip()
            if 'knot-cli' not in cmd or 'chat-watchdog' in cmd or ' chat ' not in cmd:
                continue
            ppid = open(f'/proc/{pid}/stat').read().split(') ')[1].split()[1]
            cwd = os.readlink(f'/proc/{pid}/cwd')
            m = re.search(r'--model\s+([A-Za-z0-9._-]+)', cmd)
            rows.append({'pid': pid, 'ppid': ppid, 'cwd': cwd,
                         'model': m.group(1) if m else '-', 'orphan': ppid == '1'})
        except Exception:
            pass
    return {
        'total': len(rows),
        'by_project': dict(Counter(os.path.basename(r['cwd']) for r in rows)),
        'by_model': dict(Counter(r['model'] for r in rows)),
        'orphans': [r['pid'] for r in rows if r['orphan']],
        'rows': rows,
    }


def recommend():
    """只报全局占用情况，不做配额推演。

    本项目口径：默认 free-model（可配 MTR_KNOT_MODELS），每模型最多 2 路，全局上限 10。
    其它项目占多少可以看一眼，但不用它反推本项目该开几路（用户 2026-11-12：全局监控太麻烦，没让做）。
    """
    g = global_load()
    return {'global_chat': g['total'], 'project_hard_cap': PROJECT_HARD_CAP,
            'by_project': g['by_project'], 'by_model': g['by_model'],
            'orphan_pids': g['orphans'], 'suggest_workers': min(PROJECT_HARD_CAP, len(MODELS) * PER_MODEL_CAP),
            'models': MODELS,
            'note': f"本项目 {','.join(MODELS)} 每模型最多 2 路、全局上限 10；孤儿按自己 PID 清，勿 pkill -f"}


def parse_json(out):
    """模型输出常带 [任务规划中] 前缀、requestID/sessionID 后缀、markdown 围栏。
    先括号配对提 JSON，再正则兜底抓 level/p0/reason。返回 dict 或 None。
    """
    if not out:
        return None
    clean = re.sub(r'```(?:json)?', ' ', out, flags=re.I)
    for st in (k for k, ch in enumerate(clean) if ch == '{'):
        d = 0
        for j in range(st, len(clean)):
            if clean[j] == '{':
                d += 1
            elif clean[j] == '}':
                d -= 1
                if d == 0:
                    try:
                        return json.loads(clean[st:j + 1])
                    except Exception:
                        break
    ml = re.search(r'"level"\s*:\s*"(P0|P1|无)"', clean)
    if ml:
        mp = re.search(r'"p0"\s*:\s*(true|false)', clean, re.I)
        mr = re.search(r'"reason"\s*:\s*"([^"]{0,300})"', clean)
        return {'level': ml.group(1),
                'p0': (mp.group(1).lower() == 'true') if mp else False,
                'reason': mr.group(1) if mr else ''}
    return None


def chat_once(model, prompt, timeout=TIMEOUT):
    """单次调用。**本函数不重试**：限流由 batch() 的 fallback 链切模型处理，
    其余失败快速返回 None 交给下轮断点续跑。

    返回 (verdict|None, raw, err_kind)，err_kind: '' / 'rate_limit' /
    'timeout' / 'empty'。429 时 knot RC=0、错误串在 stdout，必须用 ERR_PAT
    识别，不能只看 returncode。
    """
    cmd = [KNOT, 'chat', '--no-update', '--output-format', 'text',
           '--model', model, '-p', prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout or ''
    except subprocess.TimeoutExpired:
        return None, '', 'timeout'
    except Exception as exc:
        return None, str(exc)[:120], 'empty'
    if not out.strip():
        return None, out, 'empty'
    if ERR_PAT.search(out):
        return None, out, 'rate_limit'
    return parse_json(out), out, ''


def probe(model=None, timeout=TIMEOUT):
    """低频连通性探活。只在进程启动 + 每 PROBE_EVERY 批做一次，别每轮都探。"""
    v, raw, err = chat_once(model or MODELS[0], '输出JSON: {"level":"无","p0":false,"reason":"探活"}', timeout)
    return (v is not None), raw


def batch(items, prompt_fn, models=None, per_model=PER_MODEL, timeout=TIMEOUT,
          workers=None, on_result=None):
    """按模型分桶并发：每模型一个 Semaphore(per_model)，任务按 i % len(models) 轮转。
    失败返回 verdict=None（调用方不要写库，下轮自动重判 = 断点续跑）。
    on_result(item, model, verdict, err_kind) 回调用于即时落盘（每批一次 commit 即可）。
    """
    models = models or MODELS
    sems = {m: threading.Semaphore(per_model) for m in models}
    g = global_load()
    workers = workers or min(len(models) * per_model, max(2, GLOBAL_BUDGET - g['total']))
    results = []

    def one(job):
        i, item = job
        m = models[i % len(models)]
        with sems[m]:
            v, raw, err = chat_once(m, prompt_fn(item), timeout)
        # 官方：各模型限频「人+模型粒度」相互独立，撞限流切模型有效。
        # fallback 链最多试 2 个其它模型，且只对 rate_limit 生效；
        # timeout 是通道占用，不重试（错峰/绕过），其它失败留到下轮断点续跑。
        if err == 'rate_limit':
            for alt in (models[(i + k) % len(models)] for k in range(1, min(3, len(models)))):
                if alt == m:
                    continue
                with sems[alt]:
                    v2, raw2, err2 = chat_once(alt, prompt_fn(item), timeout)
                if v2 is not None:
                    return item, alt, v2, ''
        return item, m, v, err

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, job) for job in enumerate(items)]
        for f in as_completed(futs):
            item, m, v, err = f.result()
            results.append((item, m, v, err))
            if on_result:
                on_result(item, m, v, err)
    return results


def selfcheck():
    r = recommend()
    print('=== knot 全局状态（只看一眼，不做配额推演）===')
    print('  全局 chat 数:', r['global_chat'])
    print('  按项目:', r['by_project'])
    print('  按模型:', r['by_model'])
    print('  孤儿 PID:', r['orphan_pids'])
    print('  本项目并发:', r['suggest_workers'], '（每模型 2 路，全局上限 10）')
    ok, raw = probe()
    print('  探活:', '正常' if ok else '异常', repr(raw[:100]))
    return ok


if __name__ == '__main__':
    import sys
    if '--load' in sys.argv:
        print(json.dumps(global_load(), ensure_ascii=False, indent=2))
    else:
        sys.exit(0 if selfcheck() else 1)
