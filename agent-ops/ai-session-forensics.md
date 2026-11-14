# AI 会话真实产出定位手册（knot / codebuddy / iteration）

> 实测 ，本机 `<host>`。用途：AI 调用超时、返回莫名其妙的错误串、429 限流、或需要看「模型到底分析了什么」时，按绝对路径找到那一次会话的原始产出。
> 关键事实：knot-cli 的 `chat` 每次都会伴随一个 `chat-watchdog` 进程，**数并发时进程数要除以 2**。

## 一、knot-cli 每次会话的本地存档

| 路径 | 内容 |
|---|---|
| `/root/.bg-agent/cli/<nonce>.json` | **每次 chat 一份**。字段：`cli_pid`、`cli_started_at_milli`、`nonce`、`request_id`、`session_id`、`app_name`、`debug`、`created_at`。这是定位一切的主索引 |
| `/root/.bg-agent/tool_calls/` | 工具调用输入/输出临时文件，日志里会打印 `cleanupToolCallFiles: removed expired file ...` |
| `<knot 主日志路径>` | 主日志（本机 80MB，按天滚动成 `knot_bg_client.log-YYYYMMDD.gz`）。按 `requestID` / `sessionID` 搜即可还原一次请求 |
| `--log-dir <dir>` | `knot-cli chat` 支持把日志重定向到指定目录，批量任务建议按任务建目录 |
| `--sessionId <id>` | 续接会话；续接不是重新发 prompt |
| stdout（`text` 模式） | 结尾会打印 `requestID: xxx` 和 `sessionID: xxx`，脚本里应把这两行留档 |

两个二进制（版本不同，别混）：

```
<knot-cli 路径>        # v0.34.0，PATH 里通常优先
<knot-cli 路径>             # v0.35.1
```

`--output-format` 三选一：`text`（脚本首选）、`json`、`stream-json`（分片，要自己累加 `rawEvent.content`）。`--status-out` 输出 `{"status":"success/fail","error":""}`，适合机器判定。

## 二、codebuddy CLI 会话存档

| 路径 | 内容 |
|---|---|
| `/root/.codebuddy/projects/<workspace-slug>/<session-uuid>.jsonl` | **每次会话一份**，逐行 JSON，含消息、工具调用、结果 |
| `/root/.codebuddy/projects/<workspace-slug>/<session-uuid>/tool-results/*.txt` | 该会话里每次工具调用的原始输出（大输出不会塞进 jsonl） |
| `/root/.codebuddy/history.jsonl` | 跨会话历史索引 |
| `/root/.codebuddy/file-history/`、`/root/.codebuddy/blobs/` | 文件改动快照与二进制内容 |

workspace-slug 是工作目录绝对路径把 `/` 换成 `-`，例如 `<你的项目目录>` → `data-aiproject-业务项目`。

## 三、iteration 复现/修复任务自己的产出

```
<你的项目目录>/artifacts/mtr_iteration/<task_id>/
├── iteration-run.log          # 逐轮状态机、CLI ACTIVITY、异常堆栈
├── <task_id>.sqlite           # iteration_rounds / node_events / run_summaries / decision_records …
├── transcripts/               # knot/codebuddy 每轮对话转录
└── taskspec_<task_id>.yaml
```

查「第 1 轮为什么异常」：

```bash
sqlite3 <task_id>.sqlite "SELECT iteration_id, round_status, failure_stage FROM iteration_rounds;"
sqlite3 <task_id>.sqlite "SELECT iteration_id, phase, kind, status, error_code, error_message FROM node_events WHERE error_code != '';"
```

实测样例：第 1 轮 `CLI_HARD_TIMEOUT / knot-cli chat terminated (hard_timeout)`，框架 rollback，第 2/3 轮 `succeeded`。

## 四、按一次调用反查（可复用脚本）

```bash
# 1) 从 stdout 拿到的 requestID / sessionID 反查 state 文件
grep -rl "$REQUEST_ID" /root/.bg-agent/cli/ | head
cat /root/.bg-agent/cli/<nonce>.json

# 2) 由 state 里的 cli_pid 找进程、看它属于哪个项目
PID=$(python3 -c "import json;print(json.load(open('/root/.bg-agent/cli/<nonce>.json'))['cli_pid'])")
ps -p "$PID" -o pid,ppid,etime,cmd
#  再沿 ppid 往上找，就能知道是哪个 runner / cron 拉起的

# 3) 在主日志里还原这次请求（含 429 / 超时 / 工具调用）
grep -n "$REQUEST_ID" <knot 主日志路径> | head

# 4) 看 codebuddy 会话真实产出（逐行 JSON，只打印类型和摘要）
python3 - <<'PY'
import json
p = "/root/.codebuddy/projects/<slug>/<session>.jsonl"
for line in open(p, encoding="utf-8", errors="replace"):
    try:
        d = json.loads(line)
        print(d.get("type"), str(d.get("message") or d.get("content") or "")[:160])
    except Exception:
        pass
PY
```

