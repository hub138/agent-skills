"""CLI 业务路径冒烟：`--help` 不执行 main 的业务分支，测不出函数被误删。

2026-11-15 事故：用贪婪正则替换 agentctl.alive 时连带吞掉 8 个顶层函数
（launch_task/build_cmd/spawn/session_file/read_int/...），
当时只跑 `--help` 冒烟 + pytest 40 项，全部通过，但 `agentctl status`
直接 NameError、派单会打不到任何进程。之后已提交的版本也是坏的 (b56bae6)。

所以冒烟必须真的执行业务子命令，并断言「没有 traceback / NameError」。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)


def _no_traceback(p: subprocess.CompletedProcess) -> bool:
    blob = (p.stdout or "") + (p.stderr or "")
    return "Traceback" not in blob and "NameError" not in blob and "AttributeError" not in blob


def test_agentctl_status_executes_business_path():
    p = _run("agentctl.py", "status")
    assert _no_traceback(p), p.stderr[-600:]
    assert "任务" in p.stdout or "[]" in p.stdout


def test_agentctl_status_json_is_valid():
    import json
    p = _run("agentctl.py", "status", "--json")
    assert _no_traceback(p), p.stderr[-600:]
    json.loads(p.stdout)  # 必须是可解析 JSON，不能半截异常栈


def test_taskctl_stats_and_list():
    for args in (("stats",), ("list",)):
        p = _run("taskctl.py", *args)
        assert _no_traceback(p), f"taskctl {args}: {p.stderr[-400:]}"


def test_selfcheck_and_doccheck_run():
    for script, args in (("selfcheck.py", ()), ("doccheck.py", ())):
        p = _run(script, *args)
        assert _no_traceback(p), f"{script}: {p.stderr[-400:]}"
        assert p.returncode == 0, f"{script} rc={p.returncode}: {(p.stdout + p.stderr)[-300:]}"


def test_agentctl_has_all_core_functions():
    """静态兜底：核心函数不许再被整段吞掉。"""
    src = (SCRIPTS / "agentctl.py").read_text(encoding="utf-8")
    for fn in ("launch_task", "build_cmd", "spawn", "session_file",
               "read_int", "inspect", "cmd_dispatch", "cmd_status",
               "cmd_send", "cmd_watch", "alive"):
        assert f"def {fn}(" in src, f"agentctl.py 缺函数 {fn}"


def test_help_still_works_for_every_entry():
    for script in ("agentctl.py", "taskctl.py", "manager.py",
                   "deadman.py", "selfcheck.py"):
        p = _run(script, "--help")
        assert _no_traceback(p), f"{script} --help: {p.stderr[-300:]}"
