"""一次性工作区生命周期：终态门槛、进程引用扫描、证据保全、加锁清理。

抽象自上游回移植与边缘执行器的两个清理内核：一次性工作区只在任务
到达终态、且用户可见证据已在别处持久化之后才可丢弃；丢弃前扫描
/proc，任何进程仍以工作目录、命令行、可执行文件或文件描述符引用
该目录时拒绝清理并给出引用清单；证据保全回调先于删除执行，写入有
界摘要而不是整棵目录，防止清理本身变成磁盘写入者；清理全程持有文
件锁串行化，删除带重试并要求真正删掉，静默残留计为失败。进程树终
止走 SIGKILL 并等待真正退出，自身进程永不误伤。
"""

from __future__ import annotations

import fcntl
import os
import shutil
import signal
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class WorkspaceNotTerminalError(RuntimeError):
    """工作区尚未到达终态，拒绝清理。"""


class WorkspaceInUseError(RuntimeError):
    """仍有进程引用该工作区，拒绝清理。携带引用清单。"""

    def __init__(self, references: list[str]) -> None:
        super().__init__("仍有进程引用该工作区: " + "; ".join(references[:10]))
        self.references = references


def task_report_dir(reports_root: Path, task_id: str) -> Path:
    """报告根目录下、仅属于这一单的子目录；非法标识与路径穿越就地报错。"""
    name = (task_id or "").strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"非法任务标识: {task_id!r}")
    root = Path(reports_root).resolve()
    dest = (root / name).resolve()
    if dest == root or root not in dest.parents:
        raise ValueError(f"任务目录越出报告根: {task_id!r}")
    return dest


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _child_pids(pid: int) -> list[int]:
    """读取 /proc 里该进程的直接子进程；进程消失视为没有子进程。"""
    out: list[int] = []
    try:
        tasks = list((Path("/proc") / str(pid) / "task").iterdir())
    except OSError:
        return []
    for task in tasks:
        try:
            text = (task / "children").read_text()
        except OSError:
            continue
        out.extend(int(x) for x in text.split())
    return out


def kill_tree(pid: int, *, wait_seconds: float = 5.0) -> None:
    """终止一个进程及其全部后代，并等待真正退出；自身进程永不误伤。

    SIGKILL 后进程短暂可见属内核回收节奏，用 waitpid（子进程）与
    /proc 存在性双重判定；超时仍存活属异常，报错而不是静默放过。
    """
    if pid <= 0 or pid == os.getpid():
        return
    for child in _child_pids(pid):
        kill_tree(child, wait_seconds=wait_seconds)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done == pid:
                return
        except ChildProcessError:
            break
        if not Path("/proc", str(pid)).exists():
            return
        time.sleep(0.05)
    if Path("/proc", str(pid)).exists():
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass
        else:
            return
        raise OSError(f"进程 {pid} 在 SIGKILL 后 {wait_seconds}s 仍未退出")


def process_references(root: Path) -> list[str]:
    """扫描 /proc，返回仍在引用该目录的进程清单（工作目录、argv、可执行文件、文件描述符）。

    /proc 条目在扫描期间消失属内核固有竞态，逐条跳过不算错误。
    """
    resolved = Path(root).resolve()
    needle = str(resolved)
    folded = needle.replace("\\", "/")
    refs: list[str] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        try:
            cwd = (entry / "cwd").resolve()
            if _inside(cwd, resolved):
                refs.append(f"pid={pid} cwd={cwd}")
                continue
        except OSError:
            pass
        try:
            exe = (entry / "exe").resolve()
            if _inside(exe, resolved):
                refs.append(f"pid={pid} executable={exe}")
                continue
        except OSError:
            pass
        try:
            cmd = (entry / "cmdline").read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        if needle in cmd or folded in cmd.replace("\\", "/"):
            refs.append(f"pid={pid} argv 引用了该目录")
            continue
        try:
            descriptors = list((entry / "fd").iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                if _inside(descriptor.resolve(), resolved):
                    refs.append(f"pid={pid} fd 引用了该目录")
                    break
            except OSError:
                continue
    return refs


def kill_referencing(root: Path) -> list[int]:
    """终止命令行里引用该目录的全部进程，返回被终止的 pid 清单。"""
    resolved = Path(root).resolve()
    needle = str(resolved)
    folded = needle.replace("\\", "/")
    victims: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        if needle in cmd or folded in cmd.replace("\\", "/"):
            victims.append(pid)
    for pid in victims:
        kill_tree(pid)
    return victims


@contextmanager
def lifecycle_lock(lock_path: Path) -> Iterator[None]:
    """用文件锁把工作区的创建、删除与管理性修剪串行化。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def dispose_workspace(
    root: Path,
    *,
    terminal: bool,
    evidence: Callable[[Path], None] | None = None,
    lock_path: Path | None = None,
    retries: int = 5,
    retry_delay: float = 0.4,
    ticket: Path | None = None,
) -> dict[str, object]:
    """丢弃一个一次性工作区：终态门槛 → 引用扫描 → 证据保全 → 加锁删除。

    terminal 为假直接拒绝；发现进程引用拒绝删除并给出清单；证据回调
    在删除前执行，其报错原样上抛；删除重试后仍存在计为失败。
    """
    if not terminal:
        raise WorkspaceNotTerminalError(f"工作区 {root} 未到达终态，拒绝清理")

    def _run() -> dict[str, object]:
        refs = process_references(root)
        if refs:
            raise WorkspaceInUseError(refs)
        if evidence is not None:
            evidence(root)
        for _ in range(retries):
            if not root.exists():
                break
            shutil.rmtree(root)
            if not root.exists():
                break
            time.sleep(retry_delay)
        if root.exists():
            raise OSError(f"工作区 {root} 重试 {retries} 次后仍存在")
        ticket_removed = False
        if ticket is not None and ticket.is_file():
            ticket.unlink()
            ticket_removed = True
        return {"removed": True, "root": str(root), "ticket_removed": ticket_removed}

    if lock_path is None:
        return _run()
    with lifecycle_lock(lock_path):
        return _run()


def stop_task(
    reports_root: Path,
    task_id: str,
    *,
    pid: int | None = None,
    evidence: Callable[[Path], None] | None = None,
    lock_path: Path | None = None,
) -> dict[str, object]:
    """停掉某次任务拉起的进程并删掉它的工作目录：杀树 → 杀引用进程 → 清理。"""
    killed: list[int] = []
    if pid:
        kill_tree(pid)
        killed.append(pid)
    dest = task_report_dir(reports_root, task_id)
    killed.extend(kill_referencing(dest))
    ticket = Path(reports_root) / f"{task_id}.md"
    ticket = ticket if ticket.parent.resolve() == Path(reports_root).resolve() else None
    result = dispose_workspace(
        dest, terminal=True, evidence=evidence, lock_path=lock_path, ticket=ticket,
    )
    return {"killed": killed, **result}
