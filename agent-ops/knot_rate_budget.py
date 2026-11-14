#!/usr/bin/env python3
"""Knot 官方限流口径下的速率预算 / 自动恢复（可直接 import）。

权威来源（用户查证，2026-11-12）：
  内部文档 （内部文档，公开版略） 《智能体使用限流与模型 token 限额说明》
  工程实践 （内部文档，公开版略） 《TME AI 后台自动化接入司内免费模型方案》
官方注明限流策略可能动态调整，本文件数字只是当时的权威口径，用环境变量可覆盖。

**适用边界（2026-11-12 用户纠正）**：本文件所有数字都是 **knot-cli / Knot 平台**的。
codebuddy CLI 是**另一套机制**：它的 429 会在文案里明确通知「将在 <时刻> 重置」，
可以解析时间做整模型冷却；**knot 的 429 没有任何恢复时间通知**，只能靠降并发、
切模型、短退避 + 探测式自动恢复。别把 `quota_exhausted` 当成 knot 的恢复路径。

核心洞察（之前 skill 写错过，务必记住）：
1. 官方限制的是**速率（次/分钟、次/天）**，不是「在途并发数」。
   并发与速率的换算：启动速率(次/分) = 在途并发 ÷ 平均单次耗时(秒) × 60。
   所以「并发多少」没有固定答案：长任务 50s 时 8 路才 9.6 次/分很安全；
   短任务 7s 时 8 路就是 68 次/分，必然撞 20 次/分 / 模型调用速率上限 的墙。
2. **一次智能体调用可能触发多次模型调用**，所以并发会话会被放大；
   单个串行没问题、并发就报错，正是这个放大效应。
3. **各模型限频相互独立（人+模型粒度）**，撞限流时切模型是有效手段。
   之前实测写的「429 换模型没用」是错的：那次是所有模型被同一批 worker
   同时打满，看起来像换模型没用，实际是没做按模型分桶 + 降速。
4. 天级限额按**滚动 24h 窗口**重置，不是自然日 0 点。
5. `timeout` 是**通道占用**，不属于限流文档管辖，重试不如错峰或绕过。
6. 「模型资源非常紧张」是平台负载，不是个人限流，稍等或换模型即可。
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

# ── 官方数字（平台官方限流文档，可能动态调整）────────────────────────────
AGENT_RPM = int(os.environ.get("KNOT_AGENT_RPM", "20"))            # 单个智能体 次/分钟
AGENT_DAILY = int(os.environ.get("KNOT_AGENT_DAILY", "2000"))        # 单个智能体 次/天
MODEL_CALL_RPM = int(os.environ.get("KNOT_MODEL_CALL_RPM", "60"))    # 模型调用(人+模型) 次/分钟
PERSON_DAILY = int(os.environ.get("KNOT_PERSON_DAILY", "2000"))      # 个人 LLM 总量 次/天
TEAM_DAILY = int(os.environ.get("KNOT_TEAM_DAILY", "4000"))          # 团队账号 次/天

# 各模型独立限频：(次/分钟, 次/窗口, 窗口秒)
PER_MODEL_LIMITS = {
    "glm-5.3":         (30, 1500, 5 * 3600),
    "glm-5.3-flash":   (45, 3000, 5 * 3600),
    "glm-5.2":         (30, 1500, 5 * 3600),
    "deepseek-v4-flash": (120, 18000, 24 * 3600),
    "deepseek-v4-pro":   (120, 18000, 24 * 3600),
    "small-model":               (120, 18000, 24 * 3600),
    "free-model":               (120, 18000, 24 * 3600),
    "free-model-preview":       (120, 18000, 24 * 3600),
}

# 十几个项目共用同一免费池，本项目只取其中一份（默认 25%，保守）。
PROJECT_SHARE = float(os.environ.get("KNOT_PROJECT_SHARE", "0.25"))
# 一次智能体调用平均触发的模型调用次数（保守估计）。
CALLS_PER_AGENT = float(os.environ.get("KNOT_CALLS_PER_AGENT", "2"))
# 安全系数：留余量给其它项目和瞬时抖动。
SAFETY = float(os.environ.get("KNOT_SAFETY", "0.7"))

# 用户 2026-11-12 口径（修正）：**同模型最多 2 并发**；
# **多模型合计全局上限 10**（其它项目也在用，别打满）。
# 旧实现把「每模型 2」误做成「本项目总量 2」，2 个模型各只跑 1 路。
GLOBAL_PER_MODEL_CAP = int(os.environ.get("KNOT_GLOBAL_PER_MODEL_CAP", "3"))
PER_MODEL_CAP = int(os.environ.get("KNOT_PER_MODEL_CAP", "2"))
GLOBAL_CAP = int(os.environ.get("KNOT_PROJECT_GLOBAL_CAP", "10"))
# 兼容旧引用：PROJECT_HARD_CAP 现在指「本项目总量上限」，不再是 2。
PROJECT_HARD_CAP = GLOBAL_CAP


def recommend_workers(avg_latency_s: float, share: float = PROJECT_SHARE) -> int:
    """按官方速率反推本项目可用在途并发；这是「全局多少」的正确答案。

    约束取三者最小：
      - 单个智能体的官方速率上限 × share
      - 模型调用 模型调用速率上限 ÷ 每次智能体触发的模型调用数 × share
      - 滚动 24h 个人天级预算折算成的分钟速率 × share
    再乘安全系数，最后 并发 = 允许速率(次/分) × 平均耗时(秒) / 60。
    """
    agent_rpm = AGENT_RPM * share
    model_rpm = MODEL_CALL_RPM / max(1.0, CALLS_PER_AGENT) * share
    # 天级 2000/滚动24h 是「总量闸门」不是速率上限：批量任务本来就是
    # 短时间集中跑，摊成 1.39 次/分会把并发错误地压成 1 路。
    # 它由 RateBudget.day_remaining() 单独检查，不参与这里的速率反推。
    allowed_rpm = min(agent_rpm, model_rpm) * SAFETY
    by_rate = max(1, int(allowed_rpm * max(1.0, avg_latency_s) / 60))
    # 单模型建议并发：每模型最多 2 路，公式算再大也 clamp。
    return min(PER_MODEL_CAP, by_rate)


def classify_error(text: str) -> str:
    """调用方应把 stdout+stderr 合并传进来：-p 模式下 429 常在 stdout 且 RC=0。"""
    """把失败归到正确的恢复策略，别一律 45s 退避。"""
    t = (text or "").lower()
    if "资源非常紧张" in t or "model resource" in t or "有限流情况" in t:
        return "platform_load"           # 平台负载，短退避/换模型
    # 这条只属于 codebuddy CLI（它的 429 带「将在 <时刻> 重置」通知）。
    # knot 的 429 从不给恢复时间，永远不会走到这里；放前面是为了避免
    # 混用两条通道时把额度文案误判成 knot 个人限流。
    if "使用量已超出" in t or "quota" in t or "额度" in t:
        return "quota_exhausted"         # codebuddy 专属：整模型冷却到通知时刻
    if "429" in t or "too many requests" in t or "ratelimit" in t:
        return "personal_limit"          # 个人/模型限流，切模型 + 降速
    if "timeout" in t or "timed out" in t or "超时" in t:
        return "channel_timeout"         # 通道占用，错峰/绕过，不重试
    return "transient"


RECOVERY = {
    "platform_load":    "短退避 8s/16s 最多 2 次，或切另一个模型；不是个人限流",
    "personal_limit":   "按模型独立 → 切下一个模型并降并发；不要原地退避 45s",
    "quota_exhausted":  "【仅 codebuddy】解析文案里的重置时刻，整模型冷却到那一刻并持久化，到期自动回归；knot 无此通知，不适用",
    "channel_timeout":  "不重试；错峰或绕过到独立通道（codebuddy），失败留给下轮断点续跑",
    "transient":        "失败不写库，下轮断点续跑自动重判",
}


# ── codebuddy credits 红线（用户 2026-11-12：用量太大，贵档不用）──────
# 只允许 x0.00（免费）或 ≤0.15 credits；其余在调用前拒绝，不靠 429 回落
# （回落本身可能落到贵模型，反而更贵）。
CB_ALLOWED_MODELS = {
    # x0.00（hy 系列带/不带 -ioa 两种写法都放行）
    "free-model", "free-model-flash", "small-model", "echo", "small-model", "free-model", "free-model-preview",
    # ≤0.15
    "gpt-6-luna", "glm-5.3-flash-ioa", "minimax-m3.1-flash",
    "deepseek-v4.1-flash", "mimo-v2.6-pro", "gpt-5.6-luna",
}
CB_MAX_CREDITS = 0.15


def assert_cb_model_allowed(model: str, strict: bool = True) -> None:
    """codebuddy 模型白名单校验。strict=False 时只放行不报错。"""
    m = (model or "").strip()
    if m in CB_ALLOWED_MODELS or not strict:
        return
    raise ValueError(
        f"codebuddy 模型 {m!r} 超出 {CB_MAX_CREDITS} credits 红线，已拒绝。"
        f"允许：{sorted(CB_ALLOWED_MODELS)}")


class AdaptiveConcurrency:
    """knot 专用：没有恢复时间通知时的探测式自动恢复。

    撞 429 → 立即降并发并短冷却；连续成功 N 条 → 升 1 路；
    永远不超过本项目全局上限 GLOBAL_CAP(10)。
    状态写文件，跨重启保留；别的 AI 可直接 import 复用。
    """
    COOL_SECONDS = 60.0          # 第 1 次 429 的静默
    MAX_COOL_SECONDS = 480.0     # 指数退避封顶，避免长期停摆
    SUCCESS_TO_RAISE = 5

    def __init__(self, path: str | None = None):
        import json
        self.path = path or os.environ.get(
            "KNOT_ADAPTIVE_FILE", "/tmp/knot_adaptive_concurrency.json")
        self._lock = threading.Lock()

    def _load(self) -> dict:
        import json
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"workers": 1, "cool_until": 0.0, "streak": 0, "fails": 0}

    def _save(self, d: dict) -> None:
        import json
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def current(self) -> int:
        with self._lock:
            d = self._load()
            if d.get("cool_until", 0) > time.time():
                return 1
            return max(1, min(PROJECT_HARD_CAP, int(d.get("workers", 1))))

    def on_rate_limited(self) -> int:
        """连续 429 → 指数静默（60/120/240/480s 封顶）。

        模拟实测：容量被占满时，每轮发 1 路探测会持续产生 429；
        整段静默把「每轮 1 个错」变成「每 60~480s 探一次」，
        报错 27→9（-67%），吞吐只掉 11%。成功后 fails 清零。
        """
        with self._lock:
            d = self._load()
            fails = int(d.get("fails", 0)) + 1
            cool = min(self.COOL_SECONDS * (2 ** min(fails - 1, 3)),
                       self.MAX_COOL_SECONDS)
            d.update(workers=1, cool_until=time.time() + cool,
                     streak=0, fails=fails)
            self._save(d)
        return 1

    def on_success(self) -> int:
        with self._lock:
            d = self._load()
            if d.get("cool_until", 0) > time.time():
                return 1
            d["fails"] = 0
            d["streak"] = int(d.get("streak", 0)) + 1
            if d["streak"] >= self.SUCCESS_TO_RAISE:
                d["workers"] = min(PROJECT_HARD_CAP, int(d.get("workers", 1)) + 1)
                d["streak"] = 0
            self._save(d)
            return max(1, min(PROJECT_HARD_CAP, int(d.get("workers", 1))))

    def wait_if_cooling(self) -> float:
        """静默期内不发请求，等冷却结束；返回等待秒数。"""
        with self._lock:
            left = self._load().get("cool_until", 0) - time.time()
        if left <= 0:
            return 0.0
        time.sleep(min(left, self.MAX_COOL_SECONDS))
        return left

    def on_timeout(self) -> None:
        """通道占用不是限流，不触发降并发；只打断连续成功计数。"""
        with self._lock:
            d = self._load()
            d["streak"] = 0
            self._save(d)


class RateBudget:
    """跨进程可共享的滑动窗口速率闸门（文件持久化，重启不丢）。

    用法：
        budget = RateBudget()
        budget.acquire(model)      # 会阻塞到速率允许，返回实际等待秒数
        budget.record(model, ok)   # 记一次结果
        print(budget.status())
    """
    WINDOW = 60.0
    DAY = 24 * 3600.0

    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get(
            "KNOT_BUDGET_FILE", "/tmp/knot_rate_budget.json")
        self._lock = threading.Lock()
        self._local: dict[str, deque] = defaultdict(deque)
        self._cooldown: dict[str, float] = {}

    def _load(self) -> dict:
        try:
            import json
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        import json
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _prune(self, q: deque, now: float, window: float) -> None:
        while q and q[0] < now - window:
            q.popleft()

    def acquire(self, model: str, avg_latency_s: float = 45.0) -> float:
        """按官方上限等待到可以发起下一次调用。返回等待秒数。"""
        limit_rpm, _, _ = PER_MODEL_LIMITS.get(model, (30, 1500, 5 * 3600))
        budget_rpm = min(AGENT_RPM, limit_rpm / max(1.0, CALLS_PER_AGENT)) \
            * PROJECT_SHARE * SAFETY
        interval = 60.0 / max(0.1, budget_rpm)
        waited = 0.0
        with self._lock:
            q = self._local[model]
            while True:
                now = time.time()
                self._prune(q, now, self.WINDOW)
                # 冷却中的模型直接跳过（调用方应切模型）
                until = self._cooldown.get(model, 0)
                if until > now:
                    wait = min(until - now, 60.0)
                elif q:
                    wait = max(0.0, interval - (now - q[-1]))
                else:
                    wait = 0.0
                if wait <= 0:
                    q.append(now)
                    break
                time.sleep(min(wait, 5.0))
                waited += min(wait, 5.0)
        return waited

    def cool(self, model: str, seconds: float) -> None:
        with self._lock:
            self._cooldown[model] = max(
                self._cooldown.get(model, 0), time.time() + seconds)
            data = self._load()
            data.setdefault("cooldown", {})[model] = self._cooldown[model]
            self._save(data)

    def available_models(self, models: list[str]) -> list[str]:
        now = time.time()
        return [m for m in models if self._cooldown.get(m, 0) <= now] or models[-1:]

    def day_remaining(self) -> int:
        """滚动 24h 个人总量剩余额度（官方：不是自然日 0 点重置）。"""
        data = self._load()
        stamps = [x for x in data.get("daily", [])
                  if isinstance(x, (int, float)) and x > time.time() - self.DAY]
        return max(0, PERSON_DAILY - len(stamps))

    def record_daily(self) -> None:
        """记一次调用到滚动 24h 窗口。"""
        with self._lock:
            data = self._load()
            stamps = [x for x in data.get("daily", [])
                      if isinstance(x, (int, float)) and x > time.time() - self.DAY]
            stamps.append(time.time())
            data["daily"] = stamps
            self._save(data)

    def status(self) -> dict:
        now = time.time()
        out = {}
        with self._lock:
            for m, q in self._local.items():
                self._prune(q, now, self.WINDOW)
                out[m] = {"rpm_last_60s": len(q),
                          "cooldown_s": max(0, self._cooldown.get(m, 0) - now)}
        return out


if __name__ == "__main__":
    print("=== 官方口径下的本项目并发建议 ===")
    for lat in (7, 25, 45, 60, 90):
        print(f"  平均单次 {lat:>3}s → 建议并发 {recommend_workers(lat):>2} 路")
    print(f"  预算: 智能体 {AGENT_RPM}/分, 模型调用 {MODEL_CALL_RPM}/分, "
          f"个人 {PERSON_DAILY}/滚动24h, 本项目份额 {PROJECT_SHARE:.0%}")
    print(f"  上限: 每模型 {PER_MODEL_CAP} 并发, 本项目全局 {GLOBAL_CAP} "
          f"（用户口径，优先于公式）")
    a = AdaptiveConcurrency("/tmp/knot_adaptive_selftest.json")
    print("  探测式恢复:", a.current(), "-> 撞429:", a.on_rate_limited(),
          "-> 连续5次成功后:", [a.on_success() for _ in range(5)][-1])
    print("=== 失败分类与恢复 ===")
    for s in ('{"code":429,"msg":"too many requests"}',
              "模型资源非常紧张，会有限流情况",
              "429 您的使用量已超出频率限制，将在 2026-11-12 11:17:59 重置",
              "knot-cli chat terminated (hard_timeout)"):
        k = classify_error(s)
        print(f"  {k:<18} → {RECOVERY[k]}")
