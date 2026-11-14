#!/usr/bin/env bash
# install-runtime-cron.sh — Phase 0 运行止血：用当前 node 绝对路径生成/更新 cron
#
# 职责（仅止血，不自动装 timing paper cron）：
#   1) 分钟级 watchdog：* * * * *（检测到既有 watch.sh 行则跳过，绝不新增重复 watch）
#   2) runtime-doctor 每日体检（08:02，错峰）：2 8 * * *
#   3) 把既有现役裸 node（stock-guardian proximity/trend/hub 等）按命令全文改写为当前 NODE_BIN 绝对路径
# 不自动安装 timing paper cron：timing-update.sh 需要必填代码参数，多持仓共用同一 marker 会互相覆盖，
# 须由用户按票手动运行（paper-only，不产生交易指令）。
# 幂等：以 # phase0:runtime 标记识别本脚本管理的行；重复运行只更新这些行，不动其他 cron。
# 安全：绝不调用 crontab 写命令（由用户/AI 平台执行安装），只生成/更新 crontab 文本。
# 用法：bash install-runtime-cron.sh [--sg-home <目录>] [--out <crontab文件>] [--dry-run] [--install]
#   --out      输出文件（缺省 ./crontab.phase0.txt；传入 --install 时可直接 crontab 该文件）
#   --dry-run  只打印将要写入的两行，不生成文件
#   --install  把生成结果与现有 crontab 合并后执行 crontab 命令（显式要求才装）
#   退出码：0=成功；2=参数/环境错误
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SG_HOME="${SG_HOME:-${HOME:-/root}/.stock-guardian}"
OUT=""
DRY_RUN=0
INSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sg-home) SG_HOME="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --install) INSTALL=1; shift ;;
    -h|--help) echo "用法: bash install-runtime-cron.sh [--sg-home <目录>] [--out <文件>] [--dry-run] [--install]"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

# ---- 解析当前 node 绝对路径（复用 watch.sh 的 PATH 补全逻辑）----
for _d in "$HOME"/.nvm/versions/node/*/bin /usr/local/bin /opt/node/bin; do
  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) PATH="$_d:$PATH";; esac
done
export PATH
NODE_BIN="$(command -v node || true)"
[ -n "$NODE_BIN" ] || { echo "[install-runtime-cron] 未找到 node，拒绝生成裸 node cron" >&2; exit 2; }
case "$NODE_BIN" in /*) ;; *) echo "[install-runtime-cron] node 不是绝对路径: $NODE_BIN" >&2; exit 2 ;; esac

# 2026-10-29 修：禁止静默切换 node 版本。PATH 解析出的 node 可能是另一个 nvm 版本
# （本机 PATH 曾解析到 v20 而线上 crontab 跑的是 v22），本脚本会用 CRON1/CRON3 整行替换，
# 一装就把现役 watchdog/doctor 换到别的运行时。策略：线上 crontab 已有绝对路径 node 则沿用。
if [ -z "${NODE_BIN_FORCE:-}" ]; then
  CUR_NODE="$(crontab -l 2>/dev/null | grep -oE '/[^ ]*/bin/node' | head -1 || true)"
  if [ -n "$CUR_NODE" ] && [ -x "$CUR_NODE" ] && [ "$CUR_NODE" != "$NODE_BIN" ]; then
    echo "[install-runtime-cron] 沿用线上 crontab 既有 node：$CUR_NODE（PATH 解析到 $NODE_BIN，不静默切换）" >&2
    NODE_BIN="$CUR_NODE"
  fi
fi

