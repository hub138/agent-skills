---
name: agent-ops
description: 本机 AI agent 编排与模型运维。当一个 agent 要调度多个 CLI 子 agent（dispatch/status/brief/locate/resume/send/watch）、长任务断了要自动续接、要控制上下文与记忆（progress.md/result.json/三层记忆）、要按速率反推并发、或排查模型不被凭证池允许/假输出/会话文件在哪时使用。含多通道速率治理、AIMD 自适应并发、会话绝对路径定位、看护与断点续跑、CLI 全部踩坑。适用于 codebuddy / claude / codex / cursor / knot-cli。
---

# 本机 AI Agent 编排与模型运维

> 本机实测。正文全文内联（AGENTS.md 硬规则：禁止用 `@` 引用文件，引用行不展开正文）。
> 权威源：`<skill 安装目录>/agent-ops/`，同步安装到 `~/.codebuddy/skills`、`~/.claude/skills`、`~/.codex/skills`、`~/.cursor/skills`。

## 模型安排（先看这一节）

**只有两个模型角色：一个干活、一个监督。两个都可配置。**

| 角色 | 干什么 | 配置项 | 默认值 |
|---|---|---|---|
| ① 干活 worker | 真正执行任务的子 agent（扫描 / 判定 / 批量） | 按程序各自配置 | `$WORKER_MODEL` |
| ② 监督 supervisor | 定时读进度，判断继续 / 追加指令 / 重来 / 交人，**模型监督模型**（不是脚本判活） | `SUPERVISOR_MODEL` | 同 worker |

干活模型按程序各自的配置项（都可改，不写就用默认值）：

| 程序 | 配置项 |
|---|---|
| `knot_batch.py` 批量判定 / 调用 | `MTR_KNOT_MODELS`（逗号分隔候选池） |
| `agentctl.py` / `taskctl.py` 派单 | `dispatch --model`（命令行） |

四条必须记住：

1. **模型名按通道区分**：同一个模型在不同 CLI 通道里的 ID 可能不同，跨通道调用前先确认命名，不要混用（详见 `codebuddy-cli-notes.md`）。
2. **候选池轮转**：批内按条把任务分给池内不同模型，避免只用第一个把它的额度用尽、其余闲置。
3. **并发是项目内部量**：从每模型 1~2 路起步，多模型时设一个全局上限（见 `knot-limits.md` 的换算方法）；**不是**对全局容量的推算。监督者是定时/事件触发的一次调用，**不占 worker 并发槽**。
4. **429 分两类处理**：带重置时刻的 → 整模型冷却到该时刻；不带通知的 → 降并发 + 指数静默。两种恢复逻辑不能混用（见 §十二）。

## 〇、文件导航

