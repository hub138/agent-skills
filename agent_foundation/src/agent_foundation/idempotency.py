"""幂等接收：同一份提交重复到达时只生效一次。

抽象自中台接入端点的入库治理：发送方可能因网络重试、对账重放
把同一份负载投递多次，接收方按调用方提供的幂等键与内容指纹双通道
查重，命中即返回首次接收的结果；并发写入撞车时以指纹唯一性兜底，
同样返回已存在记录；生命周期版本更高的提交替换过期状态。
接收方不解释负载内容，只保证「同一份只生效一次」。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class AcceptState(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    SUPERSEDED = "superseded"


@dataclass
class Submission:
    """一次待接收的提交：幂等键、内容指纹、业务记录、生命周期版本。"""

    idempotency_key: str | None
    fingerprint: str
    record: object
    version: int = 0


@dataclass
class AcceptResult:
    state: AcceptState
    record: object
    accepted_version: int = 0


class IdempotencyStore(Protocol):
    """幂等索引的最小接口。实现方保证按指纹与按键的查询语义。"""

    def get_by_key(self, key: str) -> Submission | None: ...

    def get_by_fingerprint(self, fingerprint: str) -> Submission | None: ...

    def save(self, submission: Submission) -> Submission: ...

    def all_submissions(self) -> list[Submission]: ...


class InMemoryIdempotencyStore:
    """线程安全的内存幂等索引，指纹唯一：并发保存同一指纹返回先到者。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_key: dict[str, Submission] = {}
        self._by_fingerprint: dict[str, Submission] = {}

    def get_by_key(self, key: str) -> Submission | None:
        with self._lock:
            return self._by_key.get(key)

    def get_by_fingerprint(self, fingerprint: str) -> Submission | None:
        with self._lock:
            return self._by_fingerprint.get(fingerprint)

    def save(self, submission: Submission) -> Submission:
        with self._lock:
            existing = self._by_fingerprint.get(submission.fingerprint)
            if existing is not None:
                return existing
            self._by_fingerprint[submission.fingerprint] = submission
            if submission.idempotency_key:
                self._by_key.setdefault(submission.idempotency_key, submission)
            return submission

    def all_submissions(self) -> list[Submission]:
        with self._lock:
            return list(self._by_fingerprint.values())


class IdempotentReceiver:
    """幂等接收器：查重 → 过期替换 → 接受，三步之后结果可重放。"""

    def __init__(self, store: IdempotencyStore) -> None:
        self._store = store

    def receive(self, submission: Submission) -> AcceptResult:
        if submission.idempotency_key:
            existing = self._store.get_by_key(submission.idempotency_key)
            if existing is not None:
                return AcceptResult(state=AcceptState.DUPLICATE, record=existing.record, accepted_version=existing.version)
        existing = self._store.get_by_fingerprint(submission.fingerprint)
        if existing is not None:
            return AcceptResult(state=AcceptState.DUPLICATE, record=existing.record, accepted_version=existing.version)
        newer = self._find_superseding(submission)
        if newer is not None:
            return AcceptResult(state=AcceptState.SUPERSEDED, record=newer.record, accepted_version=newer.version)
        saved = self._store.save(submission)
        return AcceptResult(state=AcceptState.CREATED, record=saved.record, accepted_version=saved.version)

    def _find_superseding(self, submission: Submission) -> Submission | None:
        """同主体的提交里已有更高生命周期版本时，本次提交按过期处理。

        主体由调用方在指纹前缀中约定（如 "task:loop:"），此处只比较版本。
        """
        for existing in self._store.all_submissions():
            if existing is submission or existing.fingerprint == submission.fingerprint:
                continue
            if self._same_subject(existing.fingerprint, submission.fingerprint) and existing.version > submission.version:
                return existing
        return None

    @staticmethod
    def _same_subject(left: str, right: str) -> bool:
        left_subject, _, _ = left.partition("#")
        right_subject, _, _ = right.partition("#")
        return bool(left_subject) and left_subject == right_subject
