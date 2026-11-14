"""测试车队、预算、工件、指标与迭代环。"""

from agent_foundation import (
    BudgetExhausted,
    Convoy,
    IterationLoop,
    MetricDirection,
    NormalizedMetric,
    RunLayout,
    SpendGovernor,
    directory_size,
    prune_oldest,
)


def test_convoy_serial_within_lane_parallel_across_lanes():
    convoy = Convoy()
    assert convoy.enqueue("repo-a", "t1") is True
    assert convoy.enqueue("repo-a", "t1") is False
    assert convoy.enqueue("repo-a", "t2") is True
    assert convoy.enqueue("repo-b", "t3") is True

    assert convoy.dequeue() == ("repo-a", "t1")
    assert convoy.dequeue("repo-a") is None
    assert convoy.dequeue() == ("repo-b", "t3")

    convoy.finish("repo-a")
    assert convoy.dequeue("repo-a") == ("repo-a", "t2")
    convoy.finish("repo-a")
    convoy.finish("repo-b")
    assert convoy.dequeue() is None
    assert convoy.pending("repo-a") == {"repo-a": []}


def test_budget_hard_stop_and_remaining():
    governor = SpendGovernor(resource="tokens", max_units=10)
    governor.spend(6)
    assert governor.remaining == 4
    raised = False
    try:
        governor.spend(5)
    except BudgetExhausted as error:
        raised = True
        assert "tokens" in str(error)
    assert raised
    assert governor.spent_units == 6


def test_layout_prepare_and_prune(tmp_path):
    layout = RunLayout(root=tmp_path, run_id="run-1")
    layout.prepare()
    log = layout.task_log("task-1")
    log.write_text("x" * 100)
    checkpoint = layout.checkpoints / "cp.json"
    checkpoint.write_text("{}")

    assert directory_size(layout.root / "runs" / "run-1") == 102
    removed = prune_oldest(layout.root / "runs" / "run-1", max_bytes=50)
    assert [path.name for path in removed] == ["task-1.log"]
    assert directory_size(layout.root / "runs" / "run-1") <= 50


def test_metric_direction_aware_comparison():
    fast = NormalizedMetric("latency_p99", 90, MetricDirection.MINIMIZE, "ms")
    baseline = NormalizedMetric("latency_p99", 100, MetricDirection.MINIMIZE, "ms")
    assert fast.is_better_than(baseline, min_relative_gain=0.05) is True

    slow = NormalizedMetric("latency_p99", 99, MetricDirection.MINIMIZE, "ms")
    assert slow.is_better_than(baseline, min_relative_gain=0.05) is False

    mismatch = NormalizedMetric("latency_p99", 10, MetricDirection.MAXIMIZE, "ms")
    try:
        mismatch.is_better_than(baseline)
    except ValueError as error:
        assert "direction mismatch" in str(error)
    else:
        raise AssertionError("expected direction mismatch error")


def test_iteration_loop_accepts_rejects_and_rolls_back():
    proposals = iter(["patch-1", "patch-2"])
    reject_rollback_calls: list[str] = []

    def evaluate(proposal: str) -> dict[str, float]:
        return {"score": 0.9 if proposal == "patch-2" else 0.1}

    loop = IterationLoop(
        propose=lambda: next(proposals),
        evaluate=evaluate,
        accept=lambda metrics: metrics["score"] > 0.5,
        max_rounds=5,
        on_reject=lambda attempt: reject_rollback_calls.append(str(attempt.proposal)),
    )
    result = loop.run()
    assert result.accepted is True
    assert result.stop_reason == "accepted"
    assert [attempt.proposal for attempt in result.attempts] == ["patch-1", "patch-2"]
    assert reject_rollback_calls == ["patch-1"]


def test_iteration_loop_stops_on_round_budget():
    loop = IterationLoop(
        propose=lambda: "same",
        evaluate=lambda proposal: {"score": 0.1},
        accept=lambda metrics: False,
        max_rounds=3,
    )
    result = loop.run()
    assert result.accepted is False
    assert result.stop_reason == "max_rounds"
    assert len(result.attempts) == 3


def test_iteration_loop_reports_exhausted_source():
    loop = IterationLoop(
        propose=lambda: (_ for _ in ()).throw(StopIteration()),
        evaluate=lambda proposal: {},
        accept=lambda metrics: True,
        max_rounds=3,
    )
    result = loop.run()
    assert result.stop_reason == "exhausted"
    assert result.attempts == []