| 文件 | 职责 |
|---|---|
| `SKILL.md` | 入口：角色与配置、两条 CLI 最小用法、并发结论、安装同步 |
| `model-catalog.md` | 多通道模型选型方法：发现、白名单、成本闸门、命名对应 |
| `knot-limits.md` | 速率治理：官方口径怎么读、速率↔并发换算、AIMD+指数静默、排查与观测 |
| `codebuddy-cli-notes.md` | codebuddy 版本 / 假绿灯 / PATH 根因 / 额度口径 / 串行下的确定性失败坑 |
| `ai-session-forensics.md` | 各 CLI 会话存档路径与按 requestID 反查 |
| `knot_batch.py` | 批量调用（分桶并发、429 识别、fallback 链、JSON 兜底） |
| `knot_rate_budget.py` | 速率预算、`recommend_workers`、`AdaptiveConcurrency` |
| `orchestrator.md` | **用 1 个 agent 调度多个 CLI 子 agent**：dispatch/status/locate/resume/watch、会话绝对路径、编排模式、提示词模板 |
| `scripts/agentctl.py` | 交互式多 agent 派发（dispatch/status/brief/locate/resume/send/watch） |
| `scripts/taskctl.py` | **几十万任务级队列**（SQLite+租约+worker 监督+模板化提示词）：`add --goal` / `plan --goal` / `tick` / `daemon` / `brief` / `stats` |
| `templates/tasks/` | 任务类型模板（generic / compare-commit / reproduce-bug / fix-bug / research），用户不用写 prompt |
| `watchdog.md` | **长任务看护完整手册**：任务形态判断、jobs.json 全字段、prompts 三种模式、提示词模板、时间参数、沙箱、排查 |
| `scripts/watchdog.sh` + `templates/` | 看护脚本与 jobs.json 模板 |
| `memory.md` | **上下文工程与记忆**：三层记忆、主 agent 上下文预算、子 agent 输出契约、压缩 / rollover、交接协议 |
| `scripts/selfcheck.py` | 一键体检 8 项能力（在用 / 闲置 / 误配），改完先跑它 |
| `scripts/deadman.py` | 死士检查通用件（配置驱动，见 §十一） |
| `scripts/supervise_agents.py` / `supervise_jobs.py` | 监督的 agentctl 后端与 cron 脚本后端 |
| `templates/deadman.example.json` | 死士检查配置示例（6 种 check 类型，DB 双支持 mysql/sqlite，通知走 stdin） |
| `tests/` | 回归测试（taskctl 阈值校验 / 契约校验 / 假死判定 / compaction 留痕），`python3 -m pytest tests/ -q` |
| `FIELD-NOTES.md` | **实战补丁记录**：真实跑任务踩到的坑与修法（监督器三后端、cron python 版本、通知拆条、完成 vs 卡住的区分……每条附现象 / 根因 / 验证），新坑先查这里 |
| `dsh-lessons.md` | 深度研究笔记：领域模型、Ticket 状态机、stored work / 幂等 / 保序 / 已读未读，以及采纳与不采纳的判断 |

## 一、模型 ID 与选型

**先用 `--help` 或平台面板列可用模型，再按白名单收窄。** `--help` 会把付费档一起列出，不要据此判断免费与否。

选型三问：

1. **能不能调通**——以实测为准，不以文档列表为准；名字大小写与后缀在不同通道里规则不同（见 `codebuddy-cli-notes.md`）。
2. **贵不贵**——先确认计费口径（相对倍率还是绝对价格），代码层在发请求前拦截超预算模型，**不依赖 429 自动回落**（回落可能落到更贵的模型）。
3. **够不够用**——长上下文 / 识图 / 思考档位按任务挑；同一批任务里慢模型与快模型分开设超时，统一超时会误杀慢模型。

完整方法（发现流程、白名单配置、成本闸门、跨通道命名映射）见 `model-catalog.md`。

## 二、knot-cli 用法

```bash
knot-cli chat --model "$WORKER_MODEL" "prompt"
knot-cli chat --model "$WORKER_MODEL" --no-think "短任务，跳过思考"
```

- 每次 `chat` 伴随一个 `chat-watchdog` 子进程，**数并发要除以 2**。
- 通道被并发会话占用时会出现**模型调用 timeout**，这不是限流，重试不如错峰或换通道。
- 会话元数据（pid / request_id / session_id）落在 CLI 的会话目录，检索键是 stdout 里的 `requestID` / `sessionID`。

## 三、codebuddy CLI 用法

```bash
codebuddy -p --output-format text --model "$WORKER_MODEL" "只回答两个字：收到"
```

### 版本与假绿灯（调 codebuddy 前必读）

- **RC=0 不等于成功**：错误串可能只在 stdout，`-p` 模式下退出码仍是 0。必须把 stdout + stderr 合并做错误识别，否则会把失败当结论返回。
- **PATH 根因**：多版本共存时，`which codebuddy` 指向的可能不是实际调用的那个；用绝对路径并在日志里打印版本。
- 详细版本差异、额度文案、串行下的确定性失败坑见 `codebuddy-cli-notes.md`。

## 四、批量调用：直接用 `knot_batch.py`

同目录 **`knot_batch.py` 可直接 import 或命令行跑**，把速率治理封装好了：

```python
import sys; sys.path.insert(0, '<skill 安装目录>/agent-ops')
from knot_batch import batch, probe, global_load, recommend, MODELS
print(recommend())                       # 全局 chat / 按项目 / 按模型 / 孤儿 PID / 建议路数
ok, raw = probe()                        # 启动探活一次即可，别每轮探
results = batch(items, make_prompt,
                models=MODELS, per_model=2, timeout=25,
                on_result=lambda it, m, v, err: save(it, m, v) if v else None)
# v=None 的不要写库 → 下轮断点续跑自动重判
```

