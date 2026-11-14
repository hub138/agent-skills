---
name: agent-ops
description: 本机 AI agent 编排与模型运维。当一个 agent 要调度多个 CLI 子 agent（dispatch/status/brief/locate/resume/send/watch）、长任务断了要自动续接、要控制上下文与记忆（progress.md/result.json/三层记忆）、要选免费或便宜模型并算并发、或排查模型不被凭证池允许/假输出/会话文件在哪时使用。含 40+ 模型 credits 分层与红线、knot 与 codebuddy 两套限流机制、会话绝对路径定位、看护与断点续跑、CLI 全部踩坑。适用于 codebuddy / claude / codex / cursor / knot-cli。
---

# 本机 AI Agent 编排与模型运维

> **公开脱敏版**：`https://github.com/hub138/agent-skills`（`agent-ops/` 目录）。
> 两份同源：公开版去掉了内部文档链接、内网域名、内部模型代号与具体配额数字；
> 能力、脚本、触发词完全一致。**每次修改本 skill 后必须同步公开版并提交推送**，
> 步骤见 `orchestrator.md` 末节「同步公开版」。`agent_foundation` 的文档权威源也在该仓库
> 的 `agent_foundation/` 目录；依赖旧路径的 automation 已迁移，见 `orchestrator.md`「自动化链路的目录迁移」。

> 本机实测 2026-11-10。正文全文内联（本机 AGENTS.md 硬规则：禁止用 `@` 引用文件，引用行不展开正文）。
> 权威源：`<skill 安装目录>/agent-ops/`，已同步安装到 ~/.codebuddy/skills、~/.claude/skills、~/.codex/skills、~/.cursor/skills。

> 本机实测 2026-11-12。**免费口径**：codebuddy 侧**只有 hy 系列 x0.00**（`free-model` / `free-model-flash` / `small-model`，另有特殊用途 `echo`）；knot 侧 `free-model` / `small-model` / `free-model-preview` 实测扣费 0。不免费但**足够便宜**的可用档位见 `model-catalog.md`（`glm-5.3-flash-ioa` x0.08、`deepseek-v4.1-flash` x0.11 等）。
> 所有 ID 均以**实测能否调通**为准，不以 `--help` 里的列表为准（help 列的主要是付费 claude/gemini/gpt 系列）。

## 模型安排（先看这一节，2026-11-12 定稿）

**只有两个模型角色：一个干活、一个监督。两个都可配置，默认都是 free-model。** small-model 偏弱，默认不参与；想用要显式配。

**两条通道都有免费模型**（2026-11-12 实测）：codebuddy 侧 `free-model` / `free-model-flash` / `small-model`（x0.00）；knot 侧 `free-model` / `small-model` / `free-model-preview` 及 `glm-5.3*` / `deepseek-v4-flash` 实测扣费 0。免费池完整清单、credits 分层、**调用频率与 429 恢复策略**一屏见 `model-catalog.md` 第零节（限流数字与 AIMD 见 `knot-limits.md`）。默认两条通道都走 free-model，不默认用便宜/贵档。

| 角色 | 干什么 | 配置项 | 默认值 |
|---|---|---|---|
| ① 干活 worker | 真正执行任务的子 agent（扫描 / 判定 / 批量） | 见下表按程序配 | `free-model`（codebuddy 侧写 `free-model`） |
| ② 监督 supervisor | 定时读进度，判断继续 / 追加指令 / 重来 / 交人，**模型监督模型**（不是脚本判活） | `SUPERVISOR_MODEL` | `free-model` |

干活模型按程序各自的配置项（都可改，不写就用默认值）：

| 程序 | 配置项 | 默认 |
|---|---|---|
| `knot_batch.py` 批量判定 / 调用 | `MTR_KNOT_MODELS` | `free-model` |
| `static_scan_runner.py` 静态扫描 | `<业务环境变量>` | `free-model` |
| `agentctl.py` / `taskctl.py` 派单 | `dispatch --model`（命令行） | `free-model` |

四条必须记住：

