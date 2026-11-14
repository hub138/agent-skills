"""结构化输出的三级恢复协议。

抽象自批量工作台对 AI 子进程输出流的治理：最外层期望标准流里的
JSON 行；流没给出时，从普通文本里找回包裹在代码块中的 JSON 对象；
仍取不到才判失败。三级逐级降级，每级都有明确的输入形态，
失败时携带已观察到的原始文本供上游诊断。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from .content import extract_json_object


class RecoveryLevel(StrEnum):
    STREAM = "stream"
    EMBEDDED = "embedded"
    FAILED = "failed"


@dataclass
class ParsedOutput:
    level: RecoveryLevel
    payload: dict[str, object] | list[object] | None = None
    raw_text: str | None = None


def parse_agent_output(lines: list[str]) -> ParsedOutput:
    """逐行取流式 JSON 行，命中即返回 stream 级结果。

    全部行都不是 JSON 时，把残余文本合并后尝试提取嵌入的 JSON
    对象或数组，命中为 embedded 级；仍取不到返回 failed 并附原文。
    """
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(("data:", "{", "[")):
            continue
        if stripped.startswith("data:"):
            stripped = stripped[len("data:"):].strip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        return ParsedOutput(level=RecoveryLevel.STREAM, payload=payload)
    combined = "\n".join(lines)
    embedded = extract_json_object(combined)
    if embedded is not None:
        return ParsedOutput(level=RecoveryLevel.EMBEDDED, payload=embedded, raw_text=combined)
    return ParsedOutput(level=RecoveryLevel.FAILED, raw_text=combined)
