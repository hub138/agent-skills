#!/usr/bin/env bash
# 打包前自检：确认 skill 目录里没有混入任何用户数据。
# 用法：bash scripts/selfcheck.sh
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${WATCHDOG_HOME:-$HOME/.codebuddy/watchdog}"
ok=1

echo "skill 目录：$SKILL_DIR"
echo "数据目录：$DATA_DIR（在 skill 之外，天然不会被打包）"
echo ""

# 1. 不该出现的私有文件与目录
for f in jobs.json state logs prompts; do
  # prompts 只允许 templates/ 里有模板；skill 根下不该有 prompts 目录
  if [ "$f" = "prompts" ]; then
    if [ -e "$SKILL_DIR/prompts" ]; then echo "× 根下不该有 prompts 目录（提示词模板在 templates/ 里）"; ok=0; fi
  elif [ -e "$SKILL_DIR/$f" ]; then
    echo "× 发现私有文件/目录：$f"; ok=0
  fi
done

# 2. 不该出现的机器专属硬编码路径
#  （示例里用 ~/ 或占位符；真实路径只该出现在用户的数据目录里）
# --exclude 自己：模式字符串本身就含这些路径字面量，不排除会抓到自己
found="$(grep -rnE --exclude=selfcheck.sh "/root/|/home/[a-z]|/data/|/Users/" "$SKILL_DIR" 2>/dev/null | head -5)"
if [ -n "$found" ]; then
  echo "× 发现机器专属的硬编码路径："
  echo "$found"
  ok=0
fi

# 3. 数据目录确实在 skill 之外
case "$DATA_DIR" in
  "$SKILL_DIR"*) echo "× 数据目录在 skill 里面（$DATA_DIR），打包会连数据一起带走"; ok=0 ;;
  *) echo "√ 数据目录在 skill 之外" ;;
esac

echo ""
if [ "$ok" = "1" ]; then
  echo "√ 自检通过，skill 目录可以整包分享"
else
  echo "× 自检未通过，先处理上面标 × 的项"
  exit 1
fi