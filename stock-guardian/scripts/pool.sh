#!/usr/bin/env bash
# stock-guardian 观察池（pool.md）：荐股台账的工作区层——候选票的持续维护池。
# 定位：台账（picks.md）记对账、长期保留永不清理；池（pool.md）是活的工作区，
#   自动加减删除——用户要求"每天自动推荐+自动维护的观察区池子"（2026-10-21 立）。
# 机器行：POOL|<id>|<入池日>|<代码>|<名称>|<方向>|<触发价>|<作废价>|<有效期至>|<状态>|<顺延标记>|<理由>
#   状态：active=观察中 / triggered=已触发升级预案继续跟踪；终态（作废/超时/清出）即出池（行删除，台账留档）
#   顺延标记：0=未顺延 / 1=已顺延一次（extend 至多一次，理由必填，禁止无限顺延）
# 两层同源：入池自动落 PICK 进台账验证闭环；终态自动落 VERDICT；作废价/有效期与台账一致。
# 池容量 5 只固定，宁缺毋滥——盘后荐股筛不出合格候选时空位就空着。
# 用法：
#   pool.sh add <代码> <名称> <方向> <触发价> <作废价> <有效期至> "<理由>"    入池（自动落台账 PICK）
#   pool.sh ls                                                              列池全量
#   pool.sh hit <id> "<一句话>"                                             置已触发（留池跟踪，落 VERDICT）
#   pool.sh extend <id> <新有效期至> "<顺延理由>"                           顺延（至多一次）
#   pool.sh drop <id> <作废|超时|清出> "<一句话>"                           出池终态（落 VERDICT，池行删除）
#   pool.sh update <id> [--trig 价] [--void 价] [--exp 日期] [--dir 方向] "<理由>"  改池行（行尾留痕+台账 INSIGHT）
#   pool.sh sync-picks [YYYY-MM-DD]                                         台账当日 PICK 补入池（已入池跳过，满池即停）
set -u
SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
POOL_FILE="$SG_HOME/pool.md"
PICKS_SH="$(cd "$(dirname "$0")" && pwd)/picks-log.sh"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
# 容量默认 10（2026-10-29 用户："没有满这一说 而且多模块多个上限改成 10 吧"）：多模块覆盖需要更多挂线位，
# 单条纪律不变（同链只留一条、单票仓位上限、闸门 PASS 才动手）。可用 POOL_CAPACITY 覆盖（测试/临时扩容用）。
CAPACITY="${POOL_CAPACITY:-10}"
# 线变更留痕（2026-10-29 立）：线的增删必须可追溯——当天实测心跳 rules 在 1→5→6→8→12→14→15→8 之间跳却无痕，
# 复盘时只能靠事后重建。池侧增删在此记一笔，同步侧由 pool-watch-sync 记（同一文件 line-changes.log）。
linelog() { local a="$1"; shift; local j=""; local x; for x in "$@"; do j="$j$x|"; done; j="${j%|}"; printf 'LINECHG|%s|%s|%s\n' "$(date '+%F %T')" "$a" "$j" >> "$SG_HOME/line-changes.log" 2>/dev/null || true; }

usage() { sed -n '2,18p' "$0" | grep -E '^# ' | sed 's/^# \{0,1\}//'; }
die() { echo "❌ $*" >&2; exit 1; }

init_file() {
  [ -f "$POOL_FILE" ] || { mkdir -p "$SG_HOME"; printf '# stock-guardian 观察池（工作区层，自动维护；台账对账在 picks.md）\n# 机器行由 pool.sh 维护，人工批注写普通文本行。\n' > "$POOL_FILE"; chmod 600 "$POOL_FILE"; }
}

