#!/usr/bin/env python3
"""ANATOMY 结构对账：文档必须与代码树一致，且不允许「只追加不校」。

为什么需要：GOVERNANCE 写了「P2 变更必须更新 ANATOMY」，但只靠 AI 自觉必然漂移。
本脚本把两件事变成退出码：
  1. ANATOMY 里提到的路径/脚本必须真实存在；
  2. 代码树里的脚本、任务模板、雷达提示词必须在 ANATOMY 有位置。
它不判断文字好坏（那是 radar/prompts/anatomy-review.md 的事），只抓结构性漂移。

跑法：`python3 scripts/anatomy_check.py`（退出码 1 = 需要修订 ANATOMY）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_SECTIONS = range(1, 11)

# 这些前缀是占位符、运行时目录或外部地址，不要求存在于仓库里。
SKIP_PREFIXES = ("<", "~", "$", "http", "radar/state", "radar/cache",
                 ".git", "/", "data/", "git@")

PATH_RE = re.compile(
    r"`((?:scripts|templates|radar|tests)/[A-Za-z0-9_./-]+"
    r"|[A-Za-z0-9_]+\.(?:py|md|sh|json|sql|mjs))`")


def _referenced_paths(text: str) -> set[str]:
    """只校验带目录的路径（`scripts/x.py`、`radar/...`）。

    裸文件名（`taskctl.py`、`progress.md`、`result.json`）不在这里校验：
    脚本由「覆盖完整性」检查，运行时文件（progress/result）本来就不在仓库根。
    """
    found = set()
    for token in PATH_RE.findall(text):
        token = token.strip()
        if "/" not in token:
            continue
        if any(token.startswith(p) for p in SKIP_PREFIXES):
            continue
        if "*" in token or "<" in token:
            continue
        found.add(token)
    return found


def _section(text: str, n: int) -> str:
    start = text.find("## %d." % n)
    if start < 0:
        return ""
    nxt = re.search(r"^## \d+\.", text[start + 4:], re.M)
    end = start + 4 + nxt.start() if nxt else len(text)
    return text[start:end]


def check(root: Path | None = None) -> list[str]:
    """返回问题列表；空列表 = 结构一致。root 可注入以便测试。"""
    root = Path(root) if root else ROOT
    anatomy = root / "ANATOMY.md"
    if not anatomy.is_file():
        return ["ANATOMY.md 不存在"]
    text = anatomy.read_text(encoding="utf-8")
    issues: list[str] = []

    # 1) 固定章节：防止被改乱后读者找不到入口
    for n in REQUIRED_SECTIONS:
        if not re.search(r"^## %d\." % n, text, re.M):
            issues.append("ANATOMY 缺少第 %d 节（章节结构必须保持）" % n)

    # 2) 引用的路径必须存在（占位符/运行时目录除外）
    for token in sorted(_referenced_paths(text)):
        target = root / token
        ok = target.is_dir() if token.endswith("/") else target.exists()
        if not ok:
            issues.append("ANATOMY 引用了不存在的路径：%s" % token)

    # 3) 代码树里的脚本必须在 ANATOMY 出现（否则读者不知道它存在）
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for f in sorted(scripts_dir.glob("*.py")):
            if f.name not in text:
                issues.append("scripts/%s 未出现在 ANATOMY" % f.name)

    # 4) 任务模板必须被目录树覆盖
    tasks = root / "templates" / "tasks"
    if tasks.is_dir():
        for f in sorted(tasks.glob("*.md")):
            if f.name not in text:
                issues.append("templates/tasks/%s 未出现在 ANATOMY" % f.name)

    # 5) 雷达提示词必须被列出（新增提示词不能只丢进目录）
    prompts = root / "radar" / "prompts"
    if prompts.is_dir():
        for f in sorted(prompts.glob("*.md")):
            if f.name not in text:
                issues.append("radar/prompts/%s 未出现在 ANATOMY" % f.name)

    # 6) 影响矩阵必须覆盖最容易被改坏的三处
    matrix = _section(text, 6)
    for name in ("taskctl.py", "radar_store.py", "radar_cli.py",
                 "_done-contract.md"):
        if name not in matrix:
            issues.append("影响矩阵（第 6 节）没有覆盖 %s" % name)

    # 7) 门禁必须包含本脚本：否则「自动更新」只是口头约定
    for doc in ("GOVERNANCE.md", "SKILL.md"):
        p = root / doc
        if p.is_file() and "anatomy_check.py" not in p.read_text(encoding="utf-8"):
            issues.append("%s 的门禁/自检未包含 anatomy_check.py" % doc)

    # 8) 审阅任务书必须存在（全文审阅的入口）
    review = root / "radar" / "prompts" / "anatomy-review.md"
    if prompts.is_dir() and not review.is_file():
        issues.append("缺少 radar/prompts/anatomy-review.md（全文审阅任务书）")

    return issues


def main() -> int:
    problems = check()
    if problems:
        print("!!! ANATOMY 与代码结构不一致 !!!")
        for p in problems:
            print("  - " + p)
        print("\n按 radar/prompts/anatomy-review.md 通读全文并修订，"
              "不要只在文末追加一段。")
        return 1
    print("OK ANATOMY 与代码结构一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
