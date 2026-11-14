#!/usr/bin/env bash
# 长任务看门狗：定时检查后台 Agent 会话是否还活着，挂了就带原会话重新拉起继续干。
# 配置全部在 jobs.json：一个会话可以配多条提示词，按顺序或轮换执行。
#
# 用法：
#   watchdog.sh                 检查所有任务（crontab 用它）
#   watchdog.sh <任务名>         只检查某一个
#   watchdog.sh status          打印各任务状态，不做任何拉起
#   watchdog.sh install-cron    按 jobs.json 里的 cron_interval_minutes 装 crontab

set -uo pipefail

# SCRIPT_DIR 是 skill 的安装位置（只读、可公开）；WATCHDOG_HOME 是你的数据位置（私有、不要公开）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_HOME="${WATCHDOG_HOME:-$HOME/.codebuddy/watchdog}"
JOBS_FILE="$WATCHDOG_HOME/jobs.json"
STATE_DIR="$WATCHDOG_HOME/state"
LOG_DIR="$WATCHDOG_HOME/logs"
GEN_DIR="$STATE_DIR/gen"

mkdir -p "$STATE_DIR" "$LOG_DIR"

# cron 的 PATH 很窄，这里把 node / codebuddy 的位置补进去，保证 cron 下也能找到
if ! command -v node >/dev/null 2>&1; then
  NODE_VER="$(ls "$HOME/.nvm/versions/node" 2>/dev/null | tail -1)"
  [ -n "$NODE_VER" ] && export PATH="$PATH:$HOME/.nvm/versions/node/$NODE_VER/bin"
  export PATH="$PATH:$HOME/.local/bin:/usr/local/bin"
fi
export LANG="${LANG:-C.UTF-8}"
NODE_BIN="${NODE_BIN:-node}"
CB_BIN="${CB_BIN:-codebuddy}"

# 任务没配 prompts 时用的兜底指令。{DONE_FILE} 会被换成该任务实际的完成标记路径。
DEFAULT_PROMPT='继续执行上次未完成的任务：先读取本目录下的进度记录与最近一次产出，判断当前处于哪一步，从首个未完成或已失效的步骤继续，不要重复已完成的部分。每完成一步就把结果写回进度记录。全部做完后，创建文件 {DONE_FILE} 作为完成标记，然后停手。'

now() { date +%s; }
ts() { date '+%F %T'; }

# 单实例锁：上一轮还没跑完时，这一轮直接退出，避免重复拉起
exec 9>"$STATE_DIR/watchdog.lock"
if ! flock -n 9; then
  echo "[$(ts)] 上一轮看门狗还没结束，本轮跳过"
  exit 0
fi

watchlog="$LOG_DIR/watchdog.log"
wlog() { echo "[$(ts)] $*" >> "$watchlog"; }

# 把 jobs.json 翻译成 bash 好读的形态（改完配置立即生效，不用重启任何东西）
"$NODE_BIN" "$SCRIPT_DIR/parse-jobs.mjs" "$WATCHDOG_HOME" >/dev/null || {
  echo "[$(ts)] jobs.json 解析失败，看门狗退出" >> "$watchlog"
  exit 1
}

alive() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

# 杀进程组：wrapper 是 setsid 出来的组长，这样能带上它的子进程一起收掉
kill_group() {
  local pid="$1"
  kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  sleep 3
  kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
}

