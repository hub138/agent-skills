#!/usr/bin/env bash
# stock-guardian 分钟级盯盘 watchdog：纯工具层，零用户数据，可随 skill 整体分发。
# 依赖：bash / awk / node(westock-data) / curl；建议 timeout 与 flock（cron 行）。
# 配置与状态（全在 $HOME/.stock-guardian/，可用 SG_HOME 覆盖；删除 watch.conf 即停用）：
#   watch.conf    机器可读警报线（格式见该文件头注释），与 portfolio.md"盘中警报线"同源
#   webhook.env   WECOM_WEBHOOK_URL=企微群机器人地址（凭据，权限 600，永不进 skill 目录）
#   .watch-state  触发状态与去重（自动维护）   watch.log  日志（自动维护与截断）
# 用法：watch.sh [--force] [--dry-run]
#   --force   跳过交易时段判断（测试用）    --dry-run  只打印不发送、不写状态（测试用）
# 能力边界（如实告知用户）：只盯 A股(sh/sz/bj)价格类触发——规则线/警报线/区间/当日异动（默认 ±3%）；
#   异动阈值是私人参数：watch.conf 写 watch|<code>|pct|<阈值> 即按票覆盖（更灵敏 2%、更钝 5% 都行），未写的票走默认 3%。
#   加当日箱体动态追踪：day file 里的 BOX 行（箱体确认任务写入）自动变成"突破上沿/跌破下沿"警报，
#   箱体每天重画、警报线自动跟着变——这是"动态规则"，与 watch.conf 的静态线互补。
#   同文件 PLAN 行（箱体确认任务写入的每票白话动作）在触发时原样附上：用户收到的是"该怎么办"，
#   不是"去翻预案"——警报文案禁止出现 rules.md 等文档名。无 PLAN 行时回退通用提醒。
#   警报发出后自动落档 day file，午间/尾盘场景可衔接"早盘已警报过什么"。
#   公告、龙虎榜、市场状态切换不在此列，仍由整点任务与对话检查覆盖。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WESTOCK="${WESTOCK:-$(dirname "$(dirname "$SCRIPT_DIR")")/westock-data/scripts/index.js}"
QUOTE_BIN="$SCRIPT_DIR/quote-public.sh"   # 公开源行情适配器：westock 缺席时的降级通道（在场时它内部自动转投 westock）

# 行情拉取统一入口：westock 在场用它；缺席用公开源适配器（格式同 westock，A股/港股/美股可用）
quote_fetch(){
  if [ -f "$WESTOCK" ]; then timeout 30 node "$WESTOCK" quote "$1" 2>/dev/null
  else bash "$QUOTE_BIN" quote "$1" 2>/dev/null
  fi
}

