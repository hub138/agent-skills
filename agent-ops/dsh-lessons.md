# 从 DeepSeek Super-agent 学到的多 agent「机器」

> 仓库：`<skill 安装目录>/dsh-superagent-prototype`（`github.com/deepseek-ai/dsh-superagent-prototype`，MIT，2026-10-31）
> 官方定性：**research prototype，不是正式产品**，代码有 bug、风格不一致，参考设计即可，不要直接跑生产。
> 它做的事情：一个常驻 agent 监听 GitHub/飞书，被允许的人派活后开独立会话和目录去干，回原线程答复，网页面板列出需要人处理的事。核心原则是「**尽量少占人的注意力，尽量多给价值**」。

## 一、它的五大模块（正好是我们缺的「机器」）

| 模块 | 做法 | 解决什么 |
|---|---|---|
| 双层架构 | Router（主会话）只评估与分派；Worker（每个 Ticket 一个会话 + 一个目录）执行 | 主 agent 不被实现细节拖住，worker 上下文独立、可并行 |
| 事件驱动 | Trigger 自动作为消息到达，**禁止 sleep/poll 等结果** | 不会把 agent 卡在「等一个永远不会来的轮询」 |
| 异步多信道 | 每个 Thread 有多个 Channel（GitHub 评论 / 飞书话题），回复回原线程 | 谁在哪里问，就在哪里答，不串台 |
| 存算分离 | 状态全在 SQLite；会话上下文只是缓存，可压缩/重建 | 上下文撑满不影响正确性，重启能接着干 |
| 外部 Watchdog | 宿主进程检查会话存活并拉起，不在 agent 内部自保 | agent 挂了不会带崩监控 |

## 二、领域模型（比我们的 task/session 细一档）

```
Source → Trigger → Thread → Eval → Ticket → Assignment → Executor
                                              ↓
                                           Channel（回写）
```

| 概念 | 定义 | 关键规则（值得抄） |
|---|---|---|
| Source | 事件流（GitHub/飞书），有读位置 | **保存 read position，重启不重放** |
| Trigger | 一条不可变事件 | **幂等：同一 Trigger 接受两次只创建一个 Ticket** |
| Thread | 同一话题的事件序列 | **同一时刻最多一个 Eval**；可挂多个 Ticket |
| Eval | 判断这条事件要不要开活 | 只做评估，**不写实现计划**；超时则排队或结束为 `unavailable` |
| Ticket | 一件工作 | **自己持有状态**，不跟随会话；可 handoff / resume / 多 Executor 接手 |
| Assignment | 把 Ticket 交给某个 Executor 跑一次 | retry = 结束当前 Assignment、在同一会话/目录/分支开新的 |
| Channel | Thread 的写回侧 | 一个 Ticket 可持多个 Channel；**同 Ticket 同会话保序** |

## 三、Ticket 状态机（从「存了什么」推导，不靠内存）

| 阶段 | 条件 |
|---|---|
| `person / delivery` | 往会话投递 Input 失败，重试中（2s 起翻倍到 1min） |
| `person / answer` | 有需要人回答的 Attention |
| `person / review` | 最新 Report 是 `ready` |
| `person / blocked` / `failed` | 最新 Report 是 blocked/failed，且此后没人发消息 |
| `working / queued` | 没有 Assignment 或还在排队 |
| `idle` | 最新 Report 是 waiting，或 Assignment 已结束 |
| `working` | 其余 |

**要点**：状态是**从持久化的 Reports + Inputs 推导**出来的，所以重启不丢；人发一条消息就能把 blocked/failed 重新唤醒。

## 四、五个最值得抄的机制

### 1. Stored work（副作用先入库，提交后才执行）

> 决策后要做的动作（转发、投递、启动 Assignment）**先存储，再执行**。

- 失败重试：投递 2s 起翻倍到 1min；Channel 发送 5s 起翻倍到 300s。
- **连续 3 次失败**才在总览里报「系统问题」，不因一次抖动就报警。
- 同 `kind + key` 只保留一行：重复入队会替换 payload，不会堆积。

### 2. 幂等

- Trigger 接受两次 → 只创建一个 Ticket。
- 我们现在的 `dispatch` 没有幂等：同一个 name 连点两次会起两个进程，抢同一份文件。

### 3. 消息已读 / 未读

- 一条消息在 **claim 之后、模型调用之前**记为已读。
- 被重启切断的那一轮：后面有 Report 或 turn 结束，就算已读；被 cancel/error 切断且还没进历史的，算未读，会重新投递。
- 目的：既不重复喂同一条消息，也不因为崩溃丢消息。

### 4. 保序

- 同一 Ticket 对同一会话的消息，按入队顺序发；前一条没发出（且失败未满 3 次）时后一条等待。
- 不同 Ticket、无 Ticket 的消息互不等待。
- 我们的 `send` 现在是「谁先跑完算谁」，没有保序。

### 5. Pause processing

- 暂停会停掉调度、新 Eval、Input 投递、回复，但 **Source 继续记录 Trigger**，正在跑的 turn 不打断。
- 恢复后第一轮继续处理；暂停期间到期的 Eval，截止时间顺延。

## 五、沟通纪律（prompt 层，直接可抄）

- Router 只做评估和路由，**永远不写实现计划**；实现由 worker 自己做。
- Worker 的 Report、follow-up、新候选、后台任务结束，**都会自动作为消息到达，禁止 sleep / 轮询 / 等 job 来获取**；没活了就结束 turn。
- **日常进度保持内部**（Keep progress internal）：只有需要人决策或人能直接用结果时才发消息。
- Handoff 是**结构化 attention request**，不是例行进度；例行进度、模型重试、额度错误都**不构成打扰人的理由**。
- 空 final 保留上一次成功 report，不要为了「有 summary」重复一遍。

## 六、映射到我们现在的 `agentctl`

| 能力 | 我们现状 | 差距 | 这轮是否补 |
|---|---|---|---|
| 会话定位 | ✅ `--session-id` + `locate` 给绝对路径 | — | 已完成 |
| 多后端派发 | ✅ codebuddy / knot | — | 已完成 |
| 状态推导 | ⚠️ 只看 pid + exit code | 没有 queued/blocked/awaiting-person 的区分 | **补** |
| 幂等 | ❌ 同 name 可重复起 | 会起两个进程抢同一目录 | **补** |
| Stored work + 重试 | ❌ spawn 失败即丢 | 网络抖动就永久失败 | **补** |
| 消息保序 / 已读未读 | ❌ `send` 无序 | 连发两条会乱序 | **补**（简化版） |
| 读位置 | ❌ 无 Source 概念 | 不适用（我们不是事件流） | 不补 |
| Eval / Mandate | ❌ 无授权模型 | 靠 prompt 约束「只做这件事」 | 不补（过度设计） |
| 双层 Router/Worker | ✅ 主 agent + `agentctl dispatch` | — | 已完成 |

**不抄的部分**：Source/Trigger/Thread/Eval/Mandate 的完整实现。我们是「人直接派任务」，没有多源事件流和团队级授权表，照搬会变成过度设计。只抄**存储、幂等、保序、状态推导**这四件与「一个 agent 管多个」直接相关的事。

## 七、一句话总结

Super-agent 的价值不在「多开几个 agent」，而在**把 agent 的会话当成可丢弃的缓存，把进度、待办、投递状态全部落到持久层**——这样上下文压缩、进程崩溃、重启都不会丢活。我们之前把状态放在内存和 pid 上，就是这个「机器」缺的那一块。
