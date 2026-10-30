#!/usr/bin/env bash
# 主题跟踪队列（2026-10-29 立：用户"是不是前两天或者昨天要持续观察"）
# 雷达标「未命中监控宇宙」的主题，从此不再是一次性情报：add 进队列 → 每个交易日 tick → 3 个交易日内 close。
# 存储：$SG_HOME/themes.md（THEME 行 = 队列，THEME_LOG 行 = 每日进展，THEME_CLOSE 行 = 闭环留档）
# 用法：
#   theme-track.sh add <主题> <链条> "<证据>" ["候选载体（逗号分隔）"]
#   theme-track.sh tick <主题> "<今日进展>"            每个交易日至少一次，哪怕写"无新进展"
#   theme-track.sh due                                 只列今天还没 tick / 已超期的（盘前先跑这个）
#   theme-track.sh ls                                  全队列
#   theme-track.sh close <主题> <已覆盖|不参与> "<理由>"
set -u
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
F="$SG_HOME/themes.md"
TODAY="$(date +%F)"
LIMIT_DAYS=3   # 3 个自然日近似 3 个交易日（保守：宁可早提醒）

die() { echo "✗ $*" >&2; exit 1; }
usage() { sed -n '2,12p' "$0" | grep -E '^# ' | sed 's/^# \{0,1\}//'; }
v_text() { echo "$1" | grep -q '|' && die "文本字段禁竖线：$1"; }
# 写入必须检查成败：首版在目录不存在时静默失败却照样打印"已入队"（假报成功）
append() { printf '%s\n' "$1" >> "$F" || die "写入 $F 失败：$1"; }
DIR="$(dirname "$F")"
[ -d "$DIR" ] || mkdir -p "$DIR" || die "无法创建目录 $DIR"
[ -f "$F" ] || : > "$F" || die "无法创建 $F"

name_of() { awk -F'|' -v n="$1" '/^THEME\|/{ if ($2==n && $6=="active") print }' "$F"; }
days_between() { # 自然日差（$1 早，$2 晚）
  python3 - "$1" "$2" <<'EOF'
import sys, datetime
a = datetime.date.fromisoformat(sys.argv[1]); b = datetime.date.fromisoformat(sys.argv[2])
print((b - a).days)
EOF
}
wd_between() { # 交易日数（跳过周六日；避免周一把周五的 tick 误报成"未更新"）
  python3 - "$1" "$2" <<'EOF'
import sys, datetime
a = datetime.date.fromisoformat(sys.argv[1]); b = datetime.date.fromisoformat(sys.argv[2])
d, n = a, 0
while d < b:
    d += datetime.timedelta(days=1)
    if d.weekday() < 5:
        n += 1
print(n)
EOF
}

