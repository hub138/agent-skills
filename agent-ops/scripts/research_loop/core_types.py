"""公共底座：状态枚举（方案 9.1 四层分离）、摘要、原子写入。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

# 执行状态
EXEC_QUEUED = "queued"; EXEC_RUNNING = "running"; EXEC_RETRY_WAIT = "retry_wait"
EXEC_SUCCEEDED = "succeeded"; EXEC_FAILED = "failed"; EXEC_BLOCKED = "blocked"
EXEC_CANCELED = "canceled"
EXEC_STATUSES = {EXEC_QUEUED, EXEC_RUNNING, EXEC_RETRY_WAIT, EXEC_SUCCEEDED,
                 EXEC_FAILED, EXEC_BLOCKED, EXEC_CANCELED}

# 证据状态
EV_PENDING = "pending"; EV_VALID = "valid"; EV_INVALID = "invalid"
EV_INCOMPLETE = "incomplete"
EV_STATUSES = {EV_PENDING, EV_VALID, EV_INVALID, EV_INCOMPLETE}

# 实验状态
TRIAL_UNTESTED = "untested"; TRIAL_BENEFICIAL = "beneficial"
TRIAL_NO_GAIN = "no_gain"; TRIAL_REGRESSION = "regression"
TRIAL_INCONCLUSIVE = "inconclusive"
TRIAL_STATUSES = {TRIAL_UNTESTED, TRIAL_BENEFICIAL, TRIAL_NO_GAIN,
                  TRIAL_REGRESSION, TRIAL_INCONCLUSIVE}

# 候选状态（晋级由机器门禁推进，模型不能直接写 accepted）
CAND_PROPOSED = "proposed"; CAND_APPROVED = "approved"
CAND_IN_TRIAL = "applied_in_trial"; CAND_SCREENING = "screening"
CAND_VERIFICATION = "verification"; CAND_EXPANDED = "expanded"
CAND_FINAL_LOCKED = "final_locked"; CAND_ACCEPTED = "accepted"
CAND_REJECTED = "rejected"; CAND_ROLLED_BACK = "rolled_back"
CAND_STATUSES = {CAND_PROPOSED, CAND_APPROVED, CAND_IN_TRIAL, CAND_SCREENING,
                 CAND_VERIFICATION, CAND_EXPANDED, CAND_FINAL_LOCKED,
                 CAND_ACCEPTED, CAND_REJECTED, CAND_ROLLED_BACK}

# 探索类别（方案 6.1 三轴）
KIND_KNOWLEDGE = "knowledge_context"; KIND_PROMPT = "prompt_engineering"
KIND_CASE = "case_correctness"; KINDS = {KIND_KNOWLEDGE, KIND_PROMPT, KIND_CASE}

# 标签等级
GRADE_PRECISE = "precise"; GRADE_COARSE = "coarse"
GRADE_DISPUTED = "disputed"; GRADE_UNKNOWN = "unknown"

SCHEMA_VERSION = "1"


def now_ts() -> float:
    return time.time()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_obj(obj) -> str:
    return sha256_text(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def atomic_write_text(path: str, text: str) -> None:
    """临时写入 + 校验后原子替换（方案 9.3）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(p))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, obj) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def project_home(home, project_id: str) -> Path:
    root = home or os.environ.get("RESEARCH_LOOP_HOME") or os.path.join(
        str(Path.home()), ".research_loop")
    p = Path(root) / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p
