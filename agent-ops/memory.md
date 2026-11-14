# 上下文工程与记忆：一个 agent 管多个 agent 怎么不炸上下文

> 场景：你给主 agent（IDE 或 `codebuddy -p`）一堆子任务，让它派给多个 CLI 子 agent，每个子任务有自己的进度和提示词。
> 问题：**主 agent 的上下文是唯一稀缺资源**。子 agent 跑 30 分钟能产出几千行日志，3 个子任务就能把主上下文撑满、触发压缩、丢掉前面的决策依据。
> 结论：**能落到磁盘的，绝不放在上下文里；能压成一行状态的，绝不回灌全文。**

## 一、三层记忆，各管一段

| 层 | 放什么 | 生命周期 | 谁写 | 谁读 |
|---|---|---|---|---|
| **L1 会话上下文** | 任务清单、每个任务一行状态、待你拍板的问题 | 易失，会压缩 | 主 agent | 主 agent |
| **L2 状态层** | 状态机、待执行动作、重试计数、消息队列、session id | 跨重启 | `agentctl`（registry/effects） | 主 agent / watch |
| **L3 工作区** | `prompt.md`、`progress.md`、`result.json`、`run.log`、产出文件 | 永久 | 子 agent | 子 agent 自己；主 agent 按需定点读 |

判断标准：**这条信息下次还要用吗？要，就落 L2 或 L3；只是这一轮推理用，才留 L1。**

## 二、主 agent 的上下文预算

每轮只允许读这些（加起来一屏以内）：

```bash
python3 scripts/agentctl.py status        # 每任务一行：状态/运行时长/事件数/会话路径
python3 scripts/agentctl.py brief <name>  # 只读 result.json 的摘要字段（失败时回退最后 20 行）
```

**不要**做这些：

- 不要 `cat run.log`——子 agent 的输出是给机器看的，不是给主 agent 读的；要看也只 `tail -20`。
- 不要读子任务的会话 jsonl 全文——那是几千行事件流，只取最后一条 `assistant` 的文本。
- 不要把子 agent 的原始输出粘回主对话——要粘就粘它写进 `result.json` 的 3 个字段。

对照 dsh 的硬规则：**orchestrator 不得检查代码、详细日志、链接文档，也不得替 worker 解决阻塞**。它只做评估、路由、转发报告。这条比任何压缩技巧都有效。

## 三、子 agent 的输出契约（决定主上下文大小）

每个任务的 `prompt.md` 里必须写死这两个文件：

**`<outdir>/progress.md`**（子 agent 每步追加，供它自己恢复和主 agent 抽查）

```markdown
- [步骤1] 做了 X，结论 Y，证据 Z
- [步骤2] 尝试 A 失败，原因 B，改走 C
```

**`<outdir>/result.json`**（结束时写一次，主 agent 只读这个）

```json
{
  "status": "done | blocked | failed",
  "summary": "一句话说清做完什么，不超过 200 字",
  "evidence": ["关键文件/命令/行号，最多 5 条"],
  "question": "需要人拍板的一个具体问题；没有就 null",
  "next": "如果 blocked，下一步建议；否则 null"
}
```

规则：

- `summary` 超 200 字就是在把上下文往主 agent 里搬，砍掉。
- `question` **只能有一个**，且必须是「人能直接回答」的；模糊的「要不要继续」不算。
- `evidence` 是路径/行号，不是代码片段——主 agent 需要时自己去读那几行。

## 四、压缩与 rollover

会话撑满会触发压缩，压缩后早年细节变模糊——这是正常现象，**不要试图靠「记住」对抗它**，靠落盘。

| 触发 | 做法 |
|---|---|
| 主 agent 一轮里任务数 > 5 | 只保留「状态 + 待决策」，其余任务细节不读 |
| 子 agent 上下文将满 | 新会话接续，第一句要求它读 `progress.md` 恢复；`agentctl resume` 会自动带原 session，需要换新会话就改 `session_id` 再 dispatch |
| 子 agent 跑超过 1 小时 | 在 `progress.md` 里已经沉淀了步骤，直接用 `send` 让它「读 progress.md 继续」比塞长指令更稳 |
| 主 agent 自己上下文快满 | 把当前任务清单写进 `~/.codebuddy/agentctl/plan.md`，新开一轮先读它 |

## 五、提示词工程（每个子任务都要）

固定五段，缺一不可：

