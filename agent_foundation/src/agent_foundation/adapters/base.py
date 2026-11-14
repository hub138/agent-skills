"""Unified adapter layer for open-source / CLI-based AI coding agents.

Real-world failure this abstracts: the parent system drives multiple AI CLIs
(codebuddy, codex, claude) through subprocess calls, and each one fails
differently - rate limits read like normal errors, auth expiry looks like a
crash, one CLI returns JSON, another prints prose.

Rules encoded here:
- AgentErrorKind: a closed taxonomy of failure modes every CLI shares.
- CliAgent: probe (installed?), run a one-shot prompt, classify failures.
- AgentPool: rotate across adapters, benching ones that recently failed with
  RATE_LIMIT or AUTH (hammering an exhausted pool turned a 20-second outage
  into a 2-hour hang in production).

NOT here: model names, pricing tiers, credentials, which CLIs are "free" -
deployment decisions the caller injects. Nothing in this package names a
vendor.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..cli_session import ProcessResult, ProcessSpec, ProcessSupervisor


class AgentErrorKind(StrEnum):
    OK = "ok"
    NOT_INSTALLED = "not_installed"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    PARSE = "parse"
    TRANSPORT = "transport"
    UNKNOWN = "unknown"


_DEFAULT_PATTERNS = {
    AgentErrorKind.AUTH: (r"not logged in", r"unauthorized", r"401",
                          r"login required", r"invalid api key", r"token expired"),
    AgentErrorKind.RATE_LIMIT: (r"rate limit", r"429", r"quota exceeded",
                                r"too many requests"),
    AgentErrorKind.TIMEOUT: (r"timed? ?out", r"etimedout", r"deadline exceeded"),
    AgentErrorKind.TRANSPORT: (r"connection (refused|reset|error)", r"econnrefused",
                               r"name or service not known"),
}


def classify_error(stderr: str, *, extra_patterns=None) -> AgentErrorKind:
    text = (stderr or "").lower()
    patterns = dict(_DEFAULT_PATTERNS)
    if extra_patterns:
        patterns.update(extra_patterns)
    for kind in (AgentErrorKind.AUTH, AgentErrorKind.RATE_LIMIT,
                 AgentErrorKind.TIMEOUT, AgentErrorKind.TRANSPORT):
        if any(re.search(p, text) for p in patterns.get(kind, ())):
            return kind
    return AgentErrorKind.UNKNOWN


@dataclass(frozen=True)
class AgentRunResult:
    ok: bool
    output: str = ""
    error_kind: AgentErrorKind = AgentErrorKind.OK
    error_detail: str = ""
    model: str = ""
    seconds: float = 0.0
    raw: ProcessResult | None = None


@dataclass
class CliAgent:
    """Base adapter for one AI CLI executable. Model names are
    caller-injected - this package never names a vendor's models."""

    name: str
    executable: str
    build_argv: Callable[[str, str | None, Sequence[str] | None], list[str]]
    extract_output: Callable[[ProcessResult], str]
    family: str = "default"
    extra_error_patterns: dict = field(default_factory=dict)
    default_timeout: float = 900.0
    model_flag: str | None = None
    _prompt_via_stdin: bool = False
    _supervisor: ProcessSupervisor = field(default_factory=ProcessSupervisor, repr=False)

    def probe(self) -> AgentErrorKind:
        return AgentErrorKind.NOT_INSTALLED if shutil.which(self.executable) is None \
            else AgentErrorKind.OK

    def run(self, prompt: str, *, model: str | None = None,
            extra_args: Sequence[str] | None = None,
            timeout: float | None = None, cwd: str | None = None) -> AgentRunResult:
        if self.probe() == AgentErrorKind.NOT_INSTALLED:
            return AgentRunResult(ok=False, error_kind=AgentErrorKind.NOT_INSTALLED,
                                  error_detail=f"{self.executable} not on PATH",
                                  model=model or "", seconds=0.0)
        t0 = time.time()
        spec = ProcessSpec(
            self.build_argv(prompt, model, extra_args),
            input_text=prompt if self._prompt_via_stdin else None,
            cwd=cwd,
            hard_timeout_seconds=timeout or self.default_timeout,
            idle_timeout_seconds=min(300.0, timeout or self.default_timeout),
        )
        result = self._supervisor.run(spec)
        seconds = time.time() - t0
        if result.termination and "timeout" in str(result.termination).lower():
            return AgentRunResult(ok=False, error_kind=AgentErrorKind.TIMEOUT,
                                  error_detail=f"terminated after {seconds:.0f}s",
                                  model=model or "", seconds=seconds, raw=result)
        if result.returncode not in (0, None) and not result.stdout.strip():
            kind = classify_error(result.stderr, extra_patterns=self.extra_error_patterns)
            return AgentRunResult(ok=False, error_kind=kind,
                                  error_detail=result.stderr[:200],
                                  model=model or "", seconds=seconds, raw=result)
        try:
            output = self.extract_output(result)
        except Exception as e:
            return AgentRunResult(ok=False, error_kind=AgentErrorKind.PARSE,
                                  error_detail=f"output unparseable: {e}",
                                  model=model or "", seconds=seconds, raw=result)
        if not output.strip():
            kind = classify_error(result.stdout + result.stderr,
                                  extra_patterns=self.extra_error_patterns)
            if kind != AgentErrorKind.UNKNOWN:
                return AgentRunResult(ok=False, error_kind=kind,
                                      error_detail=(result.stdout + result.stderr)[:200],
                                      model=model or "", seconds=seconds, raw=result)
        return AgentRunResult(ok=True, output=output, error_kind=AgentErrorKind.OK,
                              model=model or "", seconds=seconds, raw=result)


