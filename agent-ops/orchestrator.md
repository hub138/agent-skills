# 用 1 个 agent 调度多个 CLI 子 agent（super agent 实操）

> 目标：主 agent 只做拆解和验收，重活交给多个 CLI 子 agent（不同模型、不同后端）去跑；每个子任务都有**确定的 session id、会话文件绝对路径、输出目录**，挂了能续接。
> 工具：同目录 `scripts/agentctl.py`（新）与 `scripts/watchdog.sh`（历史兼容，见 §8）。

## 一、能力边界（先认清哪些能做、哪些不能）

| 能 | 不能 |
|---|---|
| 主 agent 用 `agentctl dispatch` 起 N 个后台子任务，各自指定模型/后端/工作目录 | 子 agent 之间不会自动对话；需要交换信息就落文件 |
| 随时 `status` 看每个子任务的进程/退出码/会话文件/运行时长 | 读**会话 jsonl** 实时看它做到哪（`status` 显示事件数/最后事件时间）；stdout 重定向是块缓冲，要实时得用 PTY |
| `locate` 拿到会话文件与输出目录的**绝对路径**，直接读 jsonl 看它做到哪 | 不能保证子 agent 一定调用工具；要写清产出文件路径与格式 |
| 挂了用 `resume` 带原 session 续接（codebuddy `--resume` / knot `--sessionId`） | 会话已被清理时无法真正续接，只能新建（工具会自动降级） |
| `watch` 挂 cron，批量检查并续接 | 不做跨项目全局配额推演（用户明确不做，算不清） |

## 二、快速开始

```bash
ACT=<skill 安装目录>/agent-ops/scripts/agentctl.py

# 1) 派发：自己指定 session id，之后就能精确定位
python3 $ACT dispatch --name port-4364 \
  --backend codebuddy --model $WORKER_MODEL \
  --workdir <你的项目目录> \
  --prompt-file /tmp/prompt-port-4364.md

# 2) 看所有子任务
python3 $ACT status

# 3) 定位会话文件 / 输出目录 / 日志
python3 $ACT locate port-4364

# 4) 看日志
python3 $ACT logs port-4364 -n 60

# 5) 续接（会话在就带原会话；不在则降级新建）
python3 $ACT resume port-4364

# 5.1) 给已结束的任务追加一条指令（等价于 resume 进去接着说）
python3 $ACT send port-4364 "只回答三个字：已收到"

# 6) 挂 cron：每 5 分钟检查并续接挂掉的任务
*/5 * * * * /root/.pyenv/versions/3.12.0/bin/python3 \
  <skill 安装目录>/agent-ops/scripts/agentctl.py watch --quiet
```

## 三、会话绝对路径怎么来的（这是关键）

`dispatch` 时**自己传 `--session-id`**，不依赖解析输出：

| 后端 | 会话文件绝对路径 | 说明 |
|---|---|---|
| codebuddy | `~/.codebuddy/projects/<workspace-slug>/<session-id>.jsonl` | `workspace-slug` 由 `--workdir` 决定（如 `/tmp` → `tmp`，`<工作目录>` → `data-code-AIagent`）；同目录还有 `<uuid>/tool-results/*.txt` |
| codebuddy 助手索引 | `~/.codebuddy/history.jsonl` | 跨会话检索 |
| knot | 无 jsonl；看 `~/.codebuddy/agentctl/<name>/run.log` | stdout 里的 `requestID` / `sessionID` 可反查 `/root/.bg-agent/cli/<nonce>.json` |

`agentctl locate` 已经把上面这些算好，直接给绝对路径，不用自己拼。

任务目录固定为 `~/.codebuddy/agentctl/<name>/`：

```
prompt.md   本次/续接用的完整提示词（resume 会复用）
run.log     子进程 stdout+stderr（含每次 start/resume 分隔行）
pid / exit  当前 pid 与上次退出码（exit 空 = 还没退出）
out/        子任务自己的产出目录，提示词里要求它写这里
```

## 三·五、实时读输出 & 给任务追加输入（ 实测）

