"""评测集导入、split 划分、holdout 封存/开封、dev 批抽样与坏例裁决(方案 4/4.2/4.3)。

契约(方案 4.1/4.2):
- 去重按关联组而非随机行:同 group_id 的用例整组进同一 split,不跨 split;
- holdout 组在最终候选冻结前不得开封;封存冻结文件内容摘要,不只冻结数量;
- dev-discovery 批按 dev 池自然比例抽样,可对漏报过采样(miss_bias),
  过采样批次不得包装成自然分布总体效果(方案 4.2);
- 坏例裁决可追溯:记录 reason/adjudicator/时间;holdout 组冻结,组内不改数据。
"""
from __future__ import annotations

import hashlib
import json
import os
import warnings

from .core_types import atomic_write_json, digest_obj, now_ts, read_json, sha256_file

LABEL_POS = "pos"
LABEL_NEG = "neg"
LABELS = (LABEL_POS, LABEL_NEG)
GRADES = ("precise", "coarse", "disputed", "unknown")
SPLIT_TRAIN = "train"
SPLIT_DEV = "dev"
SPLIT_HOLDOUT = "holdout"
STATUS_ACTIVE = "active"
STATUS_INVALID = "invalid"


def import_cases(path: str) -> list:
    """导入 JSONL 用例清单。缺 case_id/label 或字段非法报 ValueError。"""
    cases = []
    seen = set()
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError("第 %d 行不是合法 JSON: %s" % (lineno, e))
            if not isinstance(rec, dict):
                raise ValueError("第 %d 行必须是对象" % lineno)
            for key in ("case_id", "label"):
                if not rec.get(key):
                    raise ValueError("第 %d 行缺少 %s" % (lineno, key))
            if rec["label"] not in LABELS:
                raise ValueError("第 %d 行 label 非法: %r(只允许 %s)"
                                 % (lineno, rec["label"], list(LABELS)))
            if rec["case_id"] in seen:
                raise ValueError("case_id 重复: %s" % rec["case_id"])
            seen.add(rec["case_id"])
            rec = dict(rec)
            rec.setdefault("group_id", rec["case_id"])
            grade = rec.setdefault("label_grade", "unknown")
            if grade not in GRADES:
                raise ValueError("case %s label_grade 非法: %r"
                                 % (rec["case_id"], grade))
            rec.setdefault("bucket", "")
            rec.setdefault("input_ref", "")
            rec.setdefault("label_ref", "")
            rec.setdefault("label_status", STATUS_ACTIVE)
            cases.append(rec)
    return cases


def _hash01(seed, text) -> float:
    """确定性 uniform 值(0,1),同 seed+text 恒定。"""
    h = hashlib.sha256(("%s|%s" % (seed, text)).encode("utf-8")).hexdigest()
    return (int(h[:16], 16) + 0.5) / float(1 << 64)


def assign_splits(cases, seed, holdout_groups, dev_ratio=0.4):
    """关联组整组切分（方案 4.2）。组为原子；holdout 整组进 holdout；
    其余组按 sha256(seed|group) 确定性排序，跨签名统一最大余数法分配
    train/dev（组为原子），分配后校验正负占比偏差（>5pp 告警）。"""
    import warnings as _w
    holdout_set = set(holdout_groups or [])
    unknown_holdout = holdout_set - {c.get("group_id") for c in cases}
    if unknown_holdout:
        _w.warn("holdout_groups 含不存在的组: %s" % sorted(unknown_holdout))
    groups = {}
    for c in cases:
        gid = str(c.get("group_id") or c.get("case_id"))
        groups.setdefault(gid, []).append(c)
    hkey = lambda g: int.from_bytes(
        __import__("hashlib").sha256(("%s|%s" % (seed, g)).encode()).digest()[:8],
        "big")
    gids = sorted(groups, key=lambda g: (hkey(g), g))
    total = len(cases)
    target_dev = round(total * dev_ratio)
    assigned = {}
    # 跨签名统一：按排序逐组贪心，但记录每层剩余目标，超出部分强制 train 补偿
    target_dev = round(total * dev_ratio)
    pos_total = sum(1 for c in cases if c.get("label") == "pos")
    target_pos = round(target_dev * pos_total / total) if total else 0
    dev_gids, dev_size, dev_pos = [], 0, 0
    remaining = [g for g in gids if g not in holdout_set]
    # 迭代选组进 dev：每步选使 (|dev_size-target| + |dev_pos-target_pos|) 最小的
    # 可行组（容量不超 target_dev）；等价于组粒度的比例平衡最优（方案 4.2）。
    assigned = {}
    while True:
        cand = [g for g in remaining
                if dev_size + len(groups[g]) <= target_dev]
        if not cand:
            break
        best_g, best_score = None, None
        for g in cand:
            size = len(groups[g])
            gpos = sum(1 for c in groups[g] if c.get("label") == "pos")
            score = (abs(dev_size + size - target_dev)
                     + abs(dev_pos + gpos - target_pos), g)
            if best_score is None or score < best_score:
                best_g, best_score = g, score
        if best_g is None:
            break
        size = len(groups[best_g])
        dev_size += size
        dev_pos += sum(1 for c in groups[best_g]
                       if c.get("label") == "pos")
        dev_gids.append(best_g)
        remaining.remove(best_g)
    for g in gids:
        split = "holdout" if g in holdout_set else (
            "dev" if g in dev_gids else "train")
        for c in groups[g]:
            assigned[c["case_id"]] = split
    out = []
    for c in cases:
        d = dict(c)
        d["split"] = assigned[c["case_id"]]
        out.append(d)
    # 分配后比例校验：train/dev 正例占比差 >5pp 告警
    def _pos_ratio(split):
        xs = [c for c in out if c["split"] == split]
        pos = sum(1 for c in xs if c.get("label") == "pos")
        return pos / len(xs) if xs else None
    r_dev, r_train = _pos_ratio("dev"), _pos_ratio("train")
    if r_dev is not None and r_train is not None and             abs(r_dev - r_train) > 0.05:
        _w.warn("dev/train 正例占比偏差 >5pp: dev=%.2f train=%.2f" %
                (r_dev, r_train))
    return out


