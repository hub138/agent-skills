"""Launch, monitor, and parse a line-oriented CLI session without provider semantics."""

from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .events import Event, EventKind

_TERMINAL_ESCAPE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
)


def normalize_stream_line(raw_line: str, *, accept_sse: bool = True) -> str:
    """Remove terminal control bytes and an optional SSE ``data:`` prefix."""
    line = _TERMINAL_ESCAPE.sub("", raw_line or "").strip()
    if accept_sse and line.startswith("data:"):
        line = line[5:].strip()
    return line


def decode_json_lines(
    chunks: Iterable[str],
    *,
    accept_sse: bool = True,
) -> tuple[list[dict[str, Any] | list[Any]], list[str]]:
    """Decode JSON objects/arrays and return non-JSON lines separately."""
    decoded: list[dict[str, Any] | list[Any]] = []
    rejected: list[str] = []
    for chunk in chunks:
        for raw_line in (chunk or "").splitlines():
            line = normalize_stream_line(raw_line, accept_sse=accept_sse)
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                rejected.append(line)
                continue
            if isinstance(value, (dict, list)):
                decoded.append(value)
            else:
                rejected.append(line)
    return decoded, rejected


class Termination(StrEnum):
    EXITED = "exited"
    HARD_TIMEOUT = "hard_timeout"
    IDLE_TIMEOUT = "idle_timeout"
    NOT_FOUND = "not_found"
    START_FAILED = "start_failed"


@dataclass(frozen=True)
class ProcessSpec:
    """Caller-controlled process inputs; no provider-specific fields are implied."""

    argv: Sequence[str]
    input_text: str | None = None
    cwd: str | None = None
    env: Mapping[str, str] | None = None
    hard_timeout_seconds: float | None = None
    idle_timeout_seconds: float | None = None
    heartbeat_interval_seconds: float | None = 5.0
    terminate_grace_seconds: float = 2.0


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    termination: Termination
    elapsed_seconds: float
    stdout: str
    stderr: str
    events: list[Event] = field(default_factory=list)


EventSink = Callable[[Event], None]


class ProcessSupervisor:
    """Supervise one CLI process using output activity as its liveness signal."""

    def run(self, spec: ProcessSpec, *, on_event: EventSink | None = None) -> ProcessResult:
        if not spec.argv:
            raise ValueError("argv must not be empty")
        events: list[Event] = []

        def emit(event: Event) -> None:
            events.append(event)
            if on_event is not None:
                on_event(event)

        started = time.monotonic()
        # Arguments may contain credentials. Do not copy them into event storage.
        emit(Event(EventKind.START, data={"executable": str(spec.argv[0]), "argument_count": len(spec.argv) - 1}))
        environment = dict(os.environ)
        if spec.env:
            environment.update(spec.env)
        try:
            process = subprocess.Popen(
                list(spec.argv),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=spec.cwd,
                env=environment,
                start_new_session=True,
            )
        except FileNotFoundError:
            emit(Event(EventKind.ERROR, "executable not found"))
            return ProcessResult(None, Termination.NOT_FOUND, 0.0, "", "", events)
        except OSError as exc:
            emit(Event(EventKind.ERROR, str(exc)))
            return ProcessResult(None, Termination.START_FAILED, 0.0, "", str(exc), events)

        if process.stdin is not None:
            try:
                if spec.input_text is not None:
                    process.stdin.write(spec.input_text.encode("utf-8"))
                process.stdin.close()
            except OSError:
                pass

        output_queue: queue.Queue[tuple[str, bytes | None]] = queue.Queue()
        readers = [
            _start_reader("stdout", process.stdout, output_queue),
            _start_reader("stderr", process.stderr, output_queue),
        ]
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        termination = Termination.EXITED
        last_activity = started
        last_heartbeat = started

        while True:
            now = time.monotonic()
            if _drain_output(output_queue, stdout_parts, stderr_parts, emit):
                last_activity = now

            if spec.heartbeat_interval_seconds and now - last_heartbeat >= spec.heartbeat_interval_seconds:
                emit(Event(EventKind.HEARTBEAT, data={"elapsed_seconds": round(now - started, 3), "idle_seconds": round(now - last_activity, 3)}))
                last_heartbeat = now

            if process.poll() is not None:
                break
            if spec.hard_timeout_seconds is not None and now - started > spec.hard_timeout_seconds:
                termination = Termination.HARD_TIMEOUT
                emit(Event(EventKind.ERROR, "hard timeout"))
                _terminate_process_group(process, spec.terminate_grace_seconds)
                break
            if spec.idle_timeout_seconds is not None and now - last_activity > spec.idle_timeout_seconds:
                termination = Termination.IDLE_TIMEOUT
                emit(Event(EventKind.ERROR, "idle timeout"))
                _terminate_process_group(process, spec.terminate_grace_seconds)
                break
            time.sleep(0.05)

        for reader in readers:
            reader.join(timeout=0.5)
        _drain_output(output_queue, stdout_parts, stderr_parts, emit)
        elapsed = time.monotonic() - started
        emit(Event(EventKind.END, data={"returncode": process.poll(), "termination": termination, "elapsed_seconds": round(elapsed, 3)}))
        return ProcessResult(process.poll(), termination, elapsed, "".join(stdout_parts), "".join(stderr_parts), events)


def _start_reader(name: str, stream: Any, destination: queue.Queue[tuple[str, bytes | None]]) -> threading.Thread:
    def read() -> None:
        if stream is None:
            destination.put((name, None))
            return
        try:
            for line in iter(stream.readline, b""):
                destination.put((name, line))
        finally:
            destination.put((name, None))

    thread = threading.Thread(target=read, name=f"agent-foundation-{name}", daemon=True)
    thread.start()
    return thread


def _drain_output(
    source: queue.Queue[tuple[str, bytes | None]],
    stdout_parts: list[str],
    stderr_parts: list[str],
    emit: EventSink,
) -> bool:
    had_output = False
    while True:
        try:
            stream, data = source.get_nowait()
        except queue.Empty:
            return had_output
        if data is None:
            continue
        text = data.decode("utf-8", errors="replace")
        (stdout_parts if stream == "stdout" else stderr_parts).append(text)
        emit(Event(EventKind.OUTPUT, text.rstrip("\n"), data={"stream": stream}))
        had_output = True


def _terminate_process_group(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=grace_seconds)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=grace_seconds)
    except (OSError, subprocess.TimeoutExpired):
        return