# 校验：价格只许数字与小数点；日期须合法 YYYY-MM-DD；文本禁竖线
v_price() { echo "$1" | grep -qE '^[0-9]+(\.[0-9]+)?$' || die "价格「$1」只允许数字与小数点"; }
v_date()  { echo "$1" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' && date -d "$1" >/dev/null 2>&1 || die "日期「$1」须为合法 YYYY-MM-DD"; }
v_text()  { echo "$1" | grep -q '|' && die "文本字段禁竖线：$1"; }

# 找池行对应的台账 PICK：先按（入池日, 代码）精确匹配；匹配不到时，仅当该代码在池里只剩一行，
# 才退回"同代码最后一条 PICK"。同码多行又无同日 PICK 时返回失败——宁可不核销，也不误判别的行。
# （2026-10-29 立：原实现只按代码取最后一条，同码两行时删突破行会误判低吸行的 PICK）
pick_for_row() {
  local id="$1" code="$2" day tpid cnt
  day=$(grep "^POOL|$id|" "$POOL_FILE" | awk -F'|' '{print $3}')
  tpid=$(grep "^PICK|" "$SG_HOME/picks.md" 2>/dev/null | awk -F'|' -v c="$code" -v d="$day" '$4==c && $3==d {print $2}' | tail -1)
  [ -n "$tpid" ] && { printf '%s' "$tpid"; return 0; }
  cnt=$(awk -F'|' -v c="$code" '/^POOL\|/{ if ($4==c) n++ } END{print n+0}' "$POOL_FILE")
  if [ "$cnt" -le 1 ]; then
    tpid=$(grep "^PICK|" "$SG_HOME/picks.md" 2>/dev/null | grep "|$code|" | tail -1 | awk -F'|' '{print $2}')
    [ -n "$tpid" ] && { printf '%s' "$tpid"; return 0; }
  fi
  return 1
}

# 台账该 PICK 是否已有终态（命中/作废/超时）：终态不许改判，池脚本也不重复核销
pick_settled() {
  grep -qE "^VERDICT\|$1\|[^|]*\|(命中|作废|超时)\|" "$SG_HOME/picks.md" 2>/dev/null
}

# 读某代码的链条名（chains.json 登记表；未登记输出空）
chain_of() {
  python3 - "$SG_HOME/chains.json" "$1" <<'EOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    sys.exit(0)
v = d.get(sys.argv[2])
if isinstance(v, str):
    print(v)
EOF
}

CMD="${1:-}"; shift 2>/dev/null || true
init_file
TODAY="$(date +%F)"

case "$CMD" in
  add)
    # --allow-dup-chain 是标志位，先摘掉再按位置取参
    ALLOW_CHAIN=""; ARGS=()
    for a in "$@"; do
      if [ "$a" = "--allow-dup-chain" ]; then ALLOW_CHAIN=1; else ARGS+=("$a"); fi
    done
    set -- "${ARGS[@]}"
    CODE="$1"; NAME="$2"; DIR="$3"; TRIG="$4"; VOID="$5"; EXP="$6"; WHY="${7:-}"
    [ "$#" -ge 7 ] || die "add 参数不足：<代码> <名称> <方向> <触发价> <作废价> <有效期至> \"<理由>\" [--allow-dup-chain]"
    v_price "$TRIG"; v_price "$VOID"; v_date "$EXP"; v_text "$WHY"; v_text "$NAME"
    N=$(awk -F'|' '/^POOL\|/{n++} END{print n+0}' "$POOL_FILE")
    [ "$N" -lt "$CAPACITY" ] || die "池已满（${CAPACITY} 只）：先 drop 再 add，不硬凑"
    # 池内分散度：同链（同板块风险敞口）只留一条——宽基 ETF 分散不等于链条分散（2026-10-29 立）
    MYCHAIN="$(chain_of "$CODE")"
    if [ -n "$MYCHAIN" ]; then
      while IFS= read -r OC; do
        [ -n "$OC" ] || continue
        if [ "$(chain_of "$OC")" = "$MYCHAIN" ]; then
          if [ -n "$ALLOW_CHAIN" ]; then
            echo "⚠ 同链并行（已显式放行）：$CODE 与池内 $OC 同属「$MYCHAIN」——总敞口按一条算，理由里写清为什么留两条"
          else
            die "同链重复暴露：$CODE（$MYCHAIN）与池内 $OC 同链——同一板块风险敞口池内只留一条（先 drop 或改挂别链）；确要并行加 --allow-dup-chain 并写进理由"
          fi
        fi
      done < <(awk -F'|' '/^POOL\|/{print $4}' "$POOL_FILE")
    else
      echo "⚠ 未登记链条：$CODE——在 $SG_HOME/chains.json 补登后，池内同链检查才会对它生效"
    fi
    ID=$(awk -F'|' '/^POOL\|/{n++} END{print n+0}' "$POOL_FILE")
    ID=$((ID+1)); PID="pool-$(date +%Y%m%d)-${ID}"
    # 入池同步落台账 PICK（进荐股验证闭环）；防重：同代码已有未结案 PICK 则跳过落账（转池票不重复记账）
    if awk -F'|' -v c="$CODE" '
      /^PICK\|/ && $4==c { ids[++n]=$2 }
      /^VERDICT\|/ && ($4=="命中"||$4=="作废"||$4=="超时") { fin[$2]=1 }
      END{ dup=0; for(i=1;i<=n;i++) if(!fin[ids[i]]) dup=1; exit dup?0:1 }
    ' "$SG_HOME/picks.md" 2>/dev/null; then
      echo "（台账已有 $CODE 未结案 PICK，跳过重复落账——沿用原推荐记录）"
    else
      "$PICKS_SH" rec "$CODE" "$NAME" "$DIR" "$TRIG" "$VOID" "$EXP" "$WHY" >/dev/null || die "台账 PICK 落账失败"
    fi
    printf 'POOL|%s|%s|%s|%s|%s|%s|%s|%s|active|0|%s\n' "$PID" "$TODAY" "$CODE" "$NAME" "$DIR" "$TRIG" "$VOID" "$EXP" "$WHY" >> "$POOL_FILE"
    linelog pool-add "$PID" "$CODE" "$NAME" "$DIR" "$TRIG" "$VOID" "$EXP"
    echo "已入池 $PID：$NAME（$CODE）$DIR 触发 $TRIG 作废 $VOID 有效期至 $EXP——台账 PICK 已同步落账"
    ;;
  ls)
    CHAINS_TXT=$(python3 - "$SG_HOME/chains.json" <<'EOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding='utf-8'))
except Exception:
    sys.exit(0)
print(';'.join(f"{k}={v}" for k, v in d.items() if isinstance(v, str) and not k.startswith('_')))
EOF
)
    awk -F'|' -v ch="$CHAINS_TXT" 'BEGIN{n=split(ch,a,";"); for(i=1;i<=n;i++){split(a[i],kv,"="); C[kv[1]]=kv[2]}} /^POOL\|/{printf "%-16s %-9s %-8s %-6s 触发%8s 作废%8s 至%s [%s]%s ｜链条%s %s\n",$2,$4,$5,$6,$7,$8,$9,$10,($11==1?"（已顺延）":""),(C[$4]==""?"未登记":C[$4]),$12}' "$POOL_FILE"
    N=$(awk -F'|' '/^POOL\|/{n++} END{print n+0}' "$POOL_FILE")
    # 注意：写成 [ ... ] && echo 会让"池非空"时 ls 的退出码变成 1（条件为假即非零），调用方 ls && next 会莫名不执行
    if [ "$N" -eq 0 ]; then echo "（池空——盘后荐股任务负责补新，不硬凑）"; fi
    ;;
  hit)
    ID="$1"; WHY="${2:-已触发}"
    grep -q "^POOL|$ID|" "$POOL_FILE" || die "池内无 $ID"
    v_text "$WHY"
    LINE=$(grep "^POOL|$ID|" "$POOL_FILE"); CODE=$(echo "$LINE" | awk -F'|' '{print $4}')
    TPID="$(pick_for_row "$ID" "$CODE" || true)"
    NOTE="未关联台账 PICK"
    if [ -n "$TPID" ]; then
      if pick_settled "$TPID"; then
        NOTE="台账 $TPID 已是终态，不改判"
      elif "$PICKS_SH" verify "$TPID" 命中 "$WHY（观察池 $ID 同步）" >/dev/null 2>&1; then
        NOTE="台账 $TPID 已落命中判定"
      else
        # 常见合法拒绝：当日推荐当日不核销（脚本闸门）。只置池状态，宁可说"未落成"也不假报成功
        NOTE="台账 $TPID 未落成（如当日推荐不核销），留下一交易日验证"
      fi
    fi
    sed -i "s/^POOL|$ID|\(.*\)|active|/POOL|$ID|\1|triggered|/" "$POOL_FILE"
    echo "已置触发 $ID（留池跟踪兑现度）；$NOTE"
    ;;
  extend)
    ID="$1"; NEW="$2"; WHY="${3:-}"
    grep -q "^POOL|$ID|" "$POOL_FILE" || die "池内无 $ID"
    v_date "$NEW"; v_text "$WHY"
    EXT=$(grep "^POOL|$ID|" "$POOL_FILE" | awk -F'|' '{print $11}')
    [ "$EXT" = "0" ] || die "$ID 已顺延过一次，禁止无限顺延——清出后允许以新触发价重新入池"
    LINE=$(grep "^POOL|$ID|" "$POOL_FILE"); OLD=$(echo "$LINE" | awk -F'|' '{print $9}')
    date -d "$NEW" >/dev/null 2>&1 && [ "$NEW" \> "$OLD" ] || die "顺延日期须晚于原有效期 $OLD"
    sed -i "s/^POOL|$ID|\(.*\)|$OLD|active|0|/POOL|$ID|\1|$NEW|active|1|/" "$POOL_FILE"
    echo "已顺延 $ID：有效期至 $NEW（顺延理由：$WHY）——至多这一次"
    ;;
  drop)
    ID="$1"; ST="$2"; WHY="${3:-}"
    grep -q "^POOL|$ID|" "$POOL_FILE" || die "池内无 $ID"
    case "$ST" in 作废|超时|清出) ;; *) die "终态三选一：作废/超时/清出";; esac
    v_text "$WHY"
    LINE=$(grep "^POOL|$ID|" "$POOL_FILE"); CODE=$(echo "$LINE" | awk -F'|' '{print $4}'); NAME=$(echo "$LINE" | awk -F'|' '{print $5}')
    # 台账终态词表只有 命中/作废/超时（picks-log verify 的 check_state）：清出在台账按「作废」记，理由里写明出池动作
    case "$ST" in 清出) VST=作废;; *) VST="$ST";; esac
    TPID="$(pick_for_row "$ID" "$CODE" || true)"
    if [ -n "$TPID" ]; then
      if pick_settled "$TPID"; then
        echo "# [pool出池] $(date '+%F %T') $ID 台账 $TPID 已终态，出池不改判" >> "$SG_HOME/pool-ops.log"
      elif "$PICKS_SH" verify "$TPID" "$VST" "观察池出池（$ST）：$WHY（$ID）" >> "$SG_HOME/pool-ops.log" 2>&1; then
        :
      else
        echo "# [pool出池] $(date '+%F %T') $ID 台账 $TPID 核销未成（$VST），出池已记录、待人工" >> "$SG_HOME/pool-ops.log"
      fi
    else
      echo "# [pool出池] $(date '+%F %T') $ID 无唯一对应 PICK（同码多行），出池已记录、待人工判定" >> "$SG_HOME/pool-ops.log"
    fi
    sed -i "/^POOL|$ID|/d" "$POOL_FILE"
    linelog pool-drop "$ID" "$CODE" "$NAME" "$ST" "$WHY"
    echo "# [pool出池] $(date '+%F %T') $ID $NAME（$CODE）$ST 理由：$WHY" >> "$SG_HOME/pool-ops.log"
    echo "已出池 $ID：$NAME（$ST）——台账留档，出池动作已记 pool-ops.log（多实例共写留痕，2026-10-21 无痕删行事故后立）"
    ;;
  update)
    ID="${1:-}"; [ -n "$ID" ] || die "update 用法：pool.sh update <id> [--trig 价] [--void 价] [--exp 日期] [--dir 方向] \"<理由>\""
    shift 2>/dev/null || true
    NEWT=""; NEWV=""; NEWE=""; NEWD=""; WHY=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --trig) NEWT="${2:-}"; shift 2 2>/dev/null || shift ;;
        --void) NEWV="${2:-}"; shift 2 2>/dev/null || shift ;;
        --exp)  NEWE="${2:-}"; shift 2 2>/dev/null || shift ;;
        --dir)  NEWD="${2:-}"; shift 2 2>/dev/null || shift ;;
        *)      WHY="$1"; shift ;;
      esac
    done
    grep -q "^POOL|$ID|" "$POOL_FILE" || die "池内无 $ID"
    [ -n "$NEWT$NEWV$NEWE$NEWD" ] || die "update 至少要改一个字段（--trig/--void/--exp/--dir）"
    [ -n "$WHY" ] || die "update 必须带理由：池行变更要留痕（行尾追加 + 台账 INSIGHT）"
    [ -z "$NEWT" ] || v_price "$NEWT"
    [ -z "$NEWV" ] || v_price "$NEWV"
    [ -z "$NEWE" ] || v_date "$NEWE"
    [ -z "$NEWD" ] || v_text "$NEWD"
    v_text "$WHY"
    LINE=$(grep "^POOL|$ID|" "$POOL_FILE")
    ODIR=$(printf '%s' "$LINE" | awk -F'|' '{print $6}'); OTRIG=$(printf '%s' "$LINE" | awk -F'|' '{print $7}')
    OVOID=$(printf '%s' "$LINE" | awk -F'|' '{print $8}'); OEXP=$(printf '%s' "$LINE" | awk -F'|' '{print $9}')
    # 软校验：失效距离 <3% 只告警不拦（档位判定归 prebuy-check，池脚本不重复实现规则）
    if ! awk -v t="${NEWT:-$OTRIG}" -v v="${NEWV:-$OVOID}" 'BEGIN{ if (t+0 > 0 && (t-v)/t*100 < 3) exit 1; exit 0 }'; then
      echo "⚠ 失效距离不足 3%：先跑 prebuy-check.js 再定案，别把过窄止损留在池里"
    fi
    NEWLINE=$(printf '%s\n' "$LINE" | awk -F'|' -v t="$NEWT" -v v="$NEWV" -v e="$NEWE" -v d="$NEWD" -v why="$WHY" -v day="$TODAY" 'BEGIN{OFS="|"} { if(t!="")$7=t; if(v!="")$8=v; if(e!="")$9=e; if(d!="")$6=d; if(why!="")$12=$12" ｜"day" update："why; print }')
    TMP="$POOL_FILE.tmp.$$"
    awk -v id="$ID" -v nl="$NEWLINE" 'BEGIN{done=0} $0 ~ ("^POOL\\|" id "\\|") { if(!done){print nl; done=1; next} } {print}' "$POOL_FILE" > "$TMP" || die "写临时文件失败"
    mv "$TMP" "$POOL_FILE" || die "替换池文件失败"
    NT=$(printf '%s' "$NEWLINE" | awk -F'|' '{print $7}'); NV=$(printf '%s' "$NEWLINE" | awk -F'|' '{print $8}')
    NE=$(printf '%s' "$NEWLINE" | awk -F'|' '{print $9}'); ND=$(printf '%s' "$NEWLINE" | awk -F'|' '{print $6}')
    "$PICKS_SH" insight "池行 $ID 变更：方向 $ODIR→$ND｜触发 $OTRIG→$NT｜作废 $OVOID→$NV｜有效期 $OEXP→$NE（理由：$WHY）" "$ND" >/dev/null 2>&1 || true
    echo "已更新 $ID：方向 $ND 触发 $NT 作废 $NV 有效期 $NE（行尾留痕 + 台账 INSIGHT）"
    ;;
  sync-picks)
    DAY="${1:-$TODAY}"
    v_date "$DAY"
    [ -f "$SG_HOME/picks.md" ] || die "台账不存在：$SG_HOME/picks.md"
    ADDED=0; SKIPPED=0
    while IFS='|' read -r TAG PID PDAY CODE NAME DIR TRIG VOID EXP WHY; do
      [ "$TAG" = "PICK" ] || continue
      [ "$PDAY" = "$DAY" ] || continue
      [ -n "$CODE" ] || continue
      if awk -F'|' -v c="$CODE" '/^POOL\|/{ if ($4==c) f=1 } END{ exit f?0:1 }' "$POOL_FILE"; then
        echo "跳过 $CODE（已在池）"; SKIPPED=$((SKIPPED+1)); continue
      fi
      N=$(awk -F'|' '/^POOL\|/{n++} END{print n+0}' "$POOL_FILE")
      if [ "$N" -ge "$CAPACITY" ]; then
        echo "池已满（$CAPACITY 只）：$CODE 未入池——先 drop 失效行再 sync-picks"; break
      fi
      "$SELF" add "$CODE" "$NAME" "$DIR" "$TRIG" "$VOID" "$EXP" "$WHY" || die "入池失败：$CODE"
      ADDED=$((ADDED+1))
    done < "$SG_HOME/picks.md"
    echo "sync-picks（$DAY）：新入池 $ADDED 只，跳过已在池 $SKIPPED 只"
    ;;
  *) usage; [ -n "$CMD" ] && die "未知子命令 $CMD"; exit 1;;
esac
