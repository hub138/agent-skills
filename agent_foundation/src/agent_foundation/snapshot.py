"""Byte-level file snapshots with verified restore, for AI file-edit safety.

Real-world failure this abstracts: an automated editor wrote to a live
repository while other processes (cron jobs, other agents) were writing the
same files. Restoring with ``git checkout`` would have reverted *everyone's*
changes; a partial restore would have silently corrupted the working tree.

Contract:
- ``snapshot(paths)`` copies exact bytes before any modification.
- ``restore()`` verifies every file with SHA-256 after copying and reports
  any file that could not be restored — a partial restore must never be
  reported as success, because the caller will proceed as if the world is
  back to its pre-edit state.
- Snapshots are keyed by an attempt id so concurrent editors do not
  overwrite each other's rollback points.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path


class FileSnapshot:
    def __init__(self, directory: str | Path, attempt_id: str) -> None:
        self._dir = Path(directory) / attempt_id
        self._attempt = attempt_id

    def snapshot(self, paths: list[str], repo_root: str | Path) -> list[str]:
        """Copy files (repo-relative) into the snapshot. Returns missing ones.

        Files that do not exist are recorded with ``existed: false`` — the
        editor may *create* them during the edit, and a rollback must then
        DELETE them, not leave them behind as orphans (production incident:
        AI-created files survived a "full rollback" and stayed in the repo).
        Each file's sha256 is written into the manifest at snapshot time, so
        restore verifies against the *original* bytes, not against a snapshot
        copy that may itself have been corrupted afterwards.
        """
        root = Path(repo_root)
        self._dir.mkdir(parents=True, exist_ok=True)
        missing = []
        for rel in paths:
            src = root / rel
            if not src.exists():
                missing.append(rel)
                continue
            dst = self._dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        entries = [{"path": rel,
                    "sha256": _sha256(root / rel),
                    "existed": True}
                   for rel in paths if rel not in missing]
        entries += [{"path": rel, "sha256": None, "existed": False}
                    for rel in missing]
        manifest = {"attempt": self._attempt, "files": entries,
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        (self._dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return missing

    def restore(self, repo_root: str | Path) -> tuple[bool, str]:
        """Restore every snapshotted file, verifying against recorded hashes.

        Files recorded as ``existed: false`` are DELETED on restore: they were
        created by the edit, and a rollback that leaves them behind is not a
        rollback. Hash verification compares restored bytes against the
        manifest's snapshot-time record — not against a snapshot copy that
        could itself have been damaged after the fact.
        """
        root = Path(repo_root)
        manifest_path = self._dir / "manifest.json"
        if not manifest_path.exists():
            return False, "no snapshot manifest"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            return False, f"manifest unreadable: {str(e)[:80]}"
        failures: list[str] = []
        restored = 0
        for entry in manifest.get("files", []):
            rel = entry["path"]
            recorded, existed = entry.get("sha256"), entry.get("existed", True)
            src = self._dir / rel
            dst = root / rel
            if not existed:
                # Created by the edit: rollback deletes it.
                try:
                    dst.unlink()
                except FileNotFoundError:
                    pass  # already gone — rollback goal met
                except OSError as e:
                    failures.append(f"{rel}: cannot delete created file: {e}")
                restored += 1
                continue
            if not src.exists():
                failures.append(f"{rel}: snapshot missing")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if _sha256(dst) != (recorded or _sha256(src)):
                failures.append(f"{rel}: restored bytes differ from snapshot-time hash")
                continue
            restored += 1
        if failures:
            return False, "; ".join(failures[:3])
        return True, f"restored {restored} files verified"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()
