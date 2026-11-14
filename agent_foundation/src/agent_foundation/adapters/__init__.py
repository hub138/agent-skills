"""Adapters for mainstream open-source / CLI AI coding agents.

Each adapter only describes: the executable name, how to build argv for a
one-shot prompt, and how to extract the answer from output. Model names,
tiers and credentials are caller-injected — nothing vendor-specific lives in
this package beyond the public command-line shape of each tool.
"""

from .base import AgentErrorKind, AgentPool, AgentRunResult, CliAgent, classify_error, make_cli_agent

__all__ = ["AgentErrorKind", "AgentPool", "AgentRunResult", "CliAgent",
           "make_cli_agent"]


def codebuddy(model: str | None = None, **kw) -> CliAgent:
    """codebuddy CLI: `codebuddy -p [--model M]`, prompt via stdin."""
    return make_cli_agent("codebuddy", "codebuddy",
                          ["codebuddy", "-p"] + (["--model", "{model}"] if model else []),
                          prompt_via_stdin=True, model_flag="--model", **kw)


def codex(model: str | None = None, **kw) -> CliAgent:
    """codex CLI: `codex exec [--model M] <prompt on argv>`."""
    return make_cli_agent("codex", "codex",
                          ["codex", "exec"] + (["--model", "{model}"] if model else []),
                          prompt_via_stdin=False, **kw)


def claude(model: str | None = None, **kw) -> CliAgent:
    """claude CLI: `claude -p [--model M]`, prompt via stdin."""
    return make_cli_agent("claude", "claude",
                          ["claude", "-p"] + (["--model", "{model}"] if model else []),
                          prompt_via_stdin=True, model_flag="--model", **kw)