| 想做的事 | 可行 | 怎么做 |
|---|---|---|
| 实时看子任务做到哪 | ✅ | 读**会话 jsonl**：`status` 直接显示「事件数 / 最后事件时间」；也可 `tail -f <locate 给的会话文件>` |
| 实时看 stdout | ⚠️ 默认不行 | stdout 重定向到文件时是**块缓冲**：实测前 24 秒 0 字节，进程结束才一次性写入 11.9KB。要实时只能给伪终端：`script -q -c "<命令>" run.log` |
| 给**已结束**任务追加指令 | ✅ 可靠 | `agentctl send <name> "新指令"`：带原会话 `--resume`，实测能正常返回「已收到」并写入 jsonl |
| 给**运行中**任务插话 | ❌ 不可靠 | 实测并发 resume 只把新消息 append 进 jsonl，原进程已按旧上下文跑完，**不会处理它**；必须等进程结束再 send |
| 会话被清理后还想续接 | ⚠️ 降级 | `--resume-create-missing` 只有 **2.183.0** 有（语义：目标会话不存在时用同一 id 新建空会话，而不是失败）；2.132.0 没有，`agentctl` 检测秒退后自动降级新建 |

**为什么 jsonl 比 stdout 可靠**：会话文件是 append 写，实测 6 秒内就出现并持续追加；stdout 走 Node 的块缓冲，非 TTY 时要攒满才 flush。所以监控状态看 jsonl，不要看 `run.log` 的大小。

**为什么「思考中」jsonl 也不动**：模型在 reasoning 阶段不产生新事件，mtime 不动是正常的——这就是 `watchdog` 里 `stale_minutes` 默认 0（关闭假死判定）的原因。

## 三·六、机器模型：从 DeepSeek Super-agent 借来的（详见 `dsh-lessons.md`）

主 agent 管多个子 agent，真正的难点不是「多开进程」，而是**状态放哪、失败怎么办、消息怎么不丢**。参考 `dsh-superagent-prototype`（MIT，研究原型）后，我们采纳了四条：

| 机制 | 做法 | 我们落地在哪 |
|---|---|---|
| **Stored work** | 决策后要做的动作先入库，提交后才执行；失败 2s 起指数退避，**连续 3 次才转人工** | `agentctl` 的 `effects` 队列 |
| **幂等** | 同名任务还活着就拒绝重复派发（同一 Trigger 只建一个 Ticket） | `dispatch` 返回码 4 |
| **保序** | 同一任务的多条 `send` 按入队顺序投递；前一条未完成时后一条等待 | `effects` 按 `seq` 排序 + 每轮每任务只投一条 |
| **状态推导** | 状态从落盘事实推导（effect 待执行 / 进程存活 / 退出码 / 最后事件），不靠内存 | `inspect()` |

我们的状态机（对应它的 Ticket stages）：

| 状态 | 含义 | 下一步 |
|---|---|---|
| `queued` | 有动作待执行（首次拉起或重试中） | 等 `watch` 或下轮 flush |
| `working` | 进程活着 | 等它结束；要插话先等结束 |
| `idle` | 正常退出但还没有结论事件 | 可以 `send` 追加指令 |
| `done` | 正常退出且有结论 | 读产出/收工 |
| `failed` | 异常退出，重试未耗尽 | `watch` 自动重试 |
| `awaiting-person` | 连续 3 次失败 | **需要人看**，不再自动重试 |

**沟通纪律**（照抄它的 prompt 规则）：

- 子任务的报告、后台任务结束会**自动作为状态出现**，不要 `sleep`/轮询去等结果。
- **日常进度保持内部**：只有需要人决策、或人能直接用结果时才发消息。
- 只有「需要人拍板」才升级为 `awaiting-person`；模型重试、额度错误不构成打扰人的理由。

**没抄的部分**：Source/Trigger/Thread/Eval/Mandate 的完整实现。我们是人直接派任务，没有多源事件流和团队授权表，照搬是过度设计。

## 三·七、上下文预算（主 agent 不爆的关键，全文见 `memory.md`）

**主 agent 的上下文是唯一稀缺资源。** 子 agent 跑半小时能产出几千行，3 个就能把主上下文撑满。硬规则：

| 允许读 | 禁止读 |
|---|---|
| `agentctl status`（每任务一行） | `run.log` 全文（只允许 `tail -20`） |
| `agentctl brief <name>`（result.json 的 4 个字段） | 子任务会话 jsonl 全文（只取最后一条 assistant 文本） |
| `locate` 给的路径，按需读**那几行** | 把子 agent 原始输出粘回主对话 |

**三层记忆**：L1 会话只放「任务清单 + 一行状态 + 待决策问题」；L2 状态在 `registry/effects`；L3 工作区在任务目录（`prompt.md` / `progress.md` / `result.json`）。**能落盘的绝不靠上下文记。**

**子 agent 输出契约**（写进每个 `prompt.md`）：