check_job() {
  local job="$1"
  local metafile="$GEN_DIR/$job.meta"
  [ -f "$metafile" ] || { echo "[$(ts)] $job: 没有这个任务"; return 1; }

  JOB_NAME=""; JOB_SESSION_ID=""; JOB_WORKDIR=""; JOB_MODEL=""; JOB_EXTRA_ARGS=""
  JOB_CHECK_INTERVAL_MINUTES=5; JOB_STALE_MINUTES=0; JOB_MAX_RESTARTS=20   # STALE 默认 0：-p 输出要等结束才刷，开假死判定会误杀
  JOB_RESTART_COOLDOWN_SECONDS=60; JOB_PROMPT_MODE="step"; JOB_DONE_FILE=""; JOB_SANDBOX=1; JOB_SESSION_ROLLOVER=6
  JOB_PROMPT_COUNT=0; JOB_PROMPTS_DIR=""
  # shellcheck disable=SC1090
  source "$metafile"

  local pidfile="$STATE_DIR/$job.pid"
  local exitfile="$STATE_DIR/$job.exit"
  local stepfile="$STATE_DIR/$job.step"
  local cntfile="$STATE_DIR/$job.restarts"
  local chkfile="$STATE_DIR/$job.lastcheck"
  local startfile="$STATE_DIR/$job.laststart"
  local runlog="$LOG_DIR/$job.run.log"
  local done_file="$JOB_DONE_FILE"
  [ -z "$done_file" ] && done_file="$STATE_DIR/$job.DONE"

  # ---- 已完成的不再拉起 ----
  if [ -e "$done_file" ]; then return 0; fi

  # ---- 每任务的检查节流 ----
  local t lastchk
  t="$(now)"
  lastchk="$(cat "$chkfile" 2>/dev/null || echo 0)"
  if [ "$JOB_CHECK_INTERVAL_MINUTES" -gt 0 ] && [ $(( t - lastchk )) -lt $(( JOB_CHECK_INTERVAL_MINUTES * 60 )) ]; then
    return 0
  fi
  echo "$t" > "$chkfile"

  local pid step cnt ec
  pid="$(cat "$pidfile" 2>/dev/null || echo "")"
  step="$(cat "$stepfile" 2>/dev/null || echo 0)"
  cnt="$(cat "$cntfile" 2>/dev/null || echo 0)"
  ec="$(cat "$exitfile" 2>/dev/null || echo "")"

  # ---- 判活：进程没了 / 进程在但日志不动（假死） ----
  local state="running"
  if ! alive "$pid"; then
    state="dead"
  elif [ "$JOB_STALE_MINUTES" -gt 0 ] && [ -f "$runlog" ]; then
    local lastmod elapsed
    lastmod="$(stat -c %Y "$runlog" 2>/dev/null || echo 0)"
    elapsed=$(( t - lastmod ))
    if [ "$elapsed" -gt $(( JOB_STALE_MINUTES * 60 )) ]; then state="stale(${elapsed}s)"; fi
  fi

  if [ "$state" = "running" ]; then return 0; fi

  # ---- 限额等待：Agent 遇到限流会把解除时间戳写进来，没到点不拉起，避免空转烧尝试 ----
  # 2026-10-27 教训：Agent 可能把子代理的瞬时限流当成配额耗尽，写入 20 小时外的远期时间戳，
  # 导致整晚停摆。看门狗侧封顶：无论写多远，最多等 30 分钟；到顶即恢复拉起，误判由下一轮自愈。
  # ---- 按模型的限额账:每行「模型名 时间戳」 ----
  # Agent 遇任何模型的 429 都追加一行;派活前自行避开未解除的模型,到点即视为恢复。
  # 看门狗只做一件事:主模型(JOB_MODEL)存在未解除限流时不拉起(cap 30 分钟,防远期误判锁死);
  # 子模型限流不挡拉起——任务照跑,Agent 自己避开被限的池。
  local rlfile="$STATE_DIR/$job.rate-limit"
  if [ -f "$rlfile" ] && [ -s "$rlfile" ]; then
    local now_ts="$t" wait_until=0 kept="" line_m line_ts
    while read -r line_m line_ts; do
      [ -z "$line_m" ] && continue
      case "$line_ts" in ''|*[!0-9]*) continue ;; esac
      if [ "$line_ts" -le "$now_ts" ]; then continue; fi          # 已过解除时刻 = 该模型已恢复
      if [ $(( line_ts - now_ts )) -gt 1800 ]; then line_ts=$(( now_ts + 1800 )); fi
      if [ "$line_m" = "$JOB_MODEL" ]; then
        [ "$line_ts" -gt "$wait_until" ] && wait_until="$line_ts"
      else
        kept="${kept}${line_m} ${line_ts}"$'\n'                     # 子模型限流保留,Agent 自行避开
      fi
    done < "$rlfile"
    if [ "$wait_until" -gt 0 ]; then
      local rllog="$STATE_DIR/$job.rl-waiting"
      if [ "$(cat "$rllog" 2>/dev/null || echo 0)" != "$wait_until" ]; then
        wlog "$job: 主模型 $JOB_MODEL 限额中（最多到 $(date -d "@$wait_until" "+%H:%M" 2>/dev/null || echo "$wait_until")），本轮不拉起"
        echo "$wait_until" > "$rllog"
      fi
      return 0
    fi
    # 主模型无限流(或已解除):清理过期行后照常拉起
    if [ -n "$kept" ]; then printf '%s' "$kept" > "$rlfile"; else rm -f "$rlfile" "$STATE_DIR/$job.rl-waiting"; fi
  fi

  # ---- 拉起冷却：挡住「一拉起就秒退」的风暴 ----
  local laststart
  laststart="$(cat "$startfile" 2>/dev/null || echo 0)"
  if [ $(( t - laststart )) -lt "$JOB_RESTART_COOLDOWN_SECONDS" ]; then
    wlog "$job: 冷却中（距上次拉起不足 ${JOB_RESTART_COOLDOWN_SECONDS}s），本轮不拉"
    return 0
  fi

  if [ "$state" != "dead" ]; then
    wlog "$job: 判定假死（$state），先终止 pid=$pid"
    kill_group "$pid"
  fi

  # ---- 根据上次退出码，决定用哪条提示词 ----
  local finished=0
  if [ -z "$ec" ]; then
    :   # 这个任务从来没跑过，本次是首次拉起，不算失败重试
  elif [ "$JOB_PROMPT_COUNT" -eq 0 ]; then
    # 没配提示词：永远用兜底指令，直到完成标记出现或达到重启上限
    if [ "$ec" = "0" ]; then cnt=0; rm -f "$STATE_DIR/$job.NEED-ATTENTION"; else cnt=$(( cnt + 1 )); fi
  elif [ "$ec" = "0" ]; then
    case "$JOB_PROMPT_MODE" in
      cycle) step=$(( (step + 1) % JOB_PROMPT_COUNT )) ;;
      first) step=0 ;;
      *)     step=$(( step + 1 )) ;;
    esac
    cnt=0
    wlog "$job: 上一条提示词正常结束，推进到第 $(( step + 1 ))/$JOB_PROMPT_COUNT 条"
    if [ "$JOB_PROMPT_MODE" = "step" ] && [ "$step" -ge "$JOB_PROMPT_COUNT" ]; then
      finished=1
    fi
  else
    cnt=$(( cnt + 1 ))
  fi

  if [ "$finished" -eq 1 ]; then
    echo "$step" > "$stepfile"
    : > "$done_file"
    wlog "$job: 所有提示词都跑完了，标记完成（$done_file），不再拉起"
    return 0
  fi

  if [ "$JOB_MAX_RESTARTS" -gt 0 ] && [ "$cnt" -gt "$JOB_MAX_RESTARTS" ]; then
    echo "$cnt" > "$cntfile"
    wlog "$job: 连续重启已达上限 $JOB_MAX_RESTARTS，停止拉起，需要人工看一眼 $runlog"
    # 停机不可无声:留一个文件名即告警的标志,并写入原因;下次成功归零时清除
    echo "[$(ts)] 连续 $JOB_MAX_RESTARTS 次非正常退出,已熔断停机;最后退出码见 $STATE_DIR/$job.exit;run.log 尾部: $(tail -1 "$runlog" 2>/dev/null | cut -c1-120)" > "$STATE_DIR/$job.NEED-ATTENTION"
    return 0
  fi

  # ---- 取这一轮要发的提示词 ----
  local prompt
  if [ "$JOB_PROMPT_COUNT" -eq 0 ]; then
    prompt="$DEFAULT_PROMPT"
  else
    prompt="$(cat "$JOB_PROMPTS_DIR/$step.txt" 2>/dev/null)"
    [ -z "$prompt" ] && prompt="$DEFAULT_PROMPT"
  fi
  prompt="${prompt//\{DONE_FILE\}/$done_file}"
  prompt="${prompt//\{STEP\}/$(( step + 1 ))}"
  prompt="${prompt//\{NAME\}/$job}"
  prompt="${prompt//\{WORKDIR\}/$JOB_WORKDIR}"

  # 【免费模型硬闸门】每次拉起前强制校验，发现收费模型配置拒绝启动
  if ! python3 /root/.codebuddy/watchdog/assert_free_models.py >/dev/null 2>&1; then
    wlog "$job: 免费模型闸门未通过，拒绝拉起（见 assert_free_models.py 输出）"
    return 1
  fi
  case "$JOB_MODEL" in
    free-model|small-model|free-model-preview) ;;
    *) wlog "$job: 模型 $JOB_MODEL 非免费 hy 系列，拒绝拉起"; return 1 ;;
  esac

  local model_args=()
  [ -n "$JOB_MODEL" ] && model_args=(--model "$JOB_MODEL")

  echo "$step" > "$stepfile"
  echo "$cnt" > "$cntfile"
  echo "$t" > "$startfile"
  rm -f "$exitfile"

  (
    exec 9>&-   # 别把看门狗的锁 fd 传给后台进程，否则任务跑几小时锁就一直不释放
    export PIDFILE="$pidfile" EXITFILE="$exitfile"
    # 沙箱放行：无人值守时没人能点确认，打开它才不会被权限弹窗卡住
    if [ "${JOB_SANDBOX:-1}" = "1" ]; then export CODEBUDDY_IS_SANDBOX=1; fi
    cd "$JOB_WORKDIR" || exit 1
    # 下面这几个参数各自都不能省：
    #   -p                      非交互模式，干完就退出，适合无人值守
    #   --port 0                让内核分配一个空闲端口。不加的话它会去复用上次记录的端口，
    #                           而那个端口常被已经常驻的实例占着，新进程直接报 EADDRINUSE 起不来
    #   --resume <ID>           带着原会话续接，Agent 记得前面做过什么，不会从头再来
    #   --resume-create-missing 会话万一找不到了，就按这个 ID 新建一个，不至于当场失败
    #   $JOB_EXTRA_ARGS         配置里的额外参数，无人值守至少要有 -y：
    #                           没有它，权限确认弹窗会把进程永久挂住
    # ---- 秒退检测:连续 3 次拉起后 10 秒内非正常退出 → 强制换下一代会话 ----
    # (CLI 升级/上下文超限都会表现为秒退循环,换会话是第一自救手段;熔断之前就该试)
    local lastexit laststart secdie=0 secdief="$STATE_DIR/$job.secdie"
    lastexit="$(cat "$STATE_DIR/$job.exit" 2>/dev/null || echo 0)"
    laststart="$(cat "$STATE_DIR/$job.laststart" 2>/dev/null || echo 0)"
    if [ "$lastexit" != "0" ] && [ "$laststart" != "0" ] && [ $(( t - laststart )) -lt 10 ]; then
      secdie=$(( $(cat "$secdief" 2>/dev/null || echo 0) + 1 ))
      echo "$secdie" > "$secdief"
      if [ "$secdie" -ge 3 ]; then
        local n2=$(( $(cat "$STATE_DIR/$job.rollover" 2>/dev/null || echo 0) + 1 ))
        echo "$n2" > "$STATE_DIR/$job.rollover"
        rm -f "$secdief"
        wlog "$job: 连续 $secdie 次秒退，强制换新会话(下一代)再试"
      fi
    else
      rm -f "$secdief"
    fi

    # ---- 会话轮换:每 JOB_SESSION_ROLLOVER 次拉起换一个新会话 ----
    # 主会话上下文越大,每轮续接全量重发的成本越高(实测 10MB 会话是额度消耗大头);
    # 新会话第一件事就是读 WORKLOG 与入口文档恢复进度,成本归零重新积累
    local sid="$JOB_SESSION_ID"
    if [ "$JOB_SESSION_ROLLOVER" -gt 0 ]; then
      local rofile="$STATE_DIR/$job.rollover" n gen
      n=$(( $(cat "$rofile" 2>/dev/null || echo 0) + 1 ))
      echo "$n" > "$rofile"
      gen=$(( (n - 1) / JOB_SESSION_ROLLOVER ))
      [ "$gen" -gt 0 ] && sid="${JOB_SESSION_ID}-r${gen}"
    fi
    setsid nohup bash -c 'echo $$ > "$PIDFILE"; "$@"; echo $? > "$EXITFILE"' _ \
      "$CB_BIN" -p --port 0 \
      --resume "$sid" --resume-create-missing \
      "${model_args[@]}" $JOB_EXTRA_ARGS \
      -- "$prompt" \
      # ↑ "--" 必须保留:CLI 2.177.x 会把带换行的长 prompt 里以 "-" 开头的行当成选项,
      #   报 unknown option 直接退出(exit 1, 2 秒秒退)。"--" 之后一律按位置参数处理。2026-10-28 实证。
      >> "$runlog" 2>&1 &
  )
  sleep 2
  wlog "$job: 已拉起（第 $(( step + 1 ))/$JOB_PROMPT_COUNT 条提示词，重启计数 $cnt，pid=$(cat "$pidfile" 2>/dev/null)）"
  echo "[$(ts)] ===== 拉起：第 $(( step + 1 ))/$JOB_PROMPT_COUNT 条 =====" >> "$runlog"
  # 必须异步:同步 sleep 会让本实例持续持有 flock,之后每分钟的 cron 检查全部「跳过」,
  #  看门狗反而失效(2026-10-29 实测)。放后台执行,主流程立即释放锁。
  {
    sleep 90
    local newpid="$(cat "$pidfile" 2>/dev/null)"
    if [ -n "$newpid" ] && ! ps -p "$newpid" >/dev/null 2>&1; then
      wlog "$job: 拉起后 90 秒内进程已退出(exit=$(cat "$exitfile" 2>/dev/null || echo 未知));run.log 尾部: $(tail -2 "$runlog" 2>/dev/null | tr '\n' ' ' | cut -c1-160)"
    fi
  } >> "$LOG_DIR/watchdog.log" 2>&1 &
}

