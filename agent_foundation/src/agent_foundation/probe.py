"""Safe command discovery and short-lived availability probes."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class CommandProbe:
    executable: str
    available: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


def probe_command(
    executable: str,
    arguments: Sequence[str] = ("--version",),
    *,
    timeout_seconds: float = 5.0,
) -> CommandProbe:
    """Check whether an executable starts; the caller owns authentication semantics."""
    resolved = shutil.which(executable)
    if not resolved:
        return CommandProbe(executable=executable, available=False)
    try:
        completed = subprocess.run(
            [resolved, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandProbe(
            executable=resolved,
            available=True,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
            timed_out=True,
        )
    except OSError as exc:
        return CommandProbe(executable=resolved, available=False, stderr=str(exc))
    return CommandProbe(
        executable=str(Path(resolved)),
        available=True,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
