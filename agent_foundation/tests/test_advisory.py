"""测试投递-确认-回执队列与隐私闸门对新增模块的覆盖。"""

from agent_foundation import (
    AdviceStatus,
    AdvisoryConflictError,
    AdvisoryQueue,
)


def test_publish_poll_expiration_and_gating():
    queue = AdvisoryQueue()
    queue.publish({"text": "first"})
    gated = queue.publish({"text": "need-human"}, gated=True)
    queue.publish({"text": "expired"}, expiration_round=3)

    round2 = queue.poll(current_round=2)
    assert [a.payload for a in round2] == [{"text": "first"}, {"text": "expired"}]

    with_gated = queue.poll(current_round=2, include_gated=True)
    assert gated in with_gated

    round4 = queue.poll(current_round=4)
    assert [a.payload for a in round4] == [{"text": "first"}]


def test_ack_is_idempotent_and_poll_hides_consumed():
    queue = AdvisoryQueue()
    advice = queue.publish({"n": 1})

    assert queue.ack(advice.advice_id) == "consumed"
    assert queue.ack(advice.advice_id) == "already_consumed"
    assert queue.poll() == []

    consumed = queue.publish({"n": 2})
    queue.ack(consumed.advice_id)
    assert consumed.status is AdviceStatus.CONSUMED


def test_outcome_recorded_once_then_conflict():
    queue = AdvisoryQueue()
    advice = queue.publish({"n": 1})
    queue.ack(advice.advice_id)

    applied = queue.record_outcome(advice.advice_id, applied=True, reason="took it")
    assert applied.status is AdviceStatus.APPLIED

    try:
        queue.record_outcome(advice.advice_id, applied=False)
    except AdvisoryConflictError:
        pass
    else:
        raise AssertionError("second outcome must conflict")

    ignored = queue.publish({"n": 2})
    queue.ack(ignored.advice_id)
    queue.record_outcome(ignored.advice_id, applied=False, reason="not relevant")
    assert ignored.status is AdviceStatus.IGNORED


def test_ack_unknown_advice_raises():
    queue = AdvisoryQueue()
    try:
        queue.ack(999)
    except KeyError:
        pass
    else:
        raise AssertionError("unknown id must raise KeyError")
