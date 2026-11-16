# SuperAgent：上下文包、结果信封、单写者 + 租约

- 来源：2026-11-16 11:00 #2 / https://cloud.tencent.com/developer/article/2784348
- 类型：article（证据级别 C：有机制描述与字段名，无仓库代码）
- 相关性：4
- 结论：**skip（核心机制已具备，剩余部分收益低于成本）**

## 1. 作者的核心主张

多 agent 的难点不是发任务，而是三方对齐：Router 看见全局、Worker 看见上下文、
结果有唯一表示。做法是 `GlobalContextPacket`（一次装配、按角色投影）、
`SaResultEnvelope`（单一结果信封）、大对象坐标引用、单写者 + 租约。

## 2. 机制提取

### 2.1 单一结果信封

- 原文：「同一次派发在助手正文、A2A 协作气泡、会话台账、运行台账里各有一套形状」。
- 机制形态：一次执行只产出一个结构化结果，所有消费方读同一份；正文只做展示。
- 本 skill 现状：**已具备且更严格**——`scripts/taskctl.py:147 validate_result()`
  强制校验 `status`（done/blocked/failed）、`summary`（≤400 字）、`evidence`（≤10 条）、
  `question`；不合格直接让任务失败并写回原因（`taskctl.py:785`）。这比文章描述的信封更硬。

### 2.2 单写者 + 租约

- 机制形态：同一资源同时只有一个写者；租约到期才允许接管。
- 本 skill 现状：**已具备**——`tasks.lease_until` + `worker_id`（`taskctl.py:89`），
  抢占用 `BEGIN IMMEDIATE`（`taskctl.py:681`），过期回收见 `taskctl.py:656-674`。

### 2.3 全局上下文包按角色投影

- 机制形态：全局事实装配一次，按角色裁剪后注入；避免 Worker 各说各话。
- 本 skill 现状：**部分具备**——`goal.md`（目标）、`progress.md`（进度）、
  `guidance.md`（管理者指令）在每轮渲染成 `prompt.md`（`taskctl.py:476` 注释：
  「prompt.md 是当前轮次的投影视图」）。没有显式的「全局事实包」，但投影形态已在。

## 3. 与 agent-ops 的对照

| 维度 | SuperAgent | 本 skill | 结论 |
|---|---|---|---|
| 结果唯一表示 | SaResultEnvelope | `validate_result` 四字段硬校验 | 已具备 |
| 大对象引用 | 坐标传引用 | 细节留盘，主 agent 只读摘要（memory.md 三层记忆） | 已具备 |
| 单写者 + 租约 | 是 | lease + BEGIN IMMEDIATE | 已具备 |
| 上下文包 | GlobalContextPacket | goal/progress/guidance 投影 | 形态已有，缺显式包 |

## 4. 为什么不抄「上下文包」

显式引入 `GlobalContextPacket` 需要新增一层组装器，把项目约束、上游产物、接口契约
汇总后按角色裁剪。当前 `prompt.md` 已经是投影，再加一层会让「谁负责哪段上下文」
变成两处真相，违反本 skill 的单一权威源原则。收益（减少 Worker 跑偏）没有实测数据支撑，
成本（多一层抽象 + 每轮组装）确定。判 `skip`，若未来出现「多 Worker 反复跑偏」的真实案例再评估。

## 5. 结论

`skip`。这篇文章对本 skill 的最大价值不是新机制，而是**验证了现有设计方向**：
结果信封 + 租约 + 投影视图是对的。把它列为 skip 并写清理由，避免下次重复评估。

## 6. 第二轮深读补充（结论修正：skip → adapt）

原文 5.2 给出信封完整字段：

- `state`: SUCCEEDED / FAILED / TIMEOUT / UNDELIVERABLE / WAITING_HUMAN
- `error`: 三元组 `userCause / userAction / system`
- `ArtifactRef`: 只放坐标（id/name/url/path/type/actions），不放内容
- `clarify`（一次只问一个）、`steer`、`asOf`

对照 `taskctl.validate_result()`（`scripts/taskctl.py:147`）：

| 维度 | SuperAgent | 本 skill |
|---|---|---|
| 结果唯一表示 | SaResultEnvelope | result.json + 硬校验 |
| 失败分类 | 超时/送不到/等人工/失败 | 只有 done/blocked/failed |
| 错误可读性 | userCause/userAction/system | 无结构化错误 |
| 结果新鲜度 | `asOf` | 无 |
| 大对象 | ArtifactRef 坐标 | 细节留盘，摘要进 result |

第一轮判「已具备且更严格」只看了「有没有信封」，没看「信封里的失败语义」。
失败语义直接影响 manager 决策：超时应重试、送不到应换执行体、等人工应挂起而不是重跑。

因此修正为 **adapt**：给 `result.json` 增加可选 `error{code,userCause,userAction,system}`
与 `state` 扩展（timeout/undeliverable/waiting_human），校验器兼容旧格式（缺字段按 failed 处理）。

本期不落地：`taskctl` 是核心调度，改 result 契约需要单独的失败路径测试与 manager 兼容；
方案已给，下一期执行。
