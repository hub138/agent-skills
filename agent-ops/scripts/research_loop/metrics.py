"""指标导入、Wilson 下界聚合与净收益判定(方案 5.1/5.2/5.3、13.1)。

导入契约(适配器 result.json 的逐用例结果):

    {
      "exec_status": "succeeded",            # 仅 succeeded 允许入账
      "cases": [
        {"case_id": "case-001",
         "metrics": [
           {"metric_id": "risk_recall",
            "findings": ["rp-1", "rp-2"],    # 命中的有效计数单位
            "missed": ["rp-3"],              # FN:未命中的目标单位
            "false_positives": ["alert-1"],  # FP:经复核不成立的告警
            "unknown": ["rp-4"]}             # 未审/无法判定,不计 TP
         ]}
      ]
    }

导入层只做集合去重与计数,不做语义裁决(裁决属 Judge/适配器):
- findings/missed/false_positives/unknown 均为字符串 id 列表,按集合去重,
  被去重的重复项数量记入 alerts_deduped(方案 5.1:重复告警不提高分子);
- unknown 不算 TP,保守口径计入聚合分母(方案 5.1,须提前锁定);
- 同一 metric 内计数单位必须一致(风险点与告警是不同单位,方案 5.1),
  混合口径须拆成不同 metric_id 分开建分母。
"""
from __future__ import annotations

import math
from statistics import NormalDist

_LIST_KEYS = ("findings", "missed", "false_positives", "unknown")


def _known_metric_ids(spec) -> set:
    """spec.metrics 里登记的 metric_id 集合(主指标 + guard,guard 允许字符串)。"""
    if not isinstance(spec, dict):
        return set()
    m = spec.get("metrics")
    if not isinstance(m, dict):
        return set()
    known = set()
    pm = m.get("primary_metric")
    if isinstance(pm, dict) and pm.get("metric_id"):
        known.add(pm["metric_id"])
    for g in m.get("guard_metrics") or []:
        if isinstance(g, dict) and g.get("metric_id"):
            known.add(g["metric_id"])
        elif isinstance(g, str):
            known.add(g)
    return known


def import_execution_result(result, spec) -> list:
    """逐用例导入执行结果为计数列表(方案 5.1)。

    返回 list[dict],每项恰为:
        {case_id, metric_id, tp, fn, fp, unknown, alerts_deduped}
    - tp = 去重后的 findings 数;unknown 不进 TP;
    - alerts_deduped = 各列表被集合去重掉的重复项数量;
    - metric_id 必须已在 spec.metrics(primary/guard)登记,未登记拒绝;
    - exec_status != "succeeded" 一律 ValueError(方案 13.1:
      执行失败/未完成不冒充计分数据,更不冒充"无收益")。
    """
    if not isinstance(result, dict):
        raise ValueError("result 必须是 dict")
    status = result.get("exec_status")
    if status != "succeeded":
        raise ValueError(
            "exec_status=%r 的执行结果不得进入指标账本"
            "(方案 13.1:执行失败不冒充无收益)" % (status,))
    cases = result.get("cases")
    if not isinstance(cases, list):
        raise ValueError("result.cases 必须是列表")
    known = _known_metric_ids(spec)
    counts = []
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("result.cases 项必须是对象")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("用例缺少 case_id")
        if case_id in seen:
            raise ValueError("用例 case_id 重复: %s" % case_id)
        seen.add(case_id)
        mlist = case.get("metrics") or []
        if not isinstance(mlist, list):
            raise ValueError("case.metrics 必须是列表: %s" % case_id)
        for mrec in mlist:
            if not isinstance(mrec, dict):
                raise ValueError("case.metrics 项必须是对象: %s" % case_id)
            mid = mrec.get("metric_id")
            if not isinstance(mid, str) or not mid:
                raise ValueError("缺少 metric_id: %s" % case_id)
            if known and mid not in known:
                raise ValueError("未登记指标 %r(用例 %s)" % (mid, case_id))
            uniq = {}
            dup = 0
            for key in _LIST_KEYS:
                raw = mrec.get(key) or []
                if not isinstance(raw, list) or not all(
                        isinstance(x, str) for x in raw):
                    raise ValueError("%s/%s.%s 必须是字符串列表"
                                     % (case_id, mid, key))
                s = set(raw)
                dup += len(raw) - len(s)
                uniq[key] = s
            counts.append({
                "case_id": case_id,
                "metric_id": mid,
                "tp": len(uniq["findings"]),
                "fn": len(uniq["missed"]),
                "fp": len(uniq["false_positives"]),
                "unknown": len(uniq["unknown"]),
                "alerts_deduped": dup,
            })
    return counts


