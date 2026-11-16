# 技术雷达借鉴台账

> 自动生成，请勿手改：数据在 `radar/state/radar.db`，
> 审计流在 `radar/state/audit.jsonl`，正文在 `radar/intake|analyses|applied/`。
> 重新渲染：`python3 scripts/radar_cli.py ledger`

## 汇总

| 期数 | 候选 | 待分析 | 已分析 | 采纳 | 改造 | 不抄 | 已落地变更 | 缓存占用 |
|---|---|---|---|---|---|---|---|---|
| 2 | 8 | 0 | 8 | 2 | 4 | 2 | 2 | 0.0 MB |

## 2026-11-16 技术情报简报 2026-11-16（15:00 批次）

来源：paste（radar/intake/2026-11-16-2.md）；候选 4 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [Agent 干到一半崩了：长任务续跑的工程学](https://cloud.tencent.com/developer/article/2784829) | article | deep | 5 | 采纳 | `radar/analyses/2026-11-16/05-long-task-resume.md` |
| 2 | [【学习笔记】从蚂蚁阿福谈起：面向生产流量的 Agent 可观测实践](https://www.cnblogs.com/OceanBase/p/23612511) | article | deep | 3 | 改造 | 先筛后评已具备；分层埋点在单机规模无第二个消费者 `radar/analyses/2026-11-16/06-agent-observability-trace.md` |
| 3 | [别再硬套 Docker 了：多 Agent 跨系统原生沙箱设计与全局资源调度](https://cloud.tencent.com.cn/developer/article/2781966) | article | brief | 2 | 不抄 | 正文仅摘要无实现细节；本 skill 不执行不可信代码，不需要内核沙箱 `radar/analyses/2026-11-16/07-native-sandbox.md` |
| 4 | [GitHub - openclaw/openclaw-enterprise](https://github.com/openclaw/openclaw-enterprise) | repo | deep | 4 | 采纳 | claim+审计同语句；已落地台账事务化与 claim 事件 `radar/analyses/2026-11-16/08-openclaw-control-plane.md` |

**已落地变更**

- `a7e9c50` ← Agent 干到一半崩了：长任务续跑的工程学（templates/tasks/_done-contract.md, scripts/taskctl.py, tests/test_radar.py）：断点快照四问进入任务提示词
- `a7e9c50` ← GitHub - openclaw/openclaw-enterprise（scripts/radar_store.py, tests/test_radar.py）：雷达台账变更+状态+审计同事务

## 2026-11-16 技术情报简报 2026-11-16（11:00 批次）

来源：paste（radar/intake/2026-11-16-1.md）；候选 4 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [GitHub - Tencent/LoopForge: Self-hosted workflows for coding-agent delivery. Orchestrate CodeBuddy, Codex and Claude Code with scripts and human approval gates. Includes Local workflows for coding assistants.](https://github.com/Tencent/LoopForge) | repo | deep | 4 | 改造 | 四类节点与从节点重跑是真实缺口，但需改状态机；本期只沉淀不落地 `radar/analyses/2026-11-16/01-loopforge-sop-nodes.md` |
| 2 | [SuperAgent 实战：让 Router 看见全局，让 Worker 不再各说各话-腾讯云开发者社区-腾讯云](https://cloud.tencent.com/developer/article/2784348) | article | deep | 4 | 改造 | 信封失败语义缺失：超时/送不到/等人工未区分，错误无三元组 `radar/analyses/2026-11-16/02-superagent-envelope-leases.md` |
| 3 | [多 Agent 如何协作完成复杂任务？从 GCA 看任务编排与执行控制-腾讯云开发者社区-腾讯云](https://cloud.tencent.com/developer/article/2780499) | article | deep | 4 | 改造 | Verification Epoch 可补 manager 决策过期，需改决策协议，下期落地 `radar/analyses/2026-11-16/03-gca-verification-epoch.md` |
| 4 | [GitHub - openJiuwen-ai/agent-runtime: openJiuwen Agent Runtime 是 openJiuwen 体系中的智能体运行与部署管理平台。](https://github.com/openJiuwen-ai/agent-runtime) | repo | deep | 2 | 不抄 | 部署策略与多租户不适用单机；策略自带表定义的形态留待换存储时用 `radar/analyses/2026-11-16/04-agent-runtime-deploy-strategies.md` |

