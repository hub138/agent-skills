"""「提案 → 验证 → 接纳」的通用迭代环。

抽象自迭代调优内核的多轮循环：每轮提出候选、跑评测、按判据决定接纳；
被拒绝的候选触发回滚钩子回到轮前状态，接纳或轮数耗尽即停。
循环只关心节奏与终止，不关心提案是什么、用什么验证、由谁提。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Attempt:
    index: int
    proposal: object
    metrics: dict[str, float] = field(default_factory=dict)
    accepted: bool = False


@dataclass
class IterationResult:
    attempts: list[Attempt] = field(default_factory=list)
    stop_reason: str = "max_rounds"

    @property
    def accepted(self) -> bool:
        return self.stop_reason == "accepted"


class IterationLoop:
    """驱动 propose/evaluate/accept 三个调用方提供的环节直到终止。

    propose 抛出 StopIteration 视为提案源耗尽（stop_reason="exhausted"）；
    evaluate 与 accept 抛出的任何异常直接向外传播，不在循环内吞掉。
    on_reject 在每个被拒绝的轮次结束后调用，用于回滚到轮前状态。
    """

    def __init__(
        self,
        *,
        propose: Callable[[], object],
        evaluate: Callable[[object], dict[str, float]],
        accept: Callable[[dict[str, float]], bool],
        max_rounds: int,
        on_reject: Callable[[Attempt], None] | None = None,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        self._propose = propose
        self._evaluate = evaluate
        self._accept = accept
        self._max_rounds = max_rounds
        self._on_reject = on_reject

    def run(self) -> IterationResult:
        result = IterationResult()
        for index in range(1, self._max_rounds + 1):
            try:
                proposal = self._propose()
            except StopIteration:
                result.stop_reason = "exhausted"
                return result
            metrics = self._evaluate(proposal)
            accepted = bool(self._accept(metrics))
            attempt = Attempt(index=index, proposal=proposal, metrics=metrics, accepted=accepted)
            result.attempts.append(attempt)
            if accepted:
                result.stop_reason = "accepted"
                return result
            if self._on_reject is not None:
                self._on_reject(attempt)
        result.stop_reason = "max_rounds"
        return result
