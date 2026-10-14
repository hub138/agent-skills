#!/usr/bin/env bash
# stock-guardian 群通知发送器：纯工具层，零用户数据，随 skill 整体分发。
# 本 skill 的所有推群通知统一走这里：定时场景结果、盘中警报、操作思路、
# 买入/卖出建议、做T方案、成交落档确认、装机测试消息。
# 通知渠道（2026-10-15 泛化）：WECHAT_WEBHOOK_URL 支持企微群机器人 / 钉钉群机器人（含加签）/ 
#   飞书群机器人 / Bark（iOS 推送）任一种，按 URL 特征自动选择消息格式；存量 WECOM_WEBHOOK_URL
#   变量名继续兼容（读档顺序：环境变量 → webhook.env，两个名字都认）。
#   正文格式差异由发送器吸收：钉钉/飞书把 <font> 标签剥成纯文本，Bark 只发标题+纯文本正文。
# 凭据：$HOME/.stock-guardian/webhook.env 里 WECHAT_WEBHOOK_URL='...'（权限 600，
#       永不写进 skill 目录/日志/任何文件）；删除该文件即停用本通道。
# 用法：notify-webhook.sh --title "标题" [--tag 警报|操作思路|买入|卖出|做T|成交|场景名|测试]
#                        [--body "正文"] [--require] [--dry-run]
# v2 格式加固（2026-10-14 通知排版专项）：
#   1. 头部自动加语义 emoji（tag→emoji 映射，未收录用 📣）；
#   2. --title 智能去重：剥掉误带的"股票管家"前缀/重复 tag，杜绝"股票管家·操作思路｜股票管家·xxx"复读；
#   3. 正文换行复原（node 实现，多字节安全，node 缺失时原样保留）：<br>/\r/字面 \n → 真换行；
#      两侧非字母的裸 n/nn（AI 坏习惯产物）→ 真换行；行修剪；连续空行压成一行；
#   4. 空正文兜底"✅ 详情见标题"；5. 超长按行边界截断（结论在前，保头舍尾）；6. 脚注带 ⏱。
#   正文支持企微 markdown（**粗体**、<font color="info|comment|warning">、> 引用、列表），
#   可由 --body 传入或从 stdin 读入；超长自动截断；发送失败写 $HOME/.stock-guardian/webhook.log。
#   --require：未配置 webhook 时 exit 2（调用方需要区分"已发送/未配置"时用）；
#   默认未配置时静默跳过 exit 0（适配没配 webhook 的机器，skill 逻辑层不感知差异）。
set -u

SG_HOME="${SG_HOME:-$HOME/.stock-guardian}"

