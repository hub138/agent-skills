#!/usr/bin/env python3
"""定位并加载 agent_foundation（用户的经验沉淀库，**只读**）。

为什么需要桥接层：agent-ops 是 skill，会被拷到 4 个安装副本；agent_foundation
是可 import 的库，住在 agent-skills 仓库里。两边不一定在同一目录，安装副本里
甚至没有它。所以这里只做「尽力定位 + 缺库返回 None」，**调用方必须写手写回退**
——本 skill 在任何机器上都要能跑，桥接是增强，不是依赖。

定位顺序：
  1. 环境变量 ``AGENT_FOUNDATION_SRC``（指向 ``src/`` 目录）；
  2. 内部权威源布局：``../agent-skills/agent_foundation/src``；
  3. 公开仓库布局：``../agent_foundation/src``（agent-skills 仓库里两者同级）。

红线：本模块绝不写 agent_foundation 的任何文件（曾误覆盖，靠 git checkout 才恢复）。
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


def src_dir() -> Path | None:
    env = os.environ.get("AGENT_FOUNDATION_SRC")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(SKILL_ROOT.parent / "agent-skills" / "agent_foundation" / "src")
    candidates.append(SKILL_ROOT.parent / "agent_foundation" / "src")
    for c in candidates:
        if (c / "agent_foundation").is_dir():
            return c
    return None


def load(name: str):
    """import agent_foundation 的子模块；不可用时返回 None（调用方走回退）。"""
    src = src_dir()
    if src is None:
        return None
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        return importlib.import_module(name)
    except Exception:
        return None
