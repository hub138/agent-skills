"""模型红线的唯一权威源（2026-11-15 收敛）。

此前 `agentctl.py` 与 `taskctl.py` 各写一份逐字相同的 ALLOWED_MODELS，
改一处忘另一处就会漂移；而两份都没有单测覆盖。现在统一到这里。

口径（用户 2026-11-12 红线）：
- codebuddy 侧：只允许 x0.00 或 ≤0.15 credits 的模型；贵档硬禁用，
  不依赖 429 自动回落（回落太晚，已经产生费用）。
- knot 侧：这些 ID 走免费额度，不受 codebuddy credits 红线约束，
  但仍必须在允许清单内（防止随手填一个不存在的模型名）。
- `<业务环境变量>=0` 只用于本地诊断，不能作为生产默认。
"""
from __future__ import annotations

import os

# codebuddy：x0.00 免费 + ≤0.15 credits 的便宜档
CB_ALLOWED = frozenset({
    "free-model", "free-model-flash", "small-model", "echo",
    "small-model", "free-model", "free-model-preview",
    "gpt-6-luna", "glm-5.3-flash-ioa", "minimax-m3.1-flash",
    "deepseek-v4.1-flash", "mimo-v2.6-pro", "gpt-5.6-luna",
})

# knot：实测扣费 0 的免费池
KNOT_ALLOWED = frozenset({
    "free-model", "small-model", "free-model-preview", "glm-5.3", "glm-5.3-flash",
    "deepseek-v4-flash", "deepseek-v4-pro",
})

# 兼容旧引用：默认给 codebuddy 清单
ALLOWED_MODELS = CB_ALLOWED


def allowed_for(backend: str) -> frozenset[str]:
    return KNOT_ALLOWED if backend == "knot" else CB_ALLOWED


def is_allowed(model: str, backend: str = "codebuddy") -> bool:
    return (model or "").strip() in allowed_for(backend)


def assert_model(model: str, backend: str = "codebuddy") -> None:
    """发请求前拒绝；不依赖 429 自动回落。诊断可用 <业务环境变量>=0 关闭。"""
    m = (model or "").strip()
    if os.environ.get("<业务环境变量>", "1") == "0":
        return
    if not is_allowed(m, backend):
        if backend == "knot":
            raise SystemExit(f"knot 模型 {m!r} 不在允许清单 {sorted(KNOT_ALLOWED)}")
        raise SystemExit(
            f"拒绝：模型 {m!r} 超出 0.15 credits 红线。允许 {sorted(CB_ALLOWED)}")
