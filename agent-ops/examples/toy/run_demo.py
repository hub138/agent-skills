"""迷你课题端到端：baseline → 轮次（cand-v2 提升）→ 复验 → 冻结 → leak → 终测 → 采纳。"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
from research_loop import core_types as C  # noqa: E402
from research_loop import store  # noqa: E402
from research_loop.experiment import ExperimentEngine  # noqa: E402

project = C.read_json(HERE / "project.json")
home = C.project_home(None, "toy-demo")
db = store.open_db(str(home / "state" / "research.db"))
eng = ExperimentEngine(db, home, project)



def metrics_from_result(res: dict) -> dict:
    """从评测 result 计算指标（含分子分母，可复算）。"""
    tp = sum(c.get("risk_points", {}).get("hit", 0) for c in res["cases"])
    total = sum(c.get("risk_points", {}).get("total", 0) for c in res["cases"])
    t = sum(c.get("alerts", {}).get("true", 0) for c in res["cases"])
    f = sum(c.get("alerts", {}).get("false", 0) for c in res["cases"])
    u = sum(c.get("alerts", {}).get("unknown", 0) for c in res["cases"])
    p_den = t + f
    return {"recall": {"value": (tp / total) if total else None,
                       "numerator": tp, "denominator": total},
            "precision": {"value": (t / p_den) if p_den else None,
                          "numerator": t, "denominator": p_den,
                          "unknown_count": u}}


def run_eval(candidate_dir: str, ids: list, tag: str) -> dict:
    """ids 同时作为评测分母（eval_cmd 只统计传入用例，防分母泄漏）。"""
    preds = HERE / f"preds-{tag}.jsonl"
    ids_file = HERE / f"ids-{tag}.txt"
    ids_file.write_text("\n".join(ids) + "\n", encoding="utf-8")
    all_cases = {}
    for line in open(HERE / "cases.jsonl", encoding="utf-8"):
        r = json.loads(line)
        all_cases[r["case_id"]] = r["input_ref"]
    kws = [k.strip() for k in open(Path(candidate_dir) / "KEYWORDS",
                                   encoding="utf-8") if k.strip()]
    with open(preds, "w", encoding="utf-8") as f:
        for cid in ids:
            text = all_cases.get(cid, "")
            f.write(json.dumps({"case_id": cid,
                                "findings": [k for k in kws if k in text]}) + "\n")
    r = subprocess.run([sys.executable, str(HERE / "eval_cmd.py"),
                        str(HERE / "cases.jsonl"), str(ids_file), str(preds),
                        str(HERE / f"result-{tag}.json")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.load(open(HERE / f"result-{tag}.json", encoding="utf-8"))


def ids_by(cases, split, label=None):
    return [c["case_id"] for c in cases
            if c.get("split") == split and (label is None or c["label"] == label)]


# 1) 简单切分：dev-discovery 16 条 + dev-verification 12 条（demo 直切，正式用 evalset.py）
cases = [json.loads(l) for l in open(HERE / "cases.jsonl", encoding="utf-8")]
pos = [c for c in cases if c["label"] == "pos"]
neg = [c for c in cases if c["label"] == "neg"]
for i, c in enumerate(pos):
    c["split"] = "dev-discovery" if i < 16 else ("holdout" if i < 80 else "train")
for i, c in enumerate(neg):
    c["split"] = "dev-discovery" if i < 4 else "holdout"
dev_ids = [c["case_id"] for c in cases if c["split"] == "dev-discovery"]

# 2) 基线（cand-v1）
res_base = run_eval(str(HERE / "candidates" / "cand-v1"), dev_ids, "base")
eng.record_baseline("run-base", metrics_from_result(res_base))
print("基线记录 ✓")

# 3) 轮次：cand-v2（单机制：扩充关键词表）
eng.start_round("r1", "cand-v2", "扩充 KEYWORDS 增加 bug-b/bug-c 识别",
                idea_id=None, direction="keyword-expansion")
dev_a = dev_ids[:8]
dev_b = dev_ids[8:16]
ra = run_eval(str(HERE / "candidates" / "cand-v2"), dev_a, "r1a")
ma = metrics_from_result(ra)
eng.record_dev("r1", "bA", "run-r1a", ma,
                       metrics_from_result(run_eval(str(HERE / "candidates" / "cand-v1"), dev_a, "r1a-base")), "cand-v2", dev_a)
rb = run_eval(str(HERE / "candidates" / "cand-v2"), dev_b, "r1b")
eng.verify("r1", "bB", "run-r1b", metrics_from_result(rb),
           metrics_from_result(run_eval(str(HERE / "candidates" / "cand-v1"), dev_b, "r1b-base")),
           case_ids_b=dev_b)
# 4) 扩展（整个 dev 池）
rx = run_eval(str(HERE / "candidates" / "cand-v2"), dev_ids, "r1x")
tp = sum(c["risk_points"]["hit"] for c in rx["cases"] if "risk_points" in c)
total = sum(c["risk_points"]["total"] for c in rx["cases"] if "risk_points" in c)
r = eng.expand("r1", "run-r1x", metrics_from_result(rx),
               metrics_from_result(run_eval(str(HERE / "candidates" / "cand-v1"), dev_ids, "r1x-base")), "cand-v2")
print("expand adopted:", r["adopted"], "| dev 命中 %d/%d" % (tp, total))
# 5) 冻结 → leak → 终测（holdout）
eng.lock_final("cand-v2", "run-r1x", "toy-holdout", {"digest": "demo-seal"})
eng.check_leak({"verdict": "pass", "violations": []})
hold_ids = [c["case_id"] for c in cases if c["split"] == "holdout"]
rh = run_eval(str(HERE / "candidates" / "cand-v2"), hold_ids, "final")
hits = sum(c["risk_points"]["hit"] for c in rh["cases"] if "risk_points" in c)
tot = sum(c["risk_points"]["total"] for c in rh["cases"] if "risk_points" in c)
alerts_t = sum(c["alerts"]["true"] for c in rh["cases"] if "alerts" in c)
alerts_f = sum(c["alerts"]["false"] for c in rh["cases"] if "alerts" in c)
print("终测 holdout: 召回 %d/%d=%.3f | 精确告警 %d/%d" % (hits, tot, hits / tot, alerts_t, alerts_t + alerts_f))
out = eng.final_evaluated("run-final", metrics_from_result(rh), "toy-holdout", "od-demo")
print("终测门禁:", out)
eng.adopt("cand-v2")
print("已采纳 cand-v2 ✓")
st = eng.state()
print("最终 phase:", st["phase"], "| best:", st["best"]["candidate"])
