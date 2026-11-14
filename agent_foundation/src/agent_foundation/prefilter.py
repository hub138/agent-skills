"""廉价可证明预过滤：把免费可验证的判定从昂贵评审前移，证据可复查。

抽象自上游回移植的提交预过滤内核：纯文档、纯构建配置、目标分支
不存在的源文件、依赖清单版本升级携带的修复，这些判定只靠文件清单
与只读查询就能做出，不需要语义评审；与语义判断不同，每个判定都能
展示理由并复查。预过滤不删记录：被过滤的条目只是本轮不送审，理由
写进结果，记录保留以便关闭过滤器后复审。证据不足时不过滤（未知
不裁决），读取失败一律放行，静默丢行是错误。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

#: 自身不承载生产变更的目录。
_NON_SRC_RE = re.compile(
    r"(^|/)(tests?|testing|docs?|doc|website|examples?|benchmarks?|"
    r"ci|\.github|\.gitlab|cmake|debian|docker|build)($|/)",
    re.IGNORECASE,
)

#: 自身不承载生产变更的文件名。
_NON_SRC_FILE_RE = re.compile(
    r"(\.md|\.rst|\.txt|CHANGELOG|NEWS|LICENSE|NOTICE|AUTHORS|"
    r"\.gitignore|\.yml|\.yaml|\.xml)$",
    re.IGNORECASE,
)

#: 可承载生产变更的源码扩展名。
_SRC_EXT_RE = re.compile(
    r"\.(c|cc|cpp|cxx|h|hpp|hh|hxx|java|scala|py|go|rs|js|ts|sh|sql|proto|thrift)$",
    re.IGNORECASE,
)

#: 依赖清单：清单内的版本升级本身就是生产变更（修复在被升级的组件里），
#: 按「仅构建文件」过滤会静默丢掉整类案例。
_DEPENDENCY_MANIFEST_RE = re.compile(
    r"(?:^|/)(?:pom\.xml|build\.gradle(?:\.kts)?|build\.sbt|"
    r"package(?:-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|"
    r"go\.(?:mod|sum)|Cargo\.(?:toml|lock)|requirements[^/]*\.txt|setup\.py|"
    r"pyproject\.toml|Gemfile(?:\.lock)?|composer\.(?:json|lock))$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PrefilterVerdict:
    """一条预过滤判定：放行与否、机器可读原因、供人工复查的说明。"""

    send_to_review: bool
    reason: str
    detail: str


def source_files(files: list[str]) -> list[str]:
    """返回可能承载生产变更的路径清单。"""
    out: list[str] = []
    for path in files:
        text = str(path or "").strip()
        if not text:
            continue
        if _NON_SRC_RE.search(text) or _NON_SRC_FILE_RE.search(text):
            continue
        if _SRC_EXT_RE.search(text):
            out.append(text)
    return out


def dependency_manifest_files(files: list[str]) -> list[str]:
    """返回变更中的依赖清单路径，其升级携带真实修复。"""
    return [
        str(path or "").strip()
        for path in files
        if _DEPENDENCY_MANIFEST_RE.search(str(path or "").strip())
    ]


def prefilter(
    *,
    files: list[str],
    target_has_any: Callable[[list[str]], bool] | None = None,
) -> PrefilterVerdict:
    """对一次变更做免费判定：是否值得送昂贵评审。

    target_has_any 注入「目标分支是否存在任一变更源文件」的只读查询；
    未注入或查询无证据时放行（未知不裁决）。
    """
    src = source_files(files)
    manifests = dependency_manifest_files(files)

    if not src and manifests:
        return PrefilterVerdict(True, "dependency_bump", "纯依赖清单变更，升级携带修复")
    if not src:
        return PrefilterVerdict(False, "no_source_change", "变更不含任何可承载生产修改的文件")

    if target_has_any is not None and not target_has_any(src):
        return PrefilterVerdict(False, "source_absent", "变更的源文件在目标分支全部不存在")

    return PrefilterVerdict(True, "review", "存在待评审的源码变更")