1. **free-model 与 free-model 是同一个模型**：knot-cli 侧叫 `free-model`，codebuddy CLI 侧叫 `free-model`（knot 侧喂 `free-model` 会报「不支持该模型」）。下文两处写法按通道区分，不要混。
2. **small-model 默认不用**：偏弱，不进任何默认池。要用就显式配，例如 `<业务环境变量>=free-model,small-model`、`SUPERVISOR_MODEL=small-model`、`MTR_KNOT_MODELS=free-model,small-model`。
3. **并发是本项目内部量**：每模型最多 2 路、多模型合计全局上限 10；**不是**对全局容量的推算，不做全局配额让路。监督者按定时 / 事件触发，一次调用，**不占 worker 并发槽**。
4. **429 感知分两条通道**：codebuddy 有重置时刻 → 整模型冷却；knot 无通知 → 降并发 + 指数静默。两种恢复逻辑不能混用（详见 §十二）。

## 〇、文件导航（14 个有效文件；另有 3 个「已废弃」兼容文件，内容为空指引）

| 文件 | 职责 |
|---|---|
| `SKILL.md` | 入口：免费/便宜口径、两条 CLI 最小用法、并发结论、用户偏好、安装同步 |
| `model-catalog.md` | 40+ codebuddy 模型的 credits 分层、场景选型、knot↔codebuddy 命名对应 |
| `knot-limits.md` | knot 官方限流数字、并发公式、AIMD+指数静默、实战反例与排查、全局观测 |
| `codebuddy-cli-notes.md` | codebuddy 版本/假绿灯/PATH 根因/额度口径/串行下的确定性失败坑 |
| `ai-session-forensics.md` | knot/codebuddy/iteration 会话存档路径与按 requestID 反查 |
| `knot_batch.py` | 批量调用（分桶并发、429 识别、fallback 链、JSON 兜底） |
| `knot_rate_budget.py` | 官方口径速率预算、`recommend_workers`、`AdaptiveConcurrency` |
| `orchestrator.md` | **用 1 个 agent 调度多个 CLI 子 agent**：dispatch/status/locate/resume/watch、会话绝对路径、编排模式、提示词模板 |
| `scripts/agentctl.py` | 交互式多 agent 派发（dispatch/status/brief/locate/resume/send/watch） |
| `scripts/taskctl.py` | **几十万任务级队列**（SQLite+租约+worker 监督+模板化提示词）：`add --goal` / `plan --goal` / `tick` / `daemon` / `brief` / `stats` |
| `templates/tasks/` | 任务类型模板（generic / compare-commit / reproduce-bug / fix-bug / research），用户不用写 prompt |
| `watchdog.md` | **长任务看护完整手册**：任务形态判断、jobs.json 全字段、prompts 三种模式、提示词模板、时间参数、沙箱、排查 |
| `scripts/watchdog.sh` + `templates/` | 看护脚本与 jobs.json 模板（原 watchdog（旧版），已完全并入） |
| `memory.md` | **上下文工程与记忆**：三层记忆、主 agent 上下文预算、子 agent 输出契约、压缩/rollover、交接协议 |
| `scripts/selfcheck.py` | 一键体检 8 项能力（在用/闲置/误配），改完先跑它 |
| `scripts/deadman.py` | 死士检查通用件（配置驱动，见三·十） |
| `scripts/supervise_agents.py` / `supervise_jobs.py` | 监督的 agentctl 后端与 cron 脚本后端（见三·十一） |
| `scripts/desensitize.py` | 生成公开脱敏版（仅内部版有；公开版无此文件） |
| `templates/deadman.example.json` | 死士检查配置示例（6 种 check 类型，DB 双支持 mysql/sqlite，通知走 stdin） |
| `tests/` | 回归测试（taskctl 阈值校验/契约校验/假死判定/compaction 留痕），`python3 -m pytest tests/ -q` |
| `FIELD-NOTES.md` | **实战补丁记录**：用本 skill 真实跑任务踩到的坑与修法（监督器三后端、cron python 版本、企微拆条、完成 vs 卡住的区分……每条附现象/根因/验证），新坑先查这里 |
| `dsh-lessons.md` | DeepSeek Super-agent 学习笔记：领域模型、Ticket 状态机、stored work/幂等/保序/已读未读，以及我们采纳与不采纳的判断 |

## 一、具体 ID（最上面，直接用）

### knot-cli（免费，实测全部可用）

