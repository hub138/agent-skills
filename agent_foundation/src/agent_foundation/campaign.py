"""批量任务的账本与队列。

抽象自批量缺陷复现工作台（按 commit 逐条推进、多路并发、失败重试上限）
与验证集群的中心任务派发：执行体各自独立，共享一份任务账本；
账本只记录状态与尝试次数，不关心任务内容与执行方式。

状态机：pending → running → done；running 失败回到 pending 重试，
重试次数达到上限转 failed；pending/running 可跳过为 skipped。
done 是终态，其他动作就地报错。
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum


class TaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CampaignTask:
    task_id: str
    payload: dict[str, object]
    state: TaskState = TaskState.PENDING
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None


class CampaignLedger:
    """任务账本：add/claim/complete/fail/skip 五个动作，其余都是派生状态。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, CampaignTask] = {}
        self._order: list[str] = []

    def add(self, task_id: str, payload: dict[str, object], *, max_attempts: int = 3) -> CampaignTask:
        with self._lock:
            if task_id in self._tasks:
                raise ValueError(f"task already registered: {task_id}")
            if max_attempts < 1:
                raise ValueError("max_attempts must be >= 1")
            task = CampaignTask(task_id=task_id, payload=dict(payload), max_attempts=max_attempts)
            self._tasks[task_id] = task
            self._order.append(task_id)
            return task

    def claim(self, task_id: str | None = None) -> CampaignTask | None:
        """领取任务。不指定 id 时按登记顺序取最早的 pending；无可领取任务返回 None。"""
        with self._lock:
            target = task_id
            if target is None:
                pending = [tid for tid in self._order if self._tasks[tid].state is TaskState.PENDING]
                if not pending:
                    return None
                target = pending[0]
            task = self._require(target)
            if task.state is not TaskState.PENDING:
                return None
            task.state = TaskState.RUNNING
            task.attempts += 1
            return task

    def complete(self, task_id: str) -> None:
        with self._lock:
            task = self._require(task_id)
            if task.state is not TaskState.RUNNING:
                raise ValueError(f"task not running: {task_id} ({task.state.value})")
            task.state = TaskState.DONE
            task.error = None

    def fail(self, task_id: str, error: str) -> None:
        """失败处理：尝试次数未达上限回到 pending 等待重试，达到上限转 failed。"""
        with self._lock:
            task = self._require(task_id)
            if task.state is not TaskState.RUNNING:
                raise ValueError(f"task not running: {task_id} ({task.state.value})")
            if task.attempts >= task.max_attempts:
                task.state = TaskState.FAILED
                task.error = error
            else:
                task.state = TaskState.PENDING

    def skip(self, task_id: str, reason: str | None = None) -> None:
        with self._lock:
            task = self._require(task_id)
            if task.state is TaskState.DONE:
                raise ValueError(f"done task cannot be skipped: {task_id}")
            task.state = TaskState.SKIPPED
            task.error = reason

    def counts(self) -> dict[str, int]:
        with self._lock:
            counter = Counter(task.state.value for task in self._tasks.values())
            return dict(counter)

    def pending_ids(self) -> list[str]:
        with self._lock:
            return [tid for tid in self._order if self._tasks[tid].state is TaskState.PENDING]

    def _require(self, task_id: str) -> CampaignTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"unknown task: {task_id}")
        return task
