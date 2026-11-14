"""经验准入策略：候选是否值得提炼、新教训与既有条目的关系，两个判定分开。

抽象自中台经验库的保守准入策略内核：入册判定区分正面教训（具体
候选证据加可信评估）、负面教训（失败信号针对该候选本身）与流程证
据（真实实验的过程价值）；运行环境失败（鉴权、配额、基础设施）永
远不是经验素材。相似性判定上，结构化条件冲突压过文本相似——语义
检索只能佐证结构上成立的合并，不能凭高分凭空创造合并；文本极近但
结构不足时先持留再观察，防记忆垃圾。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Admission = Literal["strategy", "process", "failure", "discard"]
Relation = Literal["merge", "new", "hold"]

# 这些描述运行环境与准备阶段的失败，不是尝试解法的结果，永不入经验库。
OPERATIONAL_FAILURE_CATEGORIES = frozenset({
    "auth_failed", "token_invalid", "token_expired", "token_missing",
    "credential_missing", "runner_unavailable", "runner_not_found",
    "preflight_failed", "configuration_error", "rate_limited",
    "quota_exhausted", "network_unavailable",
})

_TRANSFERABLE_FAILURE_CATEGORIES = frozenset({
    "off_hot_path", "invalid_evaluation", "constant_metric_placeholder",
    "constraint_violation", "metrics_regression", "regression",
    "test_failure", "syntax_error", "patch_apply_failed",
})


@dataclass(frozen=True)
class AdmissionDecision:
    disposition: Admission
    reason: str


@dataclass(frozen=True)
class SimilarityDecision:
    relation: Relation
    reason: str


def normalize(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_")


def decide_admission(
    *,
    execution_reward: float | None,
    total_reward: float | None,
    risk_reward: float | None = None,
    evaluation_quality: str | None,
    evidence_level: str | None,
    reject_reason_category: str | None,
    has_candidate_evidence: bool,
    min_total_reward: float,
) -> AdmissionDecision:
    """对已评估候选分类，不处理原始过程错误。"""
    category = normalize(reject_reason_category)
    quality = normalize(evaluation_quality)
    level = normalize(evidence_level)

    if not has_candidate_evidence:
        return AdmissionDecision("discard", "no_candidate_evidence")
    if category in OPERATIONAL_FAILURE_CATEGORIES:
        return AdmissionDecision("discard", "operational_failure")
    if quality == "invalid" and category != "invalid_evaluation":
        return AdmissionDecision("discard", "invalid_evaluation")
    if execution_reward is None:
        return AdmissionDecision("discard", "no_execution_outcome")

    positive = (
        execution_reward > 0
        and total_reward is not None
        and total_reward >= min_total_reward
        and level != "generic_fallback"
        and quality in {"reliable", ""}
    )
    if positive:
        return AdmissionDecision("strategy", "verified_positive_outcome")

    rollback = execution_reward <= -1.5
    risky_negative = execution_reward < -0.5 and risk_reward is not None and risk_reward < -0.3
    transferable = category in _TRANSFERABLE_FAILURE_CATEGORIES
    if rollback or risky_negative or transferable:
        return AdmissionDecision("failure", "candidate_specific_failure")

    if quality in {"reliable", "suspect"} and level != "generic_fallback":
        return AdmissionDecision("process", "evaluated_process_evidence")
    return AdmissionDecision("discard", "outcome_not_transferable")


def decide_similarity(
    *,
    candidate_kind: str | None,
    existing_kind: str | None,
    candidate_scenario_family: str | None = None,
    existing_scenario_family: str | None = None,
    candidate_artifact_family: str | None = None,
    existing_artifact_family: str | None = None,
    candidate_operation_direction: str | None = None,
    existing_operation_direction: str | None = None,
    candidate_hypothesis_family: str | None = None,
    existing_hypothesis_family: str | None = None,
    candidate_reject_reason: str | None = None,
    existing_reject_reason: str | None = None,
    structural_score: float,
    lexical_score: float = 0.0,
    semantic_score: float = 0.0,
) -> SimilarityDecision:
    """判定新教训与既有条目的关系：合并、新建或持留待证。"""
    left_kind, right_kind = normalize(candidate_kind), normalize(existing_kind)
    if left_kind and right_kind and left_kind != right_kind:
        return SimilarityDecision("new", "different_memory_kind")

    conflicts = (
        (candidate_scenario_family, existing_scenario_family, "scenario_family"),
        (candidate_artifact_family, existing_artifact_family, "artifact_family"),
        (candidate_operation_direction, existing_operation_direction, "operation_direction"),
        (candidate_hypothesis_family, existing_hypothesis_family, "hypothesis_family"),
    )
    for left, right, field in conflicts:
        if normalize(left) and normalize(right) and normalize(left) != normalize(right):
            return SimilarityDecision("new", f"conflicting_{field}")
    if (
        left_kind == "failure"
        and normalize(candidate_reject_reason)
        and normalize(existing_reject_reason)
        and normalize(candidate_reject_reason) != normalize(existing_reject_reason)
    ):
        return SimilarityDecision("new", "conflicting_failure_reason")

    if structural_score >= 0.90:
        return SimilarityDecision("merge", "same_structured_lesson")
    if structural_score >= 0.58 and (lexical_score >= 0.50 or semantic_score >= 0.82):
        return SimilarityDecision("merge", "structure_confirmed_by_text")
    if semantic_score >= 0.82 or lexical_score >= 0.82:
        return SimilarityDecision("hold", "semantic_match_without_structural_proof")
    return SimilarityDecision("new", "materially_new_lesson")