| ID | 上下文 | 思考档位 | 厂商 | 实测 |
|---|---|---|---|---|
| `free-model-preview` | 224K | `no_think` / `high` | 混元 | 可用 |
| `small-model` | 224K | `no_think` / `high` | 混元 | 可用 |
| `free-model` | — | — | 混元 | 可用 |
| `glm-5.3` | 128K / 200K | `low` / `high` / `max` | GLM | 可用 |
| `glm-5.3-flash` | 清单未标注 | `low` / `high` / `max` | GLM | 可用，**识图首选**，约 20s 返回 |
| `glm-5.2` | — | — | GLM | 可用 |
| `deepseek-v4-flash` | 128K | 支持思考 | DeepSeek | 可用，快 |
| `deepseek-v4-pro` | 128K | 支持思考 | DeepSeek | 可用 |

⚠️ knot 侧用 `free-model`。codebuddy CLI是`free-model`

### codebuddy CLI（**只有 hy 系列免费，x0.00**）

| ID | credits | 说明 |
|---|---|---|
| `free-model` | x0.00 | 混元旗舰，960K 输入；codebuddy 侧标准写法（knot 侧用 `free-model`） |
| `free-model-flash` | x0.00 | 混元旗舰 flash 开发版 |
| `small-model` | x0.00 | 混元上一代；**带 `-ioa` 也免费**，别因为后缀就判付费 |
| `echo` | x0.00 | Echo agent 工作流专用（特殊用途） |

**不免费但便宜、可以用**（按 credits 计费，不是免费通道）：

- `gpt-6-luna` x0.07、`minimax-m3.1-flash` x0.08、`glm-5.3-flash-ioa` x0.08（**识图首选**）、`deepseek-v4.1-flash` x0.11（1M 上下文）、`mimo-v2.6-pro` x0.13、`gpt-5.6-luna` x0.14。
- 需要多模态识图（hy 系列不支持）或要比特 hy 更快的短任务时，用这一档，**不要直接上 `claude-*` / `gpt-6-astra`**。

**贵，别用于批量**：`claude-opus-*` x2.17~3.33、`gpt-5.6-sol` x3.47、`gpt-6-astra` x6.67。

命名规则：`-ioa` 是 codebuddy 侧后缀，**knot 侧不能用带 `-ioa` 的名字**（会报「请求模型未被可用凭证池允许」）。完整 40+ 模型分层表、场景选型、knot↔codebuddy 对应关系内联在 `model-catalog.md`。

> 旧版本此处写「`*-ioa` 都不是免费通道」**是错的**：`small-model` 实测 x0.00。"只有 hy 系列免费"成立，但免费的 ID 不止 `free-model`/`small-model`/`free-model-preview` 三个。

### 并发怎么算

- 凭证池配置 `项目级模型配置（路径随部署而变）`：`knot.allowed_models` = `free-model, small-model, glm-5.3, glm-5.3-flash, deepseek-v4-flash, deepseek-v4-pro`（6 个），`own(codebuddy).allowed_models` = `free-model, small-model`（2 个），`max_concurrency_per_model: 3`。
- **官方限流口径（平台官方限流文档，2026-11-12 查证）**：单个智能体的官方速率上限、官方天级上限；模型调用（人+模型粒度）模型调用速率上限；个人 LLM 总量 ≤官方天级上限（团队 4000）；各模型独立限频、各模型独立限频、各模型独立限频。天级按**滚动 24h** 重置不是自然日；各模型限频**相互独立**，撞限流切模型有效。
- **限制的是速率，不是固定并发数**（旧版此处写「建议按 16 跑」是错的）：`并发上限 = 允许速率(次/分) × 平均单次耗时(秒) / 60`。但**用户给的实测口径优先**：**同模型最多 2 并发**；**多模型合计全局上限 10**（其它项目也在用）。`recommend_workers()` clamp 到每模型 2；总并发 = min(10, 模型数×2)。一次智能体调用会触发多次模型调用，并发会话把速率放大，这就是「并发报错、单个正常」的根因。注意**这份官方数字只适用于 knot**，codebuddy 的 429 带恢复时间通知、是另一套机制。
- 按模型分桶 + 每模型 `Semaphore(2)` 仍要做（2026-11-12 实测：全局 10 路不分桶 → 48 条失败 32；按模型分桶 → 48 条成功 35）。开并发前先 `python3 knot_batch.py` 看全局占用（业务项目 / 知识库等项目在抢同一免费池）。**孤儿 chat（ppid=1 挂 20+ 分钟）占额度不释放**，只按自己 PID 清。完整数字、公式、自动恢复状态机内联在 `knot-limits.md`。

