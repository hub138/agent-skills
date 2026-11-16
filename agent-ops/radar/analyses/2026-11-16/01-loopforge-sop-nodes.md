# LoopForge：SOP 四类节点与人工门禁

- 来源：2026-11-16 11:00 #1 / https://github.com/Tencent/LoopForge
- 分析提交：`<cache>/loopforge`（depth 1，2026-11-16）
- 类型：repo
- 相关性：4
- 结论：**adapt（本期不落地）**

## 1. 核心循环

需求 → Main Bot 开 Docker 工作区 → 调项目角色（子 agent）→ SOP 引擎按序执行
`Agent / Script / Human-gate / sub-SOP` 四类节点 → 每节点留产物与日志 → 出 PR/MR。
失败可从任意节点重试/重跑，人工门禁可暂停、打回指定步骤。

## 2. 机制拆解

### 2.1 节点类型是一等公民

- 证据：`internal/domain/workflow.go:56`（`Type` 为 `sop` 时引用子工作流）；
  `internal/runtime/workspace_preparation.go:411`（`script`/`command` 节点）；
  `internal/runtime/gate_mcp.go:265`（`pass/rework/fail/human` 四种门禁决策）。
- 形态：节点不是「一段 prompt」，而是带类型、输入输出、可单独重跑的执行单元。
- 失败分支：门禁为 `human` 时进入等待态，由人给 `pass/rework/fail`；
  `rework` 不是从头重跑，而是回到指定节点。

### 2.2 从任意节点重跑

- 证据：README「retrying or rerunning from any node」；节点产物按节点归档，
  下游读的是产物而不是上游进程的内存。
- 关键前提：**产物按节点落盘**，否则「从节点重跑」会丢上下文。

### 2.3 沙箱与镜像 digest

- 证据：`docs/deployment.md:52`（`MIRROR` 拉取后用 `docker image inspect` 核对 digest）。
- 形态：镜像名可被镜像站替换，但结果必须 tag 回官方名并核对 digest。
- 对本 skill 的价值：低——我们没有容器。

## 3. 与 agent-ops 的对照

| 维度 | LoopForge | agent-ops 现状 | 差距 |
|---|---|---|---|
| 节点类型 | Agent/Script/Human-gate/sub-SOP | `templates/tasks/*.md` 只是提示词模板 | 缺类型化节点 |
| 人工门禁 | 一等节点，可等待/打回 | `manager` 的 `escalate` + guidance | 有门禁语义，无「打回指定步骤」 |
| 从节点重跑 | 支持 | `resume` 读 progress 从断点继续 | 缺节点级重跑 |
| 隔离 | Docker 沙箱 | 进程 + 工作目录 | 不适用（单机、无容器） |

## 4. 可移植性

- 节点化 + 从节点重跑：**需要改状态机与任务模板**，不是几十行能验证的。
  最小切片是给 `result.json` 增加 `node` 与 `produced_at_step`，让 guidance 能指向步骤；
  但这会改变 result 契约，收益要等多次真实重跑才看得出来。
- Human-gate：已有 `manager` 的 `escalate`，再做一套独立门禁是重复建设。
- 沙箱/digest：依赖 Docker，不适用。

## 5. 判定与理由

**adapt，本期不落地。** 值得抄的是「产物按节点落盘 + 从节点重跑」这一条纪律，
但它要求先改任务状态机与 result 契约，属于独立立项，不应塞进雷达一期。
本期先把「断点快照四问」写进收工契约（见 #5），作为节点化的前置条件。

## 6. 若后续落地

1. `tasks` 表加 `step` / `step_started_at`（只加列）；
2. `result.json` 增加 `steps: [{name, status, artifact}]`，校验器兼容旧格式；
3. `taskctl resume --from-step <name>`：只跳过已确认步骤，不重跑外部副作用；
4. 失败测试：suspended → resume → 断言已确认步骤没有二次执行。
