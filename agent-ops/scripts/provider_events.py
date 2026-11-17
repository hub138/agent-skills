"""CLI 输出的失败分类与通道冷却（桥接 agent_foundation.provider_failure）。

假绿灯实测：RC=0 但 stdout 是 {"type":"error",...}（如 Plugin runtime
refresh 超时）——foundation 的分类词表没有这种 agent 特有形态，所以在本地
补形态识别，再交给 foundation 分类（限流自报重置时刻则按时刻冷却；knot 不
自报 → 固定长冷却）。foundation 缺库时用内置兜底词表，行为一致。

冷却落地：$WATCHDOG_HOME/state/provider_cooldown.json 记 {kind, until,
reason}。supervise_* 是 cron 单次调用，没有常驻进程，冷却状态必须落盘才能
跨轮生效——否则 429 之后每 30 分钟再撞一次。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import foundation_bridge

AGENT_ERROR_MARKERS = ('"type":"error"', '"type": "error"',
                       "Plugin runtime refresh")

FALLBACK = {
    "rate": ("429", "rate limit", "too many requests", "额度不足", "触发限流"),
    "auth": ("401 unauthorized", "http 401", "403 forbidden", "api key",
             "鉴权失败", "认证失败"),
    "transient": ("503", "502", "504", "service unavailable",
                  "connection reset"),
}


def classify_output(text: str) -> dict | None:
    """分类 CLI 输出；只认明确形态，不命中返回 None（窄口径防误伤）。"""
    t = text or ""
    if any(m in t for m in AGENT_ERROR_MARKERS):
        return {"kind": "provider_unavailable", "cooldown_seconds": 60,
                "retry_same_session": True,
                "reason": "CLI 假绿灯：RC=0 但输出是 error JSON"}
    pf = foundation_bridge.load("agent_foundation.provider_failure")
    if pf is not None:
        f = pf.classify_provider_failure(t)
        if f is not None:
            return {"kind": f.kind, "cooldown_seconds": f.cooldown_seconds,
                    "retry_same_session": f.retry_same_session,
                    "reason": f.summary}
        # foundation 窄口径未命中 → 继续本地兜底（超集）；两边都不命中才返回 None
    low = t.lower()
    low = t.lower()
    if any(m in low for m in FALLBACK["rate"]):
        return {"kind": "rate_limited", "cooldown_seconds": 5 * 3600,
                "retry_same_session": False, "reason": "限流（兜底词表）"}
    if any(m in low for m in FALLBACK["auth"]):
        return {"kind": "authentication_failed", "cooldown_seconds": 3600,
                "retry_same_session": False, "reason": "鉴权（兜底词表）"}
    if any(m in low for m in FALLBACK["transient"]):
        return {"kind": "provider_unavailable", "cooldown_seconds": 60,
                "retry_same_session": True, "reason": "暂时不可用（兜底词表）"}
    return None


def cooldown_path() -> Path:
    home = Path(os.environ.get(
        "WATCHDOG_HOME", str(Path.home() / ".codebuddy" / "watchdog")))
    return home / "state" / "provider_cooldown.json"


def _load_state(path: Path) -> dict:
    aj = foundation_bridge.load("agent_foundation.atomic_json")
    if aj is not None:
        res = aj.AtomicJsonStore(path, default={}).load()
        if res.ok:
            return res.data or {}
        print("[provider_events] 冷却状态不可读：%s" % res.error, file=sys.stderr)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(path: Path, data: dict) -> None:
    aj = foundation_bridge.load("agent_foundation.atomic_json")
    if aj is not None:
        aj.AtomicJsonStore(path, default={}).save(data)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def in_cooldown() -> dict | None:
    """冷却期内返回状态 dict（含剩余秒数）；否则 None。

    冷却期内发起监督调用是必败调用，调用方应直接跳过本轮。
    """
    data = _load_state(cooldown_path())
    until = float(data.get("until") or 0)
    if until and time.time() < until:
        data = dict(data)
        data["remaining_seconds"] = int(until - time.time())
        return data
    return None


def note_cooldown(kind: str, cooldown_seconds: int, reason: str) -> dict:
    """记录一次提供方失败及其冷却窗口。"""
    data = {"kind": kind, "until": time.time() + max(0, int(cooldown_seconds)),
            "reason": reason, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save_state(cooldown_path(), data)
    return data


def handle_output(text: str) -> dict | None:
    """一站式：分类 + 落冷却。返回分类 dict；None = 无已知失败形态。"""
    info = classify_output(text)
    if info is not None and not info.get("retry_same_session"):
        note_cooldown(info["kind"], info["cooldown_seconds"], info["reason"])
    return info
