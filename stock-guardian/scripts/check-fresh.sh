#!/usr/bin/env bash
# stock-guardian 警报线新鲜度自检：watch.conf 文案份数/股数 vs portfolio.md 同源 + PLAN 行静态化检查。
# 背景（2026-10-19）：某次用户实报份数与定案不同、却只改了档案，watch.conf 文案里旧份数继续跑 3 天，
#   警报推送的全是过期口径；check-sync.sh 只查价格同源、不查份数与新鲜度，本脚本是它的补集。
# 设计：宁可漏报不误报。
#   1) 文案数字：watch.conf 的 action 列里 3 位以上数字+份/股，须能在 portfolio.md 找到同数；找不到=定案旧数，DRIFT。
#   2) PLAN 行静态化：PLAN 是当日 day file 里的预案（watch.sh 每天读当日 day file，天然按日过期），
#      若被粘进 watch.conf 就成了跨日静态快照——配置里出现 PLAN 行即 DRIFT。
# 用法：check-fresh.sh          （退出码 0=新鲜/无配置；1=发现过期）
set -u
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
CONF="${WATCH_CONF:-$SG_HOME/watch.conf}"
PORT="${PORTFOLIO:-$SG_HOME/portfolio.md}"
DRIFT=0

[ -f "$PORT" ] || { echo "缺档案 $PORT，无法核对"; exit 1; }

# ---- 1. watch.conf 文案里的份数/股数与档案同源 ----
if [ -f "$CONF" ]; then
  N=0
  while IFS='|' read -r tag code cond arg label act || [ -n "${tag:-}" ]; do
    [ "$tag" = "watch" ] || continue
    N=$((N+1))
    for lot in $(echo "$act" | grep -oE '[0-9]{3,} ?(份|股)' | tr -d ' 份股'); do
      if ! grep -qF -- "$lot" "$PORT"; then
        echo "DRIFT：$code $cond 文案份数 $lot 未在 portfolio.md 找到——多半是定案旧数，档案改份数时文案没同步"
        DRIFT=1
      fi
    done
  done < "$CONF"
  [ "$DRIFT" -eq 0 ] && echo "OK：watch.conf 共 $N 条规则，文案份数/股数均在 portfolio.md 同源"
else
  echo "无 $CONF（watchdog 未启用），跳过文案核对"
fi

# ---- 2. watch.conf 里不许出现 PLAN 行 ----
if [ -f "$CONF" ] && grep -q "^PLAN|" "$CONF"; then
  echo "DRIFT：watch.conf 含 PLAN 行——PLAN 是当日预案（属于 day file），写进配置会跨日过期推送"
  DRIFT=1
fi

if [ "$DRIFT" -eq 0 ]; then echo "OK：新鲜度全部通过"; fi
exit "$DRIFT"