"""运行预算守门。

抽象自迭代内核的预算三闸（轮数、墙钟、花费任一耗尽即停）
与批量工作台的并发与限额：预算是硬边界，越界就地报错拒绝本次支出，
不提供悄悄放行的通道。
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExhausted(RuntimeError):
    """预算已耗尽，本次支出被拒绝。"""


@dataclass
class SpendGovernor:
    """单一资源的支出闸门。单位由调用方定义（次数、token、分钟均可）。"""

    resource: str = "default"
    max_units: float = 0.0
    spent_units: float = field(default=0.0, init=False)

    def spend(self, units: float) -> None:
        """记一笔支出；越界抛 BudgetExhausted，支出不生效。"""
        if units < 0:
            raise ValueError("units must be >= 0")
        if self.spent_units + units > self.max_units:
            raise BudgetExhausted(
                f"{self.resource}: need {units}, remaining {self.max_units - self.spent_units}"
            )
        self.spent_units += units

    @property
    def remaining(self) -> float:
        return self.max_units - self.spent_units
