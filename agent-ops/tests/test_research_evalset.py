"""research_loop.evalset 工程回归(方案 4/4.2/4.3、13.1 数据项)。"""
import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from research_loop import evalset  # noqa: E402


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")


def _case(case_id, label, group_id=None, **kw):
    d = {"case_id": case_id, "label": label, "group_id": group_id or case_id,
         "label_grade": "precise", "bucket": "b", "input_ref": "",
         "label_ref": ""}
    d.update(kw)
    return d


def _make_refs(tmp_path, rows):
    """为每条用例生成 input/label 物理分离文件并回填 ref。"""
    for r in rows:
        inp = tmp_path / ("inputs/%s.txt" % r["case_id"])
        lab = tmp_path / ("vault/%s.lbl" % r["case_id"])
        inp.parent.mkdir(exist_ok=True)
        lab.parent.mkdir(exist_ok=True)
        inp.write_text("IN::%s\n" % r["case_id"], encoding="utf-8")
        lab.write_text("LBL::%s|%s\n" % (r["case_id"], r["label"]),
                       encoding="utf-8")
        r["input_ref"] = str(inp)
        r["label_ref"] = str(lab)
    return rows


# ---------- import_cases ----------

def test_import_cases_missing_case_id_or_label_raises(tmp_path):
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [{"case_id": "c1", "label": "pos"},
                     {"case_id": "", "label": "pos"},
                     {"label": "neg"}])
    with pytest.raises(ValueError):
        evalset.import_cases(str(p))


def test_import_cases_bad_label_and_dup_rejected(tmp_path):
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [{"case_id": "c1", "label": "maybe"}])
    with pytest.raises(ValueError):
        evalset.import_cases(str(p))
    _write_jsonl(p, [{"case_id": "c1", "label": "pos"},
                     {"case_id": "c1", "label": "neg"}])
    with pytest.raises(ValueError):
        evalset.import_cases(str(p))


def test_import_cases_ok_fields_filled(tmp_path):
    p = tmp_path / "cases.jsonl"
    _write_jsonl(p, [{"case_id": "c1", "label": "pos"}])
    cases = evalset.import_cases(str(p))
    assert len(cases) == 1
    assert cases[0]["group_id"] == "c1"
    assert cases[0]["label_grade"] == "unknown"


# ---------- assign_splits ----------

def test_associated_group_never_crosses_split(tmp_path):
    rows = [_case("a1", "pos", "g-bug-1"), _case("a2", "pos", "g-bug-1"),
            _case("b1", "neg", "g-bug-2")]
    out = evalset.assign_splits(rows, seed="s1", holdout_groups=[])
    by_id = {c["case_id"]: c for c in out}
    assert by_id["a1"]["split"] == by_id["a2"]["split"]
    assert by_id["a1"]["split"] in ("train", "dev")


def test_holdout_groups_go_whole_group_to_holdout():
    rows = [_case("h1", "pos", "g-h"), _case("h2", "pos", "g-h"),
            _case("t1", "neg")]
    out = evalset.assign_splits(rows, seed="s", holdout_groups=["g-h"])
    by_id = {c["case_id"]: c for c in out}
    assert by_id["h1"]["split"] == "holdout"
    assert by_id["h2"]["split"] == "holdout"
    assert by_id["t1"]["split"] != "holdout"