1. **角色与范围**：只做这一件事，不扩范围。
2. **输入**：工作目录、上游产出路径（文件，不是对话摘要）。
3. **步骤与进度**：先读 `progress.md`，从第一个未完成项继续，每步追加。
4. **输出契约**：`result.json` 的字段和长度上限。
5. **禁止**：不改工作目录外的文件；不用超 0.15 credits 的模型；不调用需要人确认的危险命令。

**版本化**：`prompt.md` 落盘在任务目录，`dispatch` 时无法覆盖正在跑的任务（幂等拒绝）。改了提示词要重跑，用新 name，旧任务的 `prompt.md` 就是它的审计记录。

## 六、交接协议（子 agent → 主 agent）

| 子 agent 状态 | 它该做什么 | 主 agent 该做什么 |
|---|---|---|
| `done` | 写 `result.json`，`status=done` | 读 summary + evidence，验收或收工 |
| `blocked` | `status=blocked`，`question` 写**一个**具体问题 | 只把这个问题转给你（不加工、不加建议） |
| `failed` | `status=failed`，`next` 写建议 | 看 `next`，决定重跑、换模型还是放弃 |
| 还在跑 | 什么都不写 | `status` 看一行，**不要打断，不要轮询等** |

对照 dsh：
- 需要人决策时用 `human_action` 提**一个问题**，完整证据放 summary，由主 Session 转发短问题；
- 「不要把问题只写在 summary 里等着」；
- 日常进度保持内部，模型重试/额度错误不构成打扰人的理由。

## 七、你现在做法的三个风险

你说「每个的进度和提示词都自己盯着和给」，这在 2~3 个任务时没问题，5 个以上会遇到：

1. **主上下文被进度淹没**：你读的每一段进度都进了主上下文，读 3 个任务的详细日志 ≈ 一次压缩。
2. **提示词漂移**：手工给每个子任务写提示词，容易漏掉「写 progress.md」「输出契约」，导致子 agent 不复述进度、resume 时无据可依。
3. **决策串行**：你逐个读、逐个回，等于把人变成了消息总线。更好的做法是让子 agent 把问题写进 `result.json.question`，你只看「待决策清单」。

## 八、一页检查清单

派任务前：

- [ ] `prompt.md` 五段齐全，`result.json` schema 写死
- [ ] 输出目录明确，`progress.md` 路径写进提示词
- [ ] 模型在红线内（x0.00 或 ≤0.15）
- [ ] 同名任务没有在跑（`dispatch` 会幂等拒绝）

收任务时：

- [ ] 先 `status`，只对 `done/blocked/failed` 的任务 `brief`
- [ ] 只读 `summary` / `evidence` / `question`，不读 `run.log`
- [ ] `blocked` 的问题原样转给人，不自己加工
- [ ] 验收通过再合并产出，不把中间过程写回主对话

主 agent 自查：

- [ ] 本轮有没有读过任何 `run.log` 或会话 jsonl 全文？有就说明越界了
- [ ] 有没有替子 agent 改代码/调试？有就说明上下文要爆了
- [ ] 任务清单能不能一屏放下？放不下就落 `plan.md` 再开新轮

## 九、记忆实测与假死感知（2026-11-12 补）

### 断点恢复真实实验（不是文档推演）

预置 `progress.md` 三行（步骤1/2 完成、步骤3 未完成），用新会话起一个只说「读 progress.md 从第一个未完成继续」的子任务：

```
run.log        : 第3步
progress.md 新增: - 接着做：步骤3
会话 jsonl     : 11 个事件（含 function_call_result，说明它真的去读了文件）
```

**结论**：三层记忆里的 L3（进度落盘）确实能跨会话恢复，不是只写在文档里。但验证边界要说清：只测了一次短任务；上下文真被压缩后、或跑 1 小时以上的长任务，恢复效果仍未实测。

### watchdog 到底怎么判活（回答「是不是感知会话文件多久没增长」）

**之前不是，现在补上了。** 三套机制的分工：

| 机制 | 默认间隔 | 判活依据 | 假死（进程活着但不干活） |
|---|---|---|---|
| `watchdog.sh` | cron 每 1 分钟叫醒、`check_interval_minutes=5` 每任务实际检查 | `kill -0 pid`；可选 `run.log` mtime | **默认关闭**（`stale_minutes=0`）——`-p` 输出是块缓冲，结束才刷，开了必误杀正在干活的任务 |
| `taskctl daemon` | `--interval 30s` 一次 tick | 会话 jsonl / `progress.md` / `result.json` / `run.log` 的 mtime + pid | **已补**：`TASKCTL_STALE=900s`（可设 0 关闭），全部文件超时无增长 → `killpg` 精确杀 → 重排，并把「先读 progress.md 从断点继续」写进下次 prompt |
| `agentctl watch` | 挂 cron，按需 | pid + exit + 会话事件数 | 只显示事件数，不自动判定（交互式工具的定位） |

