"""模型红线单测：此前两份白名单逐字重复、零覆盖，改一处忘另一处会漂移。"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import agentctl  # noqa: E402
import model_policy as p  # noqa: E402
import taskctl  # noqa: E402


def test_single_source_of_truth():
    assert agentctl.ALLOWED_MODELS is taskctl.ALLOWED_MODELS is p.CB_ALLOWED


def test_free_models_allowed():
    for m in ("free-model", "free-model-flash", "small-model", "echo"):
        assert p.is_allowed(m)
        p.assert_model(m)


def test_cheap_models_allowed():
    for m in ("gpt-6-luna", "glm-5.3-flash-ioa", "deepseek-v4.1-flash"):
        assert p.is_allowed(m)


def test_expensive_models_rejected():
    for m in ("claude-opus-4", "gpt-6-astra", "gpt-5.6-sol"):
        assert not p.is_allowed(m)
        with pytest.raises(SystemExit):
            p.assert_model(m)


def test_knot_has_its_own_free_pool():
    assert p.is_allowed("free-model", "knot")
    assert p.is_allowed("glm-5.3", "knot")
    assert not p.is_allowed("gpt-6-astra", "knot")
    with pytest.raises(SystemExit):
        p.assert_model("gpt-6-astra", "knot")


def test_strict_env_can_disable_for_diagnosis(monkeypatch):
    monkeypatch.setenv("<业务环境变量>", "0")
    p.assert_model("claude-opus-4")  # 不抛
    monkeypatch.delenv("<业务环境变量>")
    with pytest.raises(SystemExit):
        p.assert_model("claude-opus-4")


def test_taskctl_wrapper_delegates(monkeypatch):
    with pytest.raises(SystemExit):
        taskctl.assert_model("claude-opus-4")
    taskctl.assert_model("free-model")


def test_agentctl_dispatch_rejects_expensive_model(monkeypatch):
    """派单入口必须真的调用红线，而不只是定义了一份常量。"""
    import argparse
    args = argparse.Namespace(
        model="claude-opus-4", prompt="x", prompt_file=None,
        name="t", backend="codebuddy", workdir="/tmp", session_id=None,
        max_restarts=5)
    assert agentctl.cmd_dispatch(args) == 2
