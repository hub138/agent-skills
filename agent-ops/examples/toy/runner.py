"""候选检测器：argv [cases_ids 文件, 输出路径]；关键词表来自候选目录 KEYWORDS。"""
import json
import sys
from pathlib import Path

_, ids_path, out_path = sys.argv
kw_file = Path(sys.argv[0]).parent / "KEYWORDS" if False else None
import os
cand_dir = os.environ.get("CAND_DIR", ".")
kws = [k.strip() for k in open(os.path.join(cand_dir, "KEYWORDS"), encoding="utf-8") if k.strip()]
all_cases = {}
for line in open(os.path.join(os.path.dirname(ids_path), "cases.jsonl"), encoding="utf-8"):
    r = json.loads(line)
    all_cases[r["case_id"]] = r["input_ref"]
ids = [l.strip() for l in open(ids_path, encoding="utf-8") if l.strip()]
with open(out_path, "w", encoding="utf-8") as f:
    for cid in ids:
        text = all_cases.get(cid, "")
        f.write(json.dumps({"case_id": cid,
                            "findings": [k for k in kws if k in text]}) + "\n")
print("runner ok:", len(ids))
