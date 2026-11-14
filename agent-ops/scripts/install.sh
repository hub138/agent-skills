#!/usr/bin/env bash
# 初始化：建好数据目录、放一份配置模板、装好 crontab。
# 用法：bash install.sh
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${WATCHDOG_HOME:-$HOME/.codebuddy/watchdog}"

mkdir -p "$HOME_DIR/prompts" "$HOME_DIR/state" "$HOME_DIR/logs"
echo "数据目录：$HOME_DIR"
echo ""

# 配置已存在就不覆盖，避免把用户填好的任务冲掉
fresh=0
if [ -f "$HOME_DIR/jobs.json" ]; then
  echo "√ jobs.json 已存在，保持不动：$HOME_DIR/jobs.json"
else
  cp "$SKILL_DIR/templates/jobs.example.json" "$HOME_DIR/jobs.json"
  fresh=1
  echo "√ 已从模板生成 jobs.json：$HOME_DIR/jobs.json"
fi
if [ ! -f "$HOME_DIR/prompts/example.md" ]; then
  cp "$SKILL_DIR/templates/example.md" "$HOME_DIR/prompts/example.md"
fi

echo ""
echo "接下来按顺序做四步："
echo ""
echo "  1. 先手动跑一次任务，把会话固定下来（--port 0 必须加）："
echo "       cd 你的项目目录 && codebuddy -p --port 0 --session-id 任务名 \"任务描述\""
echo ""
echo "  2. 填配置 $HOME_DIR/jobs.json，必填两样："
echo "       session_id = 第 1 步起的名字"
echo "       prompts    = 任务指令（最关键：要求 Agent 每步把进度写回文件）"
echo "     不会填就直接跟 AI 说：帮我把 jobs.json 填好，任务是……"
echo ""
echo "  3. 装定时检查："
echo "       bash $SKILL_DIR/scripts/watchdog.sh install-cron"
echo ""
echo "  4. 验证："
echo "       bash $SKILL_DIR/scripts/watchdog.sh status"
echo ""
if [ "$fresh" = "1" ]; then
  echo "提示：配置里 enabled 目前是 false，填好 session_id 后记得改成 true。"
fi