# ---- cron 环境 PATH 补全：系统 crontab 的 PATH 通常只有 /usr/bin:/bin，会缺两样东西 ----
#   1) nvm 等用户目录装的 node（缺了→行情拉不到，报错被吞表现为"不报错但瞎"）
#   2) /usr/local/bin 里的正常 curl（部分系统 /usr/bin/curl 二进制与 libcurl 版本错配，任何请求都失败）
# 无条件前置（幂等去重，交互环境无副作用），分发到任何机器都稳。
for _d in "$HOME"/.nvm/versions/node/*/bin /usr/local/bin /opt/node/bin; do
  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) PATH="$_d:$PATH";; esac
done
export PATH

SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"
WATCH_CONF="${WATCH_CONF:-$SG_HOME/watch.conf}"
STATE_FILE="${STATE_FILE:-$SG_HOME/.watch-state}"
LOG_FILE="${LOG_FILE:-$SG_HOME/watch.log}"
DAY_FILE="$SG_HOME/day/$(date +%F).md"
DAYLOG="$SCRIPT_DIR/day-log.sh"

TODAY=$(date +%F); NOW=$(date +%s); HM=$((10#$(date +%H%M))); DOW=$(date +%u)
FORCE=0; DRY=0
for a in "$@"; do case "$a" in --force) FORCE=1;; --dry-run) DRY=1;; esac; done

log(){ echo "$(date '+%F %T') $*" >>"$LOG_FILE"; }

# 日志自截断（>100KB 保留末 200 行）
if [ -f "$LOG_FILE" ] && [ "$(wc -c <"$LOG_FILE" 2>/dev/null || echo 0)" -gt 102400 ]; then
  tail -n 200 "$LOG_FILE" >"$LOG_FILE.tmp" 2>/dev/null && mv -f "$LOG_FILE.tmp" "$LOG_FILE"
fi

# ---- A股交易时段自判（北京时间，周一至五 09:30-11:30 / 13:00-15:00）；节假日由行情日期兜底 ----
if [ "$FORCE" -eq 0 ]; then
  [ "$DOW" -le 5 ] || exit 0
  if [ "$HM" -ge 0930 ] && [ "$HM" -le 1130 ]; then :;
  elif [ "$HM" -ge 1300 ] && [ "$HM" -le 1500 ]; then :;
  else exit 0; fi
fi

[ -f "$WATCH_CONF" ] || { [ "$FORCE" -eq 1 ] && log "缺配置 $WATCH_CONF（watchdog 停用）"; exit 0; }
if [ ! -f "$WESTOCK" ]; then
  log "westock-data 缺失，本机 watchdog 降级走公开源（A股可用；fx/ks/t 不支持）"
  [ -f "$QUOTE_BIN" ] || { log "缺行情适配器 $QUOTE_BIN（watchdog 停用）"; exit 0; }
fi

# ---- 收集 A股代码（去重去空格）；非 A股代码跳过并记日志 ----
CODES=""
SKIPPED=""
while IFS='|' read -r tag code rest || [ -n "${tag:-}" ]; do
  [ "$tag" = "watch" ] || continue
  code="${code// /}"
  case "$code" in
    sh*|sz*|bj*) ;;
    *) SKIPPED="$SKIPPED $code"; continue ;;
  esac
  case ",$CODES," in *",$code,"*) ;; *) CODES="$CODES$code," ;; esac
done < "$WATCH_CONF"
# BOX 动态箱体代码并入拉取清单（持仓票可能没有静态线，当日箱体是其唯一规则）
if [ -f "$DAY_FILE" ]; then
  while IFS='|' read -r tag code rest || [ -n "${tag:-}" ]; do
    [ "$tag" = "BOX" ] || continue
    code="${code// /}"
    case "$code" in sh*|sz*|bj*) ;; *) continue ;; esac
    case ",$CODES," in *",$code,"*) ;; *) CODES="$CODES$code," ;; esac
  done < "$DAY_FILE"
fi
[ -n "$SKIPPED" ] && log "跳过非A股代码:$SKIPPED（watchdog 只盯 A股）"
CODES="${CODES%,}"
[ -n "$CODES" ] || exit 0

QTMP=$(mktemp) || exit 0
STMP=$(mktemp) || exit 0
trap 'rm -f "$QTMP" "$STMP"' EXIT

# ---- 拉行情，解析为 code|name|price|change_percent|date ----
# 注：不用 timeout 包 quote_fetch（外部命令看不到 shell 函数）；限时由适配器内 curl -m 10 与 westock 自身超时保障
quote_fetch "$CODES" | awk -F'|' '
  function trim(s){gsub(/^ +| +$/,"",s);return s}
  /^ *\| *code/ {for(i=1;i<=NF;i++){h=trim($i)
      if(h=="code")ci=i; else if(h=="name")ni=i; else if(h=="price")pi=i
      else if(h=="change_percent")gi=i; else if(h=="time")ti=i}
    hdr=1; next}
  hdr && /^ *\|/ && $0 !~ /---/ {c=trim($ci); p=trim($pi)
    if(c!="" && p ~ /^[0-9.]+$/) print c"|"trim($ni)"|"p"|"trim($gi)"|"trim($ti)}
' > "$QTMP"

# 节假日/数据滞后兜底：所有行情日期都不是今天 → 今天无盘中数据，静默退出（下分钟重试）
if [ "$FORCE" -eq 0 ] && ! grep -q "$TODAY" "$QTMP"; then exit 0; fi

# ---- 状态机：规则评估（below/above/zone）+ 内置 ±3% + 心跳 + 状态剪枝 ----
# 触发语义：below/above 只在"越过"时报（恢复后重新武装）；zone 只报"进入"；±3% 每代码每方向每日一次
# 去重：同一触发 30 分钟内不重复；发送失败不写状态 → 下一分钟自动重试
OUT=$(awk -v rules="$WATCH_CONF" -v qfile="$QTMP" -v sfile="$STATE_FILE" -v boxfile="$DAY_FILE" \
        -v today="$TODAY" -v now="$NOW" -v force="$FORCE" '
  BEGIN{
    while((getline L < rules)>0){
      if(L ~ /^#/ || L=="") continue
      split(L,f,"|"); if(f[1]!="watch") continue
      gsub(/ /,"",f[2]); gsub(/ /,"",f[4])
      n++; Rcode[n]=f[2]; Rcond[n]=f[3]; Rarg[n]=f[4]; Rlabel[n]=f[5]; Ract[n]=f[6]; Rsrc[n]="conf"
      if(f[3]=="pct" && f[4]+0>0) PCTth[f[2]]=f[4]+0
    }
    # 先收 PLAN（每票白话动作），再建 BOX 规则——PLAN 行可能写在 BOX 行之后，两遍读中间须 close 重开
    while((getline L < boxfile)>0){
      if(L ~ /^PLAN\|/){ split(L,f,"|"); if(f[2]!=""){ gsub(/^ +| +$/,"",f[2]); Pup[f[2]]=f[3]; Pdown[f[2]]=f[4] } }
    }
    close(boxfile)
    while((getline L < boxfile)>0){
      if(L ~ /^BOX\|/){ split(L,f,"|"); gsub(/ /,"",f[2]); gsub(/ /,"",f[3]); gsub(/ /,"",f[4])
        if(f[2]!="" && f[3]+0>0 && f[4]+0>0){
          ua=(f[2] in Pup)?Pup[f[2]]:"无预案动作记录：先看量价与箱体结构再定，拿不准就问管家"
          da=(f[2] in Pdown)?Pdown[f[2]]:"无预案动作记录：先看量价与箱体结构再定，拿不准就问管家"
          n++; Rcode[n]=f[2]; Rcond[n]="above"; Rarg[n]=f[4]; Rlabel[n]="突破当日箱体上沿 "f[4]; Ract[n]=ua; Rsrc[n]="box"
          n++; Rcode[n]=f[2]; Rcond[n]="below"; Rarg[n]=f[3]; Rlabel[n]="跌破当日箱体下沿 "f[3]; Ract[n]=da; Rsrc[n]="box"
        }
      }
    }
    while((getline L < qfile)>0){
      split(L,q,"|"); c=q[1]
      if(c=="" || c in Qprice) continue
      Qprice[c]=q[3]+0; Qname[c]=q[2]; Qraw[c]=q[3]; QchgS[c]=q[4]
      chg=q[4]+0; gsub(/%/,"",chg); Qchg[c]=chg
      d=q[5]; sub(/[ T].*$/,"",d); Qtime[c]=d
      qc++
    }
    while((getline L < sfile)>0){
      if(L=="") continue
      split(L,s," "); STst[s[1]]=s[2]; STep[s[1]]=s[3]+0
    }
    for(i=1;i<=n;i++){
      c=Rcode[i]; if(!(c in Qprice)) continue
      if(Qtime[c]!=today && force==0) continue
      p=Qprice[c]
      if(Rcond[i]=="pct"){
        th=Rarg[i]+0; if(th<=0) continue
        d=""; if(Qchg[c]>=th) d="up"; else if(Qchg[c]<=-th) d="down"
        if(d!=""){
          k=c"|pct"th d "@" today
          if(!(k in STst) || STst[k]!="hit"){
            STst[k]="hit"; STep[k]=now
          pa=(d=="down")?("下方预案→"(Pdown[c]?Pdown[c]:"这只票没写下方预案：先看当日箱体位置与量价再定，拿不准就问管家")):("上方预案→"(Pup[c]?Pup[c]:"这只票没写上方预案：先看当日箱体位置与量价再定，拿不准就问管家"))
            print "A|pct|"Qname[c]"|"c"|"Qraw[c]"|"QchgS[c]"|当日大动静（你设的 ±"th"%）|"pa
          }
        }
        continue
      }
      k=c"|"Rcond[i]":"Rarg[i]; if(Rsrc[i]=="box") k=k"@"today; trig=0
      if(Rcond[i]=="below"){
        trig=(p<=Rarg[i]+0)
        # ---- 除权跳空防护（2026-10-16 审计补）：行情说今天没怎么跌、价格却比线低 5% 以上 = 机械跳空特征 ----
        # 除权日腾讯行情的涨跌幅按除权后昨收计算（约等于 0），真实暴跌则同步显示大跌；两者在此可区分
        # 只防静态线（conf）：当日箱体（box）按除权后价格当天重画，天然对齐不受影响
        if(trig && Rsrc[i]!="box" && Qchg[c] > -4 && (Rarg[i]-p)/Rarg[i] > 0.05){
          trig=0
          kx=c"|xdskip@"today
          if(!(kx in STst)){ STst[kx]="hit"; STep[kx]=now
            print "A|xd|"Qname[c]"|"c"|"Qraw[c]"|"QchgS[c]"|疑似除权跳空（当日涨跌仅"QchgS[c]"但价格比线低 5% 以上）|这不是跌破，是分红送股后价格记账方式变了：该票所有旧价格线今日失效，止损警报自动暂停——等除权换算或重画新线后再恢复对照"
          }
          continue
        }
      }
      else if(Rcond[i]=="above"){ trig=(p>=Rarg[i]+0) }
      else if(Rcond[i]=="zone"){ split(Rarg[i],z,","); trig=(p>=z[1]+0 && p<=z[2]+0) }
      if(trig){
        want=(Rcond[i]=="zone")?"in":"hit"
        if(STst[k]!=want){
          if(now-STep[k]>1800){
            STst[k]=want; STep[k]=now
            print "A|rule|"Qname[c]"|"c"|"Qraw[c]"|"QchgS[c]"|"Rlabel[i]"|"Ract[i]
          }
          # 冷却期内（30 分钟）的再次触发不推送、也【不】改状态：保持 armed，
          # 否则"跌破→回升→再跌破"的 V 型里第二次跌破会被永久吞掉
        }
      } else STst[k]="armed"
    }
    # 内置异动兜底（默认 ±3%）：只为"没有写 pct 自定义规则"的代码生效——
    # 异动线也是私人参数，用户在 watch.conf 写 watch|<code>|pct|<阈值> 即按票覆盖（可更灵敏 2% 或更钝 5%）
    for(c in Qprice){
      if(Qtime[c]!=today && force==0) continue
      if(PCTth[c]) continue
      d=""; if(Qchg[c]>=3) d="up"; else if(Qchg[c]<=-3) d="down"
      if(d!=""){
        k=c"|pct3" d "@" today
        if(!(k in STst) || STst[k]!="hit"){
          STst[k]="hit"; STep[k]=now
          pa=(d=="down")?("下方预案→"(Pdown[c]?Pdown[c]:"这只票没写下方预案：先看当日箱体位置与量价再定，拿不准就问管家")):("上方预案→"(Pup[c]?Pup[c]:"这只票没写上方预案：先看当日箱体位置与量价再定，拿不准就问管家"))
print "A|pct|"Qname[c]"|"c"|"Qraw[c]"|"QchgS[c]"|当日大动静（默认 ±3%）|"pa
        }
      }
    }
    # 心跳：每次运行都打一行（用户 tail watch.log 即可确认 watchdog 活着，一天约 240 行）
    print "H|心跳 rules=" n " codes=" qc
    print "S_MARK"
    for(k in STst){
      if(k ~ /^#hb@/) continue
      if(index(k,"@")>0 && index(k,today)==0) continue
      if(STst[k]=="armed" && now-STep[k]>604800) continue
      print k" "STst[k]" "STep[k]
    }
  }')

HEART=$(printf '%s\n' "$OUT" | grep '^H|' | head -1 || true)
[ -n "$HEART" ] && log "watchdog ${HEART#H|}"
ALERTS=$(printf '%s\n' "$OUT" | grep '^A|' || true)
NEWSTATE=$(printf '%s\n' "$OUT" | sed -n '/^S_MARK$/,$p' | tail -n +2)

write_state(){ printf '%s\n' "$NEWSTATE" >"$STMP" && mv -f "$STMP" "$STATE_FILE" && chmod 600 "$STATE_FILE" 2>/dev/null; }
log_alerts_to_day(){ [ -x "$DAYLOG" ] && "$DAYLOG" append "警报" "$(printf '%s\n' "$ALERTS" | awk -F'|' '{printf "- %s（%s）现价 %s（当日%s）%s：%s\n",$3,$4,$5,$6,$7,$8}' | head -n 5)" >/dev/null 2>&1; return 0; }

if [ -z "$ALERTS" ]; then if [ "$DRY" -eq 1 ]; then echo '[dry-run] 无触发，不写状态'; else write_state; fi; exit 0; fi

# ---- 组装企微 markdown（结论前置 / 橙色警示 / 引用块详情；头部由发送器统一加 emoji 与标题）----
BODY=""
while IFS='|' read -r _ typ name code price chgS label action; do
  case "$chgS" in -*) de="📉";; *) de="📈";; esac
  if [ "$typ" = "pct" ]; then
    l1="$name（$code）当日 $chgS%，$label"; l2="现价 $price"
  else
    l1="$name（$code）现价 $price，$label"; l2="当日 $chgS%"
  fi
  BODY="$BODY

$de <font color=\"warning\">**$l1**</font>
> $l2 ｜ $TODAY
> 怎么办：$action"
done <<< "$ALERTS"

if [ "$DRY" -eq 1 ]; then printf '%s\n' "$BODY"; printf '[dry-run] 未发送、未写状态\n'; exit 0; fi

# ---- 发送（统一发送器负责凭据/markdown 头尾/超长截断/日志）；成功/未配置写状态，网络失败下一分钟重试 ----
"$SCRIPT_DIR/notify-webhook.sh" --title "盘中警报 $(date '+%H:%M')" --tag "警报" --body "$BODY" --require
RC=$?
if [ "$RC" -eq 0 ]; then
  log "警报已推送企微群：$(printf '%s\n' "$ALERTS" | awk -F'|' '{printf "%s(%s) ",$3,$4}')"
  write_state; log_alerts_to_day; exit 0
elif [ "$RC" -eq 2 ]; then
  log "webhook 未配置：警报仅留日志不推群（配 $SG_HOME/webhook.env 后自动启用）"
  write_state; log_alerts_to_day; exit 0
else
  log "警报推送失败（下一分钟自动重试）"
  exit 1
fi