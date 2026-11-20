"""评测：读 predictions.jsonl（case_id/findings）+ cases.jsonl 标签 → result.json。

独立身份（只读标签与预测），不做语义裁决——关键词精确匹配。
"""
import json
import sys
from pathlib import Path

_, cases_path, ids_path, preds_path, out_path = sys.argv
cases = {}
ids = set()
for line in open(ids_path, encoding="utf-8"):
    ids.add(line.strip())
for line in open(cases_path, encoding="utf-8"):
    r = json.loads(line)
    if r["case_id"] in ids:
        cases[r["case_id"]] = r["bucket"] if r["label"] == "pos" else None
assert len(cases) == len(ids), "分母必须等于传入用例数: %d vs %d" % (
    len(cases), len(ids))
preds = {}
for line in open(preds_path, encoding="utf-8"):
    r = json.loads(line)
    preds.setdefault(r["case_id"], set()).update(r["findings"])
cases_out = []
for cid, bucket in cases.items():
    if bucket is None:
        fp = sorted(preds.get(cid, set()))
        cases_out.append({"case_id": cid,
                          "alerts": {"true": 0, "false": len(fp),
                                     "unknown": 0}})
    else:
        f = preds.get(cid, set())
        hit = 1 if bucket in f else 0
        extra_alerts = len(f - {bucket})
        cases_out.append({"case_id": cid,
                          "risk_points": {"total": 1, "hit": hit,
                                          "missed": 1 - hit},
                          "alerts": {"true": hit if extra_alerts == 0 else min(1, hit),
                                     "false": max(0, extra_alerts - (0 if hit else 0)) + (0 if hit else 0),
                                     "unknown": 0}})
Path(out_path).write_text(json.dumps(
    {"exec_status": "succeeded", "cases": cases_out}, ensure_ascii=False), encoding="utf-8")
print("eval ok:", len(cases_out), "cases")
