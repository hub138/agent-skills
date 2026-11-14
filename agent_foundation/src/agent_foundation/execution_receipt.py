"""执行回执：把一条命令结果绑定到它实际执行的源树、入口与输出字节。

抽象自上游回移植的执行证明内核：回执只做溯源不做语义判定——绑定
源树根与检出修订、入口描述的规范化哈希、退出状态与超时标志、输出
流内容的字节级摘要（哈希读原始字节而非解码文本，终端控制字节不因
换行转换而改变摘要）。校验在隔离环境仍存活时进行，输出归档后可用
重定位指针指向归档副本而不改变原摘要，后续验证以「归档件仍承载同
样字节」证明回执有效。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

RECEIPT_CONTRACT = "execution_receipt_v1"


def sha256_text(value: object) -> str:
    """文本规范化摘要：None 与空串同形，编码错误用替换符兜底。"""
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def sha256_file_or_text(path: str | Path, fallback: object) -> str:
    """哈希命令产物的原始字节；产物不可读时退回文本摘要。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return sha256_text(fallback)


def _git_head(worktree: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def issue_receipt(
    *,
    worktree: str | Path,
    cwd: str | Path,
    entrypoint: dict[str, Any],
    exit_code: int | None,
    timed_out: bool,
    stdout: object = "",
    stderr: object = "",
    stdout_path: str | Path | None = None,
    stderr_path: str | Path | None = None,
) -> dict[str, Any]:
    """签发一张执行回执：只证来源与字节，不判定观察是否证明结论。"""
    root = Path(worktree).resolve()
    resolved_cwd = Path(cwd).resolve()
    try:
        relative_cwd = resolved_cwd.relative_to(root).as_posix() or "."
    except ValueError as exc:
        raise ValueError("执行目录越出隔离源树") from exc
    entrypoint_payload = json.dumps(
        entrypoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return {
        "contract": RECEIPT_CONTRACT,
        "source_root": str(root),
        "source_revision": _git_head(root),
        "cwd": relative_cwd,
        "entrypoint_sha256": sha256_text(entrypoint_payload),
        "exit_code": exit_code,
        "timed_out": bool(timed_out),
        "stdout_sha256": sha256_file_or_text(stdout_path, stdout) if stdout_path else sha256_text(stdout),
        "stderr_sha256": sha256_file_or_text(stderr_path, stderr) if stderr_path else sha256_text(stderr),
        "stdout_path": str(stdout_path or ""),
        "stderr_path": str(stderr_path or ""),
    }


def check_receipt(
    receipt: object,
    *,
    worktree: str | Path,
    entrypoint: dict[str, Any],
    final: dict[str, Any],
) -> str:
    """校验回执与最终重跑的一致性，返回不匹配原因，空串表示通过。

    只核溯源五要素：协议版本、源树、入口、退出状态与流字节；不判定
    日志观察是否证明业务结论。
    """
    if not isinstance(receipt, dict):
        return "最终重跑缺少执行回执"
    if receipt.get("contract") != RECEIPT_CONTRACT:
        return "执行回执协议版本不受支持"
    if str(receipt.get("source_root") or "") != str(Path(worktree).resolve()):
        return "执行回执源树不一致"
    cwd = str(receipt.get("cwd") or "")
    if not cwd or Path(cwd).is_absolute() or ".." in Path(cwd).parts:
        return "执行回执目录无效"
    expected_entrypoint = sha256_text(json.dumps(
        entrypoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ))
    if receipt.get("entrypoint_sha256") != expected_entrypoint:
        return "执行回执未绑定当前入口"
    if receipt.get("exit_code") != final.get("exit_code"):
        return "执行回执退出状态不一致"
    if bool(receipt.get("timed_out")) != bool(final.get("timed_out")):
        return "执行回执超时状态不一致"
    for stream in ("stdout", "stderr"):
        path = str(final.get(f"{stream}_path") or "")
        if not path or str(receipt.get(f"{stream}_path") or "") != path:
            return f"执行回执 {stream} 路径不一致"
        try:
            content = Path(path).read_bytes()
        except OSError:
            return f"{stream} 日志不可读取"
        if receipt.get(f"{stream}_sha256") != hashlib.sha256(content).hexdigest():
            return f"执行回执 {stream} 内容不一致"
    return ""


def relocate_receipt(
    receipt: object,
    *,
    stdout_path: str | Path,
    stderr_path: str | Path,
) -> dict[str, Any]:
    """把回执指向归档副本而不改变内容摘要：先拷贝后重定位，摘要保持原值。"""
    if not isinstance(receipt, dict):
        return {}
    return {
        **receipt,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
