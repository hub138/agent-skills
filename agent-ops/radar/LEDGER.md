# 技术雷达借鉴台账

> 自动生成，请勿手改：数据在 `radar/state/radar.db`，
> 审计流在 `radar/state/audit.jsonl`，正文在 `radar/intake|analyses|applied/`。
> 重新渲染：`python3 scripts/radar_cli.py ledger`

## 汇总

| 期数 | 候选 | 待分析 | 已分析 | 采纳 | 改造 | 不抄 | 已落地变更 | 缓存占用 |
|---|---|---|---|---|---|---|---|---|
| 9 | 88 | 80 | 8 | 2 | 4 | 2 | 2 | 0.0 MB |

## 2026-11-16 技术情报简报 2026-11-16

来源：tech-radar（（原文，公开版略） 10 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [Skill 自进化：基于执行轨迹与评测反馈的多代优化实践](http://mp.weixin.qq.com/s?__biz=MzAxNDEwNjk5OQ==&mid=2650547008&idx=1&sn=88ed890da980cee1caa6c9c21b90e773&chksm=82a30a080e4a6d36f720b24d8570353cc31fb977f066a9841d37ccf7dddeb431447bca092331#rd) | article | skip | - | 待判 | - |
| 2 | [基于本体的 AI 数据研发落地：淘宝行业经营分析实战](http://mp.weixin.qq.com/s?__biz=Mzg4NTczNzg2OA==&mid=2247512497&idx=1&sn=82924a5a7f2f62006617c12080a83fc2&chksm=cef4487367dc065cd43f4dd799ab924ce3fbf19fb346933b94a5b187f262427b00bc7609f16b#rd) | article | skip | - | 待判 | - |
| 3 | [alibaba/open-code-review: Secure, fast, efficient, battle-tested at Alibaba&#39;s scale. Hybrid architecture code review tool](https://github.com/alibaba/open-code-review) | repo | skip | - | 待判 | - |
| 4 | [Securing persistent agents like OpenClaw at OpenAI](https://developers.openai.com/blog/securing-persistent-agents-like-openclaw-at-openai) | article | skip | - | 待判 | - |
| 5 | [不只是Memory：Ontology如何让Coding Agent越用越懂项目？](http://mp.weixin.qq.com/s?__biz=MjM5ODYwMjI2MA==&mid=2649808188&idx=1&sn=9493b80e2a1e4c6ab409e77f2ac57584&chksm=bf575e7d296ddafb1902d3284807bf9ee558d75df0bd86e472491947af2a91790cf592ce6128#rd) | article | skip | - | 待判 | - |
| 6 | [Qwen Code 1.0 正式发布：Qoder 与 Qwen Code Harness 融合开源](https://mp.weixin.qq.com/s/CXUnh_CP0S4gKV5MYwWWtw) | article | skip | - | 待判 | - |
| 7 | [AI 写得快，谁来接住生产责任](#) | other | skip | - | 待判 | - |
| 8 | [Codex、Claude Code 都卷完了，居然还能跑出黑马？整个产品，现在都可以是一个提示词](#) | other | brief | - | 待判 | - |
| 9 | [DeepSeek又来掀桌子了！官方App全套能力开放API，联网搜索价格不到OpenAI、Claude的8%](#) | other | skip | - | 待判 | - |
| 10 | [Super Agent 进群：今年11.11，多了个会主动干活的"数字人队长"](#) | other | brief | - | 待判 | - |

## 2026-11-16 技术情报简报 2026-11-16（15:00 批次）

来源：paste（（原文，公开版略） 4 条。

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

来源：paste（（原文，公开版略） 4 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [GitHub - Tencent/LoopForge: Self-hosted workflows for coding-agent delivery. Orchestrate CodeBuddy, Codex and Claude Code with scripts and human approval gates. Includes Local workflows for coding assistants.](https://github.com/Tencent/LoopForge) | repo | deep | 4 | 改造 | 四类节点与从节点重跑是真实缺口，但需改状态机；本期只沉淀不落地 `radar/analyses/2026-11-16/01-loopforge-sop-nodes.md` |
| 2 | [SuperAgent 实战：让 Router 看见全局，让 Worker 不再各说各话-腾讯云开发者社区-腾讯云](https://cloud.tencent.com/developer/article/2784348) | article | deep | 4 | 改造 | 信封失败语义缺失：超时/送不到/等人工未区分，错误无三元组 `radar/analyses/2026-11-16/02-superagent-envelope-leases.md` |
| 3 | [多 Agent 如何协作完成复杂任务？从 GCA 看任务编排与执行控制-腾讯云开发者社区-腾讯云](https://cloud.tencent.com/developer/article/2780499) | article | deep | 4 | 改造 | Verification Epoch 可补 manager 决策过期，需改决策协议，下期落地 `radar/analyses/2026-11-16/03-gca-verification-epoch.md` |
| 4 | [GitHub - openJiuwen-ai/agent-runtime: openJiuwen Agent Runtime 是 openJiuwen 体系中的智能体运行与部署管理平台。](https://github.com/openJiuwen-ai/agent-runtime) | repo | deep | 2 | 不抄 | 部署策略与多租户不适用单机；策略自带表定义的形态留待换存储时用 `radar/analyses/2026-11-16/04-agent-runtime-deploy-strategies.md` |

## 2026-11-15 技术情报简报 2026-11-15

来源：tech-radar（（原文，公开版略） 12 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [GitHub - TencentCloud/CubeSandbox: Instant, Concurrent, Secure &amp; Lightweight Sandbox for AI Agents.](https://github.com/TencentCloud/CubeSandbox) | repo | deep | - | 待判 | - |
| 2 | [美团把训练和推理的概率做到逐位相同：分歧藏在一个加法顺序里-阿里云开发者社区](https://developer.aliyun.com/article/1781637) | article | skip | - | 待判 | - |
| 3 | [GitHub - Tencent/LoopForge](#) | repo | brief | - | 待判 | - |
| 4 | [GitHub - openJiuwen-ai/agent-runtime](#) | repo | brief | - | 待判 | - |
| 5 | [SuperAgent 实战：让 Router 看见全局](#) | other | brief | - | 待判 | - |
| 6 | [Skill 自进化：基于执行轨迹与评测反馈](#) | other | skip | - | 待判 | - |
| 7 | [云硬盘性能与低时延选型](#) | other | skip | - | 待判 | - |
| 8 | [GitHub - TencentCloud/TencentDB-Agent-Memory](#) | repo | brief | - | 待判 | - |
| 9 | [块存储选型对照](#) | other | skip | - | 待判 | - |
| 10 | [从零搭建AI智能体平台](#) | other | brief | - | 待判 | - |
| 11 | [让 Go 走得更远：用 LLGo 打通](#) | other | skip | - | 待判 | - |
| 12 | [不只是Memory：Ontology如何让Coding Agent](#) | other | skip | - | 待判 | - |

## 2026-11-14 技术情报简报 2026-11-14

来源：tech-radar（（原文，公开版略） 12 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [别再硬套 Docker 了：多 Agent 跨系统原生沙箱设计与全局资源调度](https://developer.aliyun.com/article/1782401) | article | deep | - | 待判 | - |
| 2 | [应用只是冰山一角：构建大规模移动应用基础设施需要什么](https://www.infoq.cn/article/oKGTGPNZuleM61QqQOVf?utm_source=rss&utm_medium=article) | article | skip | - | 待判 | - |
| 3 | [【AI】Agent 全栈进阶｜AgentScope 沙箱源码解析](#) | other | brief | - | 待判 | - |
| 4 | [GitHub - TencentCloud/TencentDB-Agent-Memory](#) | repo | brief | - | 待判 | - |
| 5 | [块存储选型对照：主流云平台云硬盘类型与适用场景](#) | other | brief | - | 待判 | - |
| 6 | [让 Go 走得更远：用 LLGo 打通 Go 与 C/C++/Python](#) | other | skip | - | 待判 | - |
| 7 | [从提效到扩能：AI 驱动小团队能力突破](#) | other | brief | - | 待判 | - |
| 8 | [黄仁勋辞职：把扁平化推到极致的创始人](#) | other | brief | - | 待判 | - |
| 9 | [GitHub Actions 锁文件功能正式可用](#) | repo | brief | - | 待判 | - |
| 10 | [Docker 呼吁通过隔离与治理保障智能体安全](#) | other | brief | - | 待判 | - |
| 11 | [一套内核撑起多端产品：我们用"换源判据"分层](#) | other | brief | - | 待判 | - |
| 12 | [智能互动 Agent 在快手商业场景的落地实践](#) | other | skip | - | 待判 | - |

## 2026-11-13 技术情报简报 2026-11-13

来源：tech-radar（（原文，公开版略） 12 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [ONNX Runtime嵌入内核+算子下推：库内AI计算的执行链路拆解-阿里云开发者社区](https://developer.aliyun.com/article/1782287) | article | skip | - | 待判 | - |
| 2 | [LinkedIn 基于 OpenTelemetry 追踪用户动作全链路：从前端点击到后端服务](https://www.infoq.cn/article/3u1PmO0HqQXBFNibKZoe?utm_source=rss&utm_medium=article) | article | skip | - | 待判 | - |
| 3 | [应用只是冰山一角：构建大规模移动应用基础设施需要什么](#) | other | skip | - | 待判 | - |
| 4 | [GFlow：面向游戏设计的多 Agent 协作与验证实践｜AICon北京](#) | other | skip | - | 待判 | - |
| 5 | [奥运史上第一次，一朵云整体留给了举办国](#) | other | brief | - | 待判 | - |
| 6 | [qwen-code](#) | other | skip | - | 待判 | - |
| 7 | [黄仁勋辞职：把扁平化推到极致的创始人，体面退场的代价](#) | other | skip | - | 待判 | - |
| 8 | [zvec](#) | other | brief | - | 待判 | - |
| 9 | [批次召回的工程实现：码段索引、流向图查询与召回状态机](#) | other | skip | - | 待判 | - |
| 10 | [Agent 全栈：把一个"会思考的循环"变成"能上线的系统"](#) | other | skip | - | 待判 | - |
| 11 | [Docker 呼吁通过隔离与治理保障智能体安全](#) | other | skip | - | 待判 | - |
| 12 | [Google 终于让 PyTorch 原生跑上 TPU，开发者："早该如此！"](#) | other | skip | - | 待判 | - |

## 2026-11-12 技术情报简报 2026-11-12

来源：tech-radar（（原文，公开版略） 12 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [智能体 AI 架构中记忆、知识与上下文的系统化方案](https://www.infoq.cn/article/COuPKpA6rTf05C6JM10y?utm_source=rss&utm_medium=article) | article | brief | - | 待判 | - |
| 2 | [如何消除PD分离推理的结构性拥塞？Matrix架构深度解析](https://cloud.tencent.com/developer/article/2780584) | article | skip | - | 待判 | - |
| 3 | [大模型API网关的核心不是转发，是调度：EWMA动态打分算法的工程实现](https://cloud.tencent.com/developer/article/2781373) | article | brief | - | 待判 | - |
| 4 | [ONNX Runtime嵌入内核+算子下推：库内AI计算的执行链路拆解](https://cloud.tencent.com/developer/article/2781742) | article | skip | - | 待判 | - |
| 5 | [GitHub - deepseek-ai/deepseek-harness: DeepSeek Harness: Everything is a Plugin.](https://github.com/deepseek-ai/deepseek-harness) | repo | skip | - | 待判 | - |
| 6 | [Managed Agents 云端智能体托管平台：从跑通 Agent 到稳定交付](https://cubesandbox.com/zh/blog/posts/2026-11-06-oma-managed-agents) | article | skip | - | 待判 | - |
| 7 | [bytedance/deer-flow](#) | other | brief | - | 待判 | - |
| 8 | [多云 FinOps](#) | other | brief | - | 待判 | - |
| 9 | [Agent 正在终结 Pull Request](#) | other | skip | - | 待判 | - |
| 10 | [如何提升 AI 的环境可持续性](#) | other | skip | - | 待判 | - |
| 11 | [蚂蚁数科LingDT-Decision](#) | other | skip | - | 待判 | - |
| 12 | [工程师招聘跌至峰值一半](#) | other | brief | - | 待判 | - |

## 2026-11-11 技术情报简报 2026-11-11

来源：tech-radar（（原文，公开版略） 12 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [DeepInfer: High-performance, large-scale inference framework for DeepSeek models](https://github.com/deepseek-ai/DeepInfer) | repo | brief | - | 待判 | - |
| 2 | [阿里云发布基于 AMD 第六代 EPYC 处理器的第十代 ECS 企业级实例](https://www.infoq.cn/article/xCQx0qBofJYfBdVrxVxt?utm_source=rss&utm_medium=article) | article | brief | - | 待判 | - |
| 3 | [DLF Lance 概述与工作原理 - Alibaba Cloud](https://www.alibabacloud.com/help/zh/dlf/dlf-2-0/product-overview/dlf-lance-overview-and-how-it-works) | article | brief | - | 待判 | - |
| 4 | [OceanBase 4.4.2 LTS 解读 \| 从关键业务负载到 AI 实时智能决策](https://www.oceanbase.com/en/blog/30043501360) | article | skip | - | 待判 | - |
| 5 | [AI Coding之后：搜广推团队的研发工程化探索](http://mp.weixin.qq.com/s?__biz=MzE5ODQ3MDM4Mw==&mid=2247492726&idx=1&sn=3cc81746dc6c3352610147bc5418f15f&chksm=97aae20dc644b1d475640afebed98ff68ecd0d5d1b1cf0c893468d824b71f474d3afadb0f98f#rd) | article | skip | - | 待判 | - |
| 6 | [deepseek-recipe](https://github.com/deepseek-ai/deepseek-recipe) | repo | skip | - | 待判 | - |
| 7 | [企业微信 AI 助手架构设计与权限边界](#) | other | brief | - | 待判 | - |
| 8 | [字节跳动大模型路线图](#) | other | skip | - | 待判 | - |
| 9 | [字节AI基座团队Seed五路大军](#) | other | brief | - | 待判 | - |
| 10 | [YuanQi 低代码平台 v1.0 开源](#) | other | brief | - | 待判 | - |
| 11 | [Agent 从 Demo 到生产实战课](#) | other | brief | - | 待判 | - |
| 12 | [基于 AgentKit 重塑研发协作](#) | other | brief | - | 待判 | - |

## 2026-11-10 技术情报简报 2026-11-10

来源：tech-radar（（原文，公开版略） 10 条。

| # | 条目 | 类型 | 路由 | 相关 | 结论 | 理由 / 报告 |
|---|---|---|---|---|---|---|
| 1 | [一文拆解DSH Super-agent双层架构：如何做到后台跑任务、前台继续接活](http://mp.weixin.qq.com/s?__biz=MzI2NDU4OTExOQ==&mid=2247698141&idx=1&sn=7934b5a33583a433f7e8a0c0099e8e9b&chksm=eb31e58620dd254589a539344c4fab759fa74b2b14e6e063bd16ce6ccb6619f9a9637e87d725) | article | deep | - | 待判 | - |
| 2 | [Cloudflare KV Instant：读取 p99 仅 1.62 毫秒，写入一次却要 0.1 美元](https://www.infoq.cn/article/YrPwJgFYyBSAmJE4hJAB?utm_source=rss&utm_medium=article) | article | skip | - | 待判 | - |
| 3 | [Airbnb 借助 Chronon 将推荐延迟从两天缩短至秒级](https://www.infoq.cn/article/yuRNB72KsEbjGYSkV7FY?utm_source=rss&utm_medium=article) | article | skip | - | 待判 | - |
| 4 | [企业微信 AI 助手架构设计与权限边界-腾讯云开发者社区-腾讯云](https://cloud.tencent.com/developer/article/2779366) | article | brief | - | 待判 | - |
| 5 | [DeepSeek Harness 日活154万，官方开始给插件作者发Token](#) | other | brief | - | 待判 | - |
| 6 | [DeepSeek又开源了！公布Super agent架构](#) | other | brief | - | 待判 | - |
| 7 | [ADD 资产驱动开发：让 AI Coding 懂业务](#) | other | brief | - | 待判 | - |
| 8 | [openJiuwen首发Agent Device Foundation](#) | other | brief | - | 待判 | - |
| 9 | [硅谷疯炒 AI 自我进化，李飞飞、Jeff Dean 齐泼冷水](#) | other | skip | - | 待判 | - |
| 10 | [字节跳动大模型路线图](#) | other | skip | - | 待判 | - |

