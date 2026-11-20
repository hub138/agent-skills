#!/bin/bash
# agent-ops radar check-new 双批（8:00/13:00）：pull tech-radar → 新简报入账
cd <skill 安装目录>/tech-radar || exit 1
git pull --ff-only origin master >> data/logs/checknew.log 2>&1
/root/.pyenv/versions/3.12.0/bin/python3 <skill 安装目录>/agent-ops/scripts/radar_cli.py \
  check-new --from-dir <skill 安装目录>/tech-radar >> data/logs/checknew.log 2>&1