```bash
python3 <skill 安装目录>/agent-ops/knot_batch.py          # 全局自检
python3 <skill 安装目录>/agent-ops/knot_batch.py --load   # JSON 明细
```

它内置：`/proc` 全局统计（排除 watchdog，`pgrep` 在 Python 子进程里会漏）、按模型分桶信号量、429 / 假绿灯识别、`[任务规划中]` 前缀与围栏 / requestID 后缀的 JSON 兜底解析、低频探活。

全部推导、重试有无用的判据、探活频率、sqlite 锁 / 孤儿 / 假绿灯等配套坑见 `knot-limits.md`。

## 七、限流口径怎么读（要点，全文见 `knot-limits.md`）

不同通道的 429 形态不同：

- **带重置时刻**（如「将在 <时刻> 重置」）→ 解析出时刻，整模型冷却到那一刻，其余模型继续跑。
- **不带恢复时间** → 只能靠探测式降并发 + 指数静默，连续成功再逐步回升。

**限制的是速率，不是固定并发数**：`并发上限 = 允许速率(次/分) × 平均单次耗时(秒) / 60`。具体速率上限以你所用平台的官方说明为准，本技能不内置任何平台的配额数字。

## 八、AIMD + 指数静默（要点，推导见 `knot-limits.md`）

连续多次成功才 +1 路；一次 429 立刻砍到 1；连续 429 静默时间指数递增并封顶，**静默期不发请求**；一次成功把失败计数清零；`timeout` 属通道占用，不降并发只打断计数。

**验证边界**：模拟 + 单测 + 故障注入通过；真实平台侧的 429 收敛证据取决于你部署的通道，本技能不声称有线上数据。

## 九、全局观测与本地闸门的边界

本地闸门是**私有**的，其它项目不认，本地无法全局协调；速率预算只记本项目的调用，不是全平台账本。能严格保证的只有「自己 ≤N 并发、≤M 次/分、观测到拥堵时排队 / 静默」。

全局观测属于**事后排查工具**，不是调度输入。方法与统计坑见 `knot-limits.md`。

## 十、并发口径

- **每模型从 1~2 路起步**，多模型时设一个全局上限；上限由上面公式反推，**不做全局配额推演**。
- 并发语义：默认单模型时按每模型上限跑；多模型时总并发 = `min(全局上限, 模型数 × 每模型上限)`。
- `knot_batch.recommend()` 只报全局 chat 数与按项目 / 模型分布，**不计算「本项目还能开几路」**——别的项目占多少算不清，也没必要算。`global_load()` 仅作诊断。
- **超预算模型硬禁用**：代码层在发请求前拒绝，不依赖 429 自动回落。白名单与阈值按你的平台计费口径配置（见 `model-catalog.md`）。
- **串行 / 多路时都要轮转模型**：`start_model = batch_no % len(models)`，否则只会用列表第一个。
- **无 diff 的条目不进队列**：`pending()` 直接排除 `main_diff` 为空的 commit（重试一万次也不会有结论），补扫补上 diff 后自动回到队列。

## 十一、用 1 个 agent 调度多个子 agent（要点，全文见 `orchestrator.md`）

主 agent 只做拆解与验收，重活交给多个 CLI 子 agent，每个子任务都有确定的 session id、会话文件绝对路径、输出目录。

```bash
ACT=<skill 安装目录>/agent-ops/scripts/agentctl.py
python3 $ACT dispatch --name t1 --backend codebuddy --model "$WORKER_MODEL" \
  --workdir <你的项目目录> --prompt-file /tmp/t1.md
python3 $ACT status          # 进程 / 退出码 / 运行时长 / 会话文件
python3 $ACT locate t1       # 会话文件、输出目录、日志的绝对路径
python3 $ACT resume t1       # 带原会话续接；会话没了自动降级新建
python3 $ACT send t1 "只回答三个字：已收到"   # 给已结束的任务追加指令
python3 $ACT watch --quiet   # 挂 cron，批量续接挂掉的任务
```

