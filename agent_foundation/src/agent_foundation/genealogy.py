"""候选谱系树：记录候选之间的派生关系，孤儿引用归根并计数。

抽象自迭代内核的候选谱系机制与它的三次真实学费：新增派生字段只建了列、
写入路径没有同步，字段永远为空，树退化成一串链；父引用取自上一轮整体
状态而非具体候选，来源不稳时全部节点挂在根下；每轮只产一个候选，树只有
深度没有分支。孤儿父引用归根保展示，同时计数——孤儿数量突然变多，说明
父引用来源断了，偶发正确不是设计保证。代数从父链现场推导，不单独存储，
存了必然与链脱节。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateNode:
    """一个候选：唯一 ID、可选的父候选引用、派生方式与接纳状态。"""

    candidate_id: str
    parent_candidate_id: str | None = None
    kind: str = ""
    accepted: bool = False


class Genealogy:
    """候选谱系：登记候选、按父引用建树、孤儿归根并计数、环直接报错。"""

    def __init__(self) -> None:
        self._nodes: dict[str, CandidateNode] = {}

    def add(self, node: CandidateNode) -> None:
        """登记一个候选；重复 ID 直接报错，静默覆盖会让两条分支并成一条。"""
        if node.candidate_id in self._nodes:
            raise ValueError(f"duplicate candidate_id: {node.candidate_id}")
        self._nodes[node.candidate_id] = node

    def get(self, candidate_id: str) -> CandidateNode | None:
        return self._nodes.get(candidate_id)

    def _effective_parent(self, node: CandidateNode) -> str | None:
        """父引用指向在册候选才有效；悬空引用按孤儿归根处理。"""
        if node.parent_candidate_id and node.parent_candidate_id in self._nodes:
            return node.parent_candidate_id
        return None

    def orphan_ids(self) -> list[str]:
        """父引用悬空的候选清单：归根展示，数量突增说明父引用来源断了。"""
        return [
            node.candidate_id
            for node in self._nodes.values()
            if node.parent_candidate_id and node.parent_candidate_id not in self._nodes
        ]

    def roots(self) -> list[CandidateNode]:
        """没有有效父引用的候选：真根与孤儿都在这里。"""
        return [n for n in self._nodes.values() if self._effective_parent(n) is None]

    def children(self, parent_id: str) -> list[CandidateNode]:
        """指定候选的全部直接子代。"""
        return [
            n for n in self._nodes.values() if self._effective_parent(n) == parent_id
        ]

    def depth(self, candidate_id: str) -> int:
        """沿父链上溯的深度，代数现场推导，不信任单独存储的代数字段。"""
        seen: set[str] = {candidate_id}
        current = candidate_id
        level = 0
        while True:
            node = self._nodes.get(current)
            if node is None:
                raise ValueError(f"unknown candidate_id: {current}")
            parent = self._effective_parent(node)
            if parent is None:
                return level
            if parent in seen:
                raise ValueError(f"cycle detected at: {parent}")
            seen.add(parent)
            current = parent
            level += 1

    def ancestry(self, candidate_id: str) -> list[CandidateNode]:
        """从候选沿父链上溯到根：回答「最终被接纳的方案是哪条分支长出来的」。"""
        chain: list[CandidateNode] = []
        seen: set[str] = set()
        current = candidate_id
        while True:
            node = self._nodes.get(current)
            if node is None:
                raise ValueError(f"unknown candidate_id: {current}")
            chain.append(node)
            if current in seen:
                raise ValueError(f"cycle detected at: {current}")
            seen.add(current)
            parent = self._effective_parent(node)
            if parent is None:
                return chain
            current = parent

    def tree(self) -> list[dict]:
        """嵌套字典树，从全部根展开；孤儿按根处理，孤儿清单用 orphan_ids 查。"""

        def build(node_id: str) -> dict:
            node = self._nodes[node_id]
            return {
                "candidate": node,
                "children": [
                    build(child.candidate_id) for child in self.children(node_id)
                ],
            }

        return [build(root.candidate_id) for root in self.roots()]