**为什么用 mtime 而不是「AI 去查看」**：AI 查看要额外一次模型调用、更慢更贵，且 AI 自己也可能卡住；mtime 是内核给的客观事实。会话 jsonl 是**边跑边写**的（实测 6 秒出现、逐条追加），比 stdout 重定向可靠得多。

**为什么默认 900s 而不是 1 分钟**：模型在 reasoning 阶段不产生新事件（实测「思考 20 秒」期间 jsonl 完全不动），阈值太小会把正在干活的长任务误杀。这与 `watchdog.sh` 的 `stale_minutes=0` 是同一个道理的两种取舍——一个保守关闭、一个给足余量。

### 实测

- 阈值单测：60s 无增长 → 不判死；1000s → 判死；写入新进度 → 立刻复活；`STALE_SECONDS=0` → 关闭。
- 端到端：造一个 `sleep 300` 的假活进程 + 300s 未更新的 progress，跑 tick → `stale_requeue`、状态 `queued`、错误原因写进 `error`、假进程被精确杀掉。

## 十、纠正：监督必须是「模型监督模型」，脚本不做判断（2026-11-12）

用户指出我一度把原 `watchdog（旧版）` 的核心降级了。原设计是：

```
cron 定时 → --resume <sid> + 一条固定提示词
          → 由模型读进度、自己判断从哪继续、每步写回
```

即**判断权在模型**，脚本只管「什么时候拉起」。我上一轮用 `mtime → killpg` 的纯脚本假死判定替代它，丢掉了最关键的能力：脚本看不出「进度文件在涨但全是重复报错」「该换方向」「该追加一条指令」，也不会应对新情况。**这是方向性错误，已改回。**

### 现在的分工（无人力）

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| 脚本 `taskctl` | 收集状态、发现「疑似无增长」只**标记** `need_supervision`、给进程续租 | 不判断死活、**不杀进程** |
| 监督者模型 `scripts/supervisor.py` | **每任务独立调用**（2026-11-13 拆分）：单任务快照 + 一行全局摘要 → 单 JSON 决策；并发 2 路（SUPERVISOR_CONCURRENCY），某任务失败只影响它自己 | 不执行、不改文件 |
| 脚本 `apply()` | 归一化模型输出、防呆、执行 `continue/nudge/restart/escalate/finish`、把指令写进 `guidance.md` | 不替模型做判断 |
| 人 | 只读 `stats` / `brief`；只有 `escalate` 才需要介入 | 不需要逐个盯 |

触发：**定时**（默认 1800s，对齐原 watchdog）+ **事件**（超 120s 无增长、或任务有 error）。脚本只决定「该不该问」，问完由模型定动作。

决策五种：`continue`（正常）、`nudge`（写指令、不动进程）、`restart`（杀掉重排 + 指令注入）、`escalate`（标 awaiting-person）、`finish`（按产出收尾）。防呆：`restart` 必须有 guidance 且未超重试；模型输出无法解析/超时 → **本轮不动**，绝不误杀正在 reasoning 的长任务。

### 实测（当时用 small-model 验证，非 mock；现监督者默认已改 free-model，结论对 free-model 同样适用）

```
快照: 1 个任务，progress 尾显示「步骤2 同一条报错重复 3 次」，301s 无增长、进程存活
模型耗时 45.8s，决策:
  action=nudge
  reason=「进程存活但 progress 301s 无增长，步骤2 同一报错重复3次，疑陷重试死循环」
  guidance=「停止重试同一动作，先诊断步骤2比对语义的报错根因，确认原因后再继续」
执行: supervisor_nudge，guidance.md 已写
下一轮 prompt 含「监督者给你的最新指令」= True
```

模型自己识别出了脚本绝对看不出的「重复报错死循环」，并给出换方向的指令——这就是必须用模型监督的理由。

**过程中修的两个真 bug**：① `PROMPT.format()` 把 JSON 示例里的 `{"task":...}` 当模板变量（KeyError）；② 模型把 `task` 写成 `s3 #1 [generic]`（照抄标题）导致决策被丢弃，已加归一化（精确名 / 首 token / `#id` 兜底）。

