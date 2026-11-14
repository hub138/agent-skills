"""方向化指标的归一与比较。

抽象自迭代内核的指标记录（指标名/值/方向/单位）与指标归一化环节：
同一条指标在任何地方只允许一套口径——名称带方向，比较由方向决定，
各处不得自写比较逻辑产生第二套口径。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetricDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class NormalizedMetric:
    name: str
    value: float
    direction: MetricDirection
    unit: str | None = None

    def is_better_than(self, baseline: "NormalizedMetric", *, min_relative_gain: float = 0.0) -> bool:
        """是否严格优于基线：相对增益超过 min_relative_gain 才算更好。

        基线值为 0 时退化为绝对差值比较。方向不一致就地报错，
        静默按同方向处理会制造第二套口径。
        """
        if self.direction is not baseline.direction:
            raise ValueError(f"direction mismatch: {self.direction.value} vs {baseline.direction.value}")
        if baseline.value:
            improvement = (self.value - baseline.value) / abs(baseline.value)
        else:
            improvement = self.value - baseline.value
        if self.direction is MetricDirection.MINIMIZE:
            improvement = -improvement
        return improvement > min_relative_gain
