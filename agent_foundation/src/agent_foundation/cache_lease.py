"""稳定路径缓存租约：让以路径为哈希输入的构建缓存跨隔离环境复用。

抽象自上游回移植的构建缓存租约内核：编译器缓存把参数里的路径算进
哈希，一次性工作区路径每案不同会击穿缓存命中；租约把活动工作区经
符号链接固定暴露在槽位路径上，用建议锁防止第二个 worker 重定向同
一槽位；租约关闭时撤销链接释放槽位。共享的只有缓存条目：目标文件
与安装产物仍在一次性工作区内，缓存的构建不会验证到别的案例的二进
制。环境不具备（未启用或工具缺失）时安全回退为无租约，不挡任务。
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator


@dataclass
class CacheLease:
    """一个槽位路径上的独占租约：活跃期路径稳定，关闭时撤销。"""

    slot: int
    source_path: Path
    metadata_path: Path | None = None
    _releasers: list[Callable[[], None]] = field(default_factory=list)

    def close(self) -> None:
        for releaser in self._releasers:
            try:
                releaser()
            except OSError:
                pass
        self._releasers.clear()

    def __enter__(self) -> "CacheLease":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@contextmanager
def fixed_path_cache_lease(
    *,
    pool_root: Path,
    key: str,
    target: Path,
    slots: int = 4,
    lock_factory: Callable[[Path], Any] | None = None,
    symlink_factory: Callable[[Path, Path], None] | None = None,
) -> Iterator[CacheLease | None]:
    """租用一个稳定路径；全部槽位被占或环境不支持时返回 None 不阻塞。

    lock_factory 在槽位目录上建立独占建议锁（缺省 flock，测试可注入
    替身）；symlink_factory 把槽位 source 指向当前目标。租约持有时
    metadata 写入租约键与时间供诊断，关闭顺序为先撤链接后释放锁。
    """
    if slots <= 0 or not target.exists():
        yield None
        return
    acquire = lock_factory or _default_lock
    link = symlink_factory or _default_symlink
    for slot in range(slots):
        slot_dir = pool_root / f"slot-{slot}"
        try:
            handle = acquire(slot_dir)
        except OSError:
            continue
        if handle is None:
            continue
        source_path = slot_dir / "source"
        metadata_path = slot_dir / "lease.json"
        lease = CacheLease(slot=slot, source_path=source_path, metadata_path=metadata_path)
        try:
            link(source_path, target)
            metadata_path.write_text(
                json.dumps({"key": key, "pid": os.getpid(), "at": time.time()}, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            _release(handle)
            continue

        def release() -> None:
            try:
                if source_path.is_symlink():
                    source_path.unlink()
            finally:
                try:
                    metadata_path.unlink(missing_ok=True)
                finally:
                    _release(handle)

        lease._releasers.append(release)
        try:
            yield lease
        finally:
            lease.close()
        return
    yield None


def _default_lock(slot_dir: Path) -> Any:
    import fcntl

    slot_dir.mkdir(parents=True, exist_ok=True)
    handle = (slot_dir / ".lock").open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        handle.close()
        return None
    return handle


def _default_symlink(source_path: Path, target: Path) -> None:
    if source_path.is_symlink() or source_path.exists():
        source_path.unlink()
    os.symlink(target.resolve(), source_path)


def _release(handle: Any) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (ImportError, OSError):
        pass
    finally:
        handle.close()
