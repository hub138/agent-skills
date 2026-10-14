#!/usr/bin/env bash
# stock-guardian 公开源行情适配器：腾讯财经公开接口（qt.gtimg.cn），零密钥零账号零注册。
# 角色定位：westock-data 缺席时的行情后备通道，让本 skill 在未安装 westock-data 的机器上开箱即用。
# 优先级：westock-data 存在时一律用 westock（字段更全：换手率/量比/52周高低等），本脚本只做降级。
# 输出契约：与 westock-data quote 完全相同的 markdown 表格（同列名同列序），
#           watch.sh / monitor.sh 的解析逻辑零改动即可读；time 列必须填行情日期（watchdog 用它判数据新鲜度）。
# 覆盖范围：A股(sh/sz/bj)、港股(hk)、美股(us)。fx/ks/t* 公开接口无对应行情，降级模式明确说明不支持。
# 命令形态：quote-public.sh quote <code1,code2,...>   （只实现 quote，其余子命令一律提示走 westock-data）
# 用法示例：quote-public.sh quote sh600519,sz000001,hk00700,usAAPL
set -u

PATH="$PATH:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
WESTOCK="${WESTOCK:-$SKILLS_DIR/westock-data/scripts/index.js}"

SUB="${1:-}"; CODES="${2:-}"

if [ "$SUB" != "quote" ] || [ -z "$CODES" ]; then
  echo "用法：quote-public.sh quote <code1,code2,...>（子命令 $SUB 未实现，kline/news/notice 请安装 westock-data）"
  exit 1
fi

# westock-data 在场时把调用转给它（保持既有行为，避免两套数据源并行导致口径漂移）
if [ -f "$WESTOCK" ]; then
  exec node "$WESTOCK" "$SUB" "$CODES"
fi

# ---- 代码分类：公开接口按市场分批，批内逗号分隔一次请求 ----
CN=""; HK=""; US=""; UNSUP=""
IFS=',' read -ra ARR <<< "$CODES"
for c in "${ARR[@]}"; do
  c="${c// /}"
  case "$c" in
    sh*|sz*|bj*) CN="$CN$c," ;;
    hk*)        HK="$HK$c," ;;
    us*)        US="$US$c," ;;
    *)          UNSUP="$UNSUP $c" ;;
  esac
done
[ -n "$UNSUP" ] && echo "（⚠ 降级模式不支持 $UNSUP：公开接口无 fx/ks/t 行情，装 westock-data 后恢复）"

# ---- 表头（与 westock-data 对应市场表完全同列）----
print_cn_header(){
  printf '| code | market_type | market_name | name | symbol | price | prev_close | open | high | low | volume | amount | change | change_percent | turnover_rate | volume_ratio | range_pct | avg_price | time | wb_ratio | pe_ratio | pe_fwd | pe_lyr | pb_ratio | dividend_ratio_ttm | total_market_cap | circulating_market_cap | total_shares | float_shares | high_52week | low_52week | chg_5d | chg_10d | chg_20d | chg_60d | chg_ytd | price_ceiling | price_floor | inner_volume | outer_volume |\n'
  printf '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
}
print_us_header(){
  printf '| code | market_type | market_name | name | symbol | price | prev_close | open | high | low | volume | amount | change | change_percent | turnover_rate | volume_ratio | range_pct | avg_price | time | pe_ratio | pb_ratio | dividend_ratio_ttm | dividend_ttm | eps_ttm | total_market_cap | circulating_market_cap | total_shares | float_shares | high_52week | low_52week | chg_5d | chg_10d | chg_20d | chg_60d | chg_ytd | pre_market_price | pre_market_price_chg | pre_market_price_chg_pct | post_market_price | post_market_price_chg | post_market_price_chg_pct |\n'
  printf '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'
}

split_fields(){ printf '%s' "$1" | sed 's/^v_[a-zA-Z0-9._]*="//; s/";\r*$//'; }

# ---- A股行：腾讯 A股字段位（0 起）：1名 2码 3现价 4昨收 5今开 6量(手) 30时间戳yyyymmddHHMMSS 31涨跌 32涨跌% 33最高 34最低 37成交额(万) 38换手 39PE 43振幅 44流通市值(亿) 45总市值(亿) 46PB 47涨停 48跌停 ----
cn_row(){
  local f line="$1" prefix="$2" mtype="$3" mname="$4"
  f=$(split_fields "$line")
  local F; IFS='~' read -ra F <<< "$f"
  local t="${F[30]}"
  [ "${#t}" -ge 8 ] && t="${t:0:4}-${t:4:2}-${t:6:2}" || t=""
  printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
    "$prefix${F[2]}" "$mtype" "$mname" "${F[1]}" "$prefix${F[2]}" "${F[3]}" "${F[4]}" "${F[5]}" "${F[33]}" "${F[34]}" \
    "${F[6]}" "$(awk "BEGIN{printf \"%.0f\", ${F[37]:-0}*10000}")" "${F[31]}" "${F[32]}" "${F[38]}" "" "${F[43]}" "" "$t" "" \
    "${F[39]}" "" "${F[39]}" "${F[46]}" "" \
    "$(awk "BEGIN{printf \"%.0f\", ${F[44]:-0}*100000000}")" "$(awk "BEGIN{printf \"%.0f\", ${F[45]:-0}*100000000}")" "" "" "" "" "" "" "" "" "" "${F[47]}" "${F[48]}" "" ""
}