- **实时看进度**：读会话 jsonl（`status` 给出事件数与最后事件时间），不要看 `run.log` 大小——stdout 重定向是块缓冲，结束才 flush；要实时 stdout 用 `script -q -c`。
- **追加输入**：已结束的任务用 `send`（带 `--resume`）；运行中的任务不要插话，消息会写进 jsonl 但不会被处理。
- **会话路径**：由 `--session-id` 决定文件名；`locate` 直接给绝对路径。
- **任务目录**：`~/.codebuddy/agentctl/<name>/{prompt.md,run.log,pid,exit,out/}`。
- **提示词必须要求写 `progress.md`**：上下文压缩后只有落盘进度能恢复，resume 全靠它。
- **红线不变**：超预算模型不派；每模型并发与全局上限按 §十 配置。
- 三个实测坑已内置规避：`--port 0`（防 EADDRINUSE）、`--` 分隔长 prompt（防 `-` 开头被当选项）、不用 `unlink` 删任务文件（沙箱跨设备 Trash 会递归）。
- 旧的 `~/.codebuddy/watchdog/jobs.json` 继续由 `scripts/watchdog.sh` 接管，与 `agentctl` 状态目录互不干扰。

## 十二、并发是本地量，429 感知靠本地反馈

**分层要分清**：每模型并发与全局上限是**本项目自己内部的并发上限**，不是对全局容量的推算。默认不做全局配额推演、不按全局 chat 数让路（`MTR_KNOT_GLOBAL_MAX` 默认 0 关闭；显式设才启用）。

**但必须能感知是否 429 受限**，两条通道分开处理：

| 通道类型 | 429 形态 | 感知方式 | 恢复 |
|---|---|---|---|
| 带重置时刻 | 文案里有「将在 <时刻> 重置」 | **stdout+stderr 合并检测**，优先于普通错误串；RC=0 且错误串在 stdout 的假绿灯必须拦住 | 整模型冷却到通知时刻、持久化到本地状态文件，到期自动回归，其余模型继续跑 |
| 无恢复时间 | JSON body 里的 429 / too many requests | `_is_transport_error(stdout+stderr)` 识别 RC=0 的假绿灯 | AIMD 降并发到 1 + 指数静默，连续成功才升 1 路 |

排查口诀：**队列突然零成功时，先 grep `429` / 额度文案 / 冷却文件，别先归因到全局拥堵**。两种 429 的恢复逻辑不能混用。

## 十三、长程判活与假死

- **断点恢复**：预置 progress.md 分步进度 → 新会话子任务从断点继续并追加「接着做」，会话 jsonl 有事件留痕。L3 落盘记忆跨会话生效。
- **watchdog.sh**：cron 每 1 分钟叫醒、`check_interval_minutes` 实际检查，`kill -0 pid` 判活；`stale_minutes` 默认 0（关闭日志假死判定，因 `-p` 输出块缓冲）。
- **taskctl**：`daemon --interval 30s` tick；`TASKCTL_STALE=900s` 假死判定，看会话 jsonl / progress.md / result.json / run.log 的 mtime，全超时无增长就 `killpg` 精确杀 + 重排 + 原因回灌。`0` 关闭。
- **不用 AI 去看是否卡住**：额外模型调用更慢更贵且 AI 自己也会卡；mtime 是内核给的客观事实。会话 jsonl 边跑边写，比 stdout 可靠。
- **并发与 watchdog 的关系**：watchdog / daemon 是**监督进程，不是 agent**，不调模型、不占并发额度。一个任务 = 1 个 CLI agent + 1 个不调模型的 Python 监督进程。

完整架构图与间隔表见 `memory.md`。

## 十四、监督是「模型给模型」，不是脚本判活

脚本看不出重复报错死循环、不会应对新情况。因此：

- 脚本 `taskctl` 发现无增长只**标记** `need_supervision`、续租，**绝不自行杀进程**。
- `supervisor.py` 定时 / 事件（无增长或有 error）触发，把紧凑快照交给监督者模型（`SUPERVISOR_MODEL`），模型输出 JSON 决策 `continue/nudge/restart/escalate/finish`。
- 脚本只做归一化、防呆与执行；`guidance.md` 自动注入下一轮 prompt。模型输出解析失败 / 超时 → 本轮不动，不误杀。
- 人只读 `stats` / `brief`，`escalate` 才需介入。
