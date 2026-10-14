#!/usr/bin/env bash
# stock-guardian 监控脚本：纯工具，零用户数据。代码表来自 $HOME/.stock-guardian/portfolio.md，
# 由调用方（AI）传入，或从该档案的监控代码表自动解析。
# 用法:
#   ./monitor.sh                              # 自动解析 portfolio.md 代码表，跑全部组
#   ./monitor.sh 'sh600000,sz000001'          # 显式传任意代码列表，自动按市场类型拆批
#   ./monitor.sh group:美股                    # 按代码表"用途"列关键字过滤（如 group:美股/亚太/汇率/A股）
set -u
# 路径自解析（跨用户可移植）：monitor.sh 位于 <skills>/stock-guardian/scripts/，
# westock-data 在同级 skill 目录（兄弟目录）下；用户档案在 $HOME/.stock-guardian/；
# 三者都可用环境变量 WESTOCK / PORTFOLIO 覆盖
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"  # scripts -> stock-guardian -> skills 根
WESTOCK="${WESTOCK:-$SKILLS_DIR/westock-data/scripts/index.js}"
QUOTE_BIN="$SCRIPT_DIR/quote-public.sh"   # 公开源行情适配器：westock 缺席时的降级通道（A股/港股/美股可用，fx/ks/t 不支持）
PORTFOLIO="${PORTFOLIO:-$HOME/.stock-guardian/portfolio.md}"  # 用户数据在 skill 目录外，skill 可整体分发

# 行情拉取统一入口：westock 在场用它；缺席用公开源适配器（格式同 westock）
quote_fetch(){
  if [ -f "$WESTOCK" ]; then timeout 30 node "$WESTOCK" quote "$1" 2>/dev/null
  else bash "$QUOTE_BIN" quote "$1" 2>/dev/null
  fi
}
[ -f "$PORTFOLIO" ] || { echo "未找到用户档案 $PORTFOLIO 。首次使用请按 skill 的 portfolio.template.md 创建该文件（复制到 ~/.stock-guardian/portfolio.md 并填写），或用环境变量 PORTFOLIO 指定路径。"; exit 1; }
if [ ! -f "$WESTOCK" ]; then
  [ -f "$QUOTE_BIN" ] || { echo "未找到 westock-data（$WESTOCK）与公开源适配器（$QUOTE_BIN），两者皆缺无法拉行情"; exit 1; }
  echo "（降级模式：westock-data 缺失，走公开源——A股/港股/美股可用；fx/日韩/新闻/公告/K线不支持）"
fi

echo "=== stock-guardian 监控 $(date '+%Y-%m-%d %H:%M %A') ==="

arg="${1:-}"

# ---- 自动解析 portfolio.md 监控代码表（表格里形如 `sh600000, sz000001` 的单元格，
# ---- 单元格里可有中文注释如 `usXXXX.OQ（某美股ETF）`，只提取合法代码 token）----
parse_groups() {
  awk '
    /^\|/ && $0 !~ /用途|代码|---/ {
      n=split($0, cells, "|")
      label=""; codes=""
      for(i=2; i<=n; i++) {
        c=cells[i]; gsub(/ /, "", c)
        if(c == "") continue
        if(label=="") { label=c; continue }
        # 去掉中文括号注释，按逗号/空白切 token，只留合法代码（小写市场前缀+字母数字点号）
        gsub(/（[^）]*）/,",",c); gsub(/[,;，；\t]/,",",c)
        m=split(c, toks, ",")
        for(j=1;j<=m;j++) {
          t=toks[j]
          if(t ~ /^(sh|sz|bj|us|ks|kq|t|fx)[0-9A-Za-z.]+$/) codes=codes t ","
        }
      }
      if(codes != "") print label "\t" codes
    }
  ' "$PORTFOLIO" 2>/dev/null
}

# ---- 按市场类型拆批：A股(sh/sz/bj) 一批；港股(hk*) 一批；美股(us*) 一批；日韩(ks*/t*) 一批；汇率(fx*) 单独 ----
quote_batched() {
  local codes="$1" label="$2"
  [ -z "$codes" ] && return 0
  local cn="" hk="" us="" asia="" fx=""
  IFS=',' read -ra arr <<< "$codes"
  for c in "${arr[@]}"; do
    # 格式预警（只提醒不拦截）：westock 对无效代码会静默丢弃——宁可吵，不可瞎。
    # 注意必须 LC_ALL=C：bash/grep 的 [a-z] 在 UTF-8 locale 下按 collation 会匹配到大写，
    # 曾经把合法的 fxUSDJPY 误报成"疑似无效"。
    case "$c" in
      ks*|kq*) [ "${#c}" -ne 8 ] && echo "$c" | LC_ALL=C grep -qE '^(ks|kq)[0-9]+$' && echo "（⚠ 疑似无效韩股代码 $c：韩股为 ks/kq+6位数字（如 ks005930），无效代码会被数据源静默丢弃）" ;;
      fx*)    echo "$c" | LC_ALL=C grep -qE '^fx[a-z]' && echo "（⚠ 疑似无效汇率代码 $c：汇率代码为全大写（如 fxUSDJPY/fxCNH），无效代码会被数据源静默丢弃）" ;;
    esac
    case "$c" in
      sh*|sz*|bj*)  cn="$cn$c," ;;
      hk*)          hk="$hk$c," ;;
      us*)          us="$us$c," ;;
      ks*|kq*|t*)   asia="$asia$c," ;;
      fx*)          fx="$fx$c," ;;
      *)            echo "（未知市场类型，跳过: $c）" ;;
    esac
  done
  echo "--- $label ---"
  [ -n "$cn" ]   && { quote_fetch "${cn%,}"   || echo "A股数据拉取失败"; }
  [ -n "$hk" ]   && { quote_fetch "${hk%,}"   || echo "港股数据拉取失败"; }
  [ -n "$us" ]   && { quote_fetch "${us%,}"   || echo "美股数据拉取失败"; }
  [ -n "$asia" ] && { quote_fetch "${asia%,}" || echo "日韩数据拉取失败（降级模式不支持日韩，装 westock-data 恢复）"; }
  [ -n "$fx" ]   && { quote_fetch "${fx%,}"   || echo "汇率数据拉取失败（降级模式不支持汇率，装 westock-data 恢复）"; }
}

# ---- 入口分发 ----
if [ -z "$arg" ]; then
  # 无参数：自动解析监控代码表，逐组拉取
  parse_groups | while IFS=$'\t' read -r label codes; do
    quote_batched "${codes%,}" "$label"
    echo ""
  done
elif [[ "$arg" == group:* ]]; then
  g="${arg#group:}"
  if ! parse_groups | grep -qi "$g"; then
    echo "监控代码表里没有匹配 '$g' 的组，检查 portfolio.md 或直接传代码列表"
    exit 1
  fi
  parse_groups | grep -i "$g" | while IFS=$'\t' read -r label codes; do
    quote_batched "${codes%,}" "$label"
    echo ""
  done
elif [[ "$arg" == *,* ]] || [[ "$arg" =~ ^(sh|sz|bj|us|ks|t|fx) ]]; then
  quote_batched "$arg" "自定义代码组"
else
  echo "无法识别参数 '$arg'。用法：无参自动解析 / '代码1,代码2' / group:us|asia|cn"
  exit 1
fi
