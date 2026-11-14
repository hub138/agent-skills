"""提交前的风险闸门。

抽象自开源发布的三道警戒线与交付分支的准入准出检查：
改动逐条过规则，任一阻断级命中即拦截；命中必须携带可复查的位置；
闸门自身的定义文件通过豁免清单排除，不因自指而误报。
拦截不是失败终点，携带阻断原因交由调用方处置。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath


class RiskLevel(StrEnum):
    BLOCK = "block"
    ALLOW = "allow"


@dataclass(frozen=True)
class Finding:
    rule: str
    level: RiskLevel
    location: str
    detail: str


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: str
    level: RiskLevel


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return PurePosixPath(path.relative_to(root).as_posix()).parts
    except ValueError:
        return PurePosixPath(path.as_posix()).parts


def scan_paths(
    root: Path,
    rules: list[Rule],
    forbidden_substrings: list[str] | None = None,
    *,
    exempt_paths: list[Path] | None = None,
    exempt_parts: list[str] | None = None,
) -> list[Finding]:
    """扫描目录下全部文本文件，产出命中 Findings。

    规则按字面量精确匹配；禁词按大小写不敏感匹配。
    exempt_paths 中的文件（按绝对路径比对）整体跳过，用于闸门自身自指排除。
    exempt_parts 中的目录名（按路径部件比对）整体跳过，用于 gitignore 的中间产物目录。
    文本按行读取，无法解码的文件（二进制产物）整体跳过。
    根不是目录时抛出 NotADirectoryError 快速失败，不静默返回空集。
    """
    findings: list[Finding] = []
    lowered_substrings = [token.lower() for token in (forbidden_substrings or [])]
    exempted = {path.resolve() for path in (exempt_paths or [])}
    skipped_parts = set(exempt_parts or [])
    if not root.is_dir():
        raise NotADirectoryError(f"scan_paths 的扫描根必须是目录，收到: {root}")
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.resolve() in exempted:
            continue
        if skipped_parts & set(path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        relative = "/".join(_relative_parts(path, root))
        for number, line in enumerate(lines, start=1):
            for rule in rules:
                if rule.pattern in line:
                    findings.append(
                        Finding(
                            rule=rule.name,
                            level=rule.level,
                            location=f"{relative}:{number}",
                            detail=f"matched rule literal: {rule.pattern}",
                        )
                    )
            lowered_line = line.lower()
            for token in lowered_substrings:
                if token in lowered_line:
                    findings.append(
                        Finding(
                            rule="forbidden_substring",
                            level=RiskLevel.BLOCK,
                            location=f"{relative}:{number}",
                            detail=f"contains forbidden token: {token}",
                        )
                    )
    return findings


def adjudicate(findings: list[Finding]) -> bool:
    """有任一阻断级命中返回 False（禁止通过），否则 True。"""
    return all(finding.level is not RiskLevel.BLOCK for finding in findings)