## 二、knot-cli 用法

**路径（本机有两个，版本不同）**
```bash
command -v knot-cli          # <knot-cli 路径> → v0.34.0
<knot-cli 路径> --version   # v0.35.1（技能文档用的绝对路径）
```

**最常用**
```bash
# 一句话
knot-cli chat -p "用一句话解释写时复制"

# 指定模型
knot-cli chat -p "审查这段代码的缺陷" -m free-model

# 识图（图片必须绝对路径）
knot-cli chat -p "这是什么界面" --images /abs/path/shot.png -m glm-5.3-flash

# 塞文件
knot-cli chat -p "总结这份日志" --files /abs/path/app.log

# 指定智能体
knot-cli list-agents
knot-cli chat -a <agent_id> -p "做代码审查" -m free-model

# 思考档位 + 上下文
knot-cli chat --no-update -m glm-5.3 --reasoning-effort high --max-context-tokens 200K -p "…"
```

**接进脚本（本项目在用）**
```bash
knot-cli chat --no-update --output-format text --model <id> -p "<完整 prompt>"
```

三个坑：
1. **不读 stdin** —— prompt 只能走 `-p/--prompt`，管道喂进去不算。
2. `--output-format stream-json` 下内容分片，`rawEvent.content` 要自己累加拼接，取最后一片会丢内容；图省事用 `text`。
3. 续接用 `--sessionId <id>`，不是重新发 prompt。
4. **限流处理分场景，别一律 45s×3**：
   - 单个长任务（一次要跑几分钟的调研/改文档）：官方口径下 `429` 是「人+模型粒度」限频且**各模型相互独立**，应**切下一个模型**（fallback 链），不要原地退避 45s 重试同一模型；平台负载文案「模型资源非常紧张」才用短退避 8s/16s 最多 2 次。
   - **批量判定（几十~几千条短 prompt）：绝对不要用这个封装**。实测 `<业务调用点>`（retries=3 / timeout=180 / 45s 退避）放进 18 路并发后 **4 分钟 0 条返回**——前批撞 429 全部进入退避，worker 占满，后续根本发不出去。改单次调用 `timeout=25`、不重试、失败不写库留到下轮断点续跑，同一批 24 条 46 秒跑完。
   - 判据：429 占比 >30% 且随并发数变化 = **容量问题**，按模型分桶降并发 + 切模型；偶发单条格式错 = 抖动，短退避 8s/16s 最多 2 次。`timeout` 是通道占用（官方限流文档不管），不重试、错峰或绕过。详见 `knot-limits.md` §3 与 `knot-limits.md` §4。
5. **清理**：`knot-cli chat` 对 `SIGTERM` 不响应，卡住只能 `kill -9`；**不要 `pkill -f` 批量杀**，会误杀别人的 upstreamfix/知识库任务，只按自己 PID 清。

**调用会打印** `requestID` 和 `sessionID`。实测 `--spending-limit 0` 不拒绝，即免费通道无额度门槛。

## 三、codebuddy CLI 用法

**版本**：`2.182.0`

```bash
# 一次性问答（本项目标准形态）
codebuddy -p --output-format text --permission-mode bypassPermissions \
  --tools '' --model free-model "只回答两个字：收到"

# 加载自定义 system prompt（审代码/接智能体）
codebuddy -p --output-format text --permission-mode bypassPermissions \
  --tools '' --model free-model \
  --system-prompt-file /abs/path/ru.sys.txt "<task>"
```

**地基坑（踩过，务必记住）**：
- `--agents '{"rev":{"prompt":…}}'` **单独用不生效**，测的是默认 agent（实测输出只有 137B、强制字段 0/8）。必须用 `--system-prompt-file` 或 `--agents … --agent rev`，且跑完逐字验收输出含目标 agent 的纪律行为。
- `--tools ''` 禁全部工具；禁工具时若 prompt 要求补查文件，模型会卡在"我要 grep"然后截断——合成/离线场景要在 prompt 里注明"相关文件已全部给出，用文本推演验证语义，不要发起工具调用"。
- `--output-format` 支持 `text` / `json` / `stream-json`；`--fallback-model` 可在主模型过载时自动切。
- `--system-prompt-file` 读的是文件内容（去掉 frontmatter 更稳），**不是** `--system-prompt` 字符串。

