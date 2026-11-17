"""result.json 的 evidence 证据坐标校验（桥接 agent_foundation.evidence）。

实测（<审查项目> 191 条引用）：96.3% 逐字命中、7 条拼接重组、0 凭空
编造——引文类审计已有自包含实现；但「path:line 坐标」类证据在 agent-ops
侧从没校验过，LLM 编造坐标会直接误导人。

宽松口径：只返回问题清单，由调用方决定记警告还是拒收——误杀比漏报贵。
查证记录：foundation 的 evidence.verify_quote/repair_quote 是归一化逐字
比对（全角括号/弯引号/空白差异都能修），这里直接复用；缺库时用同源兜底
实现（NFC + 去空白 + 全角标点折叠）。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import foundation_bridge

_TRANSLATION = str.maketrans({
    "\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
    "\uff08": "(", "\uff09": ")", "\uff1a": ":", "\uff0c": ",",
})

_COORD_RE = re.compile(r"^\s*([^:\s]+\.(?:py|md|go|ts|js|json|yaml|yml|sql|sh|txt))"
                       r"(?::(\d+)(?:-(\d+))?)?\s*$")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", "", s)
    return s.translate(_TRANSLATION)


def _verify_quote(body: str, quote: str) -> bool:
    ev = foundation_bridge.load("agent_foundation.evidence")
    if ev is not None:
        return bool(ev.verify_quote(body, quote))
    n_body, n_quote = _norm(body), _norm(quote)
    return bool(n_quote) and n_quote in n_body


def check(outdir: Path, evidence: list) -> list[str]:
    """校验 evidence 列表，返回问题清单（空 = 全部可信）。

    - `path` / `path:line`：文件必须存在，行号必须在文件行数范围内；
    - 其他长文本项：当作引文，与 progress.md 归一化逐字比对（有源才校验）。
    """
    outdir = Path(outdir)
    problems: list[str] = []
    progress = outdir / "progress.md"
    progress_body = (progress.read_text(encoding="utf-8")
                     if progress.exists() else None)
    for item in evidence or []:
        text = str(item or "").strip()
        if not text:
            continue
        m = _COORD_RE.match(text)
        if m:
            rel, line, _end = m.groups()
            path = outdir.parent / rel
            if not path.exists():
                path = outdir / rel
            if not path.exists():
                problems.append("evidence 文件不存在：%s" % rel)
                continue
            if line:
                n_lines = path.read_text(encoding="utf-8",
                                         errors="replace").count("\n") + 1
                if not (1 <= int(line) <= n_lines):
                    problems.append("evidence 行号越界：%s（共 %d 行）"
                                    % (text, n_lines))
            continue
        if len(_norm(text)) >= 8 and progress_body is not None:
            if not _verify_quote(progress_body, text):
                problems.append("evidence 引文未命中 progress.md：%s…"
                                % text[:50])
    return problems
