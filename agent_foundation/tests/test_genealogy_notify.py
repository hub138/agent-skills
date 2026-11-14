from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_foundation import (
    DEFAULT_PROGRESS_INTERVAL_ROUNDS,
    CandidateNode,
    Genealogy,
    should_notify_progress,
)


def _node(cid: str, parent: str | None = None, accepted: bool = False) -> CandidateNode:
    return CandidateNode(candidate_id=cid, parent_candidate_id=parent, accepted=accepted)


def test_genealogy_builds_tree_from_parent_refs():
    g = Genealogy()
    g.add(_node("root_a"))
    g.add(_node("root_b"))
    g.add(_node("child", parent="root_a"))
    g.add(_node("grandchild", parent="child", accepted=True))
    assert len(g.roots()) == 2
    assert [n.candidate_id for n in g.children("root_a")] == ["child"]
    assert g.depth("grandchild") == 2
    chain = [n.candidate_id for n in g.ancestry("grandchild")]
    assert chain == ["grandchild", "child", "root_a"]


def test_genealogy_duplicate_id_fails_loud():
    g = Genealogy()
    g.add(_node("c1"))
    try:
        g.add(_node("c1"))
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate candidate_id must raise")


def test_genealogy_orphan_dangling_parent_goes_to_root_and_counts():
    g = Genealogy()
    g.add(_node("real_root"))
    g.add(_node("lost_child", parent="vanished"))
    assert "lost_child" in g.orphan_ids()
    assert len(g.roots()) == 2
    assert g.depth("lost_child") == 0


def test_genealogy_cycle_detected():
    g = Genealogy()
    g.add(_node("a", parent="b"))
    g.add(_node("b", parent="a"))
    try:
        g.depth("a")
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("cycle must raise, never loop forever")


def test_genealogy_tree_nests_children():
    g = Genealogy()
    g.add(_node("r"))
    g.add(_node("c1", parent="r"))
    g.add(_node("c2", parent="r", accepted=True))
    tree = g.tree()
    assert len(tree) == 1
    kids = {child["candidate"].candidate_id for child in tree[0]["children"]}
    assert kids == {"c1", "c2"}


def test_notify_failed_round_always_notifies():
    assert should_notify_progress(current_round=1, interval_rounds=100, failed=True)
    assert should_notify_progress(current_round=None, interval_rounds=0, failed=True)


def test_notify_success_follows_cadence_and_zero_disables():
    assert should_notify_progress(current_round=3, interval_rounds=3) is True
    assert should_notify_progress(current_round=4, interval_rounds=3) is False
    assert should_notify_progress(current_round=9, interval_rounds=0) is False
    assert should_notify_progress(current_round=None, interval_rounds=3) is False
    assert DEFAULT_PROGRESS_INTERVAL_ROUNDS == 3