### 版本与假绿灯（2026-11-11 实测，调 codebuddy 前必读）

本机 `which -a codebuddy` 有两个二进制：PATH 优先的 `/root/.nvm/versions/node/v22.23.2/bin/codebuddy` 是 **2.183.0**，`/usr/local/bin/codebuddy` 是 **2.132.0**。2.183.0 会返回

```
{"type":"error","error":"Plugin runtime refresh settled wait exceeded 5000ms"}
```

**退出码仍是 0、stderr 为空**，没有任何模型回答；2.132.0 加 `--model free-model` 正常返回内容。本机登录是好的（`~/.codebuddy/.env` 里有 API key），不是没登录、也不用额外 token，source 那个 .env 也修不好 2.183.0。

这是 `PLUGIN_REFRESH_SETTLED_TIMEOUT`（5 秒插件刷新等待超时），不是二进制损坏、不是废弃文件；该路径还被 IDE 交互会话和别的用户的 `-p` 任务实际使用，**不要删**。最危险的连带问题：只看 `returncode == 0` / 输出非空的封装会把这条 error JSON 判成 200 成功再写库，所以封装末尾必须检测 `"type":"error"` 并返回 500。稳定做法：用 `CODEBUDDY_CLI_BIN` 选择 `/usr/local/bin/codebuddy`（只是换用另一个已安装的二进制）。

根因是 **PATH 优先级**：IDE 会话把 nvm 目录排前面解析到 2.183.0，cron 的干净 PATH 解析到 `/usr/local/bin/codebuddy` 2.132.0（正常）；实测与登录、IDE 会话变量、MCP/设置参数、调用参数都无关。完整命令形态、环境变量剥离（`child_process_env` 解决的是另一类「零输出卡死」问题）、Node wrapper 大 prompt 传参、一行自检脚本、单测写法、knot `free-model` 与 codebuddy `free-model` 命名差异，全部内联在同目录的 `codebuddy-cli-notes.md`（可整篇复用）。

## 四、本项目（示例扫描系统）的实际配置

`judge_p0.py` / `judge_pending.py` 用的模型与并发：

```python
MODELS = ['glm-5.3-flash','glm-5.3','deepseek-v4-flash','deepseek-v4-pro','free-model']  # small-model 默认不进池
PER_MODEL = 2          # 每模型最多 2 路；默认 free-model，multi-model 时 min(10, 模型数×2)
KNOT = '<knot-cli 路径>'
```

- 双模型交叉：被测 + 裁判必须是**两个不同模型**（如 `glm-5.3-flash` 出报告、`glm-5.3` 当裁判），同一模型自己判自己测不出偏袒。
- 实测记录：`free-model` 曾写进 MODELS 导致 12 条判定里 4 条"解析失败:不支持该模型"，改成 `free-model` 后全部正常。
- 别并发打爆网络：全量取数时同时跑模型调用会 `fetch failed`；网络取数串行、模型判定并发。


## 五、会话存档与全局并发（要点）

- **knot-cli**：`/root/.bg-agent/cli/<nonce>.json`（`cli_pid`/`request_id`/`session_id`），主日志 `<knot 主日志路径>`（覆盖多天，不是按天滚动）；stdout 里的 `requestID`/`sessionID` 是检索键。**每次 chat 伴随一个 `chat-watchdog`，数并发要除以 2**。
- **codebuddy**：`/root/.codebuddy/projects/<workspace-slug>/<session-uuid>.jsonl` + 同目录 `<uuid>/tool-results/*.txt`；跨会话索引 `/root/.codebuddy/history.jsonl`。
- **iteration**：`artifacts/mtr_iteration/<task>/` 下 `iteration-run.log`、`<task>.sqlite`、`transcripts/`。
- **全局统计三坑**（会把 0 次限流误算成 640 次）：`grep 429` 命中时间戳毫秒与文件名；`限流` 命中脚本文档正文；`IsolateScheduler wake` 是心跳不是请求。只数带 `request_id`/`model` 的行。

按 `requestID`/`sessionID` 反查的命令内联在 `ai-session-forensics.md`；闸门作用域边界见 `knot-limits.md` 第九节。

## 六、批量调用：直接用 `knot_batch.py`（2026-11-12 新增）

同目录 **`knot_batch.py` 可直接 import 或命令行跑**，把上面所有经验封装好了：

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

