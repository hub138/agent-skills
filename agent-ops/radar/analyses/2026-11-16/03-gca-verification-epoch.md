# GCA：单一写入者、工作区租约、Verification Epoch

- 来源：2026-11-16 11:00 #3 / https://cloud.tencent.com/developer/article/2780499
- 类型：article（论文转述，证据级别 B：有机制与实验描述，无公开代码）
- 相关性：4
- 结论：**adapt（本期不落地，给出方案）**

## 1. 核心机制

- **制品所有权（单一写入者）**：每类制品只有一个负责 Agent，其他 Agent 只能报告问题，
  不能改不属于自己的文件；由统一 MCP 层校验路径与身份。
- **工作区租约**：不同流水线访问同一目录前，服务端固定目录并取租约，防两路同时写。
- **Verification Epoch**：验证报告带 `Run ID / Build Digest / Verification Epoch` 三重标识；
  门禁执行前检查报告对应版本是否与当前一致，**旧报告即使全绿也不能用于新构建**。

原文（验证段）：「每当系统要执行验证门禁时，都会检查报告对应的运行任务、构建摘要和
验证轮次是否与当前的状态一致。即使旧报告中的检查全部通过，只要构建版本发生变化，
这份报告就不能继续作用于当前的版本。」

## 2. 与 agent-ops 的对照

| 维度 | GCA | 本 skill 现状 | 差距 |
|---|---|---|---|
| 单写者 | 制品级所有权 | 任务级租约（lease_until + worker_id） | 缺**文件/工作区**级互斥 |
| 工作区租约 | 目录级 | 无；多任务可改同一 repo | 真实缺口 |
| 验证新鲜度 | 三重标识 | `manager` 读 progress 快照后决策，快照可能已过期 | 真实缺口 |

`manager.py` 的决策流程（`build_snapshot` → `ask_model` → `apply`）没有版本号：
模型基于 t0 时刻的快照给出 `restart`，执行时任务可能已被 worker 推进到 t1。
当前靠「解析失败不动」兜底，但没有「快照过期则丢弃决策」的机制。

## 3. 可移植性

### 3.1 Verification Epoch（可做，中等成本）

最小切片：给 `tasks` 加 `revision INTEGER NOT NULL DEFAULT 0`，每次状态变更 +1；
`build_task_snapshot` 输出 `revision`；决策 JSON 带上 `revision`；
`apply` 前在同一事务里校验 `tasks.revision` 未变，变了就丢弃本轮决策并记事件。
约 60–100 行，需改 `taskctl` schema、`manager` 决策协议、两处测试。

风险：决策格式变更会影响 `decisions.jsonl` 的消费方（目前只有人和审计脚本读）。
必须保留旧格式兼容（缺 `revision` 视为「不校验」）。

### 3.2 工作区租约（可做，但优先级低）

最小切片：`tasks` 加 `workspace` 字段 + 唯一约束 `(workspace, status='running')`，
抢占时校验。但本 skill 的并发上限是 10，且任务通常按文件划分，
真实冲突频率未测；先不做，等出现真实冲突再上。

## 4. 判定与理由

**adapt，本期不落地。** Verification Epoch 是真实缺口，但要改 manager 的决策协议，
属于 P2 机制变更，需独立立项 + 失败测试 + 兼容旧格式；塞进雷达一期会挤掉
更确定的落地项。方案已写清，下一期可直接执行。

## 5. 若后续落地（可直接照做）

1. `taskctl`：`tasks` 加 `revision`，所有 `UPDATE tasks SET status=...` 处 +1；
2. `manager`：快照带 `revision`；决策 JSON 加可选 `revision`；
3. `manager.apply`：`BEGIN IMMEDIATE` 校验 revision，不匹配则 `skipped_stale++` 并写事件；
4. 测试：构造「决策期间 revision 变化」，断言决策被丢弃且任务状态未被覆盖；
5. 文档：`memory.md` 第十节补一段「决策新鲜度」。

## 6. 第二轮深读补充

- 三重标识记录在「产物与验证报告」里；门禁执行前检查报告对应的
  Run ID / Build Digest / Verification Epoch 是否与当前状态一致，
  构建版本变化则旧报告作废。
- 交接记录（服务端签发）记录阶段状态变化：Scaffold 重生成契约时记录失效的下游文件；
  素材归并记录实际接收批次；集成完成记录构建版本。
- 对照实验只有 20 组，论文未做组件级消融，机制收益无法归因（文章自认）。

与本 skill 的差距成立（manager 决策没有「依据的快照版本」），方案见第 5 节，结论不变。