show_status() {
  printf '%-18s %-8s %-10s %-9s %s\n' 任务 状态 步骤 PID 会话
  local job pid step st cnt meta
  while IFS= read -r job; do
    [ -n "$job" ] || continue
    meta="$GEN_DIR/$job.meta"
    [ -f "$meta" ] || continue
    JOB_SESSION_ID=""; JOB_DONE_FILE=""; JOB_PROMPT_COUNT=0
    # shellcheck disable=SC1090
    source "$meta"
    pid="$(cat "$STATE_DIR/$job.pid" 2>/dev/null || echo "")"
    step="$(cat "$STATE_DIR/$job.step" 2>/dev/null || echo 0)"
    cnt="$(cat "$STATE_DIR/$job.restarts" 2>/dev/null || echo 0)"
    local df="$JOB_DONE_FILE"; [ -z "$df" ] && df="$STATE_DIR/$job.DONE"
    if [ -e "$df" ]; then st="已完成"
    elif alive "$pid"; then st="在跑"
    else st="已停"; fi
    [ "$cnt" -gt 0 ] && st="$st(${cnt}次重试)"
    local steps="$(( step + 1 ))/$JOB_PROMPT_COUNT"
    [ "$JOB_PROMPT_COUNT" -eq 0 ] && steps="默认"
    printf '%-18s %-8s %-10s %-9s %s\n' "$job" "$st" "$steps" "${pid:- -}" "$JOB_SESSION_ID"
  done < "$GEN_DIR/names.txt"
}