它内置：`/proc` 全局统计（排除 watchdog，pgrep 在 Python 子进程里会漏）、按模型分桶信号量、
429/假绿灯识别（RC=0 但 stdout 是错误串）、`[任务规划中]` 前缀与围栏/requestID 后缀的 JSON 兜底解析、
低频探活。**实测 12 条 25 秒成功 10 条**（另 1 条 429、1 条 timeout，都不写库留待下轮）。

全部实测数据、重试有无用的判据、探活频率、sqlite 锁/孤儿/codebuddy 假绿灯等配套坑，
内联在同目录 **`knot-limits.md`**（排查顺序在 §7，全局占用分析在 §1）。

## 七、Knot 官方限流（要点，全文见 `knot-limits.md`）

**官方文档只讲 knot，不是 codebuddy**：codebuddy 的 429 会通知「将在 <时刻> 重置」，可整模型冷却到那一刻；**knot 的 429 没有恢复时间通知**，只能靠探测式降并发。

数字：单个智能体的官方速率上限 + 官方天级上限；模型调用（人+模型粒度）模型调用速率上限；个人 ≤官方天级上限（团队 4000）；GLM-5.3 30/分 + 1500/5h、GLM-5.3-Flash 45/分 + 3000/5h、DeepSeek-V4-Flash/Pro/Hy3/Hy4-Preview 120/分 + 18000/天；天级按**滚动 24h** 重置。

**并发不是固定数**：`并发 = 允许速率(次/分) × 平均耗时(秒) / 60`。但**用户实测口径优先**：同模型最多 2 并发，多模型合计全局上限 10；`recommend_workers()` clamp 到每模型 2。

## 八、AIMD + 指数静默（要点，推导与模拟见 `knot-limits.md` 第七节）

连续 5 次成功才 +1 路（上限 2）；一次 429 立刻砍到 1；连续 429 静默 60/120/240/480s 封顶且**静默期不发请求**；一次成功把失败计数清零；`timeout` 属通道占用，不降并发只打断计数。模拟报错率 6.0%（9 个错、吞吐 142），比固定 1 路报错少 64% 且吞吐高 49%。

**验证边界**：模拟 + 单测 + 故障注入通过；生产 knot 侧 429 未触发（批量判定已走 codebuddy），**没有线上收敛证据**。

## 九、全局观测与本项目闸门的边界

本项目闸门（`<项目私有状态文件>`）是**私有**的，其它项目不认，本地无法全局协调；`day_remaining()` 只记本项目调用，不是官方「个人 ≤2000/24h」的全人账本。能严格保证的只有「自己 ≤2 并发、≤3.5 次/分、观测到拥堵时排队/静默」。

全局看 `<knot 主日志路径>`：2026-11-12 实测常驻 `knot-cli serve` 已跑 22 小时，近 24h 真实请求 1275 行但呈突发式（峰值 666/小时，多数小时 0~20）。方法与统计坑见 `knot-limits.md` 第九节。

## 十、用户偏好（2026-11-12 最终口径）：默认 free-model、每模型 2 路、全局上限 10

> 「small-model 其实有点菜了，能不用可以不用，默认都是 free-model」+「同模型 2 并发最多合理，多模型合计全局上限约 10」。

- **默认只用 free-model**，small-model 不进默认池（偏弱，要用显式配）。knot 侧 `free-model`；codebuddy 侧 `free-model`（= `free-model`）。不用 `free-model-preview`、`free-model-flash`、`echo`，也不用 deepseek / glm / flash / kimi。角色划分与可配置项见开头「模型安排」。
- **并发语义（修正）**：默认 `free-model` 一个模型，**每模型最多 2 路**，多模型时合计 `min(10, 模型数×2)`。旧实现把「每模型 2」误做成「本项目总量 2」，已改。`<业务环境变量>=2`、`<业务环境变量>=10`（全局上限）、`MTR_KNOT_GLOBAL_CAP=10`；批内按每 2 条连续任务分给同一模型，保证不超。AIMD 从 2 起步，连续成功才上探。
- **不做全局配额推演**：`knot_batch.recommend()` 只报全局 chat 数与按项目/模型分布，**不再计算「本项目还能开几路」**——别的项目占多少算不清，也没必要算。`global_load()` 仅作诊断。
- **贵档硬禁用（严格）**：只允许 x0.00 和 **≤0.15 credits**；`glm-5.3-flashx`(0.19)、`minimax-m2.7-ioa`(0.19)、`claude-*`、`gpt-6-astra` 等一律不用。代码层 `assert_cb_model_allowed()` 在发请求前拒绝，不依赖 429 自动回落。环境变量 `<业务环境变量>=0` 才能关（默认开）。
- **免费口径**：codebuddy 只有 hy 系列 x0.00（`free-model` / `free-model-flash` / `small-model`，另有特殊 `echo`）；但不是无限量，有账号额度限流、429 会通知重置时刻。knot 侧 hy 系列实测扣费 0，但限流**不给恢复时间**。便宜的付费档（`glm-5.3-flash-ioa` x0.08、`deepseek-v4.1-flash` x0.11 等）记在 `model-catalog.md`，本项目不用。
- **串行/2 路时都要轮转模型**：`static_scan_runner` 用 `start_model = batch_no % len(models)`，否则只会用列表第一个，把它的额度用尽、另一个闲置。
- **无 diff 的条目不进队列**：`pending()` 直接排除 `main_diff` 为空的 commit（重试一万次也不会有结论），补扫补上 diff 后自动回到队列。

