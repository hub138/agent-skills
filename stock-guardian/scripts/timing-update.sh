#!/usr/bin/env bash
# timing-update.sh — Phase 0 paper-only 版（危险 writer 已下线）
#
# REBUILD-SPEC.md §13 Phase 0「暂停危险 timing writer」要求：
#  1) 不再写 watch.conf 的主动买卖 watch 行（旧版会整文件追加择时 watch 线，属未验证自动指令源）；
#  2) 只做"marker 区块替换"：market-timing 区块整体替换，绝不动 marker 外任何行；
#  3) 未验证自动买入降为 paper：本脚本输出 PAPER_TIMING 机器行到 stdout（也可重定向到 day file），
#     状态只做 paper 观察，不构成交易指令。
#
# 用法：bash timing-update.sh <代码> [--sg-home <目录>] [--dry-run]
#   SG_HOME 缺省 $SG_HOME 环境变量 → $HOME/.stock-guardian（Phase 0 不主动创建生产目录）。
#   --dry-run：只打印将要写入的区块与 PAPER_TIMING 行，不落盘。
set -euo pipefail

# ---- 参数解析 ----
CODE=""
SG_HOME="${SG_HOME:-${HOME:-/root}/.stock-guardian}"
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sg-home) SG_HOME="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) echo "用法: bash timing-update.sh <代码> [--sg-home <目录>] [--dry-run]"; exit 0 ;;
    *) if [ -z "$CODE" ]; then CODE="$1"; shift; else echo "未知参数: $1" >&2; exit 2; fi ;;
  esac
done
[ -n "$CODE" ] || { echo "用法: bash timing-update.sh <代码> [--sg-home <目录>] [--dry-run]" >&2; exit 2; }

# cron 环境 PATH 补全（同 watch.sh：nvm node / 正常 curl）
for _d in "$HOME"/.nvm/versions/node/*/bin /usr/local/bin /opt/node/bin; do
  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) PATH="$_d:$PATH";; esac
done
export PATH

WC="$SG_HOME/watch.conf"

# ---- marker 区块定义（Phase 0 paper 区块）----
# P0-1：BEGIN/END 采用【整行全等】匹配（x 全行），杜绝前缀正则误删用户手抄留档行
M_BEGIN='# === market-timing paper BEGIN（Phase 0：paper-only，不构成交易指令）==='
M_END='# === market-timing paper END ==='

# ---- 拉 K 线（只读，失败不写任何文件）----
KJSON=$(curl -fsS --retry 2 --max-time 12 \
  -A 'Mozilla/5.0' \
  -e 'http://stock.finance.qq.com/' \
  "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${CODE},day,,,640,qfq") || {
  echo "[timing-update] K线拉取失败，本次不写任何文件"; exit 2;
}

# ---- 计算并生成 paper 区块 + PAPER_TIMING 机器行 ----
BLOCK=$(node -e '
const code = process.argv[1];
const j = JSON.parse(process.argv[2]);
const k = (j.data[code].qfqday || j.data[code].day).map(x => ({ d: x[0], c: +x[2] }));
if (k.length < 65) { console.error("[timing-update] 数据不足 65 根，跳过"); process.exit(3); }
const avg = a => a.reduce((x, y) => x + y, 0) / a.length;
const last = k.at(-1).c, lastD = k.at(-1).d;
const ma20 = avg(k.slice(-20).map(x => x.c));
const ma60 = avg(k.slice(-60).map(x => x.c));
const above20 = last > ma20, above60 = last > ma60;
const state = above20 && above60 ? "双上=paper持有口径" : (!above20 && !above60 ? "双下=paper观察仓口径" : "混合=维持上一状态");
console.log("# === market-timing paper BEGIN（Phase 0：paper-only，不构成交易指令）===");
console.log("# 本区块由 timing-update.sh 生成：只做 paper 观察记录，不写 watch.conf 主动买卖线，不触发任何交易指令");
console.log(`PAPER_TIMING|${code}|${lastD}|close=${last}|MA20=${ma20.toFixed(3)}|MA60=${ma60.toFixed(3)}|state=${state}`);
console.log("# === market-timing paper END ===");
' "$CODE" "$KJSON")

# PAPER_TIMING 行（区块内唯一机器行，供测试与下游读取）
PT_LINE=$(printf '%s\n' "$BLOCK" | grep '^PAPER_TIMING|' || true)

# ---- dry-run：打印不落盘 ----
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] 将替换 ${WC} 中 market-timing paper 区块（marker 外零改动）"
  printf '%s\n' "$BLOCK"
  exit 0
fi

# ---- marker 区块替换：只动 BEGIN..END 之间，绝不能删除 marker 外任何行 ----
if [ -f "$WC" ]; then
  # P0-1 成对校验：BEGIN/END 必须整行全等；0/0=尚无区块走追加；恰好 1/1=替换；其余（不成对/重复）=拒写
  NB=$(grep -Fxc "$M_BEGIN" "$WC" || true); NB=${NB:-0}
  NE=$(grep -Fxc "$M_END" "$WC" || true); NE=${NE:-0}
  if [ "$NB" -eq 0 ] && [ "$NE" -eq 0 ]; then
    TMP=$(mktemp)
    { cat "$WC"; printf '\n%s\n' "$BLOCK"; } > "$TMP"
    mv -f "$TMP" "$WC"
    echo "[timing-update] paper-only 区块已追加（无既有区块，marker 外零改动）"
    printf '%s\n' "$PT_LINE"
    exit 0
  fi
  if [ "$NB" != "1" ] || [ "$NE" != "1" ]; then
    echo "[timing-update][ERROR] marker 不成对（BEGIN=$NB, END=$NE，要求各恰好 1），拒写以免误删数据" >&2
    exit 2
  fi
  TMP=$(mktemp)
  # 用 awk 做区块整体替换：全行全等命中 BEGIN/END；其余所有行（含用户手抄留档）原样保留
  awk -v nb="$BLOCK" -v mb="$M_BEGIN" -v me="$M_END" '
    $0 == mb { if(!printed){ printf "%s\n", nb; printed=1 }; inblk=1; next }
    inblk && $0 == me { inblk=0; next }
    !inblk { print }
    END { if (inblk || !printed) exit 9 }
  ' "$WC" > "$TMP" || { rm -f "$TMP"; echo "[timing-update][ERROR] 区块结构异常，未写盘" >&2; exit 2; }
  mv -f "$TMP" "$WC"
else
  # 新文件：只含区块
  printf '%s\n' "$BLOCK" > "$WC"
fi

echo "[timing-update] paper-only 区块已更新（marker 外零改动）"
printf '%s\n' "$PT_LINE"
