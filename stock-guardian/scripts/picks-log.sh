#!/usr/bin/env bash
# stock-guardian 荐股台账（picks.md）：推荐与验证的长期记录，独立于用户持仓档案。
# 纯工具层，零用户数据，随 skill 整体分发。
# 定位：市场荐股的"实验室记录本"——每次推荐落一行 PICK，验证后落 VERDICT 改判归因，
#   周五复盘落 INSIGHT 沉淀思路修正。与 day file（35 天清理）相反，picks.md 长期保留，
#   因为推荐思路的扭转靠跨周比对（连续错的方向要暂停，连续对的方向要延续），35 天不够。
# 文件：$HOME/.stock-guardian/picks.md（600 权限；属用户数据，永不进 skill 目录）
# 机器行格式（| 为分隔符，文本字段内禁用竖线）：
#   PICK|<id>|<日期YYYY-MM-DD>|<代码>|<名称>|<方向>|<触发价>|<作废价>|<有效期至>|<理由一句话>[|事件YYYYMMDD-N]
#     末段可选：推荐理由直接依赖某事件时带 NEWS 事件ID（事件驱动型，事件已落地则有效期缩至 2 个交易日）
#   VERDICT|<id>|<日期YYYY-MM-DD>|<状态>|<一句话>
#     状态四态：命中/作废/超时/进行中；归因四选一：理由兑现/理由未兑现但价格到了/理由与价格双错/理由被新闻面否决
#   OUTCOME|<id>|<日期>|<成交价>|<退出价>|<往返成本bp>|<净收益%>|<MFE%>|<MAE%>|<退出原因>
#     VERDICT 的“命中”只代表价格触发；OUTCOME 只在用户确认成交并退出后写入。
#   INSIGHT|<日期YYYY-MM-DD>|<方向标签>|<一句话>
#     新闻面类标签：新闻面-新事件（推荐后新利空，运气外因）/ 新闻面-遗漏（推荐时已可查而漏查，雷达缺陷）
# 用法：
#   picks-log.sh rec <代码> <名称> <方向> <触发价> <作废价> <有效期至> "<理由>" [事件ID]
#   picks-log.sh verify <id> <状态:命中|作废|超时|进行中> "<一句话>"
#   picks-log.sh outcome <id> <成交价> <退出价> <成本bp> <MFE%> <MAE%> "<退出原因>"
#   picks-log.sh open                     列全部未结案推荐（有 PICK 无终态 VERDICT；当日荐股闸门排除）
#   picks-log.sh history [N]              列最近 N 条 PICK（默认 20）
#   picks-log.sh stats [方向标签]          汇总命中率（按方向分组）
#   picks-log.sh streak [方向标签]         按方向的终态时序与连续错计数（熔断判定依据）
#   picks-log.sh insight "<一句话>" [方向标签]   沉淀一条思路修正（无标签归"通用"）
set -u
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
PICKS_FILE="$SG_HOME/picks.md"

usage() { cat <<'EOF'
用法：picks-log.sh <子命令> [参数]
  rec <代码> <名称> <方向> <触发价> <作废价> <有效期至> "<理由>" [事件ID]   落一条推荐（事件ID可选：事件驱动型推荐）
  verify <id> <命中|作废|超时|进行中> "<一句话>"                  验证落判（当日推荐拒判）
  outcome <id> <成交价> <退出价> <成本bp> <MFE%> <MAE%> "<退出原因>"  记录已完成交易
  open                       列未结案推荐（当日荐股闸门排除）
  history [N]                列最近 N 条推荐（默认 20）
  stats [方向标签]            命中率汇总
  streak [方向标签]           终态时序与连续错计数（熔断判定）
  insight "<一句话>" [方向标签]  沉淀思路修正
台账文件：$HOME/.stock-guardian/picks.md（长期保留，永不清理；属用户数据，永不进 skill 目录）
EOF
}

die() { echo "picks-log.sh：$1" >&2; exit 1; }

check_state() {
  case "$1" in
    命中|作废|超时|进行中) ;;
    *) die "状态只允许：命中|作废|超时|进行中（收到的是「$1」）" ;;
  esac
}

init_file() {
  mkdir -p "$SG_HOME" 2>/dev/null
  if [ ! -f "$PICKS_FILE" ]; then
    printf '# stock-guardian 荐股台账\n# 推荐与验证的长期记录。机器行由 picks-log.sh 维护，人工批注写在普通文本行。\n# PICK/VERDICT/OUTCOME/INSIGHT 四类行含义见 picks-log.sh 文件头注释。\n' >"$PICKS_FILE"
    chmod 600 "$PICKS_FILE" 2>/dev/null
  fi
}