## 十一、用 1 个 agent 调度多个子 agent（要点，全文见 `orchestrator.md`）

主 agent 只做拆解与验收，重活交给多个 CLI 子 agent，每个子任务都有确定的 session id、会话文件绝对路径、输出目录。

```bash
ACT=<skill 安装目录>/agent-ops/scripts/agentctl.py
python3 $ACT dispatch --name t1 --backend codebuddy --model free-model \
  --workdir <你的项目目录> --prompt-file /tmp/t1.md
python3 $ACT status          # 进程/退出码/运行时长/会话文件
python3 $ACT locate t1       # 会话文件、输出目录、日志的绝对路径
python3 $ACT resume t1       # 带原会话续接；会话没了自动降级新建
python3 $ACT send t1 "只回答三个字：已收到"   # 给已结束的任务追加指令
python3 $ACT watch --quiet   # 挂 cron，批量续接挂掉的任务
```

- **实时看进度**：读会话 jsonl（`status` 给出事件数与最后事件时间），不要看 `run.log` 大小——stdout 重定向是块缓冲，结束才 flush；要实时 stdout 用 `script -q -c`。
- **追加输入**：已结束的任务用 `send`（带 `--resume`，实测可靠）；运行中的任务不要插话，消息会写进 jsonl 但不会被处理。
- **会话路径**：codebuddy 的 `--session-id` 决定文件名，落在 `~/.codebuddy/projects/<workspace-slug>/<session-id>.jsonl`；knot 没有 jsonl，看任务目录的 `run.log`。`locate` 直接给绝对路径。
- **任务目录**：`~/.codebuddy/agentctl/<name>/{prompt.md,run.log,pid,exit,out/}`。
- **提示词必须要求写 `progress.md`**：上下文压缩后只有落盘进度能恢复，resume 全靠它。
- **红线不变**：只允许 x0.00 / ≤0.15 credits；每模型 2 路、全局上限 10；不做全局配额推演。
- 三个实测坑已内置规避：`--port 0`（防 EADDRINUSE）、`--` 分隔长 prompt（防 `-` 开头被当选项）、不用 `unlink` 删任务文件（沙箱跨设备 Trash 会递归）。
- 旧的 `~/.codebuddy/watchdog/jobs.json` 继续由 `scripts/watchdog.sh` 接管，与 `agentctl` 状态目录互不干扰。

## 十二、并发是本项目内部量，429 感知靠本地反馈（2026-11-12）

**分层要分清**：每模型 2 路 / 全局上限 10 是**本项目自己内部的并发上限**，不是对全局容量的推算。用户明确「先不需要考虑全局」——默认不做全局配额推演、不按全局 chat 数让路（`MTR_KNOT_GLOBAL_MAX` 默认 0 关闭；显式设才启用）。knot 主日志、`global_knot_chats()` 这些全局观测属于**事后排查工具**，不是调度输入。

**但必须能感知是否 429 受限**，两条通道分开处理：