### 启动

```bash
S=<skill 安装目录>/agent-ops/scripts/supervisor.py
python3 $S snapshot            # 只看快照，不调模型
python3 $S once                # 跑一次（cron 用）
python3 $S daemon --interval 300   # 常驻，每 5 分钟一轮
```

## 十一、几十天的任务：全局更新，不截断（2026-11-13）

实测量化：30 天 × 20 步/天 × 120 字/步 → `progress.md` 约 **109KB ≈ 36K tokens**，随天数线性增长。

**主 agent 侧安全**：`status` / `brief` 都不读 `progress.md`，只读 `result.json` 的 5 个字段。

**子 agent 侧的正确做法（用户口径：不要当 AI 是傻子）**：
- 每轮 resume **读 `progress.md` 全文**——AI 有能力处理几十 K tokens 的历史。
- 执行中逐步追加，一轮结束前**读完全文后全局重写**成紧凑结构：保留所有关键决策、未完成项、下一步，不丢事实；
- **不截断、不只读尾部 200 行、不靠 50 行摘要**——那些是把 AI 当傻子的做法，已撤销。

代价：单轮 token 成本随历史增长（这是真实开销，不假装没有）；收益：不丢任何决策依据。
若真跑几十天导致模型窗口装不下，那是**该拆任务**的信号，不是截断记忆的理由。

### 已实现并实测：compaction 留痕 + 阈值参数化 + 30 天仿真（2026-11-13）

三项"未实现"已全部落地：

**① 压缩阈值参数化**（借鉴 prime-agent 的参数校验）：
- `TASKCTL_COMPACT_DROP_PCT`（默认 30.0）：progress 行数比上次记录下降 ≥ 该百分比 → 写 compaction 事件
- `TASKCTL_COMPACT_MAX_LINES`（默认 2000）：超过则 supervisor 快照标 `needs_compaction=true`
- 校验：非数值/超界（如 150）/负数 → 回退默认值并继续（`_valid_percent`，单测通过：默认 30、非法回退、超界回退、合法 45 生效）

**② compaction 事件留痕**（借鉴 deer-flow CompactionEvent）：
- 每次任务收尾自动对 `progress.md` 留痕（`archive_progress`）：
  - 内容有变 → 归档 `progress-archive/snap-N-<ts>.md`（无损原文留盘）
  - 行数下降 ≥ 阈值 → 归档 `compact-N-<ts>.md` + 事件 `compaction`（before/after 行数、字节、双 hash、归档路径）
- 模板要求模型重写前自行归档原文到 `progress-archive/prev.md`（双保险）
- "哪条旧记录压成哪句结论" = 对比 `prev.md`/`snap-*` 与新版，逐字可回溯

**③ 30 天仿真实测**（真实 free-model，非 mock）：

| 指标 | 重写前 | 重写后 |
|---|---|---|
| progress.md | 600 行 / 53,936 B（≈18K tokens） | **49 行 / 3,578 B（≈1.2K tokens）** |
| 压缩比 | — | **15.1x（字节）/ 12.2x（行）** |
| 关键决策（5 条） | 散在 600 行里 | **逐条保留**（含方案A→B依据 bug#39603649） |
| 未完成项（3 步） | 散在 600 行里 | **全部保留**（去重为 1 项待办） |
| 无损原文 | — | `prev.md` 53,936 B 与原文字节一致 |

重写质量（模型超出预期）：还做了 **592 条比对按源码文件的分布统计**（srv0srv 166 / row0merge 146 / ha_innodb 143 / dict0dict 137），并在文件头声明"原文完整复制至 prev.md，未删除、未截断"。

链路验证：`taskctl tick` 收尾自动写 compaction 事件（`before_lines=600, after_lines=49, drop_pct=91.8`），归档四件套齐全（compact-1 / prev.md / snap-1 / snap-2）。

### 同类开源 harness 怎么做的（2026-11-13 clone 实测）

已 clone 到 `<skill 安装目录>/references-upstream/`：`deer-flow`(ByteDance)、`OpenHarness`(HKUDS)、`prime-agent`(PrimeIntellect)、`LongHorizon-Harness`(AMAP-ML)、`munder-difflin`。`deepseek-ai/harness` 需私有认证，clone 失败（只有搜索结果里的二手描述，不算证据）。

