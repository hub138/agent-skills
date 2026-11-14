"""长循环进度通知的节奏判定：失败立即报，成功按轮次聚合。

抽象自中台通知策略内核：循环跑到几十上百轮时，每轮都报会把真正的失败
淹没在例行进展里，全程静默又让人在出事时一无所知。失败是行动信号，
延迟等于损失；例行进展是状态信号，攒几轮一条足够。节奏设为零表示
进展不报、只报失败。
"""

from __future__ import annotations

DEFAULT_PROGRESS_INTERVAL_ROUNDS = 3


def should_notify_progress(
    *,
    current_round: int | None,
    interval_rounds: int,
    failed: bool = False,
) -> bool:
    """失败轮永远通知；正常轮按节奏（每 interval_rounds 轮一条）通知。

    interval_rounds 为零或负数时关闭进展通知，只报失败；
    current_round 为 None 或零时不通知（尚无进展可报）。
    """
    if failed:
        return True
    if interval_rounds <= 0 or current_round is None:
        return False
    return current_round > 0 and current_round % interval_rounds == 0
