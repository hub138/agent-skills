"""跨进程共享资源池：按通道计容量、通道熔断与跨通道全局限额。

抽象自上游回移植的模型租约池内核：每条通道绑定可运行的资源集合与
并发上限，上限写成硬顶，配置里的超大值只会被压回顶值，防止把偶发
限流放大成账号级额度耗尽；同一资源出现在多条通道时，各通道空闲数
不能简单相加，全局余量只发一次；通道故障熔断按（通道, 资源）记录
冷却期，冷却期内不参与容量计算。容量为零有两种成因——忙碌与熔断，
调度方需要区分这两者才能如实报告队列状态。凭据只存环境变量引用
名，值由调用方在派发时注入，任何租约记录、日志、导出里都不出现值
本身。优先级排队属于调用方调度器的职责：本池只提供容量事实（空闲
数、忙碌与熔断的区分），调用方按优先级轮询 available 后再领取。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: 通道并发硬顶。这是有意设置的绝对上限：更高的配置值会把瞬时 429
#: 放大成账号级额度耗尽，所以配置只能往下压，不能突破。
MAX_LANE_CAP = 3

#: 熔断的兜底冷却时长。限流报文自述的账号余额不可靠，按短冷却处理
#: 并立即路由到下一条通道，避免整夜阻塞。
DEFAULT_COOLDOWN_SECONDS = 5 * 3600


class LaneCapacityError(RuntimeError):
    """请求的通道资源没有空闲槽位，携带成因（busy / circuit / global_cap / credential）。"""

    def __init__(self, lane: str, resource: str, cause: str) -> None:
        super().__init__(f"通道 {lane} 的资源 {resource} 无空闲槽位（{cause}）")
        self.lane = lane
        self.resource = resource
        self.cause = cause


@dataclass(frozen=True)
class Lane:
    """一条资源通道：允许的资源集合、并发上限与凭据引用（只存名，不存值）。"""

    name: str
    allowed: tuple[str, ...]
    cap: int
    secret_ref: str = ""
    use_host_default: bool = False

    @property
    def effective_cap(self) -> int:
        return min(MAX_LANE_CAP, max(1, int(self.cap)))

    @property
    def authenticated(self) -> bool:
        """通道是否具备可执行的认证路径：显式凭据引用或宿主默认认证。"""
        return bool(self.secret_ref) or self.use_host_default


@dataclass(frozen=True)
class Lease:
    """一次确切的资源分配记录：通道、资源、领用方与领用时刻。"""

    id: int
    lane: str
    resource: str
    requester: str
    acquired_at: float


class ResourcePool:
    """（通道, 资源）键控的租约池，线程安全；持久化底座由调用方接入。"""

    def __init__(
        self,
        lanes: Sequence[Lane],
        *,
        global_resource_cap: int = 0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._lanes = {lane.name: lane for lane in lanes}
        if len(self._lanes) != len(lanes):
            raise ValueError("通道名重复")
        self._global_cap = max(0, int(global_resource_cap))
        self._active: dict[int, Lease] = {}
        self._next_id = 1
        self._circuits: dict[tuple[str, str], tuple[float, str]] = {}

    def _active_count(self, lane: str, resource: str) -> int:
        return sum(
            1 for lease in self._active.values()
            if lease.lane == lane and lease.resource == resource
        )

    def _resource_total(self, resource: str) -> int:
        return sum(1 for lease in self._active.values() if lease.resource == resource)

    def _circuit_open(self, lane: str, resource: str, now: float) -> bool:
        entry = self._circuits.get((lane, resource))
        return entry is not None and entry[0] > now

    def acquire(self, lane_name: str, resource: str, requester: str) -> Lease:
        """领取一个租约；通道未知、资源未授权、熔断、占满或触达全局限额时就地报错。"""
        with self._lock:
            lane = self._lanes.get(lane_name)
            if lane is None:
                raise ValueError(f"未知通道: {lane_name}")
            if resource not in lane.allowed:
                raise ValueError(f"通道 {lane_name} 不允许资源 {resource}")
            now = self._clock()
            if not lane.authenticated:
                raise LaneCapacityError(lane_name, resource, "credential")
            if self._circuit_open(lane_name, resource, now):
                raise LaneCapacityError(lane_name, resource, "circuit")
            if self._active_count(lane_name, resource) >= lane.effective_cap:
                raise LaneCapacityError(lane_name, resource, "busy")
            if self._global_cap > 0 and self._resource_total(resource) >= self._global_cap:
                raise LaneCapacityError(lane_name, resource, "global_cap")
            lease = Lease(
                id=self._next_id, lane=lane_name, resource=resource,
                requester=requester, acquired_at=now,
            )
            self._next_id += 1
            self._active[lease.id] = lease
            return lease

    def release(self, lease: Lease) -> None:
        with self._lock:
            if self._active.pop(lease.id, None) is None:
                raise ValueError(f"未知租约: {lease.id}")

    def release_stale(self, max_age_seconds: float) -> list[Lease]:
        """回收持有超过时限的租约（领用方崩溃后留下的残留），返回被回收的清单。"""
        cutoff = self._clock() - max_age_seconds
        with self._lock:
            stale = [lease for lease in self._active.values() if lease.acquired_at < cutoff]
            for lease in stale:
                del self._active[lease.id]
            return stale

    def available(self, *, resource: str = "") -> int:
        """返回空闲槽位数，可只看某一资源；熔断中的通道不计数，全局限额封顶。"""
        now = self._clock()
        with self._lock:
            per_resource: dict[str, int] = {}
            for lane in self._lanes.values():
                if not lane.authenticated:
                    continue
                for name in lane.allowed:
                    if resource and name != resource:
                        continue
                    if self._circuit_open(lane.name, name, now):
                        continue
                    free = max(0, lane.effective_cap - self._active_count(lane.name, name))
                    per_resource[name] = per_resource.get(name, 0) + free
            if self._global_cap <= 0:
                return sum(per_resource.values())
            return sum(
                min(free, max(0, self._global_cap - self._resource_total(name)))
                for name, free in per_resource.items()
            )

    def trip(self, lane: str, resource: str, *, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
             reason: str = "") -> None:
        """对（通道, 资源）熔断：冷却期内该通道不参与容量计算。"""
        with self._lock:
            self._circuits[(lane, resource)] = (self._clock() + cooldown_seconds, reason[:500])

    def clear_circuit(self, lane: str, resource: str) -> None:
        with self._lock:
            self._circuits.pop((lane, resource), None)

    def circuit_open(self, lane: str, resource: str) -> bool:
        with self._lock:
            return self._circuit_open(lane, resource, self._clock())

    def circuit_reason(self, lane: str, resource: str) -> str:
        with self._lock:
            entry = self._circuits.get((lane, resource))
            return entry[1] if entry is not None else ""

    def backpressure_active(self, *, resource: str = "") -> bool:
        """全部可用通道在该资源上都处于熔断时为真；没有任何可用通道时为假。

        与 available()==0 的成因不同：忙碌是本地工作在占通道，熔断是
        提供方明确拒绝。调度方按两者区分如实报告队列状态。
        """
        now = self._clock()
        with self._lock:
            checked = 0
            for lane in self._lanes.values():
                if not lane.authenticated:
                    continue
                for name in lane.allowed:
                    if resource and name != resource:
                        continue
                    checked += 1
                    if not self._circuit_open(lane.name, name, now):
                        return False
            return checked > 0
