"""提供方失败分类：识别模型结果可信之前的失败并给出冷却策略。

抽象自上游回移植的 AI 恢复内核：只识别发生在模型结果可信之前的
提供方侧失败（鉴权、限流、暂时不可用），绝不把产品输出里的正常词
（timeout、connection）误判为提供方故障；限流若自报重置时刻则按
重置时间冷却并加安全余量，否则用固定兜底冷却；暂时不可用允许同会
话重试，鉴权与限流则换通道并留下持久恢复点。语义判定不在此层。
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import Literal

ProviderFailureKind = Literal[
    "rate_limited",
    "authentication_failed",
    "provider_unavailable",
]

_FIXED_RATE_LIMIT_COOLDOWN_SECONDS = 5 * 3600
_RESET_MARGIN_SECONDS = 60
_MIN_COOLDOWN_SECONDS = 60
_MAX_COOLDOWN_SECONDS = 24 * 3600

_AUTH_MARKERS = (
    "authentication required", "api key", "invalid api key",
    "未登录", "鉴权失败", "认证失败", "401 unauthorized", "http 401",
    "403 forbidden", "http 403", "status 403",
)
_RATE_LIMIT_MARKERS = (
    "rate limit", "ratelimiterror", "rate_limit", "frequency limit",
    "usage limit", "quota", "429", "频率限制", "额度不足", "触发限流",
)
_DAILY_LIMIT_MARKERS = ("daily limit", "daily_limit", "日限制", "达到日限制")
_TRANSIENT_MARKERS = (
    "503 service unavailable", "service unavailable", "http 503", " 503 ",
    "502 bad gateway", "http 502", "504 gateway timeout", "http 504",
    "upstream connect error", "upstream overloaded", "connection reset by peer",
)

# 限流报文自带重置时刻，如「将在 2026-09-23 18:38:38 UTC+8 重置」。
_RESET_PATTERNS = (
    re.compile(
        r"将在\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s*UTC\s*([+-])(\d{1,2})(?::?(\d{2}))?",
        re.IGNORECASE,
    ),
    re.compile(
        r"reset\s*(?:at|after)?\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})"
        r"\s*(?:UTC)?\s*([+-])(\d{1,2})(?::?(\d{2}))?",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """一次提供方侧中断，携带冷却秒数与同会话可否重试。"""

    kind: ProviderFailureKind
    cooldown_seconds: int
    retry_same_session: bool
    summary: str


def reset_cooldown_seconds(value: object) -> int | None:
    """从自报重置时刻的限流报文推出冷却秒数；无重置信息返回 None。

    固定猜测在两个方向都错：重置在八小时后时傻等会反复撞墙，
    重置在五分钟后时白烧已恢复的额度。
    """
    text = str(value or "")
    for pattern in _RESET_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        day, clock, sign, hours, minutes = match.groups()
        try:
            local = _dt.datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        offset = _dt.timedelta(hours=int(hours), minutes=int(minutes or 0))
        reset_at = local.replace(tzinfo=_dt.timezone.utc)
        reset_at -= offset if sign == "+" else -offset
        remaining = (reset_at - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
        if remaining <= 0:
            return _MIN_COOLDOWN_SECONDS
        return min(_MAX_COOLDOWN_SECONDS, max(_MIN_COOLDOWN_SECONDS, int(remaining) + _RESET_MARGIN_SECONDS))
    return None


def classify_provider_failure(value: object) -> ProviderFailure | None:
    """只分类明确的提供方或鉴权失败，判定保持窄口径防误伤。"""
    text = str(value or "").lower()
    rate_cooldown = reset_cooldown_seconds(value) or _FIXED_RATE_LIMIT_COOLDOWN_SECONDS
    if any(marker in text for marker in _DAILY_LIMIT_MARKERS):
        return ProviderFailure("rate_limited", rate_cooldown, False, "模型额度或频率受限")
    if any(marker in text for marker in _AUTH_MARKERS):
        return ProviderFailure("authentication_failed", 3600, False, "凭据不可用")
    if any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return ProviderFailure("rate_limited", rate_cooldown, False, "模型额度或频率受限")
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return ProviderFailure("provider_unavailable", 60, True, "提供方暂时不可用")
    return None


def is_quota_or_auth_failure(value: object) -> bool:
    """该失败是否应熔断通道（限流或鉴权），区别于可立即重试的暂时故障。"""
    failure = classify_provider_failure(value)
    return failure is not None and failure.kind in {"rate_limited", "authentication_failed"}


def is_transient_provider_failure(value: object) -> bool:
    """该失败是否为可同会话重试的暂时故障。"""
    failure = classify_provider_failure(value)
    return failure is not None and failure.kind == "provider_unavailable"