# ---- 港股行：腾讯港股字段位：1名 2码 3现价 4昨收 5今开 6量(股) 30时间"YYYY/MM/DD HH:MM:SS" 31涨跌 32涨跌% 33最高 34最低 37成交额 38换手(常0) 39PE 43振幅 44流通市值(亿) 45总市值(亿) 46英文名 47股息 48 52周高 49 52周低；无涨跌停 ----
hk_row(){
  local f F t
  f=$(split_fields "$1")
  IFS='~' read -ra F <<< "$f"
  t="${F[30]}"; t="${t%% *}"; t="${t//\//-}"
  printf '| hk%s | 100 | 港股 | %s | hk%s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
    "${F[2]}" "${F[1]}" "${F[2]}" "${F[3]}" "${F[4]}" "${F[5]}" "${F[33]}" "${F[34]}" "${F[6]}" "${F[37]}" \
    "${F[31]}" "${F[32]}" "${F[38]}" "" "${F[43]}" "" "$t" "" \
    "${F[39]}" "" "${F[39]}" "" "" \
    "$(awk "BEGIN{printf \"%.0f\", ${F[45]:-0}*100000000}")" "$(awk "BEGIN{printf \"%.0f\", ${F[44]:-0}*100000000}")" "" "" "${F[48]}" "${F[49]}" "" "" "" "" "" "" "" ""
}

# ---- 美股行：腾讯美股字段位：1名 2代码(带.OQ/.N) 3现价 4昨收 5今开 6量 30时间"YYYY-MM-DD HH:MM:SS" 31涨跌 32涨跌% 33最高 34最低 37成交额 38换手 39PE 43振幅 44流通市值(亿) 45总市值(亿) 48 52周高 49 52周低 ----
us_row(){
  local f F t code
  f=$(split_fields "$1")
  IFS='~' read -ra F <<< "$f"
  t="${F[30]}"; t="${t%% *}"
  code="us${F[2]%.*}"
  printf '| %s | 200 | 美股 | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
    "$code" "${F[1]}" "${F[2]}" "${F[3]}" "${F[4]}" "${F[5]}" "${F[33]}" "${F[34]}" "${F[6]}" "${F[37]}" \
    "${F[31]}" "${F[32]}" "${F[38]}" "" "${F[43]}" "" "$t" "" \
    "${F[39]}" "" "" "" "" \
    "$(awk "BEGIN{printf \"%.0f\", ${F[45]:-0}*100000000}")" "$(awk "BEGIN{printf \"%.0f\", ${F[44]:-0}*100000000}")" "" "" "${F[48]}" "${F[49]}" "" "" "" "" "" "" "" "" "" ""
}

FETCH_OK=0
fetch(){ curl -s -m 10 "https://qt.gtimg.cn/q=$1" 2>/dev/null | iconv -f GBK -t UTF-8 2>/dev/null; }

# ---- A股批（含北交所）----
if [ -n "$CN" ]; then
  RAW=$(fetch "${CN%,}") || RAW=""
  if [ -n "$RAW" ]; then print_cn_header; FETCH_OK=1; fi
  while IFS= read -r line; do
    case "$line" in
      v_sh*) cn_row "$line" "sh" "1" "上海主板" ;;
      v_sz*) cn_row "$line" "sz" "51" "深圳主板" ;;
      v_bj*) cn_row "$line" "bj" "71" "北交所" ;;
    esac
  done <<< "$RAW"
fi
# ---- 港股批 ----
if [ -n "$HK" ]; then
  RAW=$(fetch "${HK%,}") || RAW=""
  if [ -n "$RAW" ]; then print_cn_header; FETCH_OK=1; fi
  while IFS= read -r line; do
    case "$line" in v_hk*) hk_row "$line" ;; esac
  done <<< "$RAW"
fi
# ---- 美股批 ----
if [ -n "$US" ]; then
  RAW=$(fetch "${US%,}") || RAW=""
  if [ -n "$RAW" ]; then print_us_header; FETCH_OK=1; fi
  while IFS= read -r line; do
    case "$line" in
      v_us*=~*) us_row "$line" ;;
    esac
  done <<< "$RAW"
fi

[ "$FETCH_OK" -eq 0 ] && { echo "公开接口拉取失败（网络不可达或接口变更）；安装 westock-data 或检查网络"; exit 1; }
exit 0