CMD="${1:-}"; shift 2>/dev/null || true
case "$CMD" in
  add)
    N="${1:-}"; CH="${2:-}"; EV="${3:-}"; CAND="${4:-}"; D0="${5:-$TODAY}"
    [ -n "$N" ] && [ -n "$CH" ] && [ -n "$EV" ] || die "用法：theme-track.sh add <主题> <链条> \"<证据>\" [\"候选载体\"] [起始日 YYYY-MM-DD]"
    echo "$D0" | grep -qE '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$' || die "起始日格式应为 YYYY-MM-DD：$D0"
    v_text "$N"; v_text "$CH"; v_text "$EV"; v_text "$CAND"
    [ -z "$(name_of "$N")" ] || die "主题「$N」已在队列——要更新请用 tick，要收尾请用 close"
    grep -q "^THEME_CLOSE|$N|" "$F" && die "主题「$N」已闭环过（见 THEME_CLOSE 行），换名或先删旧记录"
    append "$(printf 'THEME|%s|%s|%s|%s|active|%s|%s' "$N" "$CH" "$D0" "$TODAY" "$EV" "$CAND")"
    echo "已入队主题「$N」（链条 $CH，起始 $D0，今日 tick 计时起算）——规矩：每个交易日 tick，${LIMIT_DAYS} 个交易日内 close"
    ;;
  tick)
    N="${1:-}"; PR="${2:-}"
    [ -n "$N" ] && [ -n "$PR" ] || die "用法：theme-track.sh tick <主题> \"<今日进展>\""
    v_text "$PR"
    L="$(name_of "$N")"; [ -n "$L" ] || die "队列里没有活跃主题「$N」"
    D0=$(printf '%s' "$L" | awk -F'|' '{print $4}')
    append "$(printf 'THEME_LOG|%s|%s|%s' "$N" "$TODAY" "$PR")"
    TMP="$F.tmp.$$"
    awk -F'|' -v n="$N" -v d="$TODAY" 'BEGIN{OFS="|"} $1=="THEME" && $2==n && $6=="active" { $5=d; print; next } { print }' "$F" > "$TMP" || die "写临时文件失败"
    mv "$TMP" "$F" || die "替换 $F 失败"
    D=$(days_between "$D0" "$TODAY")
    if [ "$D" -ge "$LIMIT_DAYS" ]; then
      echo "已 tick「$N」（起始 $D0，第 $((D+1)) 天）—— ⚠ 已到 ${LIMIT_DAYS} 日闭环线：今天必须 close（转池行或明确不参与）"
    else
      echo "已 tick「$N」（起始 $D0，第 $((D+1)) 天，距闭环线 $((LIMIT_DAYS-D)) 日）"
    fi
    ;;
  close)
    N="${1:-}"; ST="${2:-}"; WHY="${3:-}"
    case "$ST" in 已覆盖|不参与) ;; *) die "终态二选一：已覆盖（已变成挂线/池行）/ 不参与";; esac
    v_text "$WHY"; [ -n "$N" ] || die "用法：theme-track.sh close <主题> <已覆盖|不参与> \"<理由>\""
    L="$(name_of "$N")"; [ -n "$L" ] || die "队列里没有活跃主题「$N」"
    append "$(printf 'THEME_CLOSE|%s|%s|%s|%s' "$N" "$ST" "$TODAY" "$WHY")"
    sed -i "/^THEME|$N|\(.*\)|active|/d" "$F"
    echo "已闭环「$N」：$ST（$WHY）"
    ;;
  ls|due)
    [ "$CMD" = "due" ] && echo "## 主题跟踪 · 待动作（$(date '+%F %T')）"
    N=0
    while IFS='|' read -r TAG T CH D0 D1 ST EV CAND; do
      [ "$TAG" = "THEME" ] || continue
      [ "$ST" = "active" ] || continue
      AGE=$(wd_between "$D0" "$TODAY"); STALE=$(wd_between "$D1" "$TODAY")
      MARK=""
      [ "$STALE" -ge 1 ] && MARK="$MARK ⚠今日未tick"
      # 起始后从未处置：这正是"前两天就该持续观察"却没人管的形态，必须立刻可见（首版把它隐藏在 due 里）
      [ "$D1" = "$D0" ] && [ "$AGE" -ge 1 ] && MARK="$MARK ⚠入队后未处置"
      # 起始日就已欠账（主题出现好几天才被登记）——不许藏，due 里也要露出来
      [ "$D1" = "$TODAY" ] && [ "$AGE" -ge 1 ] && MARK="$MARK ⚠起始后${AGE}交易日才补登记"
      [ "$AGE" -ge "$LIMIT_DAYS" ] && MARK="$MARK ⚠超${LIMIT_DAYS}交易日未闭环"
      if [ "$CMD" = "due" ] && [ -z "$MARK" ]; then continue; fi
      N=$((N+1))
      printf '%-14s %-12s 起始%s（已挂%d交易日）｜最后tick %s｜载体：%s%s\n' "$T" "$CH" "$D0" "$AGE" "$D1" "${CAND:-未登记}" "$MARK"
    done < "$F"
    if [ "$N" -eq 0 ]; then
      if [ "$CMD" = "due" ]; then echo "（无待动作主题——队列干净）"; else echo "（队列空）"; fi
    fi
    ;;
  *) usage; [ -n "$CMD" ] && die "未知子命令 $CMD"; exit 1;;
esac
