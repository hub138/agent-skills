#!/usr/bin/env bash
# stock-guardian 警报线同步自检：核对 watch.conf 每条规则的价格是否仍出现在 portfolio.md。
# 用途：AI 修改任一处警报线后运行；输出 DRIFT 行 = 两处疑似不同步，须对齐后复跑至 OK。
# 说明：子串匹配是启发式（档案里能找到同数字即算同源）。
#      2026-10-29 修：POOL-AUTO 机器块内的线由 pool-watch-sync.js 从 pool.md 生成，
#      其价位只出现在 pool.md 而非 portfolio.md —— 旧版把块内线当人工线核 portfolio，
#      天天报 DRIFT（假警报）等于把校验器变成摆设。现在块内核 pool.md、块外核 portfolio.md。
#       zone 条件的两个价格都核对。
# 用法：check-sync.sh    （退出码 0=一致/无配置；1=发现不同步）
set -u
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
CONF="${WATCH_CONF:-$SG_HOME/watch.conf}"
PORT="${PORTFOLIO:-$SG_HOME/portfolio.md}"
POOL="${POOL_FILE:-$SG_HOME/pool.md}"
ALERTSRC="${ALERTS_FILE:-$SG_HOME/alerts.conf}"
[ -f "$CONF" ] || { echo "无 $CONF（watchdog 未启用），跳过自检"; exit 0; }
[ -f "$PORT" ] || { echo "缺档案 $PORT，无法核对"; exit 1; }
DRIFT=0; N=0; IN_BLOCK=0; NPOOL=0; IN_ALERT=0; NALERT=0
while IFS='|' read -r tag code cond arg label act || [ -n "${tag:-}" ]; do
  case "$tag" in
    "# === POOL-AUTO BEGIN"*) IN_BLOCK=1; continue ;;
    "# === POOL-AUTO END"*) IN_BLOCK=0; continue ;;
    "# === ALERT-AUTO BEGIN"*) IN_ALERT=1; continue ;;
    "# === ALERT-AUTO END"*) IN_ALERT=0; continue ;;
  esac
  [ "$tag" = "watch" ] || continue
  N=$((N+1)); arg="${arg// /}"; MISS=""
  # pct 规则：阈值在档案"纪律参数"或该票节里有出处即可（如"阈值 2%"），同源要求与其他规则一致
  SRC="$PORT"
  if [ "$IN_BLOCK" = "1" ]; then SRC="$POOL"; NPOOL=$((NPOOL+1)); fi
  if [ "$IN_ALERT" = "1" ]; then SRC="$ALERTSRC"; NALERT=$((NALERT+1)); fi
  OLDIFS="$IFS"; IFS=','
  for p in $arg; do grep -qF -- "$p" "$SRC" 2>/dev/null || MISS="$MISS $p"; done
  IFS="$OLDIFS"
  if [ -n "$MISS" ]; then
    if [ "$IN_BLOCK" = "1" ]; then
      echo "DRIFT：$code $cond $arg（$label）的价格$MISS 未在 pool.md 找到，机器块与池不同步（重跑 pool-watch-sync.js）"
    elif [ "$IN_ALERT" = "1" ]; then
      echo "DRIFT：$code $cond $arg（$label）的价格$MISS 未在 alerts.conf 找到，警报块与源不同步（重跑 alerts-sync.js）"
    else
      echo "DRIFT：$code $cond $arg（$label）的价格$MISS 未在 portfolio.md 找到，两处疑似不同步"
    fi
    DRIFT=1
  fi
done < "$CONF"
if [ "$DRIFT" -eq 0 ]; then echo "OK：watch.conf 共 $N 条规则（池块 $NPOOL 条核 pool.md、警报块 $NALERT 条核 alerts.conf、其余核 portfolio.md），全部同源"; fi
exit "$DRIFT"
