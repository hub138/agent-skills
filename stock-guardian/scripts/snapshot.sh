#!/usr/bin/env bash
# stock-guardian 账户快照与熔断机械判定（roadmap P0：ACCT 账本自动化，2026-10-21 立）
# 每交易日 15:35 运行：读 holdings.conf 份数 → 逐票拉收盘 → 持仓市值/仓位/回撤/熔断 → ACCT 机器行落 day file + account.jsonl 累积
# holdings.conf 格式（每行）：code=份数（用户实报成交后更新）；现金记 CASH=元
# ACCT 行：ACCT|<日期>|<持仓市值>|<现金>|<总资产>|<仓位%>|<距高点回撤%>|<熔断状态>
# 熔断规则（rules.md 账户熔断）：净值高点回撤 ≥10% → 强制降半仓以下 + 停开新仓一周（机械判定，AI 到线必须拦）
set -u
SG="${SG_HOME:-$HOME/.stock-guardian}"
HOLD="$SG/holdings.conf"
ACCT="$SG/account.jsonl"
DAYFILE="$SG/day/$(date +%F).md"
[ -f "$HOLD" ] || { printf '# 账户持仓份数（用户实报成交后更新）\nCASH=0\n' > "$HOLD"; echo "holdings.conf 已初始化（默认现金 0，请实报修正）"; }
Q="$SG/scripts/quote-public.sh"; [ -f "$Q" ] || Q="${HOME}/.codebuddy/skills/stock-guardian/scripts/quote-public.sh"
declare -A POS; CASH=0
while IFS='=' read -r k v; do [[ "$k" =~ ^#|^$ ]] && continue; if [ "$k" = "CASH" ]; then CASH="$v"; else POS["$k"]="$v"; fi; done < "$HOLD"
total=0; lines=""
for c in "${!POS[@]}"; do
  R=$(bash "$Q" quote "$c" 2>/dev/null | tail -1)
  px=$(echo "$R" | awk -F'|' '{gsub(/ /,"",$7); print $7}')
  nm=$(echo "$R" | awk -F'|' '{gsub(/ /,"",$5); print $5}')
  shares="${POS[$c]}"; [ -z "$px" ] && { echo "$c 行情缺失跳过"; continue; }
  mv=$(awk -v p="$px" -v s="$shares" 'BEGIN{printf "%.0f", p*s}')
  total=$(awk -v a="$total" -v b="$mv" 'BEGIN{printf "%.0f", a+b}')
  lines="$lines$c($nm) ${shares}份×${px}=${mv}元｜"
done
[ -z "$CASH" ] && CASH=0
totalAsset=$(awk -v t="$total" -v c="$CASH" 'BEGIN{printf "%.0f", t+c}')
posPct=$(awk -v t="$total" -v a="$totalAsset" 'BEGIN{if(a>0) printf "%.1f", t/a*100; else print 0}')
peak=$(awk -F'|' '/^ACCT\|/{if($5+0>m)m=$5+0} END{printf "%.0f", m}' "$ACCT" 2>/dev/null)
peak=$(awk -v p="$peak" -v t="$totalAsset" 'BEGIN{printf "%.0f", (p>t?p:t)}')
dd=$(awk -v p="$peak" -v t="$totalAsset" 'BEGIN{if(p>0) printf "%.2f", (p-t)/p*100; else print 0}')
status="正常"
if awk -v d="$dd" 'BEGIN{exit !(d>=10)}'; then status="熔断触发：回撤${dd}%≥10%——降半仓以下+停开新仓一周（机械判定）"; fi
mkdir -p "$SG/day" "$SG/snapshots"
ACCTLINE="ACCT|$(date +%F)|$total|$CASH|$totalAsset|${posPct}%|${dd}%|$status"
printf '%s\n' "$ACCTLINE" >> "$ACCT"
[ -f "$DAYFILE" ] && printf '\n## 15:35 账户快照\n%s\n持仓：%s\n' "$ACCTLINE" "$lines" >> "$DAYFILE"
[ -f "$SG/portfolio.md" ] && cp "$SG/portfolio.md" "$SG/snapshots/portfolio.$(date +%F).md"
echo "$ACCTLINE"
echo "持仓明细：$lines"
