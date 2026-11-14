"""多执行体的串行-并发混合车队。

抽象自多智能体中心的派发纪律：不同资源（不同仓库、不同工作区）并行，
同一资源串行排队；派发前查重，同一任务不重复处理；串行队列用完即释放，
下一个任务补位，车队不空转。
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque


class Convoy:
    """按 lane（资源标识）组织的任务队列：跨 lane 并行、同 lane 串行。

    enqueue 返回 False 表示任务已在同一 lane 等待，属重复派发；
    dequeue 指定 lane 取队首，不指定则跳过当前忙的 lane 取下一个。
    完成任务用 finish 释放 lane；lane 队列空了自动撤销登记。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, deque[str]] = defaultdict(deque)
        self._busy: set[str] = set()

    def enqueue(self, lane: str, task_id: str) -> bool:
        with self._lock:
            queue = self._queues[lane]
            if task_id in queue:
                return False
            queue.append(task_id)
            return True

    def dequeue(self, lane: str | None = None) -> tuple[str, str] | None:
        """取出下一个 (lane, task_id)。指定 lane 时严格取该 lane 队首。

        忙标记中的 lane 一律不出队（返回 None），同 lane 串行由忙标记保证；
        不指定 lane 时跳过忙 lane 取下一个可用任务。
        """
        with self._lock:
            if lane is not None:
                if lane in self._busy:
                    return None
                queue = self._queues.get(lane)
                if not queue:
                    return None
                self._busy.add(lane)
                return lane, queue.popleft()
            for candidate in list(self._queues):
                if candidate in self._busy:
                    continue
                queue = self._queues[candidate]
                if queue:
                    self._busy.add(candidate)
                    return candidate, queue.popleft()
            return None

    def finish(self, lane: str) -> None:
        with self._lock:
            if lane not in self._busy:
                raise ValueError(f"lane not busy: {lane}")
            self._busy.discard(lane)
            if not self._queues.get(lane):
                self._queues.pop(lane, None)

    def pending(self, lane: str | None = None) -> dict[str, list[str]]:
        with self._lock:
            lanes = [lane] if lane is not None else list(self._queues)
            return {name: list(self._queues.get(name, ())) for name in lanes}