# 生成递增 id：当日日期 + 当日序号（如 20261016-2）
next_id() {
  local today seq
  today=$(date +%Y%m%d)
  seq=$(grep -c "^PICK|${today}-" "$PICKS_FILE" 2>/dev/null || true)
  seq=$((seq + 1))
  echo "${today}-${seq}"
}

no_pipe() { case "$1" in *"|"*) die "文本字段里不要用竖线 | 字符（机器行分隔符）：${1:0:40}" ;; esac; }

case "${1:-}" in
  rec)
    CODE="${2:-}"; NAME="${3:-}"; DIRECTION="${4:-}"; TRIG="${5:-}"; KILL="${6:-}"; EXP="${7:-}"; REASON="${8:-}"; EVTID="${9:-}"
    [ -n "$CODE" ] && [ -n "$NAME" ] && [ -n "$DIRECTION" ] && [ -n "$TRIG" ] && [ -n "$KILL" ] && [ -n "$EXP" ] && [ -n "$REASON" ] \
      || die "rec 用法：picks-log.sh rec <代码> <名称> <方向> <触发价> <作废价> <有效期至> \"<理由>\" [事件ID]（前七项都不能空）"
    case "$CODE" in sh*|sz*|bj*) ;; *) die "rec：只支持 A股代码（sh/sz/bj 前缀），收到 $CODE" ;; esac
    # 全字段防竖线：机器行以 | 分隔，任何字段混入竖线都会让后续解析静默错位
    no_pipe "$CODE"; no_pipe "$NAME"; no_pipe "$DIRECTION"; no_pipe "$TRIG"; no_pipe "$KILL"; no_pipe "$EXP"; no_pipe "$REASON"; no_pipe "$EVTID"
    # 价格与日期格式校验：杜绝伪精度与日期口算错误进台账
    case "$TRIG" in *[!0-9.]*) die "rec：触发价只允许数字与小数点，收到 $TRIG" ;; esac
    case "$KILL" in *[!0-9.]*) die "rec：作废价只允许数字与小数点，收到 $KILL" ;; esac
    date -d "$EXP" +%F >/dev/null 2>&1 || die "rec：有效期至必须是合法日期（YYYY-MM-DD），收到 $EXP"
    # 事件ID可选：带则校验格式（YYYYMMDD-序号），供验证任务判定"理由被新闻面否决"时反查
    if [ -n "$EVTID" ]; then
      case "$EVTID" in *[!0-9-]*) die "rec：事件ID只允许数字与连字符（YYYYMMDD-序号），收到 $EVTID" ;; esac
    fi
    init_file
    ID=$(next_id)
    printf 'PICK|%s|%s|%s|%s|%s|%s|%s|%s|%s' "$ID" "$(date +%F)" "$CODE" "$NAME" "$DIRECTION" "$TRIG" "$KILL" "$EXP" "$REASON" >>"$PICKS_FILE"
    if [ -n "$EVTID" ]; then printf '|%s' "$EVTID" >>"$PICKS_FILE"; fi
    printf '\n' >>"$PICKS_FILE"
    echo "已落推荐 $ID：$NAME $DIRECTION 触发 $TRIG 作废 $KILL 有效期至 $EXP${EVTID:+（事件驱动型，事件 $EVTID）}"
    echo "理由：$REASON"
    ;;
  verify)
    ID="${2:-}"; STATE="${3:-}"; NOTE="${4:-}"
    [ -n "$ID" ] && [ -n "$STATE" ] && [ -n "$NOTE" ] || die "verify 用法：picks-log.sh verify <id> <命中|作废|超时|进行中> \"<一句话>\"（三项都不能空）"
    check_state "$STATE"
    no_pipe "$NOTE"
    init_file
    grep -q "^PICK|$ID|" "$PICKS_FILE" || die "verify：台账里不存在推荐 $ID（先 rec 才能验证）"
    # 当日闸门：推荐当日不核销（16:00 荐股 16:15 验证的时序里，行情还没走出可判定的走势）
    PICK_DAY=$(grep "^PICK|$ID|" "$PICKS_FILE" | head -1 | cut -d'|' -f3)
    [ "$PICK_DAY" != "$(date +%F)" ] || die "verify：$ID 是当日推荐，当日不核销，留 3 个交易日窗口（首个核销日：下一交易日）"
    # 终态校验：命中/作废/超时之后不允许再改判（防止事后挑好看的状态）
    for s in 命中 作废 超时; do
      if grep -q "^VERDICT|$ID|.*|$s|" "$PICKS_FILE"; then
        die "verify：$ID 已是终态「$s」，不许事后改判；复盘意见走 insight 子命令"
      fi
    done
    printf 'VERDICT|%s|%s|%s|%s\n' "$ID" "$(date +%F)" "$STATE" "$NOTE" >>"$PICKS_FILE"
    echo "已落验证 $ID → $STATE：$NOTE"
    ;;
  outcome)
    ID="${2:-}"; ENTRY="${3:-}"; EXIT="${4:-}"; COST_BP="${5:-}"; MFE="${6:-}"; MAE="${7:-}"; REASON="${8:-}"
    [ -n "$ID" ] && [ -n "$ENTRY" ] && [ -n "$EXIT" ] && [ -n "$COST_BP" ] && [ -n "$MFE" ] && [ -n "$MAE" ] && [ -n "$REASON" ] \
      || die "outcome 用法：picks-log.sh outcome <id> <成交价> <退出价> <成本bp> <MFE%> <MAE%> \"<退出原因>\""
    for value in "$ENTRY" "$EXIT" "$COST_BP" "$MFE" "$MAE"; do
      case "$value" in *[!0-9.-]*|*.*.*|*--*|-|.|-.) die "outcome：价格、成本、MFE、MAE 必须是数字" ;; esac
    done
    no_pipe "$REASON"
    init_file
    grep -q "^PICK|$ID|" "$PICKS_FILE" || die "outcome：台账里不存在推荐 $ID"
    grep -q "^OUTCOME|$ID|" "$PICKS_FILE" && die "outcome：$ID 已有交易结果，不许重复写入"
    NET=$(awk -v entryP="$ENTRY" -v exitP="$EXIT" -v bp="$COST_BP" 'BEGIN {
      if (entryP <= 0 || exitP <= 0 || bp < 0) exit 2
      printf "%.4f", (exitP / entryP - 1) * 100 - bp / 100
    }') || die "outcome：成交价、退出价必须大于 0，成本bp不能小于 0"
    printf 'OUTCOME|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' "$ID" "$(date +%F)" "$ENTRY" "$EXIT" "$COST_BP" "$NET" "$MFE" "$MAE" "$REASON" >>"$PICKS_FILE"
    echo "已记录交易结果 $ID：净收益 ${NET}%（成本 ${COST_BP}bp）"
    ;;
  open)
    init_file
    # 未结案 = 有 PICK 无终态 VERDICT（命中/作废/超时）；"进行中" VERDICT 不结案
    # 当日闸门：推荐当日不进未结案清单（行情没跑完，给 3 个交易日窗口从次日起算）
    awk -F'|' -v today="$(date +%F)" '
      $1 == "PICK" { pick[$2] = $0; order[++n] = $2; pickday[$2] = $3 }
      $1 == "VERDICT" && ($4 == "命中" || $4 == "作废" || $4 == "超时") { done[$2] = 1 }
      END {
        cnt = 0
        for (i = 1; i <= n; i++) if (!(order[i] in done) && pickday[order[i]] != today) { cnt++; print pick[order[i]] }
        if (cnt == 0) print "（台账里没有未结案推荐）"
        else print "（共 " cnt " 条未结案，当日荐股已按闸门排除）"
      }' "$PICKS_FILE"
    ;;
  history)
    N="${2:-20}"
    init_file
    grep '^PICK|' "$PICKS_FILE" | tail -n "$N"
    ;;
  stats)
    TAG="${2:-}"
    init_file
    # 四态计数 + 按方向分组；TAG 非空时只统计该方向
    awk -F'|' -v want="$TAG" '
      $1 == "PICK" {
        id = $2; dir = $6
        if (want == "" || dir == want) {
          ids[++n] = id; id_dir[id] = dir; total++
          all_dirs[dir] = 1
        }
      }
      $1 == "VERDICT" {
        v_id = $2; v_st = $4
        if (v_id in id_dir) {
          st[v_id] = v_st
          if (v_st == "命中" || v_st == "作废" || v_st == "超时") closed[v_id] = 1
        }
      }
      $1 == "OUTCOME" {
        o_id = $2
        if (o_id in id_dir) {
          outcome[o_id] = $7 + 0
          outcome_n++
          outcome_sum += $7 + 0
          if (($7 + 0) > 0) outcome_win++
        }
      }
      END {
        if (total == 0) { print "（无推荐记录）"; exit }
        for (i = 1; i <= n; i++) {
          id = ids[i]; d = id_dir[id]
          t_total[d]++
          s = (id in st) ? st[id] : "未验证"
          t_state[d "_" s]++
        }
        if (want == "") {
          printf "方向数 %d，推荐总数 %d\n", length(all_dirs), total
          for (d in t_total) {
            printf "  %s：共 %d", d, t_total[d]
            printf "｜命中 %d", t_state[d "_命中"] + 0
            printf "｜作废 %d", t_state[d "_作废"] + 0
            printf "｜超时 %d", t_state[d "_超时"] + 0
            printf "｜进行中 %d", t_state[d "_进行中"] + 0
            printf "｜未验证 %d\n", t_state[d "_未验证"] + 0
          }
        } else {
          printf "方向「%s」：共 %d", want, total
          printf "｜命中 %d", t_state[want "_命中"] + 0
          printf "｜作废 %d", t_state[want "_作废"] + 0
          printf "｜超时 %d", t_state[want "_超时"] + 0
          printf "｜进行中 %d", t_state[want "_进行中"] + 0
          printf "｜未验证 %d\n", t_state[want "_未验证"] + 0
        }
        if (outcome_n > 0) {
          printf "已完成交易 %d｜盈利 %d｜交易胜率 %.1f%%｜平均净收益 %.2f%%\n", outcome_n, outcome_win, outcome_win / outcome_n * 100, outcome_sum / outcome_n
        } else {
          print "已完成交易 0（触发命中率不能代替交易收益）"
        }
      }' "$PICKS_FILE"
    ;;
  insight)
    TEXT="${2:-}"; TAG="${3:-通用}"
    [ -n "$TEXT" ] || die "insight 用法：picks-log.sh insight \"<一句话>\" [方向标签]"
    no_pipe "$TEXT"; no_pipe "$TAG"
    init_file
    printf 'INSIGHT|%s|%s|%s\n' "$(date +%F)" "$TAG" "$TEXT" >>"$PICKS_FILE"
    printf '已沉淀思路修正：「%s」（标签：%s）\n' "$TEXT" "$TAG"
    ;;
  streak)
    # 按方向输出按时序排列的终态序列与连续错（作废/超时）计数——连续错熔断的判定依据
    # 新闻面否决豁免（rules.md 荐股台账节）：PICK 行带事件ID 且归因句含"新闻面否决"的终态不计入连续错
    # 用法：picks-log.sh streak [方向标签]；无标签时全部方向各列一组
    TAG="${2:-}"
    init_file
    awk -F'|' -v want="$TAG" '
      $1 == "PICK" { dir[$2] = $6; day[$2] = $3; evid[$2] = ($11 == "" ? "" : $11) }
      $1 == "VERDICT" && ($4 == "命中" || $4 == "作废" || $4 == "超时") {
        vid = $2; if (want == "" || dir[vid] == want) {
          n++; k = day[vid] "|" vid
          key[n] = k; state[k] = $4
          note[k] = $5
        }
      }
      END {
        if (n == 0) { print "（无终态记录，streak 无内容）"; exit }
        # 按推荐日期+id 排序（id 内含日期前缀，直接字符串排序即时间序）
        asort(key)
        # 逐方向独立统计连续错
        cur_dir = ""
        for (i = 1; i <= n; i++) {
          split(key[i], a, "|"); vid = a[2]
          d = dir[vid]
          if (d != cur_dir) {
            if (cur_dir != "") print ""
            cur_dir = d; streak_bad = 0; streak_good = 0
            print "方向「" d "」终态时序："
          }
          s = state[key[i]]
          exempt = (evid[vid] != "" && note[key[i]] ~ /新闻面否决/) ? 1 : 0
          if (s == "作废" || s == "超时") {
            if (exempt) { tag_ex = "（新闻面否决豁免，不计连续错）" } else { streak_bad++; streak_good = 0; tag_ex = "" }
          }
          else if (s == "命中") { streak_good++; streak_bad = 0; tag_ex = "" }
          printf "  %s %s %s%s", vid, day[vid], s, tag_ex
          if (streak_bad >= 2) printf "  ← 连续错 %d 次（熔断线：连续 2 次终态作废/超时，暂停该方向 5 个交易日）", streak_bad
          if (streak_good >= 2) printf "  ← 连续命中 %d 次（方向延续参考）", streak_good
          print ""
        }
      }' "$PICKS_FILE"
    ;;
  *)
    usage
    ;;
esac
