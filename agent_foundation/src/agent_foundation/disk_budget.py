"""磁盘准入控制：本地构建与复现 worker 的容量预算。

抽象自上游回移植工作台的磁盘预算内核：每个活动 worker 预留固定
容量的保守配额，为操作系统保留安全下限；工作区与根分区可能在不同
挂载点上，各自独立计账；已提交 worker 的既有占用按其配额上限一次性
抵扣，断点续跑与重试不重复扣减并发额度。预算给出从请求到放行的
完整推导演算，调用方据 allowed_workers 准入；容量不足时停止而非
中途在临时目录上撞 ENOSPC。
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3


class DiskCapacityError(RuntimeError):
    """可用磁盘不足以启动新 worker 时抛出。"""


def _mount_device(path: Path) -> int:
    """返回 path 所在挂载点的设备号，路径不存在时向上找最近的已存在祖先。"""
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return int(os.stat(candidate).st_dev)


def _allocated_bytes(path: Path) -> int:
    """返回目录树下实际分配的字节数，不跟随符号链接。"""
    total = 0
    for current, directories, files in os.walk(path, followlinks=False):
        for name in [*directories, *files]:
            entry = Path(current) / name
            if entry.is_symlink():
                continue
            total += entry.stat(follow_symlinks=False).st_blocks * 512
    return total


@dataclass
class DiskBudget:
    """磁盘预算参数：下限与每 worker 预留量。"""

    min_free_bytes: int
    reserve_per_worker_bytes: int
    max_workers: int


def disk_budget(
    *,
    workspace: Path,
    config: DiskBudget,
    root_config: DiskBudget | None,
    requested_workers: int,
    committed_worker_paths: Sequence[Path] = (),
) -> dict[str, int]:
    """计算共享 workspace 所在磁盘的准入 worker 数。

    工作区与根分区异挂载时两套预算独立计账；已提交 worker 的既有
    占用按其配额上限一次性抵扣，重试不重复扣额度。
    """
    usage = shutil.disk_usage(workspace)
    free_bytes = int(usage.free)
    root_free_bytes = int(shutil.disk_usage(Path("/")).free)
    on_root = _mount_device(workspace) == _mount_device(Path("/"))

    committed_bytes = 0
    for path in committed_worker_paths[: max(0, int(requested_workers))]:
        try:
            if _mount_device(path) != _mount_device(workspace):
                continue
            used = _allocated_bytes(path)
        except OSError:
            continue
        committed_bytes += min(max(0, used), config.reserve_per_worker_bytes)

    effective_free = free_bytes + committed_bytes
    workspace_workers = max(0, (effective_free - config.min_free_bytes) // config.reserve_per_worker_bytes)
    if on_root or root_config is None:
        root_workers = workspace_workers
    elif root_config.reserve_per_worker_bytes > 0:
        root_workers = max(0, (root_free_bytes - root_config.min_free_bytes) // root_config.reserve_per_worker_bytes)
    else:
        root_workers = root_config.max_workers if root_free_bytes >= root_config.min_free_bytes else 0
    disk_workers = min(workspace_workers, root_workers)
    allowed = min(int(requested_workers), config.max_workers, disk_workers)
    return {
        "requested_workers": int(requested_workers),
        "configured_max_workers": config.max_workers,
        "free_bytes": free_bytes,
        "effective_free_bytes": effective_free,
        "committed_worker_bytes": committed_bytes,
        "root_free_bytes": root_free_bytes,
        "min_free_bytes": config.min_free_bytes,
        "workspace_on_root": int(on_root),
        "workspace_workers": workspace_workers,
        "root_workers": root_workers,
        "disk_workers": disk_workers,
        "allowed_workers": allowed,
    }


def require_capacity(budget: dict[str, int]) -> int:
    """返回准入 worker 数；容量不足抛 DiskCapacityError，构建开始前就地拦截。"""
    allowed = int(budget["allowed_workers"])
    if allowed >= 1:
        return allowed
    raise DiskCapacityError(
        "本机可用磁盘不足，已拒绝启动新 worker："
        f"工作区可用 {budget['free_bytes'] / GIB:.1f}GiB、"
        f"根分区可用 {budget['root_free_bytes'] / GIB:.1f}GiB，"
        "不满足保留下限与每 worker 预留之和。请等待运行中的任务结束或回收临时目录后重试。"
    )