```json
{"status":"done|blocked|failed","summary":"≤200字","evidence":["路径/行号，≤5条"],"question":"一个具体问题或null","next":"建议或null"}
```

**主 agent 不做这些**（照抄 dsh 的 orchestrator 禁令）：不读代码细节、不读子 agent 日志、不替子 agent 调试、不追加需求或实现计划。只做评估、派发、转发问题、验收结果。

任务数 >5 时，把清单写进 `~/.codebuddy/agentctl/plan.md`，新开一轮先读它。

## 三·八、几十万任务：用 `scripts/taskctl.py`（SQLite 队列）

`agentctl` 适合「交互式起几个任务」；**批量、无人值守、几十万任务用 `taskctl`**。

### 为什么能到几十万

- 任务本体是数据库一行，不是进程。几十万任务 = 几十万行，不是几十万进程。
- 并发由 worker 池限制（默认 2，用户口径），队列深度无上限。
- 每次操作只碰索引命中的少量行，不做全表扫描、不 glob 目录。
- **租约（lease）代替 pid**：worker 崩溃/机器重启后，租约过期自动回收重排。

10 万行实测（）：

| 操作 | 耗时 |
|---|---|
| 批量插入 10 万行 | 0.6s |
| 取 2 条待跑（`status,priority,id` 索引） | **0.10 ms** |
| 租约过期扫描 | **0.03 ms** |
| 按状态聚合 | 7.5 ms |
| 分页 list（offset 1000） | 19 ms |
| 真实 `add`（建目录+渲染模板+写 prompt+插入） | 6.6 ms/条 → 1 万条约 1.1 分钟 |
| 数据库体积 | 19.8 MB / 10 万行 |

### 不懂 AI 的人怎么用（三步，不写提示词）

```bash
T=<skill 安装目录>/agent-ops/scripts/taskctl.py

# 1) 看看能派什么活（类型 + 每类要填什么）
python3 $T kinds

# 2) 加任务：只给类型和输入
python3 $T add --kind generic --input '{"topic":"检查这个仓库的构建脚本"}'
python3 $T add --kind reproduce-bug --input '{"bug_id":"37543247","repo":"/data/db","test_case":"mtr/x.test"}'

# 批量：每行一个 JSON（kind/input/name/priority）
python3 $T add-file tasks.txt

# 3) 跑：常驻循环（推荐）或 cron 每分钟一次
python3 $T daemon --concurrency 2 --interval 30 &
# 或：* * * * * python3 $T tick --concurrency 2 --quiet
```

**提示词不用写**：`--kind` 决定用 `templates/tasks/<kind>.md`，模板里已经写好进度文件、输出契约、禁止项，渲染时填进输出目录和输入。

### 状态机与恢复

`queued → running → done / blocked / failed / cancelled`

- `running` 带租约（默认 1800s）。租约过期且进程不在 → 自动重排；重试耗尽 → `failed`。
- **结果优先**：`result.json` 的 `status` 有效就直接收尾，不等退出码（进程可能被 killpg 杀掉、不落退出码）。
- 首次运行用 `--session-id` 新建，重试才 `--resume`；会话丢失（`No conversation found`）会自动换新 session 重排。
- `retry` 手动重置、`cancel` 取消。

### 三套东西的分工

| 工具 | 场景 | 状态在哪 |
|---|---|---|
| `taskctl` | 几十万任务、无人值守、批量 | SQLite（`~/.codebuddy/agentctl/tasks.db`） |
| `agentctl` | 交互式起几个任务、看护 | JSON registry |
| `watchdog.sh` | 历史 `jobs.json` 任务 | 文件 state |

### 已验证 / 未验证（如实说）

**已验证**：10 万行插入与索引查询；真实 `add → tick 拉起 → 子任务写 progress.md/result.json/DONE → 结果优先收尾 → brief 读出 5 字段` 全链路跑通；租约回收、会话丢失重排、`kinds` 可用。

**未验证**：见下节「三·九」的完整审计与未验证清单。

## 三·九、第二轮审判式审计（，别当成「已经好了」）

第一版 `taskctl` 只做了单链路冒烟就宣称可用，用并发测试和长任务模拟一压，暴露了**会让几十万任务全盘失效**的问题。以下都是实测复现后修的，不是推测。

