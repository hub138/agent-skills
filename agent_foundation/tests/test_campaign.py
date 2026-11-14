"""测试批量任务账本：登记、领取、重试、终态。"""

from agent_foundation import CampaignLedger, TaskState


def test_ledger_full_lifecycle():
    ledger = CampaignLedger()
    ledger.add("t1", {"commit": "abc"})
    ledger.add("t2", {"commit": "def"}, max_attempts=1)

    task = ledger.claim("t1")
    assert task is not None
    assert task.state is TaskState.RUNNING
    assert task.attempts == 1

    ledger.fail("t1", "env broken")
    assert ledger.claim("t1").attempts == 2

    ledger.complete("t1")
    assert ledger.counts() == {"done": 1, "pending": 1}

    second = ledger.claim("t2")
    ledger.fail("t2", "no recovery")
    assert second.state is TaskState.FAILED


def test_ledger_claim_order_and_skip():
    ledger = CampaignLedger()
    ledger.add("a", {})
    ledger.add("b", {})
    ledger.skip("a", "not applicable")
    assert ledger.claim().task_id == "b"
    assert ledger.pending_ids() == []