| 通道 | 429 形态 | 感知方式 | 恢复 |
|---|---|---|---|
| codebuddy | `使用量已超出频率限制，将在 <时刻> 重置`（有通知时间） | **stdout+stderr 合并检测**，优先于「普通错误串」判断；`-p` 下 RC=0 且错误串在 stdout 的假绿灯必须拦住 | 整模型冷却到通知时刻、持久化到 `<项目私有状态文件>`，到期自动回归，其余模型继续跑 |
| knot | `{"code":429,"msg":"too many requests"}`（**无恢复时间**） | `_is_transport_error(stdout+stderr)` 识别 RC=0 的假绿灯 | AIMD 降并发到 1 + 指数静默 60/120/240/480s，连续 5 次成功才升 1 路 |

实测（2026-11-12 故障注入）：
- codebuddy 假绿灯（RC=0、429 在 stdout）→ 被 `LLMBackendUnavailable` 拦截，`free-model` 冷却到 `2026-11-13 01:00:00`，`cb_available_models` 只剩 `small-model`（**当时 small-model 仍在默认池；现默认池已只留 free-model，冷却后会无可用模型，需显式配第二个**）。**修复前只看 stderr，会把它当普通失败甚至当 AI 结论返回，冷却不触发**。
- knot 假绿灯 → `_is_transport_error` 识别，`slots 2→1`、`fails=1`、静默 60s；连续 429 指数递增、一次成功 `fails` 清零。
- `wait_for_knot_slot()` 默认返回 True（不读全局）；显式设 `MTR_KNOT_GLOBAL_MAX=12` 才启用全局让路。

排查口诀：**队列突然零成功时，先 grep `429` / `使用量已超出` / 冷却文件，别先归因到全局拥堵**。两种 429 的恢复逻辑不能混用：codebuddy 能解析时刻，knot 只能靠反馈探测。

## 十三、长程判活与假死（2026-11-12 补，含实测）

- **断点恢复实测通过**：预置 progress.md 三步（第3步未完成）→ 新会话子任务回答「第3步」并追加「接着做：步骤3」，会话 jsonl 有 11 事件。L3 落盘记忆确实跨会话生效。
- **watchdog.sh**：cron 每 1 分钟叫醒、`check_interval_minutes=5` 实际检查，`kill -0 pid` 判活；`stale_minutes` 默认 0（关闭日志假死判定，因 `-p` 输出块缓冲）。
- **taskctl**：`daemon --interval 30s` tick；新增 `TASKCTL_STALE=900s` 假死判定，看会话 jsonl / progress.md / result.json / run.log 的 mtime，全超时无增长就 `killpg` 精确杀 + 重排 + 原因回灌。实测 60s 不判死、1000s 判死、写新进度复活、0 关闭；端到端 `stale_requeue` 通过。
- **不用 AI 去看是否卡住**：额外模型调用更慢更贵且 AI 自己也会卡；mtime 是内核给的客观事实。会话 jsonl 边跑边写，比 stdout 可靠。
- **并发与 watchdog 的关系**：watchdog/daemon 是**监督进程，不是 agent**，不调模型、不占并发额度。一个任务 = 1 个 CLI agent + 1 个不调模型的 Python 监督进程。所以「全局 10 并发」= 最多 10 个任务，**不是 5 个**。

完整架构图与间隔表见 `memory.md` 第九节。

## 十四、监督是「模型给模型」，不是脚本判活（2026-11-12 纠正）

原 watchdog skill 核心是「定时 `--resume` + 固定提示词 → 模型读进度自己判断下一步」。我一度降级成纯脚本 `mtime→killpg`，错了：**脚本看不出重复报错死循环、不会应对新情况**。已改回并落在 `scripts/supervisor.py`：

- 脚本 `taskctl` 发现无增长只**标记** `need_supervision`、续租，**绝不自行杀进程**。
- `supervisor.py` 定时(1800s)/事件(120s 无增长或有 error) 触发，把紧凑快照交给监督者模型（默认 `SUPERVISOR_MODEL=free-model`，可配），模型输出 JSON 决策 `continue/nudge/restart/escalate/finish`。
- 脚本只做归一化、防呆与执行；`guidance.md` 自动注入下一轮 prompt。模型输出解析失败/超时 → 本轮不动，不误杀。
- 人只读 `stats`/`brief`，`escalate` 才需介入。

真实实测：模型识别出「步骤2 同一报错重复 3 次 = 重试死循环」，给出「先诊断根因再继续」的 nudge 指令，45.8s 完成，`guidance.md` 落盘且注入下一轮 prompt 验证为 True。详见 `memory.md` 第十节。
