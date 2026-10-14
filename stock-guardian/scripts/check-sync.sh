#!/usr/bin/env bash
# stock-guardian 警报线同步自检：核对 watch.conf 每条规则的价格是否仍出现在 portfolio.md。
# 用途：AI 修改任一处警报线后运行；输出 DRIFT 行 = 两处疑似不同步，须对齐后复跑至 OK。
# 说明：子串匹配是启发式（portfolio 里能找到同数字即算同源），宁可漏报不误报；
#       zone 条件的两个价格都核对。
# 用法：check-sync.sh    （退出码 0=一致/无配置；1=发现不同步）
set -u
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
CONF="${WATCH_CONF:-$SG_HOME/watch.conf}"
PORT="${PORTFOLIO:-$SG_HOME/portfolio.md}"
[ -f "$CONF" ] || { echo "无 $CONF（watchdog 未启用），跳过自检"; exit 0; }
[ -f "$PORT" ] || { echo "缺档案 $PORT，无法核对"; exit 1; }
DRIFT=0; N=0
while IFS='|' read -r tag code cond arg label act || [ -n "${tag:-}" ]; do
  [ "$tag" = "watch" ] || continue
  N=$((N+1)); arg="${arg// /}"; MISS=""
  # pct 规则：阈值在档案"纪律参数"或该票节里有出处即可（如"阈值 2%"），同源要求与其他规则一致
  OLDIFS="$IFS"; IFS=','
  for p in $arg; do grep -qF -- "$p" "$PORT" || MISS="$MISS $p"; done
  IFS="$OLDIFS"
  if [ -n "$MISS" ]; then
    echo "DRIFT：$code $cond $arg（$label）的价格$MISS 未在 portfolio.md 找到，两处疑似不同步"
    DRIFT=1
  fi
done < "$CONF"
if [ "$DRIFT" -eq 0 ]; then echo "OK：watch.conf 共 $N 条规则，价格均能在 portfolio.md 找到（同源）"; fi
exit "$DRIFT"
