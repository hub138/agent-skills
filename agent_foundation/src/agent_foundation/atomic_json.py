"""Crash-safe JSON key-value storage with backup-then-atomic-replace.

Real-world failure this abstracts: a task database written with plain
``write_text`` was killed mid-write, leaving a truncated JSON file. The next
load treated the corruption as "empty database" and the next save **permanently
wrote the empty state back** — hundreds of records unrecoverable.

Contract:
- ``load`` never silently returns empty. On corruption it falls back to the
  last good backup (``<file>.bak``) and reports what happened via the
  ``recovered`` flag — the caller decides whether an empty database is
  legitimate.
- ``save`` rotates the previous good file to ``.bak`` **before** writing,
  then writes a tmp file and atomically renames it. A kill mid-write leaves
  the tmp file behind, never a truncated main file.
- An optional ``validate`` hook rejects structurally-wrong payloads at load
  time (a valid JSON that is semantically wrong is still corruption).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class LoadResult:
    """What load() found. ``recovered_from`` names the fallback used."""

    data: Any
    ok: bool
    recovered_from: str | None = None
    error: str | None = None


class AtomicJsonStore:
    def __init__(self, path: str | Path, *,
                 validate: Callable[[Any], bool] | None = None,
                 default: Any = None) -> None:
        self._path = Path(path)
        self._backup = self._path.with_suffix(self._path.suffix + ".bak")
        self._validate = validate
        self._default = default

    def load(self) -> LoadResult:
        """Load, falling back to the backup. Never silently report empty.

        A missing main file with a present-but-unreadable backup is a
        corruption, not an empty database — the backup's existence proves
        data was saved before. Reporting ok=True + default here would let
        the next save() permanently write the empty state (production
        incident: hundreds of records lost exactly this way).
        """
        last_error: str | None = None
        for path, origin in ((self._path, "main"), (self._backup, "backup")):
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
                last_error = f"{origin}: {str(e)[:100]}"
                continue
            if self._validate is not None and not self._validate(data):
                last_error = f"{origin}: structural validation failed"
                continue
            recovered = origin == "backup"
            return LoadResult(data=data, ok=True,
                              recovered_from=("backup" if recovered else None))
        if not self._path.exists() and not self._backup.exists():
            return LoadResult(data=self._default, ok=True)  # genuinely fresh
        return LoadResult(data=self._default, ok=False,
                          error=f"unreadable: {last_error}")

    def save(self, data: Any) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=1)
        if self._validate is not None and not self._validate(data):
            raise ValueError("refusing to save structurally invalid data")
        try:
            if self._path.exists():
                self._path.replace(self._backup)
        except OSError:
            pass  # best-effort backup; the atomic write below still protects
        # mkstemp: unique name per call — concurrent writers cannot clobber
        # each other's tmp file (a fixed name trampled a parallel save once).
        # fsync before rename: the rename is atomic but the *content* must be
        # on disk first, or a power loss lands an empty rename target.
        import tempfile
        fd, tmp_name = tempfile.mkstemp(dir=str(self._path.parent),
                                        suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self._path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    def exists(self) -> bool:
        return self._path.exists()
