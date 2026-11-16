# OpenClaw Enterprise：控制平面组件划分与「变更+审计同事务」

- 来源：2026-11-16 15:00 #4 / https://github.com/openclaw/openclaw-enterprise
- 分析提交：`<cache>/openclaw-enterprise`（depth 1，2026-11-16）
- 类型：repo
- 相关性：4
- 结论：**adopt（本期落地：雷达台账事务化）**

## 1. 核心循环

OCC（控制平面）持有期望状态、授权与资源生命周期；Driver 把状态变成基础设施操作。
所有资源变更、排队工作与审计记录**一起提交**；Agent 每次部署记录一个不可变 revision。

## 2. 机制拆解

### 2.1 组件边界（`docs/design.md:139-143`）

| 组件 | 职责 |
|---|---|
| `apps/controller` | API、控制台、准入、组合、worker 入口 |
| `packages/contracts` | 资源模型、Driver 接口、API schema |
| `packages/occ` | 资源所有权、生命周期、持久化、工作队列 |
| `packages/iam` | 身份查找与授权 |
| `packages/audit` | 审计事件与敏感值脱敏 |

形态：**契约（contracts）与实现（controller/driver）分离**；授权与审计是独立包，
不是散落在业务代码里的调用。

### 2.2 变更 + 队列 + 审计同事务

- 证据：`docs/design.md:125`：「Resource mutations, queued work, and audit records commit together.」
- 证据：`:203-204`：敏感值不出现在资源响应、Agent revision、审计记录里；
  授权或审计失败会**阻止**变更。
- 形态：审计不是「事后补一条日志」，而是提交事务的一部分；写不进去就不许改。

### 2.3 不可变 revision

- 证据：`:115` 部署时记录配置与执行设置到 Agent revision，后续编辑不改旧 revision。
- 形态：历史可回放，当前状态只有一个指针。

## 3. 与 agent-ops 的对照

| 维度 | OpenClaw | 本 skill | 差距 |
|---|---|---|---|
| 组件边界 | contracts/occ/iam/audit 分包 | 脚本按职能分文件 | 形态可接受（单机无需分包） |
| 变更 + 审计同事务 | 是 | `taskctl` 的 `event()` 与 UPDATE 同连接但未显式事务 | 部分 |
| 雷达台账 | — | `radar_store` 的 analysis/status/audit 分三次 commit | **真实缺口** |
| 不可变 revision | Agent revision | `task_events` 只追加，任务行可变 | 已具备事件史 |

`radar_store.record_analysis` 当前顺序：INSERT analysis → commit → UPDATE candidate → commit
→ INSERT event → commit。任一步崩溃会留下「分析已入账但候选仍是 new」或「状态变了但没事件」，
台账与事实不一致。

## 4. 最小切片

把 `record_analysis` / `record_change` / `record_workspace` 包进单个 `BEGIN IMMEDIATE` 事务：
状态更新、分析/变更记录、事件写入一次提交；`audit.jsonl` 的文件追加放在 commit 之后
（best effort，失败不影响一致性）。约 40 行，纯 `radar_store` 内部改动，不改表结构。

验证：注入一个在 `set_status` 后抛错的场景，断言 analysis 与 candidate 状态都回滚，
且事件不存在。

## 5. 判定与理由

`adopt`。它解决的是「可追溯」的本体问题：**如果审计能与变更分离，台账就不可信**。
成本低、可测试、不影响 taskctl 核心。

## 6. 没抄什么及原因

- 多租户/IAM/Driver 体系：单机不需要。
- 不可变 Agent revision：`task_events` 已提供追加式历史，再造一层 revision 表是重复。
- 敏感值脱敏包：本 skill 的台账不存凭证；`desensitize.py` 负责公开版脱敏，职责已分开。

## 7. 第二轮深读补充（更细的提交语义）

- **claim 与审计同一条 SQL**：`ClaimRequest.recordAudit` 的注释是
  「Require an audit append in the same database statement as the claim」
  （`packages/occ/src/state/postgres-work-queue.ts:62`）。
- **终态与证据同一条 SQL**：`FAIL_EXHAUSTED_NAMESPACES_SQL` 与 `insertEvidenceCteSql`
  在同一个 CTE 里更新状态并写 evidence（`postgres-work-queue.ts:644` 附近）。
- **恢复有分类统计**：`RecoverySummary` 区分 recovered / requeued / failedPermanent /
  exhaustedQueued / failed，失败永久与可重试不同桶。
- **幂等与身份校验**：`idempotency_key` + claim token（UUID v4），非法直接
  `ScopeViolationError`。
- **审计可开关**（`controlPlaneAuditEnabled`）：说明审计有成本，不是无条件全量。

本 skill 已落地「变更+状态+审计同事务」，并在此基础上补了
`take_next` 领取时写 `claim` 事件——此前领取只改状态、没有任何事件，
事后无法回答「这条是谁在什么时候领走的」。这正是 claim+audit 同语句要解决的问题。

未抄：多租户/IAM/Driver/revision 表（理由见第 6 节）。
