"""research_loop.metrics 工程回归(方案 5.1/5.2/5.3、13.1)。"""
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from research_loop import metrics  # noqa: E402


def _count(case_id, metric_id, tp=0, fn=0, fp=0, unknown=0):
    return {"case_id": case_id, "metric_id": metric_id,
            "tp": tp, "fn": fn, "fp": fp, "unknown": unknown}


def _spec(comparison="gt", threshold=0.98):
    return {
        "metrics": {
            "primary_metric": {"metric_id": "risk_recall",
                               "direction": "maximize", "threshold": threshold,
                               "comparison": comparison, "unit": "ratio"},
            "guard_metrics": [{"metric_id": "alert_precision",
                               "direction": "maximize",
                               "non_inferiority_tolerance": 0}],
            "non_inferiority_tolerance": 0,
        }
    }


def _agg_risk(tp, fn, precision_tp=30, precision_fp=20):
    return metrics.aggregate([
        _count("c1", "risk_recall", tp=tp, fn=fn),
        _count("c2", "alert_precision", tp=precision_tp, fp=precision_fp)])


def test_wilson_two_sided_reference_values():
    agg = metrics.aggregate([_count("c", "p", tp=40, fn=60)], conf=0.95,
                            side="two")
    rec = agg["p"]
    assert rec["denominator"] == 100
    assert abs(rec["lower_bound"] - 0.3094) < 0.002   # 13.1: 40/100 ≈ 0.3094
    rec30 = metrics.aggregate([_count("c", "p", tp=30, fn=70)])["p"]
    assert abs(rec30["lower_bound"] - 0.2189) < 0.002  # 13.1: 30/100 ≈ 0.2189


def test_wilson_one_sided_differs_from_two():
    counts = [_count("c", "p", tp=40, fn=60)]
    two = metrics.aggregate(counts, side="two")["p"]["lower_bound"]
    one = metrics.aggregate(counts, side="one")["p"]["lower_bound"]
    assert two != one
    assert one > two  # 95% 单侧 z 更小,下界更高


def test_aggregate_n_zero_is_none_not_100_percent():
    rec = metrics.aggregate([_count("c", "m")])["m"]
    assert rec["value"] is None
    assert rec["lower_bound"] is None
    assert rec["stat_method"] == "n0_no_estimate"
    assert metrics.wilson_lower_bound(40, 0) is None


def test_import_counts_contract_shape():
    counts = metrics.import_execution_result(
        {"exec_status": "succeeded",
         "cases": [{"case_id": "case-1",
                    "metrics": [{"metric_id": "risk_recall",
                                 "findings": ["rp-1", "rp-1", "rp-2"],
                                 "missed": ["rp-3"],
                                 "false_positives": ["alert-1", "alert-1"],
                                 "unknown": ["rp-4"]}]}]},
        _spec())
    assert counts == [{"case_id": "case-1", "metric_id": "risk_recall",
                       "tp": 2, "fn": 1, "fp": 1, "unknown": 1,
                       "alerts_deduped": 2}]
    rec = metrics.aggregate(counts)["risk_recall"]
    assert rec["numerator"] == 2          # unknown 不进 TP
    assert rec["unknown_count"] == 1
    assert rec["denominator"] == 5        # tp+fn+fp+unknown(保守口径)
    assert rec["value"] == 0.4


def test_import_rejects_failed_status_and_unregistered_metric():
    with pytest.raises(ValueError):
        metrics.import_execution_result({"exec_status": "failed",
                                         "cases": []}, _spec())
    with pytest.raises(ValueError):
        metrics.import_execution_result(
            {"exec_status": "succeeded",
             "cases": [{"case_id": "c", "metrics": [
                 {"metric_id": "not_registered"}]}]}, _spec())
    with pytest.raises(ValueError):
        metrics.import_execution_result({"exec_status": "succeeded"}, _spec())


def test_net_gain_121_of_123_passes():
    res = metrics.net_gain(_agg_risk(110, 13), _agg_risk(121, 2), _spec("gt"))
    assert metrics.aggregate([_count("c1", "risk_recall", tp=121, fn=2)])[
        "risk_recall"]["value"] > 0.98    # 121/123 严格过 98%
    assert res["verdict"] == "beneficial"
    assert res["primary_delta"] > 0
    assert res["guard_failures"] == []


def test_net_gain_120_of_123_fails():
    res = metrics.net_gain(_agg_risk(110, 13), _agg_risk(120, 3), _spec("gt"))
    assert res["verdict"] == "no_gain"    # 120/123 不过线,执行有效故非 inconclusive


def test_threshold_boundary_gte_passes_gt_fails():
    cand = _agg_risk(98, 2)               # 98/100 恰好等于阈值 0.98
    assert metrics.aggregate([_count("c1", "risk_recall", tp=98, fn=2)])[
        "risk_recall"]["value"] == 0.98
    res_gt = metrics.net_gain(_agg_risk(110, 13), cand, _spec("gt"))
    assert res_gt["verdict"] == "no_gain"
    res_gte = metrics.net_gain(_agg_risk(110, 13), cand, _spec("gte"))
    assert res_gte["verdict"] == "beneficial"


def test_guard_regression_blocks_beneficial():
    # 主指标过线,但 precision 0.6 → 0.333 跌穿不可退化门槛(方案 5.3)
    res = metrics.net_gain(_agg_risk(110, 13),
                           _agg_risk(121, 2, precision_tp=10, precision_fp=20),
                           _spec("gt"))
    assert res["guard_failures"] == ["alert_precision"]
    assert res["verdict"] != "beneficial"
    assert res["verdict"] == "no_gain"


def test_failed_attempt_never_reaches_net_gain():
    with pytest.raises(ValueError):
        metrics.import_execution_result({"exec_status": "failed",
                                         "cases": []}, _spec())
    cand = _agg_risk(121, 2)
    # 失败执行不产生合法计数 → baseline 缺失 → inconclusive
    assert metrics.net_gain({}, cand, _spec("gt"))["verdict"] == "inconclusive"
    # 即使把 failed 状态直接塞进聚合记录,也必须抛错
    bad = {"risk_recall": dict(cand["risk_recall"], exec_status="failed")}
    with pytest.raises(ValueError):
        metrics.net_gain({}, bad, _spec("gt"))


def test_aggregate_accepts_db_metric_rows():
    rows = [{"case_id": "att-1", "metric_id": "risk_recall", "numerator": 40,
             "denominator": 100, "unknown_count": 0}]
    rec = metrics.aggregate(rows)["risk_recall"]
    assert rec["value"] == 0.4
    assert abs(rec["lower_bound"] - 0.3094) < 0.002
