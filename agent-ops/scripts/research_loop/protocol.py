"""project.json 契约加载与校验（方案 3.1 九组）+ 适配器命令执行（3.2）。"""
from __future__ import annotations

import json
import subprocess

from .core_types import digest_obj, read_json

REQUIRED_GROUPS = {
    "identity": ["schema_version", "project_id", "objective_version", "goal"],
    "metrics": ["primary_metric"],
    "data": ["manifest", "version"],
    "evaluator": ["adapter_id"],
    "candidate": ["allowed_paths"],
    "explore": ["categories"],
    "budget": ["max_rounds"],
    "isolation": ["mode"],
    "completion": ["final_gate"],
}

METRIC_KEYS = ["metric_id", "direction", "threshold", "comparison", "unit"]
ISOLATION_MODES = {"full", "limited", "blocked"}


class ProtocolError(ValueError):
    """契约非法，拒绝进入实验。"""


def load_project(path: str) -> dict:
    project = read_json(path)
    errors = validate_project(project)
    if errors:
        raise ProtocolError("; ".join(errors))
    project["_digest"] = digest_obj(
        {k: v for k, v in project.items() if not k.startswith("_")})
    return project


def validate_project(project: dict) -> list:
    errors = []
    if not isinstance(project, dict):
        return ["project.json 顶层必须是对象"]
    for group, keys in REQUIRED_GROUPS.items():
        if group not in project:
            errors.append("缺少契约组: %s" % group)
            continue
        for key in keys:
            if key not in project[group]:
                errors.append("%s 缺少必填字段: %s" % (group, key))
    metrics = project.get("metrics", {})
    pm = metrics.get("primary_metric")
    if isinstance(pm, dict):
        for k in METRIC_KEYS:
            if k not in pm:
                errors.append("primary_metric 缺少: %s" % k)
        if pm.get("comparison") not in ("gt", "gte"):
            errors.append("comparison 只允许 gt/gte，禁止模糊口径")
        if pm.get("direction") not in ("maximize", "minimize"):
            errors.append("direction 只允许 maximize/minimize")
    iso = project.get("isolation", {})
    if iso.get("mode") not in ISOLATION_MODES:
        errors.append("isolation.mode 必须是 %s" % sorted(ISOLATION_MODES))
    cand = project.get("candidate", {})
    paths = cand.get("allowed_paths")
    if not isinstance(paths, list) or not paths:
        errors.append("candidate.allowed_paths 必须是非空列表（候选改动边界）")
    if "guard_metrics" not in metrics:
        errors.append("metrics.guard_metrics 缺少（不可退化门槛，方案 5.3）")
    if "dev_batch_size" not in project.get("explore", {}):
        errors.append("explore.dev_batch_size 缺少（方案 6.2 对照批大小）")
    if "stall_limit" not in project.get("explore", {}):
        errors.append("explore.stall_limit 缺少（连续无净收益换向阈值）")
    return errors


def run_adapter_cmd(argv: list, cwd: str | None = None, timeout: int = 1800) -> dict:
    """适配器命令执行：argv 数组（方案 3.2，不拼 shell）。"""
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise ProtocolError("适配器命令必须是 argv 字符串数组")
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)
    return {"rc": proc.returncode, "stdout": proc.stdout,
            "stderr": proc.stderr, "argv": argv}