def _check_group_id(group_id) -> str:
    """group_id 白名单：防路径穿越（审计问题 5）。"""
    import re as _re
    g = str(group_id)
    if not _re.fullmatch(r"[\w.-]+", g) or ".." in g:
        raise ValueError("非法 group_id: %r" % group_id)
    return g


def seal_holdout(cases: list, group_id: str, home) -> dict:
    """封存 holdout 组:冻结组内每个 case 的 input/label 文件 sha256。

    manifest 写 <home>/<group_id>/seal.json,含 group digest(方案 4.1:
    冻结身份与文件内容,不只冻结数量)。返回 manifest。
    """
    group_id = _check_group_id(group_id)
    members = [c for c in cases
               if (c.get("group_id") or c["case_id"]) == group_id]
    if not members:
        raise ValueError("holdout 组不存在或无用例: %s" % group_id)
    files = {}
    for c in members:
        entry = {}
        for role in ("input", "label"):
            ref = c.get(role + "_ref")
            if not ref or not os.path.exists(ref):
                raise ValueError("用例 %s 的 %s 文件缺失: %r"
                                 % (c["case_id"], role, ref))
            entry[role + "_ref"] = ref
            entry[role + "_sha256"] = sha256_file(ref)
        files[c["case_id"]] = entry
    manifest = {
        "group_id": group_id,
        "sealed_ts": now_ts(),
        "case_count": len(files),
        "cases": files,
        "group_digest": digest_obj({"group_id": group_id, "cases": files}),
    }
    atomic_write_json(os.path.join(str(home), group_id, "seal.json"), manifest)
    return manifest


