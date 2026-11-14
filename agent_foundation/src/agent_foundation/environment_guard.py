"""运行态一致性守护：改完与重启生效是两件事，用证据判定运行实例的状态。

抽象自隔离环境基线守护内核：源码恢复到基线、二进制重编完成，都不
等于正在服务的进程已经加载新版本——旧进程可能仍持有被替换文件的
旧 inode，甚至持有标记为已删除的路径。三类判定各有明确证据：源码
基线看 HEAD 修订与未提交改动；构建产物新鲜度由调用方注入构建系统
的 dry-run 命令判定（输出非空即有未完成的构建步骤）；运行态把
/proc/<pid>/exe 的 inode 与磁盘文件比对，路径带 (deleted) 标记直接
判旧。判定结果如实汇报，重启动作由调用方决定。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

_DELETED_MARK = "(deleted)"


@dataclass(frozen=True)
class RuntimeBinaryStatus:
    """一个运行中进程的二进制新鲜度，附证据。"""

    pid: int
    running_exe: str
    matches_disk: bool
    deleted: bool
    detail: str


def _stat_inode(path: Path, *, follow: bool) -> int | None:
    try:
        return int(path.stat(follow_symlinks=follow).st_ino)
    except OSError:
        return None


def runtime_binary_status(
    pid: int,
    disk_binary: str | Path,
    *,
    proc_root: str | Path = "/proc",
) -> RuntimeBinaryStatus:
    """判定运行中进程是否加载了磁盘上当前的二进制。

    proc_root 可注入，测试用它指向伪造的 /proc 结构；真实使用保持
    默认。读取失败按不可判定处理，绝不静默判新。
    """
    exe_link = Path(proc_root) / str(pid) / "exe"
    try:
        running = Path(os.readlink(exe_link))
    except OSError as exc:
        return RuntimeBinaryStatus(pid, "", False, False, f"无法读取 {exe_link}: {exc}")
    text = str(running)
    if _DELETED_MARK in text:
        return RuntimeBinaryStatus(pid, text, False, True, "运行中的可执行文件已被替换删除")
    disk = Path(disk_binary)
    running_inode = _stat_inode(exe_link, follow=True)
    disk_inode = _stat_inode(disk, follow=False)
    if running_inode is None or disk_inode is None:
        return RuntimeBinaryStatus(pid, text, False, False, "inode 不可读，状态未知")
    if running_inode != disk_inode:
        return RuntimeBinaryStatus(
            pid, text, False, False,
            f"运行中 inode {running_inode} 与磁盘 inode {disk_inode} 不一致（旧版本仍在服务）",
        )
    return RuntimeBinaryStatus(pid, text, True, False, "运行实例与磁盘二进制一致")


@dataclass(frozen=True)
class BaselineStatus:
    """一个检出源的基线漂移状态，附逐项证据。"""

    head: str
    head_matches: bool
    dirty_count: int
    residue_files: int
    issues: tuple[str, ...]


def source_baseline_status(
    worktree: str | Path,
    baseline_revision: str,
    *,
    residue_globs: tuple[str, ...] = ("*.bak", "*.bak.iter*"),
    max_depth: int = 5,
) -> BaselineStatus:
    """检查一个检出源是否仍在基线上：HEAD 修订、未提交改动、编辑残留。

    git 读取失败按问题上报，不静默视为干净。
    """
    root = Path(worktree)
    issues: list[str] = []
    head = ""
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True, capture_output=True, timeout=30, check=False,
    )
    if probe.returncode != 0:
        issues.append(f"git 读取失败: {(probe.stderr or probe.stdout).strip()[-200:]}")
    else:
        head = probe.stdout.strip()
        if head[: len(baseline_revision)] != baseline_revision:
            issues.append(f"HEAD {head[:11]} 不匹配基线 {baseline_revision[:11]}")
    dirty = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only"],
        text=True, capture_output=True, timeout=60, check=False,
    )
    dirty_count = 0
    if dirty.returncode != 0:
        issues.append(f"git diff 失败: {(dirty.stderr or dirty.stdout).strip()[-200:]}")
    else:
        dirty_count = len([line for line in dirty.stdout.splitlines() if line.strip()])
        if dirty_count:
            issues.append(f"存在 {dirty_count} 个未提交改动")
    residue = 0
    for pattern in residue_globs:
        residue += sum(1 for _ in root.glob(pattern))
    if residue:
        issues.append(f"存在 {residue} 个编辑残留文件")
    return BaselineStatus(head, bool(head) and head[: len(baseline_revision)] == baseline_revision,
                          dirty_count, residue, tuple(issues))


@dataclass(frozen=True)
class BuildFreshness:
    """构建产物与源码的一致性，由调用方注入的 dry-run 判定。"""

    fresh: bool
    pending_steps: int
    detail: str


def binary_freshness(
    dry_run_cmd: list[str],
    *,
    cwd: str | Path,
    timeout: int = 120,
) -> BuildFreshness:
    """用构建系统的 dry-run 判定产物是否与源码一致。

    dry_run_cmd 输出里出现构建/链接动作即存在未完成步骤；命令本身
    失败按不可判定上报，绝不静默判新。构建系统由调用方选择（make
    dry-run、cmake --build -- 等），本模块不绑定任何构建工具。
    """
    probe = subprocess.run(
        dry_run_cmd, text=True, capture_output=True, timeout=timeout,
        cwd=str(cwd), check=False,
    )
    if probe.returncode != 0:
        return BuildFreshness(False, -1, f"dry-run 失败: {(probe.stderr or probe.stdout).strip()[-200:]}")
    pending = sum(
        1 for line in probe.stdout.splitlines()
        if any(word in line.lower() for word in ("building", "compiling", "linking", "generating"))
    )
    if pending:
        return BuildFreshness(False, pending, f"dry-run 显示 {pending} 个未完成构建步骤")
    return BuildFreshness(True, 0, "产物与源码一致")