| 审计项 | 复现证据 | 修复 |
|---|---|---|
| **抢占竞态** | 并发上限=1，两个 `tick` 同时跑 → 同一任务被 `spawn` **2 次**（`attempts=2`） | `BEGIN IMMEDIATE` 拿 SQLite 写锁 + `UPDATE ... WHERE status='queued'` 判 `rowcount`，commit 之后才起进程 |
| **租约误判** | 进程还活着但租约过期 → 被置回 `queued`，会再起一个进程 | `tick` 每轮给存活进程**续租**；回收时也先验 `/proc/<pid>` |
| **事务冲突** | 回收阶段已有隐式事务，再 `BEGIN IMMEDIATE` → `cannot start a transaction within a transaction` | 显式 `conn.commit()` 后再开事务 |
| **exit 不落盘** | `codebuddy` 超时清理 `killpg` 整个进程组，bash 包装层被连带杀掉，`exit` 永远空 | 改为**独立 Python worker 进程**持有 `Popen` 并写 pid/exit，两层 `start_new_session` 隔离；不用 bash 包装 |
| **session 首次 `--resume`** | 首次运行 session 为空 → `No conversation found` 启动即退 | 首次 `--session-id`，重试才 `--resume`；会话丢失自动换新 session 重排 |
| **10 万目录爆炸** | 旧 `add` 每条都建目录+写 prompt.md → 10 万任务 = 30 万 inode | **惰性创建**：`add` 只插一行，目录和提示词只在 `tick` 真正拉起时生成。实测加 2000 条、目录数 = **0** |
| **outbox 空表** | 建了表但从未写入，是「看起来有」 | 抢占时写 `spawn` 事件、commit 后执行，成功标 done、失败标 failed |
| **无模型红线** | `add --model 高价模型` 能通过 | `assert_model()`：只允许 白名单内且不超预算，add 与 tick 双重校验 |
| **result 无校验** | 子任务写 `{"status":"ok"}` 也会被当成功 | `validate_result()` 校验 status 枚举 / summary 长度 / evidence 类型；不合格重排并把原因写进下次 prompt |
| **cancel 不杀进程** | 只改状态，进程继续跑继续写 | 读 `worker_id` 里的 pid，`killpg(SIGTERM)` |
| **还要填 JSON** | `add --input '{"topic":"..."}'` 对不懂 AI 的人仍是门槛 | `add --goal "一句话"` + `plan --goal "一句话"` 自动拆任务 |

复测（全部 PASS）：

```
原子抢占：两个 tick 并发=1 → spawn 1 次
长任务续租：进程活着+租约过期 → status=running，续租 1800s，spawn 0 次
10 万行：插入 0.7s，取 2 条待跑 0.09ms，任务目录数 0
端到端：add --goal → tick 拉起 → worker 写 exit=0 → progress.md/result.json/DONE
        → 结果优先收尾 → brief 读出 5 字段
plan：一句话自动拆成 3 个任务（generic/research），每个带路径、动作、交付物
```

### 不懂 AI 的人最终入口

```bash
T=<skill 安装目录>/agent-ops/scripts/taskctl.py

# 一句话派一个活
python3 $T add --goal "检查 /data/project 的构建脚本，找出不可用的命令" --repo /data/project

# 一句话自动拆成多个活并全部入队（planner 的提示词内置，用户不写）
python3 $T plan --goal "审查这个代码库：构建、测试覆盖、安全" --repo /data/project --max-tasks 10

# 开跑，然后只看这两条
python3 $T daemon --concurrency 2 --interval 30 &
python3 $T stats
python3 $T brief <ID>
```

### 仍未验证（不能说「健壮」）

1. **单机连续跑 10 万任务的长时间稳定性**（需数天；10 万行查询压测不等于 10 万次真实执行）。
2. **多机共享同一个 SQLite**——SQLite 不适合，要多机得换 Postgres（存储层已隔离可替换）。
3. **`blocked` 任务在有人回答后自动恢复**——目前要 `retry`。
4. **planner 在超长目标（100 万行代码级）上的拆解质量**——只验过 3 个子任务的小目标；拆 1000 个需要分批递归。
5. **`result.json` 契约的长期遵守率**——单次成功不代表稳定；已加 schema 校验 + 失败原因回灌，但没有统计样本。

## 四、编排模式

**并行（独立任务，多模型分摊）**

```bash
python3 $ACT dispatch --name scan-a --backend codebuddy --model $WORKER_MODEL --prompt-file a.md --workdir /path/a
python3 $ACT dispatch --name scan-b --backend codebuddy --model $WORKER_MODEL --prompt-file b.md --workdir /path/b
# 要显式用 等其它模型（偏弱、非默认）才把上面某个 --model 改成 等其它模型
```