def _append_open_event(home, group_id: str, manifest: dict) -> None:
    """开封事件只追加(方案 8.1:开封事件 append-only)。"""
    group_id = _check_group_id(group_id)
    d = os.path.join(str(home), group_id)
    os.makedirs(d, exist_ok=True)
    event = {"ts": now_ts(), "group_id": group_id,
             "group_digest": manifest.get("group_digest")}
    with open(os.path.join(d, "open_events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def open_holdout(home, group_id: str) -> dict:
    """开封 holdout 组:核对每个文件 sha256 与封存清单一致,否则 ValueError。

    通过后追加开封事件并返回 manifest。
    """
    group_id = _check_group_id(group_id)
    path = os.path.join(str(home), group_id, "seal.json")
    if not os.path.exists(path):
        raise ValueError("封存清单不存在,组未封存: %s" % path)
    manifest = read_json(path)
    if manifest.get("group_id") != group_id:
        raise ValueError("封存清单 group_id 不符: %r != %r"
                         % (manifest.get("group_id"), group_id))
    if not manifest.get("cases"):
        raise ValueError("封存清单为空(空 manifest 不允许开封)")
    recalc = digest_obj({"group_id": manifest["group_id"],
                         "cases": manifest["cases"]})
    if recalc != manifest.get("group_digest"):
        raise ValueError("封存清单自身被篡改(group_digest 不符)")
    problems = []
    for case_id, entry in (manifest.get("cases") or {}).items():
        for role in ("input", "label"):
            ref = entry.get(role + "_ref")
            if not ref or not os.path.exists(ref):
                problems.append("%s/%s 文件缺失: %r" % (case_id, role, ref))
                continue
            if sha256_file(ref) != entry.get(role + "_sha256"):
                problems.append("%s/%s 内容与封存摘要不一致" % (case_id, role))
    if problems:
        raise ValueError("holdout 组 %s 开封校验失败(文件已被改动): %s"
                         % (group_id, "; ".join(problems)))
    _append_open_event(home, group_id, manifest)
    return manifest


def _proportional(total: int, counts: dict) -> dict:
    """最大余数法按比例分配,total 拆到各类别。"""
    s = sum(counts.values())
    if s <= 0 or total <= 0:
        return {}
    raw = {k: total * v / s for k, v in counts.items()}
    base = {k: int(v) for k, v in raw.items()}
    rem = total - sum(base.values())
    if rem > 0:
        order = sorted(counts,
                       key=lambda k: (-(raw[k] - base[k]), k))
        for k in order[:rem]:
            base[k] += 1
    return {k: v for k, v in base.items() if v > 0}


def sample_dev_batch(cases: list, size: int, exclude_ids=None, seed="",
                     miss_bias: dict = None) -> list:
    """从 dev-discovery 池确定性抽一批 case_id(方案 4.2/6.2)。

    - 池 = split==dev 且未 invalid 的用例,先排除 exclude_ids(已用过的批);
    - 正负按 dev 池自然比例(最大余数法分配);
    - miss_bias: case_id→weight(>1 提升 baseline 漏报用例权重),
      层内用 Efraimidis-Spirakis 加权无放回抽样:
      key = u^(1/w),u=hash(seed,id) 的 uniform 值,取 key 最大的 n 条;
    - 池不足 size 时回落全选并发 warning(不虚报批完整性)。
    """
    if size <= 0:
        return []
    excluded = set(exclude_ids or [])
    pool = [c for c in cases
            if c.get("split") == SPLIT_DEV
            and c.get("label_status", STATUS_ACTIVE) != STATUS_INVALID
            and c["case_id"] not in excluded]
    bias = miss_bias or {}

    def weight(c):
        w = bias.get(c["case_id"], 1.0)
        try:
            w = float(w)
        except (TypeError, ValueError):
            w = 1.0
        return w if w > 0 else 1.0

    def key(c):
        return _hash01(seed, "case|" + c["case_id"]) ** (1.0 / weight(c))

    if len(pool) <= size:
        if len(pool) < size:
            warnings.warn(
                "dev-discovery 池仅剩 %d 条(请求 %d 条),回落全选并已排除"
                " exclude_ids;本批不代表完整对照批" % (len(pool), size))
        return [c["case_id"] for c in sorted(pool, key=key, reverse=True)]
    by_label = {}
    for c in pool:
        by_label.setdefault(c["label"], []).append(c)
    quota = _proportional(size, {lab: len(v) for lab, v in by_label.items()})
    picked = []
    for lab in sorted(quota):
        ranked = sorted(by_label[lab], key=key, reverse=True)
        picked.extend(ranked[:quota[lab]])
    return [c["case_id"] for c in picked]


def invalidate_case(cases: list, case_id: str, reason: str,
                    adjudicator: str) -> tuple:
    """坏例裁决(方案 4.3):dev/train 用例标 invalid 并从 reserve 替换。

    - 替换池(reserve)=同 split、同 label、未 invalid 的用例,按确定性
      哈希取第一条;无可替换时 replacement 为 None(不静默凑数);
    - holdout 组冻结,组内不改数据,返回 unchanged=True;
    - 返回 (new_cases, info);new_cases 不改入参对象。
    """
    target = None
    for c in cases:
        if c["case_id"] == case_id:
            target = c
            break
    if target is None:
        raise ValueError("用例不存在: %s" % case_id)
    new_cases = [dict(c) for c in cases]
    if target.get("split") == SPLIT_HOLDOUT:
        return new_cases, {
            "unchanged": True, "case_id": case_id, "split": SPLIT_HOLDOUT,
            "reason": reason, "adjudicator": adjudicator,
            "note": "holdout 组冻结,组内不改数据;裁决走预注册规则与敏感性分析",
        }
    tgt = next(c for c in new_cases if c["case_id"] == case_id)
    tgt["label_status"] = STATUS_INVALID
    tgt["invalid_reason"] = reason
    tgt["adjudicator"] = adjudicator
    tgt["invalidated_ts"] = now_ts()
    reserve = [c for c in new_cases
               if c["case_id"] != case_id
               and c.get("split") == target.get("split")
               and c["label"] == target["label"]
               and c.get("label_status", STATUS_ACTIVE) != STATUS_INVALID]
    replacement = None
    if reserve:
        replacement = min(reserve, key=lambda c: _hash01(
            "reserve", c["case_id"]))
    return new_cases, {
        "unchanged": False,
        "invalidated_case_id": case_id,
        "reason": reason,
        "adjudicator": adjudicator,
        "replacement_case_id": replacement["case_id"] if replacement else None,
        "replacement_label": replacement["label"] if replacement else None,
    }
