# Harness 对比研究（2026-11-13，9 个开源项目）

> 简报来源：技术情报 2026-11-13（agent 编排层集中爆发）。
> 全部 clone 在 `<skill 安装目录>/references-upstream/`。
> 原则：单机 skill 只吸收**设计模式**，不抄 K8s 基建代码。每条注明「采纳/不采纳 + 理由」。

## 一、行业共识（简报主题串联 + 我们逐一对照）

**「agent 是有状态、间歇运行的 workload」——我们 11-12 就独立走到同一结论**：

| 行业做法 | 我们的对应物 | 结论 |
|---|---|---|
| google/ax：PostgreSQL 存资源 + 分布式锁（lease）+ **轮询**（不依赖 LISTEN/NOTIFY） | SQLite tasks 表 + lease_until + 30s tick 轮询 | **同构**。ax 把同一模式扩到集群级；单机 SQLite 是它的退化形式，方向被验证 |
| ax：Task immutable once created | prompt.md 落盘版本化 + dispatch 幂等拒绝 | 一致 |
| substrate：actor→少量 worker 映射、快照恢复 500ms | 任务=DB 行 + worker 池（按模型分桶 + 全局上限） | 一致；我们不做内存快照（CLI agent 状态在会话文件里，天然持久化） |
| ax：SuspendTask/ResumeTask 检查点 | **原缺** → 已补 `taskctl suspend/resume`（2026-11-13） | 采纳落地 |
| trueforge：上下文工程（compaction、deferred tool loading） | memory.md 全局重写 + compaction 留痕 | 一致；deferred tool loading 不适用（CLI agent 自带工具管理） |
| PrimusClaw：NATS JetStream 队列 / API-Brain-Hands 三服务 | SQLite 队列 / supervisor / CLI agent | 结构同构，消息队列对单机是过度设计 |
| deer-flow：LangGraph 状态图 + 沙箱 | 文件+SQLite 零依赖 | 不采纳——更重，且我们绑定本机 CLI 的真实坑是差异化价值 |

## 二、本次落地（有 git 留痕，可回退）

**`taskctl suspend <task>` / `resume <task>`**（借鉴 ax SuspendTask/ResumeTask）：

- `suspend`：SIGTERM 停 worker 组 → status=`suspended` → 写 `out/SUSPENDED` 标记 → 事件留痕。
  与 cancel（终态）/ restart（耗一次重试）的区别：**不消耗 attempts**，可无限次恢复。
- `resume`：清标记 → 回 `queued` → 下一轮 tick 正常拉起，prompt 自动带「读 progress.md 从断点继续」。
- 端到端实测：挂起后 tick 不调度（suspended 不参与）、resume 回队列、事件 `suspended`/`resumed_from_suspend` 落 task_events。
- 使用场景：人要临时腾出并发额度（如夜间批量要占满 10 路）、或要观察中间状态再放行。

## 三、明确不抄的（防过度设计）

1. **声明式 manifest（ax apply -f task.yaml）**：watchdog 的 jobs.json 已是这个形态；taskctl 的 `add-file` 批量导入覆盖同需求。两套并存即可，不做第三种。
2. **内存快照恢复（substrate 500ms resume）**：CLI agent 的「内存」在会话 jsonl 里，`--resume` 天然恢复；无需自建快照层。
3. **gRPC 控制面 / NATS 队列 / K8s CRD**：单机 skill 用不上，引入即负债。
4. **Token 用量仪表盘（deer-flow）**：knot_batch/global_load 已有事后观测；实时仪表盘无消费方。

## 四、clone 清单（2026-11-13 清理后）

**保留**（有未完成待办）：
- `ax`(2.3M)——suspend/resume 借鉴来源；待办：`ax ssh` 隧道看运行中任务
- `trueforge`(74M)——待办：git 驱动 SKILL.md 打包

**已删**（约 1.2G，结论已固化进本 skill 文档，需要时 shallow clone 三分钟可回）：
- deer-flow → compaction 事件留痕设计已落 `memory.md` §十一
- munder-difflin → "无损原文留盘、只压缩副本" 已落 `memory.md` §十一
- prime-agent → 阈值参数化校验已落 `taskctl._valid_percent`
- substrate / PrimusClaw / OpenHarness / LongHorizon-Harness → K8s 基建模式不采纳，对照结论见本文第一节

## 五、下次再看

- trueforge 的 git 驱动 SKILL.md 打包（与我们的 skill 目录结构对照）。
- ax 的 `ax ssh`（隧道看运行中任务）——我们 `locate/logs` 已覆盖 80%，若长任务排障频繁再考虑 `taskctl attach`（实时 tail 会话 jsonl）。
