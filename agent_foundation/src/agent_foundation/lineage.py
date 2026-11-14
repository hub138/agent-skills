"""血缘溯源：事实先入可靠收件箱，确认后的实体关系进可查边索引。

抽象自中台 lineage 的机制内核：主流程只把事实事件投递到带去重键
的持久收件箱（同一事实重放只入账一次），由独立的消费者认领、聚合
出候选关系、确认后写入边索引；处理失败按尝试次数升级为待重试或
失败终态，不阻塞主流程。边按五元组端点唯一，重复确认以最新证据覆盖
置信度与评审状态，双向可查任意实体的全部上游下游。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class InboxEvent:
    """收件箱里的一条事实：类型、实体、去重键与任意负载。"""

    event_id: int
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict = field(default_factory=dict)
    dedupe_key: str | None = None
    status: str = "pending"
    attempts: int = 0
    last_error: str = ""
    created_at: datetime = field(default_factory=_utc_now)
    processed_at: datetime | None = None


@dataclass
class ProvenanceEdge:
    """一条已确认的实体关系边：五元组端点唯一。"""

    edge_type: str
    src_entity_type: str
    src_entity_id: str
    dst_entity_type: str
    dst_entity_id: str
    confidence: float | None = None
    review_status: str = "auto"
    evidence: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (self.edge_type, self.src_entity_type, self.src_entity_id,
                self.dst_entity_type, self.dst_entity_id)


@dataclass
class LineageLedger:
    """内存版血缘账本：收件箱与边索引，线程安全。"""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _next_event_id: int = 1
    _events: dict[int, InboxEvent] = field(default_factory=dict)
    _by_dedupe: dict[str, int] = field(default_factory=dict)
    _edges: dict[tuple[str, str, str, str, str], ProvenanceEdge] = field(default_factory=dict)

    def emit(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict | None = None,
        dedupe_key: str | None = None,
    ) -> tuple[InboxEvent, bool]:
        """投递事实事件；去重键已存在时返回既有事件并标记重复。"""
        with self._lock:
            if dedupe_key and dedupe_key in self._by_dedupe:
                return self._events[self._by_dedupe[dedupe_key]], False
            event = InboxEvent(
                event_id=self._next_event_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload or {},
                dedupe_key=dedupe_key,
            )
            self._events[event.event_id] = event
            if dedupe_key:
                self._by_dedupe[dedupe_key] = event.event_id
            self._next_event_id += 1
            return event, True

    def claim_pending(self) -> InboxEvent | None:
        """认领一条待处理事件；无待处理返回 None。"""
        with self._lock:
            for event in self._events.values():
                if event.status == "pending":
                    event.attempts += 1
                    return event
            return None

    def complete(self, event: InboxEvent) -> None:
        with self._lock:
            event.status = "processed"
            event.processed_at = _utc_now()
            event.last_error = ""

    def fail(self, event: InboxEvent, error: str) -> None:
        """处理失败：五次以内保持待重试，超过升级为失败终态。"""
        with self._lock:
            event.status = "pending" if event.attempts < 5 else "dead"
            event.last_error = error[:2000]

    def confirm_edge(self, edge: ProvenanceEdge) -> ProvenanceEdge:
        """确认一条关系边：同端点已存在时以最新证据与置信度覆盖。"""
        with self._lock:
            existing = self._edges.get(edge.key)
            if existing is None:
                self._edges[edge.key] = edge
                return edge
            if edge.confidence is not None:
                existing.confidence = edge.confidence
            existing.review_status = edge.review_status
            existing.evidence = edge.evidence
            return existing

    def edges_for_entity(self, entity_type: str, entity_id: str) -> list[ProvenanceEdge]:
        """双向查询：返回与该实体相关的全部边，按创建时间与事件号排序。"""
        eid = str(entity_id)
        with self._lock:
            hits = [
                edge
                for edge in self._edges.values()
                if (edge.src_entity_type == entity_type and edge.src_entity_id == eid)
                or (edge.dst_entity_type == entity_type and edge.dst_entity_id == eid)
            ]
            return sorted(hits, key=lambda e: (e.created_at, e.key))
