"""测试经验沉淀与分层检索。"""

from agent_foundation import (
    ExperienceVault,
    FailureSignal,
    RetrievalQuery,
    Scope,
)


def test_repeat_failure_detection_gates_distillation():
    vault = ExperienceVault()
    signal = FailureSignal(phenomenon="compile_error")

    assert vault.observe_failure(signal) is False
    assert vault.observe_failure(signal) is True

    assert vault.distill(
        content="编译错误先查依赖版本",
        phenomenon="compile_error",
        scope=Scope.CASE,
    ) is True


def test_wide_scope_rejects_insufficient_support():
    vault = ExperienceVault()

    assert vault.distill(
        content="孤证不该进全局",
        phenomenon="flake",
        scope=Scope.GLOBAL,
        support_count=1,
    ) is False
    assert vault.distill(
        content="三个案例支撑可进场景层",
        phenomenon="flake",
        scope=Scope.SCENARIO,
        support_count=3,
    ) is True


def test_retrieve_filters_by_scope_and_ranks_by_trust():
    vault = ExperienceVault()
    vault.distill(content="案例层经验", phenomenon="p1", scope=Scope.CASE)
    vault.distill(content="仓库层经验", phenomenon="p1", scope=Scope.REPO, support_count=2)
    vault.distill(
        content="仓库层采纳过的经验",
        phenomenon="p1",
        scope=Scope.REPO,
        accepted_before=True,
        support_count=2,
    )
    vault.distill(
        content="仓库层对话来源经验",
        phenomenon="p1",
        scope=Scope.REPO,
        source="conversation_extract",
        support_count=2,
    )

    case_only = vault.retrieve(RetrievalQuery(text="经验", max_scope=Scope.CASE))
    assert [entry.content for entry, _ in case_only] == ["案例层经验"]

    ranked = vault.retrieve(RetrievalQuery(text="经验", max_scope=Scope.GLOBAL))
    contents = [entry.content for entry, _ in ranked]
    assert contents == ["仓库层对话来源经验", "仓库层采纳过的经验", "仓库层经验", "案例层经验"]


def test_empty_content_rejected():
    vault = ExperienceVault()
    assert vault.distill(content="  ", phenomenon="x", scope=Scope.CASE) is False
