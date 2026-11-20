"""生成迷你课题：100 条（80 pos + 20 neg），文本含 bug 关键词。"""
import json
import random
from pathlib import Path

out = Path(__file__).parent / "cases.jsonl"
random.seed(7)
rows = []
for i in range(80):
    bug = "bug-a" if i % 3 == 0 else ("bug-b" if i % 3 == 1 else "bug-c")
    rows.append({"case_id": "p%03d" % i, "label": "pos", "group_id": "g%d" % (i // 4),
                 "input_ref": "text with %s issue" % bug, "bucket": bug})
for i in range(20):
    rows.append({"case_id": "n%03d" % i, "label": "neg", "group_id": "gn%d" % (i // 2),
                 "input_ref": "clean text no issue", "bucket": "clean"})
with open(out, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("cases:", len(rows))
