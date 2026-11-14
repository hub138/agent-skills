"""运行工件的规范布局与磁盘保留。

抽象自批量工作台的工作区布局（每次运行一个目录，日志按任务命名、
磁盘水位看守定时清理）与迭代内核的按任务隔离产物目录：
每次运行一个目录，超预算从最旧文件开始删除，删除动作返回清单可复核。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunLayout:
    """一次运行的全部工件位置。root 下 runs/<run_id>/ 为本次运行目录。"""

    root: Path
    run_id: str

    @property
    def logs(self) -> Path:
        return self.root / "runs" / self.run_id / "logs"

    @property
    def checkpoints(self) -> Path:
        return self.root / "runs" / self.run_id / "checkpoints"

    @property
    def reports(self) -> Path:
        return self.root / "runs" / self.run_id / "reports"

    def task_log(self, task_id: str) -> Path:
        return self.logs / f"{task_id}.log"

    def prepare(self) -> None:
        for path in (self.logs, self.checkpoints, self.reports):
            path.mkdir(parents=True, exist_ok=True)


def directory_size(root: Path) -> int:
    """目录内全部文件的字节总量。"""
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def prune_oldest(root: Path, max_bytes: int) -> list[Path]:
    """从最旧的文件开始删除，直到目录总量不超过预算；返回被删除的文件清单。"""
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    total = sum(path.stat().st_size for path in files)
    removed: list[Path] = []
    for path in files:
        if total <= max_bytes:
            break
        size = path.stat().st_size
        path.unlink()
        removed.append(path)
        total -= size
    return removed
