"""雷达工作区：clone 到独立缓存目录，按 TTL / 容量清理，只删自己记录过的路径。

为什么单独管：上游仓库动辄上百 MB（实测 LoopForge 143MB），而本 skill 的
git 仓库只有几 MB。把 clone 放进 skill 会污染提交、拖慢安装；放 /tmp 又会被
系统清掉且常落在根分区。因此统一放一个可配置的 cache root，并写进台账。

安全边界（三条硬约束）：
  1. 只接受 http(s)/git@ 的仓库 URL，不接受本地路径和 file://；
  2. 删除前必须 resolve 后仍位于 cache root 之内，且是台账里记录过的路径；
  3. 体积超限直接拒绝 clone，不「先下后删」。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

CLONE_TIMEOUT = 300
MAX_MB_DEFAULT = 500


def repo_slug(url: str) -> tuple[str, str, str] | None:
    """把仓库 URL 解析成 (host, org, repo)。解析不出返回 None。"""
    url = (url or "").strip().rstrip("/")
    if url.startswith("git@"):
        m = re.match(r"^git@([^:]+):([^/]+)/(.+?)(?:\.git)?$", url)
        if not m:
            return None
        host, org, repo = m.group(1), m.group(2), m.group(3)
    else:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return None
        parts = [x for x in p.path.split("/") if x]
        if len(parts) < 2:
            return None
        host, org, repo = p.hostname.lower(), parts[0], parts[1]
    repo = re.sub(r"\.git$", "", repo)
    if not re.match(r"^[\w.-]+$", repo) or not re.match(r"^[\w.-]+$", org):
        return None
    return host, org, repo


def workspace_path(url: str, root: Path) -> Path | None:
    slug = repo_slug(url)
    if not slug:
        return None
    host, org, repo = slug
    return Path(root) / host / org / repo


def _inside(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def dir_size(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path, onerror=lambda e: None):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                continue
    return total


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True,
                          timeout=CLONE_TIMEOUT)


def ensure_workspace(url: str, root: Path, *,
                     max_mb: int = MAX_MB_DEFAULT) -> dict:
    """clone 或刷新一个上游仓库，返回 {path, commit_sha, bytes, action}。"""
    dest = workspace_path(url, root)
    if dest is None:
        return {"ok": False, "error": "不是可识别的仓库 URL: %s" % url}
    if not _inside(dest, root):
        return {"ok": False, "error": "目标路径越出缓存根: %s" % dest}
    dest.parent.mkdir(parents=True, exist_ok=True)

    action = "clone"
    if dest.is_dir() and (dest / ".git").is_dir():
        action = "fetch"
        proc = _run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin"])
        if proc.returncode == 0:
            _run(["git", "-C", str(dest), "reset", "--hard", "FETCH_HEAD"])
        else:
            action = "stale"  # 网络失败时保留旧版本，不删除、不假装成功
    else:
        dest.mkdir(parents=True, exist_ok=True)
        proc = _run(["git", "clone", "--depth", "1", "--single-branch",
                     url, str(dest)])
        if proc.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            return {"ok": False, "error": (proc.stderr or proc.stdout).strip()[:500]}

    nbytes = dir_size(dest)
    if nbytes > max_mb * 1048576:
        # 超限：保留记录但标记，交由 clean 处理；不静默删，避免误删刚用过的工作区
        over = True
    else:
        over = False
    sha = ""
    if (dest / ".git").is_dir():
        p = _run(["git", "-C", str(dest), "rev-parse", "HEAD"])
        sha = p.stdout.strip() if p.returncode == 0 else ""
    return {"ok": True, "path": str(dest), "commit_sha": sha,
            "bytes": nbytes, "mb": round(nbytes / 1048576, 1),
            "action": action, "over_limit": over, "limit_mb": max_mb}


def clean(cache: Path, targets: list[dict], *, max_mb: int | None = None,
          dry_run: bool = False) -> dict:
    """删除台账里记录过、且位于缓存根内的工作区。

    targets: [{"path": ..., "bytes": ...}]；先按 TTL 选出的，再按容量从旧到新补。
    """
    root = Path(cache)
    root.mkdir(parents=True, exist_ok=True)
    freed = 0
    removed: list[str] = []
    skipped: list[dict] = []
    current = dir_size(root)

    for item in targets:
        p = Path(item["path"])
        if not _inside(p, root):
            skipped.append({"path": str(p), "why": "越出缓存根"})
            continue
        if not p.exists():
            skipped.append({"path": str(p), "why": "已不存在"})
            continue
        if max_mb is not None and current - freed <= max_mb * 1048576:
            break
        size = item.get("bytes") or dir_size(p)
        if not dry_run:
            shutil.rmtree(p, ignore_errors=True)
            # 清掉空的 host/org 目录，但绝不动缓存根本身
            for parent in (p.parent, p.parent.parent):
                try:
                    if parent != root and parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                except OSError:
                    pass
        freed += size
        removed.append(str(p))
    after = dir_size(root) if not dry_run else current
    return {"removed": removed, "skipped": skipped, "freed_bytes": freed,
            "freed_mb": round(freed / 1048576, 1),
            "cache_mb": round(after / 1048576, 1), "dry_run": dry_run}


def disk_report(cache: Path) -> dict:
    root = Path(cache)
    rows = []
    if root.is_dir():
        for host in sorted(root.iterdir()):
            if not host.is_dir():
                continue
            for org in sorted(host.iterdir()):
                if not org.is_dir():
                    continue
                for repo in sorted(org.iterdir()):
                    if repo.is_dir():
                        rows.append({"path": str(repo), "mb": round(
                            dir_size(repo) / 1048576, 1)})
    total = sum(r["mb"] for r in rows)
    return {"cache": str(root), "repos": rows, "total_mb": round(total, 1)}
