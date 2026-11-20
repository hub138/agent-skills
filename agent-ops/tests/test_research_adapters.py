"""research_loop.adapters 工程回归（方案 3.2/9.3/1.2 条 5）。"""
import json
import sys
import textwrap
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from research_loop import adapters, store  # noqa: E402

FAKE_TASKCTL = textwrap.dedent("""
    import sys
    from pathlib import Path
    counter = Path(__file__).resolve().parent / "taskctl_calls"
    calls = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(calls))
    print("task-123")
""")

SLOW_TASKCTL = textwrap.dedent("""
    import time
    time.sleep(10)
    print("task-slow")
""")


@pytest.fixture()
def db(tmp_path):
    return store.open_db(str(tmp_path / "state.sqlite"))


@pytest.fixture()
def fake_taskctl(tmp_path):
    path = tmp_path / "fake_taskctl.py"
    path.write_text(FAKE_TASKCTL, encoding="utf-8")
    return str(path)


def _dispatch(db, taskctl, exp="exp-1", stage="candidate", attempt="a-1"):
    return adapters.dispatch_attempt(
        taskctl, db, exp, stage, attempt, "/tmp/prompt.md", "/tmp/work",
        {"project_id": "p1"})


def test_ensure_outbox_idempotent_by_key(db):
    o1 = adapters.ensure_outbox(db, "exp-1", "candidate", "a-1")
    o2 = adapters.ensure_outbox(db, "exp-1", "candidate", "a-1")
    assert o1 == o2
    o3 = adapters.ensure_outbox(db, "exp-1", "candidate", "a-2")
    assert o3 != o1
    n = db.execute("SELECT COUNT(*) AS c FROM outbox").fetchone()["c"]
    assert n == 2


def test_dispatch_attempt_saves_task_id(fake_taskctl, db):
    got = _dispatch(db, fake_taskctl)
    assert got["exec_status"] == "dispatched"
    assert got["task_id"] == "task-123"
    assert not got["reused"]
    row = db.execute("SELECT task_id, dispatch_status FROM outbox"
                     " WHERE outbox_id = ?", (got["outbox_id"],)).fetchone()
    assert row["task_id"] == "task-123"
    assert row["dispatch_status"] == "dispatched"


def test_dispatch_attempt_reuses_registered_task_id(fake_taskctl, db):
    first = _dispatch(db, fake_taskctl)
    calls = int((Path(fake_taskctl).parent / "taskctl_calls").read_text())
    second = _dispatch(db, fake_taskctl)
    assert second["task_id"] == first["task_id"]
    assert second["reused"] and not second["outbox_id"] != first["outbox_id"]
    assert int((Path(fake_taskctl).parent / "taskctl_calls").read_text()) == calls
    n = db.execute("SELECT COUNT(*) AS c FROM outbox").fetchone()["c"]
    assert n == 1


def test_dispatch_attempt_blocked_when_taskctl_missing(db):
    got = _dispatch(db, str(Path("no_such_taskctl_cli.py")))
    assert got["exec_status"] == "blocked"
    row = db.execute("SELECT dispatch_status, task_id FROM outbox"
                     " WHERE outbox_id = ?", (got["outbox_id"],)).fetchone()
    assert row["dispatch_status"] == "blocked" and row["task_id"] is None


def test_crash_reconcile_and_redispatch_once(fake_taskctl, db):
    outbox_id = adapters.ensure_outbox(db, "exp-9", "candidate", "a-9")
    # 模拟崩溃窗口：taskctl 已受理但回执未写回（dispatching 且无 task_id）
    with store.tx_ctx(db):
        db.execute("UPDATE outbox SET dispatch_status = 'dispatching'"
                   " WHERE outbox_id = ?", (outbox_id,))
    # 对账先发现缺口
    report = adapters.reconcile(db, fake_taskctl)
    assert report == {"reconciled": 0, "missing": 1}
    row = db.execute("SELECT dispatch_status FROM outbox WHERE outbox_id = ?",
                     (outbox_id,)).fetchone()
    assert row["dispatch_status"] == "pending"
    # 重派一次后不再重复：仍是同一行，且拿到 task_id
    got = _dispatch(db, fake_taskctl, exp="exp-9", stage="candidate",
                    attempt="a-9")
    assert got["task_id"] == "task-123" and got["outbox_id"] == outbox_id
    n = db.execute("SELECT COUNT(*) AS c FROM outbox").fetchone()["c"]
    assert n == 1
    # 行已是 dispatched（dispatch_attempt 成功回填）→ reconcile 无需处理
    report = adapters.reconcile(db, fake_taskctl)
    assert report == {"reconciled": 0, "missing": 0}


def test_check_execution_result_strict(tmp_path):
    ok = tmp_path / "result.json"
    ok.write_text(json.dumps({
        "exec_status": "succeeded",
        "cases": [{"case_id": "c1", "metrics": [{"metric_id": "recall",
                    "hit": 1, "total": 1}]}],
        "started_at": "2026-11-20T00:00:00", "finished_at": "2026-11-20T01:00:00",
    }), encoding="utf-8")
    assert adapters.check_execution_result(str(ok))["valid"] is True

    assert adapters.check_execution_result(
        str(tmp_path / "missing.json")) == {
            "valid": False, "reason": "missing"}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    got_bad = adapters.check_execution_result(str(bad))
    assert got_bad["valid"] is False and got_bad["reason"].startswith("malformed")
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"exec_status": "succeeded",
                                   "cases": []}), encoding="utf-8")
    got = adapters.check_execution_result(str(partial))
    assert got["valid"] is False and "missing field" in got["reason"]
    # cases 元素缺 case_id / 字符串数组 → 逐条校验拒绝（审计问题 2）
    strcases = tmp_path / "strcases.json"
    strcases.write_text(json.dumps({"exec_status": "succeeded",
                                    "cases": ["c1"], "started_at": "x",
                                    "finished_at": "y"}), encoding="utf-8")
    got = adapters.check_execution_result(str(strcases))
    assert got["valid"] is False and "cases[0]" in got["reason"]
    failed = tmp_path / "failed.json"
    failed.write_text(json.dumps({
        "exec_status": "failed", "cases": [], "started_at": "x",
        "finished_at": "y"}), encoding="utf-8")
    got = adapters.check_execution_result(str(failed))
    assert got["valid"] is False and "failed" in got["reason"]


def test_run_stage_cmd_argv_validation():
    with pytest.raises(ValueError):
        adapters.run_stage_cmd("echo hi")
    with pytest.raises(ValueError):
        adapters.run_stage_cmd(["echo", 1])


def test_run_stage_cmd_exec_and_timeout(tmp_path):
    got = adapters.run_stage_cmd(["true"])
    assert got["exec_status"] == "succeeded" and got["rc"] == 0
    got = adapters.run_stage_cmd(["false"])
    assert got["exec_status"] == "failed" and got["timeout"] is False
    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(10)\n", encoding="utf-8")
    got = adapters.run_stage_cmd([sys.executable, str(slow)], timeout=1)
    assert got["exec_status"] == "failed" and got["timeout"] is True
