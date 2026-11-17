"""把大 prompt 安全地交给 CLI（Linux 单参数上限 MAX_ARG_STRLEN≈128KB）。

实测：<审查项目> <业务项目> 补跑 232 条里 2 条 knot 因此 "Argument list too long"。
codebuddy / knot 的 --prompt-file 语义各家不一，所以这里不赌 CLI 能力，
统一「超限即截断」：保头部 55%（目标/约束在前）+ 尾部 45%（结果 JSON 契约
与「断点快照四问」在收工契约尾部，不能丢）。

截断是有损的——所以截断必须显式打日志让失败可归因，而不是静默变形。
查证记录：agent_foundation 的 cli_session.py 是进程监督、content.py 是
schema-free 抽取，都没有 argv 上限处理；这个坑只能在 agent-ops 侧补。
"""
from __future__ import annotations

import sys

ARG_LIMIT = 120_000  # 字符上限（≈120KB，给命令行里其余参数留余量）


def cap_prompt(text: str, limit: int = ARG_LIMIT, log=None) -> str:
    """超限则保头尾截断；未超限原样返回。"""
    if len(text) <= limit:
        return text
    head = int(limit * 0.55)
    tail = limit - head
    marker = ("\n\n…[prompt 超出 CLI 单参数上限 %d 字符，中间已截断 %d 字符；"
              "若本次结果质量异常，优先怀疑这里]…\n\n" % (limit, len(text) - limit))
    out = text[:head] + marker + text[-tail:]
    print("[prompt_transport] prompt %d -> %d 字符（截断保头尾）"
          % (len(text), len(out)), file=log or sys.stderr)
    return out
