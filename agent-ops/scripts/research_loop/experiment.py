"""实验状态机（方案 6.2/5.3/9.1）：单机制、双批复验、换向、终测门禁。"""
from __future__ import annotations

import json

from . import store
from .core_types import (TRIAL_BENEFICIAL, TRIAL_NO_GAIN,
                         digest_obj, now_ts)


class LoopRuleError(ValueError):
    """违反实验纪律，机器门禁拒绝。"""


def _dev_gate_pass(metrics: dict, spec: dict) -> bool:
    gate = spec.get("explore", {}).get("dev_recall_min")
    if gate is None:
        return True
    m = metrics.get(spec["metrics"]["primary_metric"]["metric_id"])
    if not m or m.get("value") is None:
        return False
    cmp = spec["metrics"]["primary_metric"].get("comparison", "gt")
    return m["value"] > gate if cmp == "gt" else m["value"] >= gate


def fold_state(events: list) -> dict:
    st = {"phase": "initialized", "best": None, "open_round": None,
          "plateau": {}, "freeze": None, "leak": None, "final": None,
          "rounds": []}
    for ev in events:
        k, d = ev["kind"], ev.get("data", {})
        if k == "round.started":
            st["open_round"] = dict(d, stage="propose")
            st["rounds"].append(dict(d, stage="propose"))
        elif k == "round.stage":
            if st["open_round"] and st["open_round"]["round_id"] == d.get("round_id"):
                st["open_round"]["stage"] = d.get("stage")
        elif k == "round.aborted":
            rid = d.get("round_id")
            if st["open_round"] and st["open_round"]["round_id"] == rid:
                st["open_round"] = None
            st["phase"] = "round_aborted"
        elif k == "round.closed":
            rid = d.get("round_id")
            if st["open_round"] and st["open_round"]["round_id"] == rid:
                st["open_round"] = None
            st["phase"] = "round_closed"
            direction = d.get("direction")
            if direction:
                pl = st["plateau"].setdefault(direction, {"no_gain": 0})
                if d.get("verdict") == TRIAL_NO_GAIN:
                    pl["no_gain"] = pl.get("no_gain", 0) + 1
                elif d.get("verdict") == TRIAL_BENEFICIAL:
                    pl["no_gain"] = 0
            if d.get("verdict") == TRIAL_BENEFICIAL and d.get("adopted"):
                st["best"] = {"candidate": d.get("candidate_id"),
                              "run_id": d.get("expand_run_id") or d.get("run_id"),
                              "metrics": d.get("metrics")}
        elif k == "baseline.recorded":
            if st["best"] is None:
                st["best"] = {"candidate": d.get("candidate_id") or "baseline",
                              "run_id": d.get("run_id"),
                              "metrics": d.get("metrics")}
            st["phase"] = "baseline"
        elif k == "freeze.locked":
            st["freeze"] = d
            st["phase"] = "final_locked"
        elif k == "leak.checked":
            st["leak"] = d
        elif k == "final.evaluated":
            st["final"] = d
            st["phase"] = "final_evaluated"
    return st


