#!/usr/bin/env bash
# 依赖预检（初始化第 0 步 + 环境诊断共用）：一键体检本 skill 的全部依赖。
# 分两级：必需（缺失 FAIL，exit 1）/ 建议（缺失 WARN，不拦）。
# 行情双源（2026-10-15）：westock-data 缺席时自动降级公开源（qt.gtimg.cn，A股/港股/美股可用），
#         故 westock-data 降为建议级（缺了仍可初始化，但 fx/日韩/新闻/公告/K线不可用）；
#         node 降为建议级（westock-data 在场才需要；公开源适配器纯 bash+curl+awk）。
# 检测项：curl+awk（必需：公开源与通知）、westock-data（建议：全字段行情源）、
#         westock-tool（建议：荐股/筛选，纯监控可缺）、node≥18（建议：westock 系依赖）、
#         timeout / flock（建议，cron watchdog 行）。
# 用法：bash check-deps.sh ；路径可用环境变量 WESTOCK / WESTOCK_TOOL 覆盖。
set -u

# cron/受限环境 PATH 兜底（与 watch.sh 同款）
PATH="$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"  # scripts -> stock-guardian -> skills 根

WESTOCK="${WESTOCK:-$SKILLS_DIR/westock-data/scripts/index.js}"
WESTOCK_TOOL="${WESTOCK_TOOL:-$SKILLS_DIR/westock-tool/scripts/index.js}"

fail=0

# --- 建议：westock-data（全字段行情源；缺席自动降级公开源，A股/港股/美股可用）---
if [ -f "$WESTOCK" ]; then
  echo "✅ westock-data：$WESTOCK（行情主源，字段全）"
else
  echo "⚠️ westock-data 缺失——将降级走公开源（qt.gtimg.cn）：A股/港股/美股可用，汇率/日韩/新闻/公告/K线不可用"
  echo "   修复：把 westock-data skill 装到 skills 目录（与 stock-guardian 同级），或设环境变量 WESTOCK 指向其 scripts/index.js"
fi

# --- 荐股/筛选必需：westock-tool（纯监控可缺，不拦）---
if [ -f "$WESTOCK_TOOL" ]; then
  echo "✅ westock-tool：$WESTOCK_TOOL"
else
  echo "⚠️ westock-tool 缺失（荐股/筛选场景必需；只用监控/警报可不装）——预期路径 $WESTOCK_TOOL"
  echo "   修复：装 westock-tool skill，或设环境变量 WESTOCK_TOOL 指向其 scripts/index.js"
fi

# --- 建议：node ≥ 18（westock-data / westock-tool 依赖；公开源降级模式不需要）---
if command -v node >/dev/null 2>&1; then
  node_ver="$(node -v 2>/dev/null | tr -d 'v' | cut -d. -f1)"
  case "$node_ver" in
    ""|*[!0-9]*)
      echo "⚠️ node 无法获取版本（$(command -v node)）——westock 系不可用，将走公开源降级" ;;
    *)
      if [ "$node_ver" -lt 18 ]; then
        echo "⚠️ node v$node_ver 版本过低（westock 系需 ≥18）——westock 系不可用，将走公开源降级"
      else
        echo "✅ node v$node_ver（$(command -v node)）"
      fi
      ;;
  esac
else
  echo "⚠️ node 未安装——westock-data/westock-tool 不可用；公开源降级模式（bash+curl）不受影响"
fi

# --- 必需：awk（watchdog 行情解析）---
if command -v awk >/dev/null 2>&1; then
  echo "✅ awk（$(command -v awk)）"
else
  echo "❌ awk 未安装（必需：分钟级 watchdog 依赖）"
  fail=1
fi

# --- 必需：curl（公开源行情 + 通知发送器共用）---
if command -v curl >/dev/null 2>&1; then
  echo "✅ curl（$(command -v curl)）"
else
  echo "❌ curl 未安装（必需：公开源行情与 notify-webhook.sh 都依赖）"
  fail=1
fi

# --- 建议：timeout / flock（cron watchdog 行）---
command -v timeout >/dev/null 2>&1 || echo "⚠️ timeout 未安装（建议：cron watchdog 行用它限时防卡）"
command -v flock  >/dev/null 2>&1 || echo "⚠️ flock 未安装（建议：cron watchdog 行用它防重叠）"

echo "---"
if [ "$fail" -eq 0 ]; then
  echo "OK：必需依赖全部在位（⚠️ 项为建议级，缺了不拦初始化）"
  exit 0
else
  echo "FAIL：必需依赖缺失——按上方指引修复后重跑本脚本，再开始初始化"
  exit 1
fi