def wilson_lower_bound(k, n, conf=0.95, side="two"):
    """Wilson 区间下端(方案 5.2 公式)。n<=0 返回 None(不支持估计)。"""
    if not (isinstance(k, (int, float)) and isinstance(n, (int, float))):
        raise ValueError("k/n 必须是数值")
    if not (0 < conf < 1):
        raise ValueError("conf 必须在 (0, 1) 区间")
    if side not in ("two", "one"):
        raise ValueError("side 只允许 two/one")
    if n <= 0:
        return None
    if k < 0 or k > n:
        raise ValueError("k 必须在 [0, n] 内")
    p = k / n
    z = NormalDist().inv_cdf(conf if side == "one" else (1 + conf) / 2)
    z2 = z * z
    centre = p + z2 / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return min(1.0, max(0.0, (centre - spread) / (1 + z2 / n)))


def _as_intlike(x):
    f = float(x)
    return int(f) if f.is_integer() else f


def _norm_count(item):
    """归一化 counts 项,兼容两种形态:

    - 逐用例形态(import_execution_result 产出): tp/fn/fp/unknown,
      denominator = tp+fn+fp+unknown(unknown 保守计入分母,不计 TP);
    - research.db metrics 表行形态: numerator/denominator/unknown_count
      (报告"数字全部来自 db 经 aggregate 重算"用)。
    返回 (numerator, denominator, unknown, fn, fp);行形态 fn/fp 为 None。
    """
    if "numerator" in item or "denominator" in item:
        num = item.get("numerator") or 0
        den = item.get("denominator") or 0
        un = item.get("unknown_count") or 0
        if den < num:
            raise ValueError("numerator 不得超过 denominator")
        return float(num), float(den), float(un), None, None
    tp = float(item.get("tp") or 0)
    fn = float(item.get("fn") or 0)
    fp = float(item.get("fp") or 0)
    un = float(item.get("unknown") or 0)
    return tp, tp + fn + fp + un, un, fn, fp


def aggregate(counts, conf=0.95, side="two"):
    """按 metric_id 聚合计数并计算 Wilson 下界(方案 5.1/5.2)。

    counts: import_execution_result 的逐用例计数,或 db metrics 行
    (numerator/denominator/unknown_count)的列表(可混用)。
    返回 {metric_id: {value, numerator, denominator, unknown_count,
                      lower_bound, stat_method}};
    - numerator=tp;denominator=tp+fn+fp+unknown(保守口径,unknown 不计 TP);
    - n=0 → value=None, lower_bound=None, stat_method="n0_no_estimate",
      不能当精确率 100%(方案 5.2);
    - stat_method: wilson_two_sided / wilson_one_sided(置信度由调用方
      写入 db 的 stat_params 字段)。
    """
    if not (0 < conf < 1):
        raise ValueError("conf 必须在 (0, 1) 区间")
    if side not in ("two", "one"):
        raise ValueError("side 只允许 two/one")
    acc = {}
    for item in counts or []:
        if not isinstance(item, dict):
            raise ValueError("counts 项必须是对象")
        mid = item.get("metric_id")
        if not isinstance(mid, str) or not mid:
            raise ValueError("counts 项缺少 metric_id")
        num, den, un, fn, fp = _norm_count(item)
        a = acc.setdefault(mid, {"num": 0.0, "den": 0.0, "un": 0.0,
                                 "fn": 0.0, "fp": 0.0})
        a["num"] += num
        a["den"] += den
        a["un"] += un
        if fn is not None:
            a["fn"] += fn
        if fp is not None:
            a["fp"] += fp
    out = {}
    for mid, a in acc.items():
        if a["den"] <= 0:
            out[mid] = {
                "value": None,
                "numerator": _as_intlike(a["num"]),
                "denominator": _as_intlike(a["den"]),
                "unknown_count": _as_intlike(a["un"]),
                "lower_bound": None,
                "stat_method": "n0_no_estimate",
            }
        else:
            out[mid] = {
                "value": a["num"] / a["den"],
                "numerator": _as_intlike(a["num"]),
                "denominator": _as_intlike(a["den"]),
                "unknown_count": _as_intlike(a["un"]),
                "lower_bound": wilson_lower_bound(a["num"], a["den"],
                                                  conf=conf, side=side),
                "stat_method": "wilson_%s_sided" % side,
            }
    return out