class ExperimentEngine:
    """实验编排：晋级走机器门禁（方案 9.1，模型不能直接写 accepted）。"""

    def __init__(self, db, home, project):
        self.db = db
        self.home = str(home)
        self.project = project
        self.pm = project["metrics"]["primary_metric"]
        self.explore = project.get("explore", {})
        self.stall_limit = int(self.explore.get("stall_limit", 2))
        self.batch_size = int(self.explore.get("dev_batch_size", 10))

    def _event(self, kind, data):
        with store.tx_ctx(self.db):
            store.append_event(self.db, kind, data)

    def state(self) -> dict:
        return fold_state(store.replay_events(self.db))

    def record_baseline(self, run_id: str, metrics: dict,
                        candidate_id: str = "baseline"):
        st = self.state()
        if st["open_round"]:
            raise LoopRuleError("存在未闭合轮次，先 close_round")
        with store.tx_ctx(self.db):
            conn = self.db
            conn.execute("INSERT OR REPLACE INTO experiments(experiment_id,"
                         " created_ts, stage, objective_version, data_version,"
                         " evaluator_digest) VALUES(?,?,?,?,?,?)",
                         ("baseline", now_ts(), "baseline",
                          self.project["identity"]["objective_version"],
                          self.project["data"]["version"],
                          self.project["evaluator"].get("judge_version", "n/a")))
            conn.execute("INSERT OR REPLACE INTO attempts(attempt_id,"
                         " experiment_id, stage, exec_status,"
                         " evidence_status, trial_status, finished_ts)"
                         " VALUES(?,?,?,?,?,?,?)",
                         (run_id, "baseline", "baseline",
                          "succeeded", "valid", "untested", now_ts()))
            for mid, m in (metrics or {}).items():
                conn.execute("INSERT OR REPLACE INTO metrics(attempt_id,"
                             " metric_id, value, numerator, denominator,"
                             " lower_bound, stat_method)"
                             " VALUES(?,?,?,?,?,?,?)",
                             (run_id, mid, m.get("value"),
                              m.get("numerator"), m.get("denominator"),
                              m.get("lower_bound"), "imported"))
            store.append_event(conn, "baseline.recorded", {
                "run_id": run_id, "candidate_id": candidate_id,
                "metrics": metrics})

    def best_metrics(self) -> dict:
        return (self.state()["best"] or {}).get("metrics") or {}

    def start_round(self, round_id: str, candidate_id: str, mechanism: str,
                    idea_id=None, direction=None, hypothesis: str = "",
                    parent_candidate: str = ""):
        st = self.state()
        if st["open_round"]:
            raise LoopRuleError("存在未闭合轮次: %s" % st["open_round"]["round_id"])
        if not st["best"]:
            raise LoopRuleError("尚未记录 baseline")
        if st["freeze"]:
            raise LoopRuleError("候选已冻结进入终测，开新轮需先 adopt/rollback")
        if len(mechanism.splitlines()) > 1 or len(mechanism) > 200:
            raise LoopRuleError("机制描述必须单行且 ≤200 字（单机制纪律）")
        plateau = st["plateau"]
        if direction and sum(plateau.get(direction, {}).values()) >= self.stall_limit:
            raise LoopRuleError("方向 %s 连续 %d 轮无净收益，必须换向（方案 6.2 条 4）"
                                % (direction, self.stall_limit))
        self._event("round.started", {"round_id": round_id,
                                      "candidate_id": candidate_id,
                                      "mechanism": mechanism,
                                      "hypothesis": hypothesis or "",
                                      "parent_candidate": (st["best"] or {}).get("candidate", ""),
                                      "idea_id": idea_id,
                                      "direction": direction or (idea_id or "unspecified"),
                                      "baseline_best": st["best"], "ts": now_ts()})
        return {"round_id": round_id, "candidate_id": candidate_id}

    def record_dev(self, round_id: str, batch_id: str, run_id: str,
                   candidate_metrics: dict, baseline_metrics: dict,
                   candidate_id: str, case_ids: list):
        """同批对照（batch_id 必须记录；跨批比较禁止）。"""
        events = store.replay_events(self.db)
        open_r = next((e["data"] for e in events if e["kind"] == "round.started"
                       and e["data"]["round_id"] == round_id), None)
        if not open_r:
            raise LoopRuleError("轮次不存在: %s" % round_id)
        net = self._net_gain(baseline_metrics, candidate_metrics)
        gate_ok = _dev_gate_pass(candidate_metrics, self.project)
        with store.tx_ctx(self.db):
            self.db.execute("INSERT OR REPLACE INTO attempts(attempt_id,"
                            " experiment_id, stage, exec_status,"
                            " evidence_status, trial_status, finished_ts)"
                            " VALUES(?,?,?,?,?,?,?)",
                            (run_id, round_id, "dev", "succeeded",
                             "valid", net["verdict"], now_ts()))
            for mid, m in (candidate_metrics or {}).items():
                self.db.execute("INSERT OR REPLACE INTO metrics(attempt_id,"
                                " metric_id, value, numerator, denominator,"
                                " lower_bound, stat_method) VALUES(?,?,?,?,?,?,?)",
                                (run_id, mid, m.get("value"),
                                 m.get("numerator"), m.get("denominator"),
                                 m.get("lower_bound"), "imported"))
            store.append_event(self.db, "dev.recorded", {
                "round_id": round_id, "batch_id": batch_id, "run_id": run_id,
                "candidate_id": candidate_id,
                                     "case_ids": list(case_ids),
                "case_ids_digest": digest_obj(sorted(case_ids)),
                "candidate_metrics": candidate_metrics,
                "baseline_metrics": baseline_metrics,
                "net": net, "dev_gate_pass": gate_ok})
        return net

    def verify(self, round_id: str, batch_id_b: str, run_id_b: str,
               candidate_metrics_b: dict, baseline_metrics_b: dict,
               case_ids_b: list | None = None):
        """dev B 独立复验：与 A 批不重叠（方案 6.2 条 5）。"""
        events = store.replay_events(self.db)
        dev_a = [e["data"] for e in events if e["kind"] == "dev.recorded"
                 and e["data"]["round_id"] == round_id]
        if not dev_a:
            raise LoopRuleError("dev A 未记录，不能复验")
        a = dev_a[-1]
        if not case_ids_b:
            raise LoopRuleError(
                "复验必须显式传入批次用例清单 case_ids_b（防分母泄漏）")
        bset = set(case_ids_b)
        for drec in dev_a:  # 全部历史发现批都要不重叠（审计问题 11）
            if drec.get("batch_id") == batch_id_b:
                raise LoopRuleError("复验批必须与发现批不重叠")
            ov = set(drec.get("case_ids") or []) & bset
            if ov:
                raise LoopRuleError("复验批与发现批 %s 重叠 %d 条: %s" % (
                    drec.get("batch_id"), len(ov), sorted(ov)[:3]))
        vb_net = self._net_gain(baseline_metrics_b, candidate_metrics_b)
        with store.tx_ctx(self.db):
            self.db.execute("INSERT OR REPLACE INTO attempts(attempt_id,"
                            " experiment_id, stage, exec_status,"
                            " evidence_status, trial_status, finished_ts)"
                            " VALUES(?,?,?,?,?,?,?)",
                            (run_id_b, round_id, "verify", "succeeded",
                             "valid", vb_net["verdict"], now_ts()))
            store.append_event(self.db, "verify.recorded", {
                "round_id": round_id, "batch_id": batch_id_b,
                "run_id": run_id_b, "candidate_metrics": candidate_metrics_b,
                "baseline_metrics": baseline_metrics_b, "net": vb_net})
        both = (a["net"]["verdict"] == TRIAL_BENEFICIAL
                and self._net_gain(baseline_metrics_b,
                                   candidate_metrics_b)["verdict"] == TRIAL_BENEFICIAL)
        self._event("verify.concluded", {"round_id": round_id, "both_pass": both,
                                         "gate_ok_a": a.get("dev_gate_pass"),
                                         "gate_ok_b": _dev_gate_pass(candidate_metrics_b,
                                                                     self.project)})
        return {"both_pass": both}

    def expand(self, round_id: str, run_id: str, candidate_metrics: dict,
               baseline_metrics: dict, candidate_id: str):
        """扩展批：双批复验通过是前置（方案 6.2 条 5/12 阶段 D）。"""
        events = store.replay_events(self.db)
        concl = [e["data"] for e in events
                 if e["kind"] == "verify.concluded"
                 and e["data"]["round_id"] == round_id]
        if not concl or not concl[-1].get("both_pass"):
            raise LoopRuleError(
                "双批复验未通过或未执行（both_pass），不能扩展")
        net = self._net_gain(baseline_metrics, candidate_metrics)
        adopted = net["verdict"] == TRIAL_BENEFICIAL
        self._event("expand.recorded", {"round_id": round_id, "run_id": run_id,
                                        "candidate_id": candidate_id,
                                        "metrics": candidate_metrics,
                                        "net": net, "adopted": adopted})
        self.close_round(round_id, verdict=net["verdict"], adopted=adopted,
                         candidate_id=candidate_id, run_id=run_id,
                         metrics=candidate_metrics)
        return {"adopted": adopted, "net": net}

    def close_round(self, round_id: str, verdict: str, adopted: bool,
                    candidate_id: str, run_id: str, metrics: dict):
        st = self.state()
        open_r = st["open_round"]
        if not open_r or open_r["round_id"] != round_id:
            raise LoopRuleError("轮次不存在或已闭合: %s" % round_id)
        with store.tx_ctx(self.db):
            conn = self.db
            if adopted:
                conn.execute("INSERT OR REPLACE INTO experiments(experiment_id,"
                             " created_ts, stage, objective_version,"
                             " data_version, evaluator_digest)"
                             " VALUES(?,?,?,?,?,?)",
                             (round_id, now_ts(), "expand",
                              self.project["identity"]["objective_version"],
                              self.project["data"]["version"],
                              self.project["evaluator"].get("judge_version", "n/a")))
                conn.execute("INSERT OR REPLACE INTO attempts(attempt_id,"
                             " experiment_id, stage, exec_status,"
                             " evidence_status, trial_status, finished_ts)"
                             " VALUES(?,?,?,?,?,?,?)",
                             (run_id, round_id, "expand", "succeeded",
                              "valid", "beneficial", now_ts()))
                for mid, m in (metrics or {}).items():
                    conn.execute("INSERT OR REPLACE INTO metrics(attempt_id,"
                                 " metric_id, value, numerator, denominator,"
                                 " lower_bound, stat_method)"
                                 " VALUES(?,?,?,?,?,?,?)",
                                 (run_id, mid, m.get("value"),
                                  m.get("numerator"), m.get("denominator"),
                                  m.get("lower_bound"), "imported"))
            store.append_event(conn, "round.closed", {
                "round_id": round_id, "verdict": verdict, "adopted": adopted,
                "candidate_id": candidate_id, "run_id": run_id,
                "metrics": metrics, "direction": open_r.get("direction"),
                "ts": now_ts()})

    def abort_round(self, round_id: str, reason: str):
        """执行失败/证据无效：登记 abort，不算 no_gain（方案 9.1）。"""
        st = self.state()
        if not st["open_round"] or st["open_round"]["round_id"] != round_id:
            raise LoopRuleError("轮次不存在: %s" % round_id)
        self._event("round.aborted", {"round_id": round_id, "reason": reason,
                                      "ts": now_ts()})
        self.db.execute("UPDATE attempts SET exec_status='canceled' "
                        "WHERE experiment_id=? AND exec_status IN "
                        "('queued','running','retry_wait')", (round_id,))

    def _net_gain(self, baseline: dict, candidate: dict) -> dict:
        """委托 metrics.net_gain（唯一判定口径；minimize/gt/gte 均支持）。"""
        from . import metrics as M
        exec_ok = all(
            (m or {}).get("exec_status", "succeeded") == "succeeded"
            for m in (baseline, candidate) if isinstance(m, dict))
        if not exec_ok and any(isinstance(m, dict) and "exec_status" in m
                               for m in (baseline, candidate)):
            raise LoopRuleError("执行失败的尝试不得冒充无收益（方案 13.1）")
        # 轮内对照=相对 baseline 的净收益；threshold 是终验门槛（方案 6.2 vs 5.2）
        round_spec = json.loads(json.dumps(self.project, ensure_ascii=False))
        round_spec["metrics"]["primary_metric"].pop("threshold", None)
        return M.net_gain(baseline, candidate, round_spec)


    def lock_final(self, candidate_id: str, run_id: str, holdout_group: str,
                   seal_manifest: dict):
        st = self.state()
        best = st["best"]
        if not best or best.get("candidate") != candidate_id:
            raise LoopRuleError("只有当前最佳候选可冻结")
        if not self._candidate_freezable(candidate_id):
            raise LoopRuleError("候选未在两批不重叠开发用例+扩展批确认，不能冻结")
        self._event("freeze.locked", {"candidate_id": candidate_id,
                                      "run_id": run_id,
                                      "holdout_group": holdout_group,
                                      "seal_manifest_digest": digest_obj(seal_manifest),
                                      "metrics_digest": digest_obj(best.get("metrics") or {}),
                                      "ts": now_ts()})
        return {"locked": True}

    def _candidate_freezable(self, candidate_id: str) -> bool:
        events = store.replay_events(self.db)
        return any(e["kind"] == "expand.recorded"
                   and e["data"].get("candidate_id") == candidate_id
                   and e["data"].get("adopted") for e in events)

    def check_leak(self, leak_report: dict):
        if leak_report.get("verdict") != "pass":
            raise LoopRuleError("隔离检查未通过（%s），不能终测" % leak_report.get("verdict"))
        st = self.state()
        if not st["freeze"]:
            raise LoopRuleError("未冻结候选，不能终测")
        self._event("leak.checked", dict(leak_report, ts=now_ts()))

    def final_evaluated(self, run_id: str, metrics: dict, holdout_group: str,
                        outputs_digest: str):
        """终测：R 点估计与 P 下界分别对阈值（方案 5.2）；开封只追加。"""
        st = self.state()
        if not st["freeze"]:
            raise LoopRuleError("未冻结")
        if not st.get("leak") or st["leak"].get("verdict") != "pass":
            raise LoopRuleError("隔离检查未通过，不能终测")
        if st["final"]:
            raise LoopRuleError("该留出集已开封（方案 8.1：终测失败不得原地重测同留出集）")
        results = {}
        for g in self.project["completion"]["final_gate"]:
            m = metrics.get(g["metric_id"])
            if not m or m.get("value") is None:
                results[g["metric_id"]] = False
                continue
            th = float(g["threshold"])
            if g.get("apply_lower_bound") and m.get("lower_bound") is None:
                results[g["metric_id"]] = False
                continue
            v = m.get("lower_bound") if g.get("apply_lower_bound") else m["value"]
            results[g["metric_id"]] = (v > th if g.get("comparison", "gt") == "gt"
                                       else v >= th)
        passed = all(results.values())
        self._event("final.evaluated", {"run_id": run_id,
                                        "holdout_group": holdout_group,
                                        "metrics": metrics, "gates": results,
                                        "passed": passed,
                                        "outputs_digest": outputs_digest,
                                        "ts": now_ts()})
        return {"passed": passed, "gates": results}

    def adopt(self, candidate_id: str):
        st = self.state()
        fin = st["final"]
        if not fin or not fin.get("passed"):
            raise LoopRuleError("终测未通过，不能采纳")
        if st["freeze"] and st["freeze"].get("candidate_id") != candidate_id:
            raise LoopRuleError("终测的候选是 %s，不能采纳 %s" % (
                st["freeze"].get("candidate_id"), candidate_id))
        self._event("candidate.adopted", {"candidate_id": candidate_id,
                                          "ts": now_ts()})

    def rollback(self, candidate_id: str, reason: str):
        self._event("candidate.rolled_back", {"candidate_id": candidate_id,
                                              "reason": reason, "ts": now_ts()})