def test_stratified_ratio_consistent_80_pos_20_neg():
    rows = [_case("p%02d" % i, "pos", group_id="g%02d" % (i // 2))
            for i in range(80)] + \
           [_case("n%02d" % i, "neg", group_id="gn%02d" % (i // 2))
            for i in range(20)]
    out = evalset.assign_splits(rows, seed="s1", holdout_groups=[])
    dev = [c for c in out if c["split"] == "dev"]
    train = [c for c in out if c["split"] == "train"]
    dev_pos = sum(1 for c in dev if c["label"] == "pos")
    train_pos = sum(1 for c in train if c["label"] == "pos")
    assert len(dev) == 40 and len(train) == 60
    # 组为原子的贪心不保证逐条等比；改验偏差 ≤5pp（审计问题 3 的校验机制）
    assert abs(dev_pos / len(dev) - train_pos / len(train)) <= 0.05


def test_assign_splits_deterministic_same_seed():
    rows = [_case("c%02d" % i, "pos" if i % 4 else "neg") for i in range(30)]
    a = evalset.assign_splits(rows, seed="zz", holdout_groups=[])
    b = evalset.assign_splits(rows, seed="zz", holdout_groups=[])
    assert [(c["case_id"], c["split"]) for c in a] == \
        [(c["case_id"], c["split"]) for c in b]


# ---------- seal / open holdout ----------

def _holdout_fixture(tmp_path):
    rows = [_case("h1", "pos", "g-h"), _case("h2", "pos", "g-h")]
    _make_refs(tmp_path, rows)
    home = tmp_path / "home"
    return rows, str(home)


def test_seal_then_open_ok(tmp_path):
    rows, home = _holdout_fixture(tmp_path)
    manifest = evalset.seal_holdout(rows, "g-h", home)
    assert manifest["group_id"] == "g-h"
    assert manifest["case_count"] == 2
    assert len(manifest["group_digest"]) == 64
    reopened = evalset.open_holdout(home, "g-h")
    assert reopened["group_digest"] == manifest["group_digest"]


def test_tampered_label_file_fails_open(tmp_path):
    rows, home = _holdout_fixture(tmp_path)
    evalset.seal_holdout(rows, "g-h", home)
    # 改 label 文件一个字节
    lab = Path(rows[0]["label_ref"])
    text = lab.read_text(encoding="utf-8")
    lab.write_text(text.replace("|pos", "|neg"), encoding="utf-8")
    with pytest.raises(ValueError):
        evalset.open_holdout(home, "g-h")


def test_open_unsealed_group_raises(tmp_path):
    with pytest.raises(ValueError):
        evalset.open_holdout(str(tmp_path), "nope")


def test_open_event_appended_only(tmp_path):
    rows, home = _holdout_fixture(tmp_path)
    evalset.seal_holdout(rows, "g-h", home)
    evalset.open_holdout(home, "g-h")
    ev = Path(home) / "g-h" / "open_events.jsonl"
    lines1 = ev.read_text(encoding="utf-8").strip().splitlines()
    evalset.open_holdout(home, "g-h")
    lines2 = ev.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == len(lines1) + 1


# ---------- sample_dev_batch ----------

def _dev_pool(n_pos=30, n_neg=10):
    rows = []
    for i in range(n_pos):
        rows.append(_case("dp%02d" % i, "pos", split="dev"))
    for i in range(n_neg):
        rows.append(_case("dn%02d" % i, "neg", split="dev"))
    return rows


def test_sample_dev_batch_deterministic_same_seed():
    pool = _dev_pool()
    a = evalset.sample_dev_batch(pool, size=10, seed="s1")
    b = evalset.sample_dev_batch(pool, size=10, seed="s1")
    assert a == b and len(a) == 10


def test_sample_dev_batch_excludes_and_batches_disjoint():
    pool = _dev_pool()
    b1 = evalset.sample_dev_batch(pool, size=10, seed="s1")
    b2 = evalset.sample_dev_batch(pool, size=10, seed="s1",
                                  exclude_ids=b1)
    assert not set(b1) & set(b2)
    assert set(b1) <= {c["case_id"] for c in pool}


def test_sample_dev_batch_miss_bias_lifts_missed_case():
    pool = _dev_pool()
    biased = evalset.sample_dev_batch(pool, size=3, seed="s1",
                                      miss_bias={"dp05": 1000.0})
    assert "dp05" in biased


def test_sample_dev_batch_natural_label_proportion():
    pool = _dev_pool(n_pos=30, n_neg=10)  # 池内 pos:neg = 3:1
    batch = evalset.sample_dev_batch(pool, size=10, seed="s1")
    got = {c["case_id"]: c for c in pool if c["case_id"] in set(batch)}
    n_pos = sum(1 for c in got.values() if c["label"] == "pos")
    assert abs(n_pos - 7.5) <= 1.0  # 自然比例 7~8 个 pos


def test_sample_dev_batch_insufficient_pool_falls_back_with_warning():
    pool = _dev_pool(n_pos=4, n_neg=2)
    with pytest.warns(UserWarning):
        batch = evalset.sample_dev_batch(pool, size=100, seed="s1")
    assert len(batch) == 6


def test_sample_dev_batch_skips_invalid_cases():
    pool = _dev_pool(n_pos=4, n_neg=2)
    pool[0]["label_status"] = "invalid"
    batch = evalset.sample_dev_batch(pool, size=100, seed="s1")
    assert pool[0]["case_id"] not in batch


# ---------- invalidate_case ----------

def test_invalidate_dev_case_marks_and_replaces():
    pool = [_case("d1", "pos", split="dev"),
            _case("d2", "pos", split="dev"),
            _case("d3", "neg", split="dev")]
    new_cases, info = evalset.invalidate_case(
        pool, "d1", "标签复核不成立", "adjudicator-A")
    assert info["unchanged"] is False
    assert info["replacement_case_id"] == "d2"  # 同 split 同 label 的 reserve
    tgt = next(c for c in new_cases if c["case_id"] == "d1")
    assert tgt["label_status"] == "invalid"
    assert tgt["invalid_reason"] == "标签复核不成立"
    assert tgt["adjudicator"] == "adjudicator-A"
    rep = next(c for c in new_cases if c["case_id"] == "d2")
    assert rep.get("label_status", "active") == "active"  # 替换例不改数据
    assert pool[0].get("label_status", "active") == "active"  # 入参不被改


def test_invalidate_holdout_case_frozen_unchanged():
    rows = [_case("h1", "pos", "g-h", split="holdout"),
            _case("h2", "pos", "g-h", split="holdout")]
    new_cases, info = evalset.invalidate_case(
        rows, "h1", "疑似坏例", "adjudicator-B")
    assert info["unchanged"] is True
    assert all(c.get("label_status", "active") == "active" for c in new_cases)
    assert "label_status" not in new_cases[0]


def test_invalidate_missing_case_raises():
    with pytest.raises(ValueError):
        evalset.invalidate_case([_case("d1", "pos")], "nope", "r", "a")