MARK="# phase0:runtime"
CRON1="* * * * * flock -n /tmp/stock-guardian-watch.lock timeout 60 bash $SCRIPT_DIR/watch.sh >> $SG_HOME/watch.log 2>&1 $MARK"
CRON3="2 8 * * * $NODE_BIN $SCRIPT_DIR/runtime-doctor.js --sg-home $SG_HOME >> $SG_HOME/doctor.log 2>&1 $MARK"
# CRON4（2026-10-29 立）：池票→watch.conf 自动挂线。此前池票靠人工回忆挂线，
# 池里有票而 watch.conf 没线 → 盘中穿越/破位零通知（池票静默故障复盘）。
# 纯本地读写、无网络调用，故全时段每 10 分钟跑，池一改线即生效。
CRON4="*/10 * * * * SG_HOME=$SG_HOME $NODE_BIN $SCRIPT_DIR/pool-watch-sync.js >> $SG_HOME/pool-sync.log 2>&1 && SG_HOME=$SG_HOME $NODE_BIN $SCRIPT_DIR/alerts-sync.js >> $SG_HOME/pool-sync.log 2>&1 && SG_HOME=$SG_HOME $NODE_BIN $SCRIPT_DIR/line-audit.js --notify >> $SG_HOME/pool-sync.log 2>&1 && SG_HOME=$SG_HOME $NODE_BIN $SCRIPT_DIR/hold-review.js >> $SG_HOME/pool-sync.log 2>&1 && SG_HOME=$SG_HOME $NODE_BIN $SCRIPT_DIR/coverage-audit.js --notify >> $SG_HOME/pool-sync.log 2>&1 $MARK"
# CRON5（2026-10-29 立）：开盘前 5 分钟覆盖体检 + 欠账推送。
# 由来（当天实测）：09:30:02 心跳 rules=1 codes=1 —— 开盘那一刻全市场只有 1 条线在册，
# 神华/卫星连"待扫描"都算不上，而体检只在 08:02 跑过一次且只落日志没人看。
# 09:25 再体检一次并把欠账推到群里，让"今天能盯到几只票"在开盘前就是明牌，而不是收盘后才发现。
CRON5="25 9 * * 1-5 SG_HOME=$SG_HOME $NODE_BIN $SCRIPT_DIR/coverage-audit.js --notify >> $SG_HOME/pool-sync.log 2>&1 $MARK"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] 将生成/更新以下五条 cron（node=$NODE_BIN，SG_HOME=$SG_HOME；timing paper cron 不自动安装）："
  printf '%s\n%s\n%s\n%s\n' "$CRON1" "$CRON3" "$CRON4" "$CRON5"
  exit 0
fi

OUT="${OUT:-./crontab.phase0.txt}"

# ---- 合并：保留现有 crontab 中非本脚本管理的行；两条 cron 以标记行整行替换 ----
EXISTING=""
if [ "$INSTALL" -eq 1 ]; then
  EXISTING="$(crontab -l 2>/dev/null || true)"
elif [ -f "$OUT" ]; then
  EXISTING="$(cat "$OUT")"
fi

TMP="$(mktemp)"
merge_crontab() {
  # $1 = 现有 crontab 文本（可为空）；$2 = 输出文件
  local existing="$1" out="$2" etmp has_wd
  etmp="$(mktemp)"
  printf '%s\n' "$existing" | awk -v m="$MARK" 'NF && $0 !~ m { print }' > "$etmp"

  # P0-2a：检测现有 crontab 中已含 watch.sh 的行——存在则跳过 CRON1，避免与既有 watchdog 双跑
  has_wd=0
  if grep -q 'watch\.sh' "$etmp"; then
    has_wd=1
    echo "[install-runtime-cron] 检测到既有 watchdog（watch.sh）cron 行，未重复安装 CRON1" >&2
  fi

  # P0-2b：现有行中的裸 node 改写为绝对路径（按命令全文匹配，含 flock/wrap 前缀形式）；其余行原样保留
  if [ -n "$existing" ]; then
    sed -E "s#(^|[;&|[:space:]])node([[:space:]]|\$)#\1$NODE_BIN\2#g" "$etmp"
  fi > "$out"
  {
    [ "$has_wd" -eq 1 ] || printf '%s\n' "$CRON1"
    printf '%s\n' "$CRON3"
    printf '%s\n' "$CRON4"
    printf '%s\n' "$CRON5"
  } >> "$out"
  rm -f "$etmp"
  [ "$has_wd" -eq 1 ] && echo "[install-runtime-cron] CRON1: 跳过（已有 watchdog）" || echo "[install-runtime-cron] CRON1: 已安装"
  return 0
}

merge_crontab "$EXISTING" "$OUT"
echo "[install-runtime-cron] 已生成 $OUT（node=$NODE_BIN；runtime-doctor 已装；裸 node 行已改写绝对路径；timing paper cron 不自动安装；其余行原样保留）"

# ---- 幂等自检：把输出再当作现有 crontab 跑一次合并，应产生完全相同内容 ----
TMP2="$(mktemp)"
merge_crontab "$(cat "$OUT")" "$TMP2" 2>/dev/null
if cmp -s "$OUT" "$TMP2"; then
  echo "[install-runtime-cron] 幂等自检通过（重复运行输出不变）"
else
  echo "[install-runtime-cron][WARN] 幂等自检未通过，请人工检查 $OUT" >&2
fi
rm -f "$TMP2"

if [ "$INSTALL" -eq 1 ]; then
  crontab "$OUT"
  echo "[install-runtime-cron] 已安装到当前用户 crontab（crontab -l 可核对）"
fi
