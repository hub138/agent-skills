#!/usr/bin/env python3
"""文档事实自检：防止 README / SKILL.md 里的数字随代码演进漂移。

跑法：`python3 scripts/doccheck.py`（退出码 1 = 文档与事实不符）。
也能当 CI 门禁：`python3 scripts/doccheck.py && python3 -m pytest tests/ -q`。

2026-11-15 起因：README 写「28 项回归测试」，实际已 36 项；
SKILL.md 写「14 个有效文件」，实际 11 个脚本 + 5 个测试 + 6 个模板。
文档数字写死就会过时，所以让脚本来核，而不是靠人记得改。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def check() -> list[str]:
    issues: list[str] = []
    scripts = sorted((ROOT / "scripts").glob("*.py"))
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    templates = sorted((ROOT / "templates/tasks").glob("*.md"))

    # 1) 测试数：跑 pytest 收集，不数文件（一个文件可含多项）
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    m = re.findall(r"(\d+) tests? collected", proc.stdout)
    if not m:
        # 新版 pytest 的 -q 输出形如 "36 tests collected" 或直接列 nodeid
        m = re.findall(r"^(\d+)\s+tests?\s+collected", proc.stdout, re.M)
    collected = int(m[-1]) if m else len([
        x for x in proc.stdout.splitlines() if "::" in x])

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for name, text in (("README.md", readme), ("SKILL.md", skill)):
        for found in re.findall(r"(\d+)\s*项回归测试|当前\s*(\d+)\s*项", text):
            n = int(next(x for x in found if x))
            if n != collected:
                issues.append(f"{name} 写 {n} 项回归测试，实际收集到 {collected} 项")
        for found in re.findall(r"\*\*(\d+)/(\d+)\*\*\s*通过", text):
            if int(found[0]) != collected or int(found[1]) != collected:
                issues.append(f"{name} 写 {found[0]}/{found[1]} 通过，实际 {collected} 项")

    # 2) FIELD-NOTES 条数
    fn = (ROOT / "FIELD-NOTES.md").read_text(encoding="utf-8")
    nums = [int(x) for x in re.findall(r"^## (\d+)\.", fn, re.M)]
    max_no = max(nums) if nums else 0
    for name, text in (("README.md", readme),):
        for n in re.findall(r"(\d+)\s*条实战坑", text):
            if int(n) != max_no:
                issues.append(f"{name} 写 {n} 条实战坑，实际最大编号 {max_no}")

    # 3) 导航表不许再写死文件数（一加文件就漂移，改由本脚本对账）
    if re.search(r"最近一次核对：\d+ 个脚本", skill):
        issues.append("SKILL.md 导航又写死了文件数，应交给 doccheck 对账")

    # 3b) 新模块必须出现在导航表里，否则 AI 读 SKILL.md 会不知道它存在
    for needed in ("platform_util.py", "model_policy.py", "doccheck.py",
                   "_done-contract.md"):
        if needed not in skill:
            issues.append(f"SKILL.md 导航表漏了 {needed}")

    # 4) 命令速查里的脚本必须存在
    for ref in set(re.findall(r"`([a-z_]+\.py)", readme)):
        if not (ROOT / "scripts" / ref).is_file():
            issues.append(f"README 命令速查引用了不存在的 scripts/{ref}")

    # 5) 平台/模型模块的单一权威源不得被绕过
    for f in ("agentctl.py", "taskctl.py"):
        s = (ROOT / "scripts" / f).read_text(encoding="utf-8")
        if re.search(r"ALLOWED_MODELS\s*=\s*\{", s):
            issues.append(f"scripts/{f} 又写了一份 ALLOWED_MODELS，应引用 model_policy")
        if re.search(r'["\']/usr/local/bin/codebuddy["\']', s) and "resolve_bin" not in s:
            issues.append(f"scripts/{f} 又写死了 codebuddy 路径，应走 resolve_bin")

    return issues


if __name__ == "__main__":
    problems = check()
    if problems:
        print("!!! 文档/事实不一致 !!!")
        for x in problems:
            print("  " + x)
        sys.exit(1)
    print("OK 文档数字与代码事实一致")