class AgentPool:
    """Rotate across adapters, benching recent RATE_LIMIT/AUTH failures."""

    def __init__(self, agents: Sequence[CliAgent], *, bench_seconds: float = 300.0) -> None:
        self._agents = list(agents)
        self._bench: dict[str, float] = {}
        self._bench_seconds = bench_seconds

    def run(self, prompt: str, *, model: str | None = None,
            timeout: float | None = None) -> AgentRunResult:
        now = time.time()
        failures: list[str] = []
        seen_families: set[str] = set()
        for agent in self._agents:
            if now < self._bench.get(agent.name, 0):
                continue
            if agent.family in seen_families:
                continue
            seen_families.add(agent.family)
            r = agent.run(prompt, model=model, timeout=timeout)
            if r.ok:
                return r
            failures.append(f"{agent.name}: {r.error_kind.value} {r.error_detail[:60]}")
            if r.error_kind in (AgentErrorKind.RATE_LIMIT, AgentErrorKind.AUTH):
                self._bench[agent.name] = time.time() + self._bench_seconds
                # 同族跳过只针对**预算类失败**（共享限流预算）：安装错误/
                # 解析错误与家族无关，同族的其他 agent 仍要试——否则一个
                # CLI 没安装会把同族的健康 agent 一起跳掉（实测发生过）。
                if agent.family != "default":
                    seen_families.add(agent.family)
            elif r.error_kind in (AgentErrorKind.NOT_INSTALLED,):
                seen_families.discard(agent.family)
        # 全部被 bench 时 failures 为空——如实说明，别返回空字符串
        detail = " | ".join(failures)[:300] or \
            "all agents benched or unavailable (no attempt made)"
        return AgentRunResult(ok=False, error_kind=AgentErrorKind.UNKNOWN,
                              error_detail=detail)


def make_cli_agent(name: str, executable: str, argv_template: Sequence[str],
                   output_json_pointer: str | None = None,
                   output_regex: str | None = None, *, family: str = "default",
                   extra_error_patterns: dict | None = None,
                   prompt_via_stdin: bool = True,
                   default_timeout: float = 900.0,
                   model_flag: str | None = "--model",
                   extract: Callable[[ProcessResult], str] | None = None) -> CliAgent:
    """Convenience builder: argv_template uses {prompt}/{model} placeholders.

    ``model_flag`` (e.g. "--model") lets the caller pass a model at run time
    even when the template has no {model} slot - the flag+value pair is
    appended at build. None disables model injection for this CLI."""
    tmpl = list(argv_template)

    def build(prompt: str, model: str | None, extra: Sequence[str] | None) -> list[str]:
        argv = [a.format(prompt=prompt, model=model or "") if "{" in a else a
                for a in tmpl]
        if model and model_flag and model_flag not in argv:
            argv.extend([model_flag, model])
        if extra:
            argv.extend(extra)
        if not prompt_via_stdin:
            argv.append(prompt)
        return argv

    def extract_output(result: ProcessResult) -> str:
        if extract is not None:
            return extract(result)
        text = result.stdout
        if output_json_pointer:
            try:
                data = json.loads(text)
                hit = data
                for part in output_json_pointer.strip("/").split("/"):
                    hit = hit.get(part) if isinstance(hit, dict) else None
                    if hit is None:
                        break
                if hit is not None:
                    return str(hit)
            except (json.JSONDecodeError, ValueError, AttributeError):
                pass
            return text
        if output_regex:
            m = re.search(output_regex, text, re.S)
            if m:
                return m.group(1) if m.groups() else m.group(0)
        return text

    return CliAgent(
        name=name, executable=executable, build_argv=build,
        extract_output=extract_output, family=family,
        extra_error_patterns=extra_error_patterns or {},
        model_flag=model_flag,
        _prompt_via_stdin=prompt_via_stdin,
        default_timeout=default_timeout,
    )