| 项目 | 记忆做法 | 对我们的启示 |
|---|---|---|
| **munder-difflin**（markdown-first memory） | "lossless original on disk, compress a **copy** for recall — never let the summary become the only record"；索引坏了退回读 markdown | 已做到：`prev.md`/`snap-*` 是无损原文，重写版是副本；不是只留摘要 |
| **deer-flow**（ByteDance） | compaction **destructive by design**，发 `CompactionEvent`（content hashes / task_id）供审计 | 已做到：compaction 事件 + 双 hash + 归档 |
| **prime-agent** | 压缩阈值参数化 + 校验 | 已做到：`_valid_percent` + 两个环境变量 |
| **OpenHarness** | session storage 与运行时解耦 | L2/L3 分层同思路 |
| **LongHorizon-Harness** | 每轮先独立验证再推进 | supervisor 的模型判断部分覆盖，非强制门禁 |

**残留边界**：30 天仿真是**一次性重写**实测；"每轮都重写、连跑 30 天"的持续行为未实测。重写依赖模型执行，若模型偷懒只追加不重写，supervisor 的 `needs_compaction` 会提醒但仍需模型配合。

### 监督者拆分：混批 → 每任务独立调用（2026-11-13，用户判断驱动）

用户指出「不同任务混一起乱七八糟」——三个具体理由全部成立：
1. **上下文污染**：A 任务的报错特征干扰 B 的判断；
2. **注意力稀释**：长快照中段的任务质量差；
3. **爆炸半径**：旧版一次调用解析失败/超时，10 个任务全部失去监督。

实测（3 任务：正常推进 / 假死重复报错 / 2600 行需压缩）：
- a1 → continue（正确不动作）；a2 → 超时跳过（只影响它自己）；a3 → nudge「先读全文全局重写，重写前归档原文」一字不差。
- 旧版同样场景：a2 超时 = 3 任务全跳过。爆炸半径 3 → 1。

全局摘要仍保留一行/任务（`overview`）——监督模型用它判断「是不是系统性问题」
（如 3 个任务同时 idle 可能是限流），但决策只针对目标任务。
`PROMPT` 多任务数组版保留（supervise_agents 后端复用），taskctl 后端走 `PROMPT_SINGLE`。

## 十二、监督者 → 管理者：任务主人的化身（2026-11-13）

用户定义的角色升级：管理者不是"盯卡的脚本"，是**主人在任务现场的代理人**——
主人发起任务时并不确定多复杂、要多久；管理者让这件事被持续做好，
甚至可以微调目标本身（refine）。自由度高，但每一步留痕。

### 四个新能力（全部端到端实测）

| 能力 | 实现 | 实测 |
|---|---|---|
| **目标演化 refine** | 管理者输出 new_goal → 旧目标归档 `goal-archive/goal-<ts>.md` → 新目标写 `goal.md` → worker 下一轮 prompt 自动注入"以此为准" | "对比排序差异" → refine → "深入对比 sort 模块 ORDER BY"，归档/注入全对 |
| **决策全留痕** | 每条决策（**含 continue 与理由**）追加 `decisions.jsonl` | 实测 continue 的理由："idle=209s 符合刚启动形态…按拿不准就 continue 处理" |
| **读全部进度** | ≤400 行全文直读；更长头 30+尾 200（全局重写机制管膨胀） | 快照含 goal 与全文（测试断言） |
| **任务全史 history** | `taskctl history <task>`：原始目标→当前目标→事件时间线→管理者决策 | 一屏输出验证 |

### 参数与坑

- 管理者读全文后单次调用可达 **~420s**（通道慢时段实测），`SUPERVISOR_TIMEOUT` 默认已从 180 → 420。
- **prompt.md 每轮重渲染**（修复旧版只渲染一次 → 重试时 error/guidance 回灌静默失效的真 bug）。
  prompt.md 是"当前轮次的投影视图"；源状态在 goal.md / progress.md / guidance.md。
- 会话 id 前缀 `mgr-<任务名>-<ts>`，codebuddy 会话文件名可直接反查是哪次监督。
- 事件名保留 `supervisor_nudge`（历史连续性），人设与文档已是管理者。
- `supervise_agents` / `supervise_jobs` 两个后端暂未管理者化（无 refine/decisions 留痕）——标注待做。
- 测试：`tests/test_manager.py` 5 项（goal 生命周期/决策留痕/重渲染注入/history/解析防呆），全 mock 不调真实模型。
