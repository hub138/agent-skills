#!/usr/bin/env bash
# stock-guardian 跨场景动态档案（day file）：让 isolated 定时会话之间状态可衔接。
# 纯工具层，零用户数据，随 skill 整体分发。
# 背景：每个定时任务跑在独立会话里，10 点画的箱体 11:45 的午间检查默认看不见——
#   day file 让每个场景把要点落档，后继场景读取衔接，watchdog 警报也自动落档，复盘时汇总。
# 文件：$HOME/.stock-guardian/day/YYYY-MM-DD.md（600 权限，自动清理 35 天前旧档案）
# 用法：
#   day-log.sh read [YYYY-MM-DD]        读当天（或指定日期）档案；无档案输出一行说明
#   day-log.sh append "场景名" "要点"    追加一条（自动加 HH:MM 标题；单条超 2000 字符截断）
#   day-log.sh list [N]                 列最近 N 天档案（默认 10，供复盘定位）
#   day-log.sh box <代码> <下沿> <上沿>  记录当日箱体（同代码替换式）
#   day-log.sh plan <代码> "<突破上沿怎么办>" "<跌破下沿怎么办>"  记录当日预案动作（同代码替换式；文本禁竖线|）
#   plan 的两句话在 watchdog 触发该票箱体警报时原样推给用户——用户要看的是"该怎么办"，不是"去翻预案"
set -u
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
DAY_DIR="$SG_HOME/day"
KEEP_DAYS="${KEEP_DAYS:-35}"

cleanup(){ [ -d "$DAY_DIR" ] && find "$DAY_DIR" -name '20*.md' -mtime +"$KEEP_DAYS" -delete 2>/dev/null; return 0; }

case "${1:-}" in
  read)
    D="${2:-$(date +%F)}"
    F="$DAY_DIR/$D.md"
    if [ -f "$F" ]; then cat "$F"; else echo "（$D 无动态档案）"; fi
    ;;
  append)
    SCENE="${2:-}"; BODY="${3:-}"
    [ -n "$SCENE" ] && [ -n "$BODY" ] || { echo "用法：day-log.sh append \"场景名\" \"要点\"（两项都不能空）" >&2; exit 1; }
    mkdir -p "$DAY_DIR" 2>/dev/null && chmod 700 "$DAY_DIR" 2>/dev/null
    F="$DAY_DIR/$(date +%F).md"
    if [ ! -f "$F" ]; then printf '# %s 动态档案\n' "$(date +%F)" >"$F"; chmod 600 "$F" 2>/dev/null; fi
    [ "${#BODY}" -gt 2000 ] && BODY="${BODY:0:2000}……（超长截断）"
    printf '\n## %s %s\n%s\n' "$(date +%H:%M)" "$SCENE" "$BODY" >>"$F"
    cleanup
    echo "已落档 $F（$(date '+%H:%M') $SCENE）"
    ;;
  list)
    N="${2:-10}"
    if [ -d "$DAY_DIR" ] && ls -1t "$DAY_DIR"/20*.md >/dev/null 2>&1; then ls -1t "$DAY_DIR"/20*.md | head -n "$N"; else echo "（尚无动态档案）"; fi
    ;;
  box)
    CODE="${2:-}"; LO="${3:-}"; HI="${4:-}"
    case "$CODE" in sh*|sz*|bj*) ;; *) echo "box：只支持 A股代码（sh/sz/bj 前缀）" >&2; exit 1;; esac
    OK=$(awk -v a="$LO" -v b="$HI" 'BEGIN{print (a+0>0 && b+0>0 && b+0>a+0) ? 1 : 0}')
    [ "$OK" = "1" ] || { echo "box：用法 day-log.sh box sh600000 7.20 7.45（两价为当日箱体下/上沿，须 0<lo<hi）" >&2; exit 1; }
    mkdir -p "$DAY_DIR" 2>/dev/null && chmod 700 "$DAY_DIR" 2>/dev/null
    F="$DAY_DIR/$(date +%F).md"
    if [ ! -f "$F" ]; then printf '# %s 动态档案\n' "$(date +%F)" >"$F"; chmod 600 "$F" 2>/dev/null; fi
    # 同代码旧 BOX 行先删再写（替换而非追加）：watchdog 才不会同时盯新旧两个箱体
    grep -v "^BOX|$CODE|" "$F" >"$F.tmp" 2>/dev/null && mv -f "$F.tmp" "$F"
    printf 'BOX|%s|%s|%s\n' "$CODE" "$LO" "$HI" >>"$F"
    cleanup
    echo "已记录当日箱体 $CODE 下沿 $LO 上沿 $HI（同代码旧箱体已替换；watchdog 将自动盯突破上沿/跌破下沿）"
    ;;
  plan)
    CODE="${2:-}"; UP="${3:-}"; DOWN="${4:-}"
    case "$CODE" in sh*|sz*|bj*) ;; *) echo "plan：只支持 A股代码（sh/sz/bj 前缀）" >&2; exit 1;; esac
    [ -n "$UP" ] && [ -n "$DOWN" ] || { echo "plan：用法 day-log.sh plan sh600000 \"<突破上沿怎么办>\" \"<跌破下沿怎么办>\"（两句都不能空）" >&2; exit 1; }
    case "$UP$DOWN" in *"|"*) echo "plan：动作文本里不要用竖线 | 字符（机器行分隔符）" >&2; exit 1;; esac
    mkdir -p "$DAY_DIR" 2>/dev/null && chmod 700 "$DAY_DIR" 2>/dev/null
    F="$DAY_DIR/$(date +%F).md"
    if [ ! -f "$F" ]; then printf '# %s 动态档案\n' "$(date +%F)" >"$F"; chmod 600 "$F" 2>/dev/null; fi
    # 同代码旧 PLAN 行先删再写（与 box 同语义）：预案每天随箱体重画，昨天的动作不能留到今天
    grep -v "^PLAN|$CODE|" "$F" >"$F.tmp" 2>/dev/null && mv -f "$F.tmp" "$F"
    printf 'PLAN|%s|%s|%s\n' "$CODE" "$UP" "$DOWN" >>"$F"
    cleanup
    echo "已记录当日预案 $CODE：突破上沿→$UP；跌破下沿→$DOWN（watchdog 触发时原样推给用户）"
    ;;
  *)
    echo "用法：day-log.sh read [日期] | append \"场景名\" \"要点\" | box <代码> <下沿> <上沿> | plan <代码> \"<突破动作>\" \"<跌破动作>\" | list [N]"
    echo "档案目录：$DAY_DIR（35 天自动清理；属用户数据，永不进 skill 目录）"
    ;;
esac
