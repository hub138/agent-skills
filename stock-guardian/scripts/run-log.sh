#!/usr/bin/env bash
# 结构化执行日志（agent/非agent 通用）：任务执行的分段耗时+状态，机器可读 JSONL
# 用法：run-log.sh start 任务名 | run-log.sh stage 任务名 阶段名 | run-log.sh end 任务名 状态[OK/FAIL/DELAY] | run-log.sh query [日期]
set -u
SG="$HOME/.stock-guardian"
LOG="$SG/run-log.jsonl"
mkdir -p "$SG"
ts() { date '+%F %T'; }
case "${1:-}" in
  start) echo "{\"ts\":\"$(ts)\",\"task\":\"$2\",\"event\":\"start\"}" >> "$LOG"; echo "已记录 start: $2" ;;
  stage) echo "{\"ts\":\"$(ts)\",\"task\":\"$2\",\"event\":\"stage\",\"stage\":\"$3\"}" >> "$LOG"; echo "已记录 stage: $2/$3" ;;
  end)   echo "{\"ts\":\"$(ts)\",\"task\":\"$2\",\"event\":\"end\",\"status\":\"${3:-OK}\"}" >> "$LOG"; echo "已记录 end: $2 (${3:-OK})" ;;
  query)
    D="${2:-$(date +%F)}"
    echo "=== 任务执行日志 $D（时序+间隔）==="
    grep "\"ts\":\"$D" "$LOG" 2>/dev/null | node -e "
let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{
  const rows=s.trim().split('\n').filter(Boolean).map(l=>JSON.parse(l));
  let prev=null;
  rows.forEach(r=>{
    const t=r.ts.slice(11);
    const gap=prev?((new Date(r.ts)-new Date(prev))/1000).toFixed(0)+'s':'-';
    console.log(\`\${t} [\${r.event}] \${r.task}\${r.stage?'/'+r.stage:''}\${r.status?' status='+r.status:''}  (距上条 \${gap})\`);
    prev=r.ts;
  });
});"
    ;;
  *) echo "用法: run-log.sh start|stage|end|query";;
esac