同一模型不要超过 2 个进程：总并发 = min(全局上限, 模型数×每模型上限)；默认只用 $WORKER_MODEL。

**串行（有依赖，前一步产出是后一步输入）**

1. `dispatch` 第一步 → `status` 等到 `done`
2. 读 `locate` 给的会话文件或 `out/` 产出
3. 把结果写进第二步的 `prompt.md`，再 `dispatch` 第二步

**流水线（判定 → 复现 → 修复）**

每步一个任务目录，用 `out/stepN.json` 当交接契约；主 agent 只检查 JSON 字段是否齐全，不读全过程。

## 五、提示词模板（决定质量，别省）

```markdown
你是子任务「{name}」，只做这一件事。

## 输入
- 工作目录：{workdir}
- 上游产出：{outdir}/step1.json（没有就跳过）

## 步骤
1. 先读 {outdir}/progress.md，判断上次做到哪一步，从第一个未完成项继续
2. 每完成一步，**立刻**把结论追加进 {outdir}/progress.md（必须写，不能只在回复里说）
3. 产出写到 {outdir}/result.json，字段：status / items / reason
4. 全部完成后创建 {outdir}/DONE 文件

## 判定标准
- 什么算完成、什么要排除、边界情况怎么处理

## 禁止
- 不要修改 {workdir} 之外的文件
- 不要调用超过 预算阈值 的模型
```

**为什么强制写 `progress.md`**：会话上下文撑满会压缩，只有落盘进度不会丢；`resume` 续接时靠它恢复。

## 六、限额与红线

- **模型**：默认 `$WORKER_MODEL`；等其它模型 偏弱、非默认，要用显式配。红线仍是只允许 白名单内且不超预算（`便宜档模型` / `便宜档模型` 等便宜档可用）。`agentctl dispatch` 在起进程前校验，传贵模型直接拒绝。
- **并发**：每模型 1~2 路、多模型设全局上限（当前 2 个模型 → 4 路）。不要因为「反正是免费」就打满。
- **knot 限流**：429 没有恢复时间通知，撞了就降并发/切模型/短冷却；不要原地 45s×3 退避。
- **不做全局配额推演**：别的项目占用算不清，`agentctl` 只统计自己派发的任务。

## 七、排查表

| 现象 | 先看 | 处理 |
|---|---|---|
| `dispatch` 立即失败 | `logs <name>` 里的 stderr | 模型名不在白名单 / prompt 为空 / workdir 不存在 |
| 状态一直 `running` 但没产出 | `locate` 的会话文件 mtime、`out/progress.md` | `-p` 输出多在结束时落盘，日志不动是正常的；看进度文件 |
| `resume` 后秒退 | `run.log` 是否含 `unknown option` / `No conversation` | 2.132.0 不支持 `--resume-create-missing`；工具已自动降级新建 |
| `send` 返回 3 | 任务是否还在跑 | 运行中插话不可靠（消息不会被处理），等结束再 send |
| 想看实时 stdout | `run.log` 是否 0 字节 | 块缓冲所致；改看会话 jsonl，或用 `script -q -c` 拿 PTY |
| 会话文件找不到 | `~/.codebuddy/projects/*/<sid>.jsonl` | `--workdir` 变了会导致 slug 变，用 `locate` 看当前值 |
| `watch` 不拉起 | `restarts` 是否达 `max_restarts`、是否在冷却期 | 调大上限或缩短 `AGENTCTL_COOLDOWN` |
| 沙箱报 `Invalid cross-device link` | 是否用了 `unlink` 删任务文件 | 改成清空写（工具已内置规避） |

## 八、与 `watchdog.sh` 的分工

| | `agentctl.py`（推荐） | `watchdog.sh`（历史） |
|---|---|---|
| 任务定义 | 命令行 dispatch，注册表 JSON | `~/.codebuddy/watchdog/jobs.json` |
| 提示词 | 每条任务一个 `prompt.md` | `prompts[]` 数组，支持 step/cycle/first 轮换 |
| 会话 | 自己指定 session id | 自己指定 session id |
| 续接 | `--resume`，失败降级新建 | `--resume --resume-create-missing`（依赖 2.183.0） |
| 适用 | 临时/多模型/需要精确路径 | 已有长期任务、需要提示词轮换 |

两者都保留：新任务用 `agentctl`，旧 jobs.json 继续用 `watchdog.sh`，互不干扰（状态目录不同）。
