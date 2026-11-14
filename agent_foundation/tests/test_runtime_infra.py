"""共享资源池、一次性工作区与运行态一致性守护的测试。"""

import os
from pathlib import Path

import pytest

from agent_foundation.resource_pool import (
    DEFAULT_COOLDOWN_SECONDS,
    Lane,
    LaneCapacityError,
    ResourcePool,
)
from agent_foundation.workspace_lifecycle import (
    WorkspaceInUseError,
    WorkspaceNotTerminalError,
    dispose_workspace,
    kill_tree,
    process_references,
    task_report_dir,
)
from agent_foundation.environment_guard import (
    BuildFreshness,
    RuntimeBinaryStatus,
    binary_freshness,
    runtime_binary_status,
    source_baseline_status,
)


# ---------- resource_pool ----------

def _pool(**kw) -> ResourcePool:
    return ResourcePool(
        [
            Lane(name="lane-a", allowed=("model-x", "model-y"), cap=2, use_host_default=True),
            Lane(name="lane-b", allowed=("model-x",), cap=1, secret_ref="LANE_B_TOKEN"),
        ],
        **kw,
    )


def test_lane_cap_is_hard_ceiling():
    lane = Lane(name="a", allowed=("m",), cap=10)
    assert lane.effective_cap == 3
    lane = Lane(name="a", allowed=("m",), cap=0)
    assert lane.effective_cap == 1


def test_acquire_release_roundtrip_and_counts():
    pool = _pool()
    lease = pool.acquire("lane-a", "model-x", "worker-1")
    assert pool.available() == 4
    assert pool.available(resource="model-x") == 2
    pool.release(lease)
    assert pool.available(resource="model-x") == 3
    assert pool.available() == 5
    assert pool.available(resource="model-y") == 2


def test_same_model_across_lanes_does_not_double_count():
    pool = _pool(global_resource_cap=2)
    pool.acquire("lane-a", "model-x", "w1")
    pool.acquire("lane-b", "model-x", "w2")
    with pytest.raises(LaneCapacityError) as err:
        pool.acquire("lane-a", "model-x", "w3")
    assert err.value.cause == "global_cap"


def test_unauthenticated_lane_rejected():
    pool = ResourcePool([Lane(name="dead", allowed=("m",), cap=1)])
    with pytest.raises(LaneCapacityError) as err:
        pool.acquire("dead", "m", "w")
    assert err.value.cause == "credential"


def test_circuit_blocks_lane_and_backpressure_reports_truth():
    pool = _pool()
    assert pool.backpressure_active() is False
    pool.trip("lane-a", "model-x", cooldown_seconds=60)
    pool.trip("lane-b", "model-x", cooldown_seconds=60)
    assert pool.backpressure_active(resource="model-x") is True
    assert pool.available(resource="model-x") == 0
    pool.clear_circuit("lane-a", "model-x")
    assert pool.backpressure_active(resource="model-x") is False
    assert DEFAULT_COOLDOWN_SECONDS > 0


def test_release_stale_reclaims_expired_leases():
    now = [1000.0]
    pool = _pool(clock=lambda: now[0])
    lease = pool.acquire("lane-a", "model-x", "w")
    now[0] += 3601
    stale = pool.release_stale(3600)
    assert [s.id for s in stale] == [lease.id]
    assert pool.available(resource="model-x") == 3


# ---------- workspace_lifecycle ----------

def test_task_report_dir_rejects_traversal(tmp_path: Path):
    assert task_report_dir(tmp_path, "t1") == tmp_path / "t1"
    with pytest.raises(ValueError):
        task_report_dir(tmp_path, "../escape")
    with pytest.raises(ValueError):
        task_report_dir(tmp_path, "")
    with pytest.raises(ValueError):
        task_report_dir(tmp_path, "a/b")


def test_dispose_requires_terminal_state(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(WorkspaceNotTerminalError):
        dispose_workspace(ws, terminal=False)


def test_dispose_refuses_when_process_references(tmp_path: Path):
    import subprocess

    ws = tmp_path / "ws"
    ws.mkdir()
    child = subprocess.Popen(["sleep", "30"], cwd=str(ws))
    try:
        refs = process_references(ws)
        assert any(f"pid={child.pid}" in ref for ref in refs), refs
        with pytest.raises(WorkspaceInUseError):
            dispose_workspace(ws, terminal=True)
        assert ws.exists()
    finally:
        child.kill()
        child.wait()
    result = dispose_workspace(ws, terminal=True)
    assert not ws.exists()


def test_dispose_removes_directory_and_ticket(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "f.txt").write_text("x")
    ticket = tmp_path / "ticket.md"
    ticket.write_text("x")
    seen = []
    result = dispose_workspace(ws, terminal=True, evidence=seen.append, ticket=ticket)
    assert not ws.exists()
    assert not ticket.exists()
    assert result["removed"] is True
    assert seen == [ws.resolve()] or seen == [ws]


def test_kill_tree_self_protection():
    kill_tree(0)
    kill_tree(os.getpid())


# ---------- environment_guard ----------

def test_runtime_binary_status_inode_match(tmp_path: Path, monkeypatch):
    disk = tmp_path / "bin"
    disk.write_bytes(b"payload")
    proc = tmp_path / "proc"
    (proc / "42").mkdir(parents=True)
    (proc / "42" / "exe").symlink_to(disk)
    status = runtime_binary_status(42, disk, proc_root=proc)
    assert status.matches_disk is True
    assert status.deleted is False


def test_runtime_binary_status_detects_deleted_and_stale(tmp_path: Path):
    proc = tmp_path / "proc"
    old = tmp_path / "old_bin"
    old.write_bytes(b"old")
    stale = tmp_path / "stale"
    stale.mkdir()
    (stale / "exe").symlink_to(old)
    status = runtime_binary_status(7, tmp_path / "never", proc_root=stale)
    assert status.matches_disk is False
    deleted = tmp_path / "del"
    deleted.mkdir()
    target = tmp_path / "gone.bin"
    link = deleted / "exe"
    link.symlink_to(target)
    link.unlink()
    (deleted / "not_exe").write_text("(deleted)")
    status2 = runtime_binary_status(8, tmp_path / "x", proc_root=deleted)
    assert status2.matches_disk is False


def test_binary_freshness_counts_pending_steps(tmp_path: Path):
    script = tmp_path / "fake_make"
    script.write_text("#!/bin/sh\necho 'Building foo.c\nLinking bar'\n")
    script.chmod(0o755)
    result = binary_freshness([str(script)], cwd=tmp_path)
    assert result.fresh is False
    assert result.pending_steps == 2
    clean = tmp_path / "clean_make"
    clean.write_text("#!/bin/sh\nexit 0\n")
    clean.chmod(0o755)
    assert binary_freshness([str(clean)], cwd=tmp_path).fresh is True
