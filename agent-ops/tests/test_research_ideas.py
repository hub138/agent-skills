"""research_loop.ideas 工程回归（方案 3.2/6.1/6.3）。"""
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from research_loop import ideas, store  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    return store.open_db(str(tmp_path / "state.sqlite"))


def _add(db, title, direction="dir-a", kind="prompt_engineering"):
    return ideas.add_idea(db, title, kind, direction, "test", [], "反证计划")


def test_add_idea_returns_id_and_kind_validated(db):
    idea_id = _add(db, "缓存评估器摘要")
    assert idea_id
    with pytest.raises(ValueError):
        ideas.add_idea(db, "bad", "not_a_kind", "d", "s", [], "f")


def test_fingerprint_dedupe_same_title_direction(db):
    first = _add(db, "同题", "dir-1")
    second = _add(db, "同题", "dir-1")
    assert first == second
    n = db.execute("SELECT COUNT(*) AS c FROM ideas").fetchone()["c"]
    assert n == 1
    other = _add(db, "同题", "dir-2")
    assert other != first


def test_update_idea_status_validates(db):
    idea_id = _add(db, "状态流")
    ideas.update_idea_status(db, idea_id, ideas.IDEA_PAUSED)
    row = db.execute("SELECT status FROM ideas WHERE idea_id = ?",
                     (idea_id,)).fetchone()
    assert row["status"] == "paused"
    with pytest.raises(ValueError):
        ideas.update_idea_status(db, idea_id, "accepted")


def test_record_outcome_tries_wins(db):
    idea_id = _add(db, "记账")
    ideas.record_outcome(db, idea_id, True, "exp-1")
    ideas.record_outcome(db, idea_id, False, "exp-2")
    row = db.execute("SELECT tries, wins, status FROM ideas WHERE idea_id = ?",
                     (idea_id,)).fetchone()
    assert row["tries"] == 2 and row["wins"] == 1 and row["status"] == "won"
    events = [e["kind"] for e in store.replay_events(db)]
    assert events.count("idea_outcome") == 2


def test_next_ideas_queued_first_retired_excluded(db):
    fresh = _add(db, "零尝试", "dir-fresh")
    tested = ideas.add_idea(db, "有战绩", "case_correctness", "dir-b",
                            "test", [], "f")
    ideas.record_outcome(db, tested, True, "e1")
    ideas.record_outcome(db, tested, False, "e2")
    retired = _add(db, "已退役", "dir-r")
    ideas.update_idea_status(db, retired, ideas.IDEA_RETIRED)
    paused = _add(db, "已暂停", "dir-p")
    ideas.update_idea_status(db, paused, ideas.IDEA_PAUSED)

    got = ideas.next_ideas(db, limit=5)
    ids = [g["idea_id"] for g in got]
    assert retired not in ids
    assert ids[0] == fresh  # 零尝试探索加成排前
    assert set(ids) == {fresh, tested, paused}
    first = got[0]
    assert set(first) == {"idea_id", "title", "kind", "tries", "wins"}


def test_next_ideas_stall_dirs_downweight(db):
    lossy = ideas.add_idea(db, "常失败但非 stall", "case_correctness",
                           "dir-ok", "test", [], "f")
    for _ in range(3):
        ideas.record_outcome(db, lossy, False, "e")  # tries=3 wins=0 保持 queued
    fresh = _add(db, "stall 方向零尝试", "dir-stall")  # 自然分 1.0
    assert ideas.next_ideas(db, limit=2)[0]["idea_id"] == fresh
    demoted = ideas.next_ideas(db, limit=2, stall_dirs=["dir-stall"])
    assert demoted[0]["idea_id"] == lossy
    assert ideas.next_ideas(db, limit=2,
                            stall_dirs=["dir-stall"])[1]["idea_id"] == fresh


def test_next_ideas_deterministic(db):
    for i in range(4):
        _add(db, "同分-%d" % i, "dir-%d" % i)
    a = [g["idea_id"] for g in ideas.next_ideas(db, limit=3)]
    b = [g["idea_id"] for g in ideas.next_ideas(db, limit=3)]
    assert a == b
