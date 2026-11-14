#!/usr/bin/env python3
"""已升级并改名为 manager.py——管理者（任务主人的化身）。

本文件保留为兼容 shim：旧 cron（supervise_jobs/agents 引用）与用户习惯不受影响。
新代码请 import manager。
"""
from manager import *  # noqa: F401,F403
from manager import main, run_once, build_snapshot, apply, PROMPT  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
