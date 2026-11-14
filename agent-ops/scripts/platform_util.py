"""跨平台进程探测：统一处理 Linux / macOS / 其它。

背景（2026-11-15）：仓库里 4 个脚本共 6 处直接读 `/proc/<pid>`，
在 macOS 上要么抛 FileNotFoundError、要么把活着的进程误判成死了。
逐处打补丁会漏，统一到这一个模块。

机器类型只检测一次（lru_cache），后续调用走缓存：
- Linux：优先 /proc/<pid>/cmdline（无子进程、最快）
- macOS / Darwin：ps -p <pid>（判活）/ ps -eo pid,args（按模式找进程）
- 其它（Windows 等）：判活退回 os.kill(pid, 0)，模式匹配退回 ps，能力不足时
  返回 None 让调用方按「未知」保守处理，不静默当成「进程已死」。

注意：判活与「按 cmdline 找进程」是两件事，不要混用同一个函数。
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache


@lru_cache(maxsize=1)
def os_kind() -> str:
    """返回 'linux' / 'macos' / 'other'，只测一次。"""
    s = platform.system().lower()
    if s == "linux":
        return "linux"
    if s == "darwin":
        return "macos"
    return "other"


def pid_exists(pid: int | None) -> bool:
    """进程是否活着。所有平台都可用。"""
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    kind = os_kind()
    # Linux 正常走 /proc；但容器可能没挂载 /proc，此时退回 os.kill，
    # 不能把「探测不到」误报成「进程已死」。
    if kind == "linux" and os.path.isdir("/proc"):
        return os.path.isdir(f"/proc/{pid}")
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _ps_rows() -> list[tuple[int, str]]:
    """(pid, cmdline) 列表；失败返回空列表。"""
    try:
        out = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1]))
    return rows


def process_alive(pattern: str) -> bool:
    """按 cmdline 子串找进程。排除 grep 与自身，避免自匹配。

    Linux 走 /proc（无子进程开销）；macOS/其它走 ps -eo pid,args。
    取不到进程表时返回 False，但调用方应把「探测能力不可用」与
    「确实没这个进程」区分开（见 probe_available）。
    """
    if not pattern:
        return False
    kind = os_kind()
    cmds: list[str] = []
    if kind == "linux" and os.path.isdir("/proc"):
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as f:
                    cmds.append(f.read().decode("utf-8", "replace").replace("\x00", " "))
            except OSError:
                continue
    else:
        cmds = [cmd for _, cmd in _ps_rows()]
    for cmd in cmds:
        if pattern in cmd and "grep" not in cmd and "deadman" not in cmd:
            return True
    return False


def probe_available() -> bool:
    """进程表探测是否可用。False 时调用方应按「未知」处理，别当没进程。"""
    if os_kind() == "linux":
        return os.path.isdir("/proc")
    return bool(_ps_rows())


@lru_cache(maxsize=16)
def resolve_bin(name: str, env_var: str | None = None,
                candidates: tuple[str, ...] = ()) -> str:
    """找 CLI 二进制：环境变量 > 显式候选 > PATH > 原名（让调用方报清晰错误）。

    2026-11-15 实测：macOS 上 `codebuddy` 在 ~/.nvm/.../bin 与 /opt/homebrew/bin，
    而仓库 4 个脚本写死 `/usr/local/bin/codebuddy`（Linux 生产机路径），
    该文件在本机根本不存在，派单会直接失败。
    """
    if env_var:
        v = os.environ.get(env_var)
        if v:
            return v
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    found = shutil.which(name)
    if found:
        return found
    return name