def net_gain(baseline, candidate, spec):
    """净收益判定(方案 5.3):先过不可退化门槛,再比较主目标。

    baseline/candidate: aggregate(...) 的输出 {metric_id: {...}}。
    spec: project.json 契约;读取 metrics.primary_metric(metric_id/
    direction/threshold/comparison)、metrics.guard_metrics、
    metrics.non_inferiority_tolerance(容差,默认 0)。

    判定顺序:
    1. 任一参与判定的记录(baseline/candidate 的主指标与全部 guard)
       缺失,或其 value/lower_bound 为 None → inconclusive;
       记录携带 exec_status 且 != succeeded → ValueError(执行失败
       不得冒充无收益,方案 13.1);
    2. guard 不可退化(maximize: cand.value >= base.value - 容差;
       minimize: cand.value <= base.value + 容差);跌穿者计入
       guard_failures,主指标即使过线也只能 no_gain,不能自动采纳;
    3. 主指标按 comparison(gt/gte)对 threshold 判定(点估计,
       方案 5.2:R 是点估计,不擅改成下界);threshold 缺省时退化为
       "严格优于 baseline"。

    返回 {verdict, primary_delta, guard_failures, reasons};
    verdict ∈ beneficial / no_gain / regression / inconclusive;
    primary_delta = candidate.value - baseline.value(原始差值;
    direction=minimize 时退化判断按 base-cand 折算)。
    """
    if not isinstance(spec, dict):
        raise ValueError("spec 必须是 project 契约对象")
    m = spec.get("metrics")
    m = m if isinstance(m, dict) else {}
    pm = m.get("primary_metric")
    pm = pm if isinstance(pm, dict) else {}
    pid = pm.get("metric_id")
    if not isinstance(pid, str) or not pid:
        raise ValueError("spec.metrics.primary_metric.metric_id 缺失")
    comp = pm.get("comparison", "gte")
    if comp not in ("gt", "gte"):
        raise ValueError("comparison 只允许 gt/gte,禁止模糊口径")
    pdir = pm.get("direction", "maximize")
    if pdir not in ("maximize", "minimize"):
        raise ValueError("direction 只允许 maximize/minimize")
    tol = m.get("non_inferiority_tolerance", 0)
    if isinstance(tol, bool) or not isinstance(tol, (int, float)) or tol < 0:
        raise ValueError("non_inferiority_tolerance 必须是非负数")

    base = baseline if isinstance(baseline, dict) else {}
    cand = candidate if isinstance(candidate, dict) else {}

    def _checked(rec, label):
        if not isinstance(rec, dict):
            return None
        st = rec.get("exec_status")
        if st is not None and st != "succeeded":
            raise ValueError(
                "%s 的 exec_status=%r,执行失败的结果不得参与净收益判定"
                % (label, st))
        # 方案 5.2:轮内净收益用点估计;lower_bound 缺失不再判 inconclusive
        # (lower_bound 只在 final_gate 的 apply_lower_bound 时必需)
        if rec.get("value") is None:
            return None
        return rec

    def _inconclusive(reason):
        return {"verdict": "inconclusive", "primary_delta": None,
                "guard_failures": [], "reasons": [reason]}

    base_rec = _checked(base.get(pid), "baseline 主指标 %s" % pid)
    cand_rec = _checked(cand.get(pid), "candidate 主指标 %s" % pid)
    if base_rec is None:
        return _inconclusive(
            "baseline 主指标 %s 缺失或 value/lower_bound 为 None" % pid)
    if cand_rec is None:
        return _inconclusive(
            "candidate 主指标 %s 缺失或 value/lower_bound 为 None" % pid)

    base_val = float(base_rec["value"])
    cand_val = float(cand_rec["value"])
    raw_delta = cand_val - base_val
    eff_delta = base_val - cand_val if pdir == "minimize" else raw_delta

    reasons = []
    guard_failures = []

    threshold = pm.get("threshold")
    if threshold is None:
        passed = eff_delta > 0
        reasons.append("threshold 未配置,退化为与 baseline 比较:"
                       " 有效差值=%.4f" % eff_delta)
    else:
        threshold = float(threshold)
        passed = cand_val > threshold if comp == "gt" else cand_val >= threshold
        reasons.append("主指标 '%s' cand=%.4f %s threshold=%.4f → %s"
                       % (pid, cand_val, comp, threshold,
                          "过线" if passed else "未过线"))

    for g in m.get("guard_metrics") or []:
        if isinstance(g, dict):
            gid = g.get("metric_id")
            gdir = g.get("direction", "maximize")
            gtol = g.get("non_inferiority_tolerance", tol)
        else:
            gid, gdir, gtol = g, "maximize", tol
        if not isinstance(gid, str) or not gid:
            raise ValueError("guard_metrics 项缺少 metric_id")
        if gdir not in ("maximize", "minimize"):
            raise ValueError("guard %s direction 非法" % gid)
        if isinstance(gtol, bool) or not isinstance(gtol, (int, float)) or gtol < 0:
            raise ValueError("guard %s 容差非法" % gid)
        b_rec = _checked(base.get(gid), "baseline guard %s" % gid)
        c_rec = _checked(cand.get(gid), "candidate guard %s" % gid)
        if b_rec is None or c_rec is None:
            return _inconclusive(
                "guard '%s' 聚合缺失或 value/lower_bound 为 None" % gid)
        bv = float(b_rec["value"])
        cv = float(c_rec["value"])
        if gdir == "minimize":
            ok = cv <= bv + gtol
            desc = "cand %.4f <= base %.4f + 容差 %.4f" % (cv, bv, gtol)
        else:
            ok = cv >= bv - gtol
            desc = "cand %.4f >= base %.4f - 容差 %.4f" % (cv, bv, gtol)
        if ok:
            reasons.append("guard '%s' 未退化(%s)" % (gid, desc))
        else:
            guard_failures.append(gid)
            reasons.append("guard '%s' 跌穿不可退化门槛(%s)" % (gid, desc))

    if guard_failures:
        verdict = "regression" if eff_delta < 0 else "no_gain"
        reasons.append("guard 跌穿,主指标即使过线也不能自动采纳(方案 5.3)")
    elif passed:
        verdict = "beneficial"
        reasons.append("净收益成立: 不可退化通过且主指标过线")
    elif eff_delta < 0:
        verdict = "regression"
        reasons.append("主指标退化: 有效差值=%.4f < 0" % eff_delta)
    else:
        verdict = "no_gain"
        reasons.append("无净收益: 主指标未过线且未退化")
    return {"verdict": verdict, "primary_delta": raw_delta,
            "guard_failures": guard_failures, "reasons": reasons}