# ---- cron 环境 PATH 补全：系统 crontab 的 PATH 通常只有 /usr/bin:/bin，会缺两样东西 ----
#   1) nvm 等用户目录装的 node（本脚本用它组装 JSON，缺了推送必失败）
#   2) /usr/local/bin 里的正常 curl（部分系统 /usr/bin/curl 二进制与 libcurl 版本错配，任何请求都失败）
# 无条件前置（幂等去重，交互环境无副作用），分发到任何机器都稳。
for _d in "$HOME"/.nvm/versions/node/*/bin /usr/local/bin /opt/node/bin; do
  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) PATH="$_d:$PATH";; esac
done
export PATH

LOG_FILE="${SG_HOME}/webhook.log"
TITLE=""; TAG=""; BODY=""; DRY=0; REQUIRE=0
while [ $# -gt 0 ]; do
  KEY=""; VAL=""
  case "$1" in
    --title|--tag|--body) KEY="$1"; shift; if [ $# -gt 0 ]; then VAL="$1"; shift; fi ;;
    --dry-run) DRY=1; shift ;;
    --require) REQUIRE=1; shift ;;
    *) shift ;;
  esac
  case "$KEY" in
    --title) TITLE="$VAL" ;;
    --tag) TAG="$VAL" ;;
    --body) BODY="$VAL" ;;
  esac
done
[ -n "$TITLE" ] || TITLE="通知"

# stdin 兜底（仅管道/重定向文件，避免挂在终端上；必须在正文规范化之前）
if [ -z "$BODY" ] && { [ -p /dev/stdin ] || [ -f /dev/stdin ]; }; then BODY=$(cat); fi

# ---- tag → 语义 emoji（通知头的视觉锚点，手机通知栏一眼区分场景）----
emoji_of_tag(){
  case "$1" in
    警报) printf '🚨' ;;
    操作思路) printf '💡' ;;
    荐股) printf '🎯' ;;
    买入) printf '🟢' ;;
    卖出) printf '🔴' ;;
    做T) printf '🔁' ;;
    成交) printf '✅' ;;
    早报) printf '🌅' ;;
    亚太早巡) printf '🌏' ;;
    开盘快照) printf '📷' ;;
    箱体确认) printf '📐' ;;
    午间检查) printf '🍜' ;;
    盘中巡检) printf '🔍' ;;
    尾盘决策) printf '🌇' ;;
    美股开盘报) printf '🗽' ;;
    美股半场报) printf '🌓' ;;
    美股收盘报) printf '🌙' ;;
    测试) printf '🧪' ;;
    *) printf '📣' ;;
  esac
}

# ---- title 去重：剥误带的"股票管家"前缀与开头重复的 tag，防止头部复读 ----
strip_title(){
  local t="$1" tag="$2"
  while :; do
    case "$t" in
      股票管家·*|股票管家\ *|股票管家｜*) t="${t#股票管家}" ;;
      *) break ;;
    esac
  done
  case "$t" in ·*|｜*|\|*) t="${t:1}" ;; esac
  if [ -n "$tag" ]; then
    case "$t" in
      "$tag"｜*|"$tag"·*|"$tag"\|*|"$tag"\ *)
        t="${t#"$tag"}"
        case "$t" in ｜*|·*|\|*\ *\ ) t="${t:1}" ;; esac ;;
    esac
  fi
  printf '%s' "$t"
}

EMOJI=$(emoji_of_tag "$TAG")
TITLE_C=$(strip_title "$TITLE" "$TAG")

# ---- 正文规范化：换行复原 + 行修剪 + 空行压缩（node 实现，多字节安全；node 缺失时尽量保真）----
if command -v node >/dev/null 2>&1; then
  BODY_NORM=$(printf '%s' "$BODY" | node -e '
let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
  s=s.replace(/\r/g,"\n");
  s=s.replace(/\\n/g,"\n").replace(/<br\s*\/?>/gi,"\n");
  s=s.replace(/(^|[^a-zA-Z])([nN]{1,2})(?![a-zA-Z])/g,(m,p,ns)=>p+"\n".repeat(ns.length));
  s=s.split("\n").map(l=>l.trim()).filter(l=>l!=="").join("\n\n");
  s=s.trim();
  if(!s) s="✅ 详情见标题";
  process.stdout.write(s);
})' 2>/dev/null) || BODY_NORM=""
else
  BODY_NORM="$BODY"
fi
[ -n "$BODY_NORM" ] || BODY_NORM="$BODY"
[ -n "$BODY_NORM" ] || BODY_NORM="✅ 详情见标题"

log(){ mkdir -p "$SG_HOME" 2>/dev/null; echo "$(date '+%F %T') $*" >>"$LOG_FILE"; }
# 日志自截断（>100KB 保留末 200 行）
if [ -f "$LOG_FILE" ] && [ "$(wc -c <"$LOG_FILE" 2>/dev/null || echo 0)" -gt 102400 ]; then
  tail -n 200 "$LOG_FILE" >"$LOG_FILE.tmp" 2>/dev/null && mv -f "$LOG_FILE.tmp" "$LOG_FILE"
fi

# ---- 组装：头（emoji 股票管家·tag｜去重标题）+ 正文 + 灰色脚注 ----
HEAD="${EMOJI} **股票管家${TAG:+·$TAG}**"
[ -n "$TITLE_C" ] && HEAD="$HEAD｜$TITLE_C"

FOOT="<font color=\"comment\">⏱ $(date '+%m-%d %H:%M') 自动推送</font>"

MSG="$HEAD

$BODY_NORM

$FOOT"

# ---- 超长截断：按行边界保头舍尾（结论在前，截尾不截头；给脚注留 60 字节余量）----
if [ "$(printf '%s' "$MSG" | wc -c)" -gt 3800 ]; then
  MSG=$(printf '%s\n' "$MSG" | head -n -3)
  while [ -n "$MSG" ] && [ "$(printf '%s' "$MSG" | wc -c)" -gt 3700 ]; do
    MSG=$(printf '%s\n' "$MSG" | head -n -1)
  done
  MSG="$MSG

<font color=\"comment\">…后面还有内容，看聊天全文</font>

$FOOT"
fi

# dry-run 优先于凭据检查：没配 webhook 的机器也要能预验消息格式（打印后即退出，不读凭据不发送）
if [ "$DRY" -eq 1 ]; then printf '%s\n' "$MSG"; echo '[dry-run] 未发送'; exit 0; fi

# ---- 读凭据：环境变量优先，其次 webhook.env；两者皆无 = 通道停用 ----
# 变量名双兼容：新 WECHAT_WEBHOOK_URL（任意渠道），旧 WECOM_WEBHOOK_URL（企微时代名字）
URL="${WECHAT_WEBHOOK_URL:-${WECOM_WEBHOOK_URL:-}}"
if [ -z "$URL" ] && [ -f "$SG_HOME/webhook.env" ]; then . "$SG_HOME/webhook.env"; URL="${WECHAT_WEBHOOK_URL:-${WECOM_WEBHOOK_URL:-}}"; fi
if [ -z "$URL" ]; then
  if [ "$REQUIRE" -eq 1 ]; then echo "webhook 未配置（$SG_HOME/webhook.env 缺 WECHAT_WEBHOOK_URL）" >&2; exit 2; fi
  echo "webhook 未配置，跳过推送（删除/缺失 webhook.env 即停用通道）" >&2
  log "skip：未配置 webhook"
  exit 0
fi

# ---- 按渠道组装并发送：企微(qyapi.weixin.qq.com) markdown；钉钉(oapi.dingtalk.com) text；
#      飞书(open.feishu.cn) text；Bark(api.day.app / bark.day.app) 标题+正文 ----
send_notify(){
  local url="$1" msg="$2" payload resp
  case "$url" in
    *qyapi.weixin.qq.com*)
      payload=$(printf '%s' "$msg" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(JSON.stringify({msgtype:"markdown",markdown:{content:s}})))' 2>/dev/null)
      resp=$(curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "$url" 2>/dev/null)
      case "$resp" in *'"errcode":0'*|*'"errcode": 0'*) return 0;; esac ;;
    *oapi.dingtalk.com*)
      # 钉钉机器人多数开了加签：URL 里带 &access_token=... 可直接用；加签密钥另配 DINGTALK_SECRET 时自动补 timestamp&sign
      local ts sign query="$url"
      if [ -n "${DINGTALK_SECRET:-}" ]; then
        ts=$(date +%s%3N)
        sign=$(printf '%s\n' "$ts" "$DINGTALK_SECRET" | openssl dgst -sha256 -hmac "$DINGTALK_SECRET" -binary 2>/dev/null | base64 | sed 's/+/%2B/g; s/\//%2F/g; s/=/%3D/g')
        query="${query}&timestamp=${ts}&sign=${sign}"
      fi
      local plain; plain=$(printf '%s' "$msg" | sed 's/<font color="[^"]*">//g; s/<\/font>//g; s/\*\*//g')
      payload=$(printf '【股票管家】%s' "$plain" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(JSON.stringify({msgtype:"text",text:{content:s}})))' 2>/dev/null)
      resp=$(curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "$query" 2>/dev/null)
      case "$resp" in *'"errcode":0'*|*'"errcode": 0'*) return 0;; esac ;;
    *open.feishu.cn*)
      local plain; plain=$(printf '%s' "$msg" | sed 's/<font color="[^"]*">//g; s/<\/font>//g; s/\*\*//g')
      payload=$(printf '%s' "$plain" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(JSON.stringify({msg_type:"text",content:{text:s}})))' 2>/dev/null)
      resp=$(curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "$url" 2>/dev/null)
      case "$resp" in *'"StatusCode":0'*|*'"code":0'*) return 0;; esac ;;
    *bark*|*api.day.app*)
      local title="股票管家通知" body; body=$(printf '%s' "$msg" | sed 's/<font color="[^"]*">//g; s/<\/font>//g; s/\*\*//g')
      payload=$(printf '【股票管家】%s' "$body" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(JSON.stringify({title:s,body:"股票管家通知，见群或日志"})))' 2>/dev/null)
      resp=$(curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "${url%/}" 2>/dev/null)
      case "$resp" in *'"code":200'*) return 0;; esac ;;
    *)
      # 通用 JSON POST（自定义网关）：把消息按 markdown JSON 发过去，200 即成功
      payload=$(printf '%s' "$msg" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(JSON.stringify({msgtype:"markdown",markdown:{content:s}})))' 2>/dev/null)
      resp=$(curl -s -m 10 -H 'Content-Type: application/json' -d "$payload" "$url" 2>/dev/null)
      case "$resp" in *'errcode'*|*'"code":0'*) return 0;; esac
      [ -n "$resp" ] && return 0 ;;
  esac
  return 1
}

if send_notify "$URL" "$MSG"; then
  log "已推群 [$TAG] $TITLE"; exit 0
else
  log "推送失败 [$TAG] $TITLE：${RESP:-无响应}"
  echo "webhook 推送失败：${RESP:-无响应}" >&2; exit 1
fi