install_cron() {
  local n
  export JOBS_FILE
  n="$("$NODE_BIN" -e "const c=require(process.env.JOBS_FILE);process.stdout.write(String((c.watchdog&&c.watchdog.cron_interval_minutes)||c.cron_interval_minutes||1))")"
  local sched="*/$n * * * *"
  [ "$n" = "1" ] && sched="* * * * *"
  local newf="$STATE_DIR/crontab.new"
  crontab -l 2>/dev/null | awk '/CODEBUDDY_WATCHDOG_BEGIN/{skip=1} !skip{print} /CODEBUDDY_WATCHDOG_END/{skip=0}' > "$newf"
  printf '\n# === CODEBUDDY_WATCHDOG_BEGIN ===\n' >> "$newf"
  printf '# 夜间长任务续跑：挂了就带原会话重新拉起继续干，间隔看 jobs.json 的 cron_interval_minutes\n' >> "$newf"
  # timeout 必须保留:watchdog 实例一旦卡住(实测发生过:拉起后不退出、锁被持有 20 分钟以上),
  # 之后每分钟的 cron 检查都会被 flock 挡掉,看门狗彻底失效。超时强杀保证锁最多被占 5 分钟。
  printf '%s timeout 300 %s >> %s/cron.log 2>&1\n' "$sched" "$SCRIPT_DIR/watchdog.sh" "$LOG_DIR" >> "$newf"
  printf '# === CODEBUDDY_WATCHDOG_END ===\n' >> "$newf"
  crontab "$newf" && rm -f "$newf"
  echo "已装入 crontab：$sched $SCRIPT_DIR/watchdog.sh"
}

case "${1:-}" in
  status) show_status; exit 0 ;;
  install-cron) install_cron; exit 0 ;;
  "") mapfile -t JOBS < "$GEN_DIR/names.txt" ;;
  *) JOBS=( "$1" ) ;;
esac

for j in "${JOBS[@]}"; do
  [ -n "$j" ] || continue
  check_job "$j"
done
