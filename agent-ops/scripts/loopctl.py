#!/usr/bin/env python3
"""研究 Loop 唯一 CLI（方案 12）。所有子命令按方案阶段 A-F 组装。

运行根：RESEARCH_LOOP_HOME（默认 ~/.research_loop）。核心不认识具体领域。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from research_loop import core_types as C  # noqa: E402
from research_loop import store  # noqa: E402
from research_loop import protocol as P  # noqa: E402


def _home(args) -> str:
    return args.home


def _load_ctx(args):
    """加载课题上下文：project.json + db + engine。"""
    project = P.load_project(args.project)
    home = C.project_home(_home(args), project["identity"]["project_id"])
    db = store.open_db(str(home / "state" / "research.db"))
    from research_loop.experiment import ExperimentEngine
    engine = ExperimentEngine(db, home, project)
    return project, home, db, engine


def cmd_init(args) -> int:
    src = Path(args.project)
    project = P.load_project(str(src))
    pid = project["identity"]["project_id"]
    home = C.project_home(args.home, pid)
    # project 冻结副本与摘要（方案 9.2 protocols/<version>/）
    v = project["identity"]["objective_version"]
    d = home / "protocols" / v
    d.mkdir(parents=True, exist_ok=True)
    C.atomic_write_json(str(d / "project.json"), project)
    C.atomic_write_text(str(d / "project.sha256"), project["_digest"])
    db = store.open_db(str(home / "state" / "research.db"))
    store.append_event(db, "project.initialized", {
        "project_id": pid, "objective_version": v,
        "digest": project["_digest"], "source": str(src)})
    print(json.dumps({"ok": True, "project_id": pid, "home": str(home),
                      "digest": project["_digest"]}, ensure_ascii=False))
    return 0


def cmd_doctor(args) -> int:
    """只读体检：协议校验 + 运行目录 + （--smoke 才做受限真实请求）。"""
    report = {"checks": []}
    try:
        project = P.load_project(args.project)
        report["checks"].append({"item": "protocol", "ok": True,
                                 "digest": project["_digest"]})
    except Exception as e:
        report["checks"].append({"item": "protocol", "ok": False,
                                 "error": str(e)[:200]})
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 1
    pid = project["identity"]["project_id"]
    home = C.project_home(args.home, pid)
    report["checks"].append({"item": "home", "ok": True, "path": str(home)})
    if args.smoke:
        # 受限真实请求探活由调用方适配器实现；此处只提示，不自动花钱
        report["checks"].append({"item": "model_smoke", "ok": None,
                                 "note": "用项目适配器的 smoke 命令显式执行，成本单列"})
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


def cmd_status(args, replay_check: bool = False) -> int:
    project = P.load_project(args.project)
    home = C.project_home(args.home, project["identity"]["project_id"])
    db = store.open_db(str(home / "state" / "research.db"))
    from research_loop.experiment import fold_state
    st = fold_state(store.replay_events(db))
    out = {"project_id": project["identity"]["project_id"],
           "phase": st["phase"], "best": st["best"],
           "open_round": st["open_round"], "rounds": len(st["rounds"]),
           "freeze": st["freeze"], "final": st["final"]}
    if replay_check:
        # 重放核对：事件链与表的实验数一致性（方案 9.3，audit2 偏差 3）
        n_events = len(store.replay_events(db))
        n_exp = db.execute("SELECT COUNT(*) c FROM experiments").fetchone()["c"]
        out["replay_check"] = {"events": n_events, "experiments": n_exp,
                               "consistent": n_events >= n_exp}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cmd_record_metrics(args) -> int:
    """把一次运行的逐用例结果导入 metrics（exec_status=succeeded 才接受）。"""
    project = P.load_project(args.project)
    home = C.project_home(args.home, project["identity"]["project_id"])
    result = C.read_json(args.result)
    if result.get("exec_status") != "succeeded":
        print(json.dumps({"ok": False,
                          "reason": "exec_status=%s 不入账" %
                                    result.get("exec_status")},
                         ensure_ascii=False))
        return 1
    from research_loop.metrics import import_execution_result
    counts = import_execution_result(result, project)
    aid = args.attempt_id or result.get("attempt_id") or "manual"
    with store.tx_ctx(store.open_db(str(home / "state" / "research.db"))) as db:
        eid = args.experiment_id or "exp-" + aid
        db.execute("INSERT OR REPLACE INTO experiments(experiment_id,"
                   " created_ts, stage, objective_version, data_version,"
                   " evaluator_digest) VALUES(?,?,?,?,?,?)",
                   (eid, C.now_ts(), args.stage or "dev",
                    project["identity"]["objective_version"],
                    project["data"]["version"],
                    project["evaluator"].get("judge_version", "n/a")))
        db.execute("INSERT OR REPLACE INTO attempts(attempt_id, experiment_id,"
                   " stage, exec_status, evidence_status, trial_status,"
                   " finished_ts) VALUES(?,?,?,?,?,?,?)",
                   (aid, eid, args.stage or "dev",
                    "succeeded", "valid", "untested", C.now_ts()))
        agg = None
        from research_loop.metrics import aggregate
        agg = aggregate(counts)
        for mid, m in agg.items():
            db.execute("INSERT OR REPLACE INTO metrics(attempt_id, metric_id,"
                       " value, numerator, denominator, unknown_count,"
                       " lower_bound, stat_method) VALUES(?,?,?,?,?,?,?,?)",
                       (aid, mid, m.get("value"), m.get("numerator"),
                        m.get("denominator"), m.get("unknown_count"),
                        m.get("lower_bound"), m.get("stat_method")))
        store.append_event(db, "metrics_imported", {
            "attempt_id": aid, "experiment_id": args.experiment_id or "",
            "per_metric": {mid: [c for c in counts
                                 if c["metric_id"] == mid]
                           for mid in agg}})
    print(json.dumps({"ok": True, "attempt_id": aid,
                      "metrics": agg}, ensure_ascii=False, default=str))
    return 0


def cmd_report(args) -> int:
    project = P.load_project(args.project)
    home = C.project_home(args.home, project["identity"]["project_id"])
    from research_loop.report import render_report
    out = render_report(str(home / "state" / "research.db"), project,
                        str(home / "reports"))
    print(json.dumps({"ok": True, "files": out}, ensure_ascii=False))
    return 0




# ---------------- 阶段 C/D/E 执行子命令（方案 12） ----------------

def _mk_engine(args):
    from research_loop.experiment import ExperimentEngine
    project = P.load_project(args.project)
    home = C.project_home(_home(args), project["identity"]["project_id"])
    db = store.open_db(str(home / "state" / "research.db"))
    return project, home, db, ExperimentEngine(db, home, project)


def _metrics_arg(args, name="--metrics-file"):
    if not getattr(args, "metrics_file", None):
        raise SystemExit("需要 %s（aggregate 输出 JSON）" % name)
    return C.read_json(args.metrics_file)


def cmd_baseline(args) -> int:
    project, home, db, eng = _mk_engine(args)
    eng.record_baseline(args.run_id, _metrics_arg(args), args.candidate_id)
    store.append_event(db, "experiment.assigned", {
        "experiment_id": args.run_id, "stage": "baseline"})
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_propose(args) -> int:
    project, home, db, eng = _mk_engine(args)
    eng.start_round(args.round_id, args.candidate_id, args.mechanism,
                    idea_id=args.idea_id, direction=args.direction,
                    hypothesis=args.hypothesis)
    exp_dir = home / "experiments" / args.round_id
    C.atomic_write_json(str(exp_dir / "plan.json"), {
        "round_id": args.round_id, "candidate_id": args.candidate_id,
        "mechanism": args.mechanism, "hypothesis": args.hypothesis,
        "idea_id": args.idea_id, "direction": args.direction,
        "preregistered_ts": C.now_ts()})
    print(json.dumps({"ok": True, "plan": str(exp_dir / "plan.json")},
                     ensure_ascii=False))
    return 0


def _trial_common(args, stage: str) -> int:
    project, home, db, eng = _mk_engine(args)
    if stage == "trial":
        r = eng.record_dev(args.round_id, args.batch_id, args.run_id,
                           _metrics_arg(args, "--candidate-metrics"),
                           C.read_json(args.baseline_metrics),
                           args.candidate_id,
                           C.read_json(args.case_ids))
    else:
        r = eng.verify(args.round_id, args.batch_id, args.run_id,
                       _metrics_arg(args, "--candidate-metrics"),
                       C.read_json(args.baseline_metrics),
                       case_ids_b=C.read_json(args.case_ids))
    print(json.dumps({"ok": True, "stage": stage, "result": r},
                     ensure_ascii=False, default=str))
    return 0


def cmd_trial(args) -> int:
    return _trial_common(args, "trial")


def cmd_verify(args) -> int:
    return _trial_common(args, "verify")


def cmd_expand(args) -> int:
    project, home, db, eng = _mk_engine(args)
    r = eng.expand(args.round_id, args.run_id,
                   _metrics_arg(args, "--candidate-metrics"),
                   C.read_json(args.baseline_metrics), args.candidate_id)
    print(json.dumps({"ok": True, "result": r}, ensure_ascii=False, default=str))
    return 0


def cmd_lock_final(args) -> int:
    project, home, db, eng = _mk_engine(args)
    seal = C.read_json(args.seal) if args.seal else {"digest": "manual"}
    r = eng.lock_final(args.candidate_id, args.run_id, args.holdout_group, seal)
    print(json.dumps({"ok": True, "result": r}, ensure_ascii=False))
    return 0


def cmd_final(args) -> int:
    project, home, db, eng = _mk_engine(args)
    if args.leak_report:
        eng.check_leak(C.read_json(args.leak_report))
    else:
        eng.check_leak({"verdict": "pass",
                        "note": "调用方声明无泄漏（未提供扫描报告）"})
    r = eng.final_evaluated(args.run_id, _metrics_arg(args),
                            args.holdout_group, args.outputs_digest)
    print(json.dumps({"ok": True, "result": r}, ensure_ascii=False))
    return 0 if r["passed"] else 1


def cmd_adopt(args) -> int:
    _, _, _, eng = _mk_engine(args)
    eng.adopt(args.candidate_id)
    print(json.dumps({"ok": True, "adopted": args.candidate_id},
                     ensure_ascii=False))
    return 0


def cmd_rollback(args) -> int:
    _, _, _, eng = _mk_engine(args)
    eng.rollback(args.candidate_id, args.reason)
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_pause(args) -> int:
    _, home, db, eng = _mk_engine(args)
    store.append_event(db, "loop.paused", {"reason": args.reason,
                                           "ts": C.now_ts()})
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_resume(args) -> int:
    _, home, db, eng = _mk_engine(args)
    st = eng.state()
    rid = st["open_round"]["round_id"] if st["open_round"] else None
    print(json.dumps({"ok": True, "resumed_round": rid}, ensure_ascii=False))
    return 0


def cmd_tick(args) -> int:
    """执行推进：对账 outbox（确定性部分；判断由 AI 会话）。"""
    from research_loop.adapters import reconcile
    project, home, db, eng = _mk_engine(args)
    taskctl = str(Path(__file__).resolve().parent / "taskctl.py")
    r = reconcile(db, taskctl)
    print(json.dumps({"ok": True, "reconcile": r}, ensure_ascii=False))
    return 0


def cmd_idea(args) -> int:
    project, home, db, eng = _mk_engine(args)
    from research_loop import ideas
    if args.op == "add":
        iid = ideas.add_idea(db, args.title, args.kind, args.direction,
                             args.source, args.prerequisites,
                             args.falsify_plan)
        print(json.dumps({"ok": True, "idea_id": iid}, ensure_ascii=False))
    elif args.op == "status":
        ideas.update_idea_status(db, args.idea_id, args.status)
        print(json.dumps({"ok": True}, ensure_ascii=False))
    elif args.op == "list":
        rows = db.execute("SELECT * FROM ideas ORDER BY updated_ts DESC").fetchall()
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False, default=str))
    return 0


def cmd_explore(args) -> int:
    project, home, db, eng = _mk_engine(args)
    from research_loop import ideas
    stall = [d for d, v in eng.state()["plateau"].items()
             if sum(v.values()) >= eng.stall_limit]
    print(json.dumps({"next": ideas.next_ideas(db, limit=args.limit,
                                               stall_dirs=stall)},
                     ensure_ascii=False, default=str))
    return 0


def cmd_child(args) -> int:
    project, home, db, eng = _mk_engine(args)
    child_home = C.project_home(args.home, args.child_project_id)
    db2 = store.open_db(str(child_home / "state" / "research.db"))
    store.append_event(db, "child.spawned", {
        "child_project_id": args.child_project_id,
        "parent_experiment_id": args.parent_experiment_id,
        "ts": C.now_ts()})
    store.append_event(db2, "child.linked", {
        "parent_project_id": project["identity"]["project_id"],
        "parent_experiment_id": args.parent_experiment_id, "ts": C.now_ts()})
    print(json.dumps({"ok": True, "child_home": str(child_home)},
                     ensure_ascii=False))
    return 0


def cmd_budget(args) -> int:
    project, home, db, eng = _mk_engine(args)
    b = project.get("budget", {})
    n_exp = db.execute("SELECT COUNT(*) c FROM experiments").fetchone()["c"]
    n_att = db.execute("SELECT COUNT(*) c FROM attempts").fetchone()["c"]
    print(json.dumps({"budget": b, "used": {"experiments": n_exp,
                                            "attempts": n_att}},
                     ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="loopctl")
    ap.add_argument("--project", required=True, help="project.json 路径")
    ap.add_argument("--home", default=None, help="运行根覆盖")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    d = sub.add_parser("doctor"); d.add_argument("--smoke", action="store_true")
    sub.add_parser("status")
    sub.add_parser("status-replay")  # status + 重放核对
    s = sub.add_parser("record")
    s.add_argument("--result", required=True)
    s.add_argument("--attempt-id"); s.add_argument("--experiment-id")
    s.add_argument("--stage", default="dev")
    sub.add_parser("report")

    # 阶段 C/D/E（方案 12）
    b = sub.add_parser("baseline")
    b.add_argument("--run-id", required=True)
    b.add_argument("--metrics-file", required=True)
    b.add_argument("--candidate-id", default="baseline")
    pr = sub.add_parser("propose")
    pr.add_argument("--round-id", required=True)
    pr.add_argument("--candidate-id", required=True)
    pr.add_argument("--mechanism", required=True)
    pr.add_argument("--idea-id"); pr.add_argument("--direction")
    pr.add_argument("--hypothesis", default="")
    for name, extra in (("trial", "dev A 同批对照"), ("verify", "dev B 独立复验")):
        t = sub.add_parser(name); t.add_argument("--round-id", required=True)
        t.add_argument("--batch-id", required=True)
        t.add_argument("--run-id", required=True)
        t.add_argument("--candidate-metrics", required=True)
        t.add_argument("--baseline-metrics", required=True)
        t.add_argument("--case-ids", required=True,
                       help="批次用例 ID 的 JSON 数组文件")
    e = sub.add_parser("expand"); e.add_argument("--round-id", required=True)
    e.add_argument("--run-id", required=True)
    e.add_argument("--candidate-metrics", required=True)
    e.add_argument("--baseline-metrics", required=True)
    e.add_argument("--candidate-id", required=True)
    lf = sub.add_parser("lock-final")
    lf.add_argument("--candidate-id", required=True)
    lf.add_argument("--run-id", required=True)
    lf.add_argument("--holdout-group", required=True)
    lf.add_argument("--seal", help="封存 manifest JSON")
    fi = sub.add_parser("final")
    fi.add_argument("--run-id", required=True)
    fi.add_argument("--metrics-file", required=True)
    fi.add_argument("--holdout-group", required=True)
    fi.add_argument("--outputs-digest", required=True)
    fi.add_argument("--leak-report", help="leak.py 扫描报告 JSON")
    ad = sub.add_parser("adopt"); ad.add_argument("--candidate-id", required=True)
    rb = sub.add_parser("rollback")
    rb.add_argument("--candidate-id", required=True)
    rb.add_argument("--reason", required=True)
    pa = sub.add_parser("pause"); pa.add_argument("--reason", default="")
    sub.add_parser("resume")
    sub.add_parser("tick")
    idd = sub.add_parser("idea"); idd.add_argument("--op",
             choices=["add", "status", "list"], required=True)
    idd.add_argument("--title"); idd.add_argument("--kind")
    idd.add_argument("--direction"); idd.add_argument("--source")
    idd.add_argument("--prerequisites"); idd.add_argument("--falsify-plan")
    idd.add_argument("--idea-id"); idd.add_argument("--status")
    ex = sub.add_parser("explore"); ex.add_argument("--limit", type=int, default=3)
    ch = sub.add_parser("child")
    ch.add_argument("--child-project-id", required=True)
    ch.add_argument("--parent-experiment-id", required=True)
    sub.add_parser("budget")

    args = ap.parse_args()
    table = {"init": cmd_init, "doctor": cmd_doctor, "status": cmd_status,
             "record": cmd_record_metrics, "report": cmd_report,
             "status-replay": lambda a: cmd_status(a, replay_check=True),
             "baseline": cmd_baseline, "propose": cmd_propose,
             "trial": cmd_trial, "verify": cmd_verify, "expand": cmd_expand,
             "lock-final": cmd_lock_final, "final": cmd_final,
             "adopt": cmd_adopt, "rollback": cmd_rollback,
             "pause": cmd_pause, "resume": cmd_resume, "tick": cmd_tick,
             "idea": cmd_idea, "explore": cmd_explore, "child": cmd_child,
             "budget": cmd_budget}
    return table[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
