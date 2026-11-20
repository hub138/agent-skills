"""实验状态机纪律测试（方案 13.1 状态/恢复行）。"""
import sys

import pytest

sys.path.insert(0, "scripts")

from research_loop import experiment as E  # noqa: E402
from research_loop import store  # noqa: E402

PROJECT = {
    "identity": {"schema_version": "1", "project_id": "p1",
                 "objective_version": "v1", "goal": "g"},
    "data": {"manifest": "cases.jsonl", "version": "t-v1"},
    "evaluator": {"adapter_id": "exact", "judge_version": "exact-v1"},
    "metrics": {
        "primary_metric": {"metric_id": "recall", "direction": "maximize",
                           "threshold": 0.98, "comparison": "gt", "unit": "risk_point"},
        "guard_metrics": [{"metric_id": "precision", "direction": "maximize"}],
        "non_inferiority_tolerance": 0},
    "explore": {"dev_batch_size": 10, "stall_limit": 2},
    "completion": {"final_gate": [
        {"metric_id": "recall", "threshold": 0.98, "comparison": "gt"},
        {"metric_id": "precision_lb", "threshold": 0.30, "comparison": "gt",
         "apply_lower_bound": True}]},
}


def mk_metrics(recall, precision=0.5):
    from statistics import NormalDist
    z = NormalDist().inv_cdf(0.975)

    def lb(k, n):
        p_ = k / n
        d = 1 + z * z / n
        c = p_ + z * z / (2 * n)
        mm = z * ((p_ * (1 - p_) / n + z * z / (4 * n * n)) ** 0.5)
        return max(0.0, (c - mm) / d)
    return {"recall": {"value": recall, "numerator": round(recall * 100),
                       "denominator": 100,
                       "lower_bound": lb(round(recall * 100), 100)},
            "precision": {"value": precision,
                          "numerator": round(precision * 100),
                          "denominator": 100,
                          "lower_bound": lb(round(precision * 100), 100)}}


    return {"recall": {"value": recall, "lower_bound": None},
            "precision": {"value": precision, "lower_bound": None}}


@pytest.fixture
def eng(tmp_path):
    db = store.open_db(str(tmp_path / "research.db"))
    return E.ExperimentEngine(db, tmp_path, PROJECT)


def _round(eng, rid, cand, recall_c, precision_c=0.5, batch="bA"):
    eng.record_dev(rid, batch, "run-" + rid, mk_metrics(recall_c, precision_c),
                   mk_metrics(0.5), cand, ["c%d" % i for i in range(10)])
    return eng.record_dev  # 返回便于链式


def test_baseline_required_before_round(eng):
    with pytest.raises(E.LoopRuleError, match="baseline"):
        eng.start_round("r1", "c1", "单机制")


def test_no_nested_round(eng):
    eng.record_baseline("run0", mk_metrics(0.5))
    eng.start_round("r1", "c1", "机制A")
    with pytest.raises(E.LoopRuleError, match="未闭合"):
        eng.start_round("r2", "c2", "机制B")


def test_net_gain_and_guard(eng):
    eng.record_baseline("run0", mk_metrics(0.5, 0.6))
    net = eng._net_gain(mk_metrics(0.5, 0.6), mk_metrics(0.6, 0.4))
    assert net["verdict"] == "no_gain"  # 主指标涨但 guard 退化 → 不采纳
    assert "precision" in net["guard_failures"]
    net2 = eng._net_gain(mk_metrics(0.5, 0.6), mk_metrics(0.45, 0.6))
    assert net2["verdict"] == "regression"


def test_verify_requires_disjoint_batch(eng):
    eng.record_baseline("run0", mk_metrics(0.5))
    eng.start_round("r1", "c1", "机制A")
    eng.record_dev("r1", "bA", "run1", mk_metrics(0.6), mk_metrics(0.5), "c1", ["x"])
    with pytest.raises(E.LoopRuleError, match="case_ids_b"):
        eng.verify("r1", "bA", "run1b", mk_metrics(0.6), mk_metrics(0.5))
    with pytest.raises(E.LoopRuleError, match="不重叠"):
        eng.verify("r1", "bA", "run1b", mk_metrics(0.6), mk_metrics(0.5),
                   case_ids_b=["x"])


def test_abort_not_no_gain(eng):
    """执行失败 → abort（inconclusive 语义），不算 no_gain。"""
    eng.record_baseline("run0", mk_metrics(0.5))
    eng.start_round("r1", "c1", "机制A")
    eng.abort_round("r1", "codebuddy rc=127 env node 缺失")
    evs = [e["kind"] for e in store.replay_events(eng.db)]
    assert "round.aborted" in evs and "round.closed" not in evs


def test_final_gates(eng):
    eng.record_baseline("run0", mk_metrics(0.5))
    eng.start_round("r1", "c1", "机制A")
    eng.record_dev("r1", "bA", "run1", mk_metrics(0.6), mk_metrics(0.5), "c1", ["x"] * 0 + ["c%d" % i for i in range(10)])
    eng.verify("r1", "bB", "run1b", mk_metrics(0.6), mk_metrics(0.5),
               case_ids_b=["d%d" % i for i in range(10)])
    r = eng.expand("r1", "run1x", mk_metrics(0.6), mk_metrics(0.5), "c1")
    assert r["adopted"]
    # 冻结（expand 采纳后）
    eng.lock_final("c1", "run1x", "g1", {"digest": "d"})
    # 未 leak：final 拒绝
    with pytest.raises(E.LoopRuleError, match="隔离"):
        eng.final_evaluated("f1", {"recall": {"value": 0.99},
                                   "precision_lb": {"value": 0.5, "lower_bound": 0.5}}, "g1", "od")
    with pytest.raises(E.LoopRuleError, match="隔离"):
        eng.check_leak({"verdict": "fail"})
    eng.check_leak({"verdict": "pass"})
    # 终测：R 0.99>0.98 过，P 下界 0.5>0.30 过
    out = eng.final_evaluated("f1", {"recall": {"value": 0.99},
                                     "precision_lb": {"value": 0.5, "lower_bound": 0.5}}, "g1", "od")
    assert out["passed"] and out["gates"]["recall"]
    # 已开封不能再测
    with pytest.raises(E.LoopRuleError, match="开封"):
        eng.final_evaluated("f2", {"recall": {"value": 0.99},
                                   "precision_lb": {"value": 0.5, "lower_bound": 0.5}}, "g1", "od")
    eng.adopt("c1")
    with pytest.raises(E.LoopRuleError, match="终测未通过|未冻结|不能采纳"):
        eng.adopt("c-bad")


def test_final_fail_blocks_and_precision_gate(eng):
    eng.record_baseline("run0", mk_metrics(0.5))
    eng.start_round("r1", "c1", "机制A")
    eng.record_dev("r1", "bA", "run1", mk_metrics(0.6), mk_metrics(0.5), "c1", ["c%d" % i for i in range(10)])
    eng.verify("r1", "bB", "run1b", mk_metrics(0.6), mk_metrics(0.5),
               case_ids_b=["d%d" % i for i in range(10)])
    eng.expand("r1", "run1x", mk_metrics(0.6), mk_metrics(0.5), "c1")
    eng.lock_final("c1", "run1x", "g1", {"digest": "d"})
    eng.check_leak({"verdict": "pass"})
    # P 下界 0.2 < 0.30 不过；R 0.99 过 → 整体 fail
    out = eng.final_evaluated("f1", {"recall": {"value": 0.99},
                                     "precision_lb": {"value": 0.2, "lower_bound": 0.2}}, "g1", "od")
    assert not out["passed"] and out["gates"]["precision_lb"] is False
