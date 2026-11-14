"""经验沉淀与分层检索：失败教训提炼为案例，按可迁移范围召回。

抽象自中台记忆蒸馏与分层检索的机制内核：一次执行结束后，从成功
与失败里提炼经验候选；失败候选做重复失败检测（同一现象出现多次
才值得入册）；入册的经验带范围标签——本任务、仓库、场景、全局，
范围越宽要求的支持案例越多；检索时按证据信号、假设族、场景族等
字段过滤与加权，来源可信度与历史采纳记录参与排序。库只管提炼、
准入与召回的账，不解释业务含义。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Scope(StrEnum):
    CASE = "case"
    REPO = "repo"
    SCENARIO = "scenario"
    GLOBAL = "global"


#: 每个层级要求的最小支持案例数：范围越宽，孤证越不可信。
SCOPE_SUPPORT_MINIMUM = {Scope.CASE: 1, Scope.REPO: 2, Scope.SCENARIO: 3, Scope.GLOBAL: 3}

#: 来源可信度加分，与中台蒸馏器的来源分思路一致。
_SOURCE_RANK = {
    "conversation_extract": 0.06,
    "engine_extract": 0.04,
    "human_advice": 0.02,
}

_ACCEPTED_RANK_BONUS = 0.05
_REPEAT_FAILURE_MIN = 2


@dataclass
class Experience:
    """一条入册经验：陈述、范围、现象族、证据与来源。"""

    content: str
    scope: Scope
    phenomenon: str = ""
    evidence: tuple[str, ...] = ()
    source: str = ""
    accepted_before: bool = False
    support_count: int = 1


@dataclass
class FailureSignal:
    """一次失败的现象记录，供重复失败检测。"""

    phenomenon: str
    detail: str = ""


@dataclass
class RetrievalQuery:
    """检索条件：自由文本加可选的结构化字段。"""

    text: str = ""
    phenomenon: str | None = None
    scenario: str | None = None
    max_scope: Scope = Scope.GLOBAL


@dataclass
class ExperienceVault:
    """经验库：提炼入册与分层检索，线程安全。"""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _entries: list[Experience] = field(default_factory=list)
    _failures: dict[str, int] = field(default_factory=dict)

    def observe_failure(self, signal: FailureSignal) -> bool:
        """登记一次失败现象；同一现象累计达到阈值后返回 True 表示值得提炼。"""
        with self._lock:
            count = self._failures.get(signal.phenomenon, 0) + 1
            self._failures[signal.phenomenon] = count
            return count >= _REPEAT_FAILURE_MIN

    def admit(self, experience: Experience) -> bool:
        """准入检查：陈述非空且支持案例数达到该层级下限，拒绝孤证入册宽范围。"""
        if not experience.content.strip():
            return False
        minimum = SCOPE_SUPPORT_MINIMUM[experience.scope]
        if experience.support_count < minimum:
            return False
        with self._lock:
            self._entries.append(experience)
            return True

    def distill(
        self,
        *,
        content: str,
        phenomenon: str,
        scope: Scope,
        source: str = "",
        evidence: tuple[str, ...] = (),
        support_count: int = 1,
        accepted_before: bool = False,
    ) -> bool:
        """提炼入口：从一次执行的现象与陈述构造经验并尝试入册。"""
        return self.admit(
            Experience(
                content=content,
                scope=scope,
                phenomenon=phenomenon,
                evidence=evidence,
                source=source,
                accepted_before=accepted_before,
                support_count=support_count,
            )
        )

    def retrieve(self, query: RetrievalQuery) -> list[tuple[Experience, float]]:
        """分层检索：范围过滤 + 结构化字段过滤，按信任分排序，同分时可迁移层级更宽者在前。"""
        with self._lock:
            scored: list[tuple[Experience, float]] = []
            for entry in self._entries:
                if _scope_rank(entry.scope) > _scope_rank(query.max_scope):
                    continue
                if query.phenomenon and entry.phenomenon != query.phenomenon:
                    continue
                score = 1.0
                score += _SOURCE_RANK.get(entry.source, 0.0)
                if entry.accepted_before:
                    score += _ACCEPTED_RANK_BONUS
                if query.text and query.text in entry.content:
                    score += 0.1
                scored.append((entry, score))
            scored.sort(
                key=lambda pair: (
                    pair[1],
                    _scope_rank(pair[0].scope),
                ),
                reverse=True,
            )
            return scored


def _scope_rank(scope: Scope) -> int:
    return {Scope.CASE: 0, Scope.REPO: 1, Scope.SCENARIO: 2, Scope.GLOBAL: 3}[scope]
