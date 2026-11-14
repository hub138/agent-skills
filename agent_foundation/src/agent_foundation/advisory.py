"""投递-确认-回执：消费侧不丢不重的建议投递。

抽象自中台 live advice 端点的机制内核：生产方发布带时效的建议，
消费方每轮开始拉取待办，先在本地持久化、再发消费确认；确认幂等，
重复确认返回已消费；确认之后上报结果（采纳或忽略），同一事项的
结果只允许记录一次，重复上报按冲突拒绝；超过时效轮次的建议不再
可见。「先保存后确认」保证确认失败时重拉还能拿到同一份内容。
队列只管投递与回执的账，不解释建议内容。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AdviceStatus(StrEnum):
    PENDING = "pending"
    CONSUMED = "consumed"
    APPLIED = "applied"
    IGNORED = "ignored"


class AdvisoryConflictError(RuntimeError):
    """同一建议的结果已被记录过时抛出。"""


@dataclass
class Advice:
    """一条带时效的建议：发布方任意负载，expiration_round 之前可见。"""

    advice_id: int
    payload: Any
    expiration_round: int | None = None
    status: AdviceStatus = AdviceStatus.PENDING
    outcome_reason: str = ""
    outcome_recorded: bool = False


@dataclass
class AdvisoryQueue:
    """内存版建议队列：发布、按轮拉取、幂等确认、一次回执。

    gated 的建议默认不进自动消费路径，须调用方显式放行，
    与「人工确认过的内容才允许被自动执行」的纪律对应。
    """

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _next_id: int = 1
    _items: dict[int, Advice] = field(default_factory=dict)

    def publish(self, payload: Any, *, expiration_round: int | None = None, gated: bool = False) -> Advice:
        with self._lock:
            advice = Advice(advice_id=self._next_id, payload=payload, expiration_round=expiration_round)
            if gated:
                advice.status = AdviceStatus.PENDING
                self._items[self._next_id] = advice
                self._items[self._next_id].outcome_reason = _GATED_MARK
            else:
                self._items[self._next_id] = advice
            self._next_id += 1
            return self._items[advice.advice_id]

    def poll(self, current_round: int | None = None, *, include_gated: bool = False) -> list[Advice]:
        """列出可见待办：已消费的不返回，过期轮次的隐藏，gated 默认隐藏。"""
        with self._lock:
            visible: list[Advice] = []
            for advice in self._items.values():
                if advice.status is not AdviceStatus.PENDING:
                    continue
                if advice.expiration_round is not None and current_round is not None and advice.expiration_round < current_round:
                    continue
                if advice.outcome_reason == _GATED_MARK and not include_gated:
                    continue
                visible.append(advice)
            return visible

    def ack(self, advice_id: int) -> str:
        """幂等消费确认：首次标记 consumed，重复确认返回 already_consumed。"""
        with self._lock:
            advice = self._items.get(advice_id)
            if advice is None:
                raise KeyError(advice_id)
            if advice.status is AdviceStatus.PENDING:
                advice.status = AdviceStatus.CONSUMED
                return "consumed"
            return "already_consumed"

    def record_outcome(self, advice_id: int, applied: bool, reason: str = "") -> Advice:
        """记录采纳或忽略的结果；同一建议只允许记录一次。"""
        with self._lock:
            advice = self._items.get(advice_id)
            if advice is None:
                raise KeyError(advice_id)
            if advice.outcome_recorded:
                raise AdvisoryConflictError(f"advice {advice_id} outcome already recorded")
            advice.status = AdviceStatus.APPLIED if applied else AdviceStatus.IGNORED
            advice.outcome_reason = reason
            advice.outcome_recorded = True
            return advice


_GATED_MARK = "__gated__"