## 五、全局并发上限与 429（十几个项目共用免费模型的关键）

**上限**：凭证池配置里通常有 `max_concurrency_per_model`（每个模型的并发上限），按你平台的配置读取。本 skill 的预算从每模型 1~2 并发起步，多模型时在整机上不超过一个你设定的全局上限。

**怎么数当前真实并发**：

```bash
# chat 进程（排除 watchdog 才是真实请求数）
pgrep -af 'knot-cli chat ' | grep -v 'chat-watchdog' | wc -l
# 每个 chat 都有对应 watchdog，看配对
pgrep -af 'knot-cli chat-watchdog' | wc -l
# 按模型分组，看是否挤在单模型
pgrep -af 'knot-cli chat ' | grep -o -- '--model [a-z0-9.-]*' | sort | uniq -c
```

 实测：28 个 `knot-cli` 进程 = 14 个 `chat` + 14 个 `chat-watchdog`，其中 6 个挤在 `$WORKER_MODEL`，超过预算，于是出现：

```
❌ 处理失败: 创建异步请求失败: API request failed with status 429: {"code":429,"msg":"too many requests"}
```

**最坑的地方**：knot-cli 进程 **RC=0、stderr 空、这条错误串在 stdout**，任何只看退出码的封装都会当成 AI 正常回答返回，下游解析不到结构化判定就整批失败，日志里还看不出是限流。

治理（三层）：

1. 调用层识别并退避：检测 `429` / `too many requests` / `创建异步请求失败` / `RateLimitError`，抛专用异常。**仅对单个长任务**用「退避 45s 重试同一模型最多 3 次」（限流是全局的，换模型无助于缓解）。
   ⚠️ **批量短判定场景不适用「长退避 + 多次重试」**：把 retries=3 / timeout=180 / 45s 退避放进多路并发，前批撞墙全部退避、worker 占满，后续发不出去（实测多路并发下数分钟零返回）；改成短超时、单次调用、失败留待下轮断点续跑后，同批任务数十秒内跑完。当 429 占比高且随并发数变化，是**容量问题，重试无用**，应降并发（按模型分桶）。详见 `knot-limits.md` 与 `knot_batch.py`。
2. 项目内限并发：一个项目同时最多 1~2 个 chat，批量扫描串行 + 断点续跑，不要靠多进程堆速度。
3. 跨项目共享信号量（可选，所有项目都用同一文件时才有效）：

```python
import fcntl, os, time
GATE = "/tmp/knot_global_gate.lock"   # 所有项目约定同一个路径
MAX = 16                              # 整机预算
f = open(GATE, "a+")
fcntl.flock(f, fcntl.LOCK_EX)         # 简化版：排他锁=整机串行；要限 N 需另写计数槽
try:
    ...调用 knot-cli...
finally:
    fcntl.flock(f, fcntl.LOCK_UN)
    f.close()
```

排查时先 `pgrep` 看是谁占满了槽，再决定降哪个项目的并发，不要盲目加超时或换模型。

**实测坑：Python 子进程里 `pgrep` 会漏统计**。`subprocess.run(["pgrep","-af","knot-cli chat "])` 返回 0，而 shell 里同一命令是 9 个。自适应闸门必须直接读 `/proc`：

```python
import os
def global_knot_chats() -> int:
    n = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode("utf-8", "replace").replace("\x00", " ")
        except OSError:
            continue
        if "knot-cli" in cmd and " chat " in cmd and "chat-watchdog" not in cmd:
            n += 1
    return n
```

`业务项目` 的 `static_scan_runner.py` 已落地这套闸门：全局 chat 数 >= `MTR_KNOT_GLOBAL_MAX`（默认 8）就每 30s 复查（最多 10 分钟），连续失败 3 条整体休眠 300s；配合 429 退避，限流期间队列安静等待而不是疯狂重试打爆通道。

## 六、一句话结论

- 会话主索引：knot 在 `/root/.bg-agent/cli/<nonce>.json`，codebuddy 在 `/root/.codebuddy/projects/<slug>/<uuid>.jsonl`，iteration 在 `artifacts/mtr_iteration/<task>/`。
- 超时 / 429 先看 `knot_bg_client.log` 与 state 文件里的 `request_id`，不要只看自己封装层的日志。
- 十几个项目共用免费通道时，429 是全局排队问题；退避 + 项目内串行比换模型有效。

> 全局 24h 观测、闸门作用域边界已并入 `knot-limits.md` 第九节。
