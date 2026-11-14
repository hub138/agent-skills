#!/usr/bin/env bash
# 一键脱敏发布 stock-guardian 到 技能市场
# 用法：
#   export <身份环境变量>='<临时token>'   # 技能市场 token，1小时有效期，用完即弃，绝不写进任何文件
#   export <身份环境变量>='<用户名>'
#   bash scripts/publish.sh [skill-id] [change-message]
# 流程：①从用户数据区实时派生敏感词表（代码/票名/份数/价格）→ ②全目录扫描，
#       命中即列出并拒绝发布（人工脱敏后重跑）→ ③零命中才调 publish_skill.py 打包发布。
# 铁律：本脚本与 skill 目录永不存储 token 与用户数据；发布前扫描是硬闸门，跳过扫描=与泄漏同级事故。
set -uo pipefail
SG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
PUBLISHER="$(dirname "$SG_DIR")/<技能发布工具>/scripts/publish_skill.py"
SKILL_ID="${1:-}"
CHANGE_MSG="${2:-stock-guardian 例行更新（脱敏扫描零命中后发布）}"

[ -n "${<身份环境变量>:-}" ] || { echo "❌ 缺 <身份环境变量> 环境变量（技能市场 token，不落盘）" >&2; exit 1; }
[ -n "${<身份环境变量>:-}" ] || { echo "❌ 缺 <身份环境变量> 环境变量" >&2; exit 1; }
[ -f "$PUBLISHER" ] || { echo "❌ 找不到发布器 $PUBLISHER" >&2; exit 1; }

# ①派生词表：数据区实时提取——代码 + 台账票名 + 账户数字（词表只在临时文件，绝不落 skill 目录）
TMPWL="$(mktemp)"
{
  # 代码：持仓台账/监控配置/机器真相/叙事档案（带市场前缀 + 裸 6 位数字）
  for f in "$SG_HOME"/holdings.conf "$SG_HOME"/watch.conf "$SG_HOME"/MASTER.md "$SG_HOME"/portfolio.md "$SG_HOME"/picks.md "$SG_HOME"/pool.md; do
    [ -f "$f" ] && grep -rhoE '(sh|sz|kq|ks|bj)[0-9]{6}(\.OQ|\.N)?|\b[0-9]{6}\b' "$f" 2>/dev/null
  done
  # 台账/池票名：只取 PICK/POOL 机器行第 4、5 字段——VERDICT 行第 4 字段是"作废/命中"判定词，取之会毒化词表
  awk -F'|' '/^(PICK|POOL)\|/ {print $4; print $5}' "$SG_HOME/picks.md" 2>/dev/null
  awk -F'|' '/^POOL\|/ {print $4; print $5}' "$SG_HOME/pool.md" 2>/dev/null
  # 持仓章节票名（去掉"（代码）"后缀）
  grep -hoE '^## 持仓 [0-9]：.*' "$SG_HOME/portfolio.md" 2>/dev/null | sed 's/.*：//; s/（.*//'
  # 账户数字：MASTER 里的价格（≥2 位小数）与金额/份数（≥5 位整数）；4 位及以下整数多与程序默认参数碰撞，不纳入
  grep -oE '[0-9]+\.[0-9]{2,}' "$SG_HOME/MASTER.md" 2>/dev/null
  grep -oE '\b[0-9]{5,}\b' "$SG_HOME/MASTER.md" 2>/dev/null
} | grep -vE '^\s*$|^[0-9]{1,4}$|^20[0-9]{4}$|^20[0-9]{6}$|^[0-9]\.[0-9]{2}$' | sort -u > "$TMPWL"
WL_COUNT=$(wc -l < "$TMPWL")
[ "$WL_COUNT" -ge 1 ] || { echo "❌ 敏感词表为空——数据区异常，拒绝在无法扫描的情况下发布" >&2; rm -f "$TMPWL"; exit 1; }
echo "📋 派生敏感词 $WL_COUNT 个（代码/票名/账户数字，来自用户数据区实时提取）"

# ②全目录扫描（-F 固定串：词表里的代码/价格元字符不参与正则；覆盖发布包全部文本类型）
echo "🔍 扫描 $SG_DIR ..."
HITS=$(grep -rnFf "$TMPWL" --include='*.md' --include='*.sh' --include='*.js' --include='*.py' --include='*.json' --include='*.conf' --include='*.txt' --include='*.yaml' --include='*.yml' "$SG_DIR" 2>/dev/null)
rm -f "$TMPWL"
if [ -n "$HITS" ]; then
  echo "❌ 脱敏扫描命中 $(echo "$HITS" | wc -l) 处，拒绝发布（先人工脱敏再重跑）：" >&2
  echo "$HITS" | cut -c1-160 >&2
  exit 1
fi
echo "✅ 脱敏扫描零命中"

# ③发布
ARGS=("$SG_DIR")
[ -n "$SKILL_ID" ] && ARGS+=(--skill-id "$SKILL_ID")
ARGS+=(--change-message "$CHANGE_MSG")
python3 "$PUBLISHER" "${ARGS[@]}"
