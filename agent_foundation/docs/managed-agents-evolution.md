# agentic 接口面的演进：用 Claude Managed Agents 构建（The evolution of agentic surfaces: building with Claude Managed Agents）

- 原文：[The evolution of agentic surfaces: building with Claude Managed Agents](https://claude.com/resources/articles/building-with-claude-managed-agents)
- 来源：Anthropic（claude.com），作者 Gagan Bhat、Isabella He
- 发布：2026-06-10
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 assets.claude.com 绝对直链并配中文短描述；三代接口演进、生产六项挑战、brain 与 hands 解耦、context anxiety 案例、三原语、四项生产收益、客户案例与上手路径完整翻译。

把 agent 送进生产需要的远超一个好的 prompt。agent 需要一个地方运行它写的代码，需要凭据去触达你的数据，需要可观察的 session，还需要随用量伸缩的基础设施。在 Applied AI 团队，我们站在产品、研究与在 Claude 上构建的客户三者的交汇处——同一个模式反复出现：基础设施是原型与生产级 agent 之间的分界线。太多团队把开发周期消耗在安全、状态管理、权限与 harness 调校上。

[Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) 是我们用于构建与部署生产级 agent 的一组可组合 API，它把为性能调校过的 agent harness 与生产基础设施配对，让团队从原型到上线用几天而非几个月。本文覆盖 Anthropic agentic 构建模块的演进、我们为什么构建 Claude Managed Agents，以及团队今天如何把它用在生产中。

## agent 架构的演进

2023 年我们向开发者开放 Claude 时，API 刻意保持简单：token 进，token 出。你发一个 prompt，Claude 返回一段补全，harness 与底层基础设施都由你自己构建。

这些年 API 稳步变丰富，但底下的约定从未改变：一次请求、一个模型回合，你的应用决定接下来发生什么。在很长时间里这就够了。总结一篇文档、给一张支持工单分类、改写一段文字——这类工作轻松装进单个回合。

但随着时间推移，人们想交出去的任务开始装不下了。他们想让 Claude 把任务从头做到尾：查一件事、对它采取行动、看看发生了什么变化、决定下一步。他们还想让它在自己工作本来就运行着的系统里干活，比如代码库、内部 wiki 或工单系统。

用这套 API 把 Claude 变成 agent，意味着自建循环：问模型该做什么，运行工具，把结果喂回去，重复。你要负责构建和部署 agent 脚手架，并且随着模型演进去调校它。对需要完全定制的 agent，这条路成立。对更可预测、复杂度更低的 agentic 工作负载，随着模型与产品演进去持续调校 harness 就变得乏味。

![图：从 Messages API 的单请求单回合，到自建 agent 循环的演进示意](https://assets.claude.com/fe30ad015136d78e5367ec44d8fca508f184104e.png)

[Claude Code](https://claude.com/product/claude-code) 是我们 2025 年发布的 agentic 编程工具，让 Claude 直接与你的代码库交互，它内部就装着我们自己那版 harness：循环、工具执行、subagent、context 管理，以及让它成为有效 agent 的丰富能力。开发者自然想在各种领域为自己的 agent 拿到同类 harness 机制。

为了让团队能在 Claude Code harness 之上构建 agent，我们发布了 [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)。它给开发者一套工具，在与 Claude Code 相同的机制上构建自己的 agent，免去维护自研循环。对很多团队来说，agent 从这一刻起才变得实用：harness 到手时已经为 Claude 调校好，带着基础设施原语，并且随着 Claude Code 一起持续改进。

即便有了 harness，把 agent 部署进生产环境仍然充满挑战，原因有六：

- 托管与伸缩。agent 跑在哪里？多小时任务的进程能活多久？用量上涨时谁来伸缩？
- Session 管理。agent 的历史与进度存在哪里？一次运行能否在中断后干净恢复？能否回头检视先前 session 里发生过什么？
- 文件系统管理。干真活就要产出工件：改代码、写文件、构建输出。agent 从哪里拿到可操作的工作区，两次运行之间这个工作区怎么办？
- 执行隔离。Claude 写的代码总得在某处执行。如果它错了，爆炸半径多大？你在生产里真正信得过哪条边界？
- 凭据。agent 需要访问你的系统。它怎样拿到访问权，又不把你专属的信息暴露给它生成的代码？
- 可观察性。当 agent 自主工作一小时后做出意外的事，你能逐步还原它走过的每一步吗？

有了 Agent SDK，上述生产基础设施的许多要素经由 Claude Code 的机制提供：agent 得到真实文件系统可用，session 状态持久化到本地或外部存储，可观察性经 OpenTelemetry 导出到你已经在用的任何监控系统。

![图：Agent SDK 经 Claude Code 机制提供文件系统、session 持久化与 OpenTelemetry 可观察性](https://assets.claude.com/df5faaa1a40adae1b9607307078bd88e7c636dae.png)

但随着团队越来越多地把 agent 从本地开发推向生产，他们需要一种方式以托管基础设施做规模化部署。模型与周边 harness 越来越先进——运行更久、执行更多代码、触碰更多系统、采取更多动作——伸缩、安全与沙箱化都变得更难。

这些障碍中有几个源自一个共同的架构选择：agent harness 常与它操作的文件系统跑在同一个容器里。容器得先转起来（付一笔启动成本）Claude 才能思考，agent 连同代码执行紧挨着你的凭据，容器一停，运行跟着一起消失。

Managed Agents 用 [brain 与 hands 解耦](https://www.anthropic.com/engineering/managed-agents)来解决这些问题。调用 Claude 的 harness 与执行代码的沙箱分开运行，session——一份只增不改的日志，记录每一次模型调用、工具调用与结果——把两者连起来。Claude 可以在任何容器存在之前开始推理，沙箱离你的凭据远远的，整段运行随时可以从 session 重建。

![图：harness 与沙箱分离，session 作为只增日志连接两者](https://assets.claude.com/b715041a8258b4c9b675a42f047aa4202c30b851.png)

## 何时以及为什么使用 Claude Managed Agents

用 Managed Agents 构建时，用户定义任务、工具与护栏，Anthropic 在我们的基础设施上运行 agent 并处理底下的 agentic 循环：怎样给 agent 一个可调用工具的执行环境、出错时怎样恢复、多 agent 编排等等。

[harness 不随模型智力一起演进时，agent 就退化](https://www.anthropic.com/engineering/harness-design-long-running-apps)。在 Claude Sonnet 4.5 上，agent 临近上下文末尾会匆忙收尾，放着剩余空间不用提前结束工作——这个模式叫 context anxiety（上下文焦虑）。我们的修复是给 harness 加 context resets，等于把 Claude 在接近上限时需要帮助才能保持连贯写成了假设。这个假设没活过下一代模型。到了 Claude Opus 4.5，该行为消失了，我们加的 resets 只剩开销。

对多数组织来说，维护 harness 是不产生差异化价值的开销。harness 必须为特定模型行为调校；compaction、工具执行、缓存这些原语在 Claude 上与其他模型上的工作方式不同。有了 Claude Managed Agents，harness 随模型一起演进，团队可以专注真正让 agent 产生差异的两件事：context 管理与领域专长。

为了让开发者配置构建有效 agent 所需的 context 与工具，Managed Agents 围绕三个主资源构建：agents、environments 与 sessions。agent 是一份配置：模型、prompt、一组工具，以及围绕它们的护栏。environment 是 agent 运行其中的执行环境：沙箱容器、它的网络规则、预装的包，托管在我们的云或你控制的基础设施上。每次运行是一个 session，把一个 agent 与一个 environment 配对，得到自己独立的沙箱实例。session 在服务端持久化完整事件历史、沙箱状态与输出，长时间运行的工作可以暂停、干净恢复、事后逐步追溯。有了 Managed Agents，你可以定义一次 agent 与 environment，随工作负载增长在同一份配置上跑很多个 session。

![图：agent 配置与 environment 配对生成 session，session 持久化事件历史与沙箱状态](https://assets.claude.com/c06d2e0399c4172fcb6de31bd538749d03e6c68b.png)

## 在 Managed Agents 上为生产与规模构建

在 Applied AI，我们看到 agent 从原型走向生产，既发生在 Anthropic 内部，也发生在客户系统里，覆盖编程、财务、支持、法律等十几个领域。这让我们清楚看到演示与生产就绪 agent 的差别，以及团队常卡在哪里。

下面是我们看到的、在 Claude Managed Agents 这类托管服务上构建的最常见理由：

**1. 凭据留在沙箱之外。** 所有东西跑在一个容器里时，Claude 生成的代码紧挨着你的凭据，prompt injection 可以说服模型读取自己的环境变量把 token 泄出去。我们可以在同一容器里设置可靠护栏来防，但解耦架构给出一条更安全的路：让凭据彻底不进沙箱。MCP、CLI、GitHub 仓库这类工具用的 token 存在独立的 vault 里，由代理按需取用、按需解密。Managed Agents 提供开箱即用的 [Vaults](https://platform.claude.com/docs/en/managed-agents/vaults)，你不必自跑密钥库、不必每次调用传输 token、也不会弄丢某个 agent 在替哪位最终用户行事的记录。vault 凭据在存储前经 envelope encryption 保护，取回需要签名请求 token 做验证。

![图：凭据存放在沙箱之外的 vault，代理按需取用解密](https://assets.claude.com/46c77d9f7b059194123c719f3aee706e647dc4ed.png)

**2. 消除沙箱开销带来的更低延迟。** 延迟是很多企业团队挂在心上的指标，用户对等待 Claude 回应的感受最敏锐。没有 Managed Agents 架构时，每个 session 都得转起一个容器，哪怕这个 session 里 agent 只需要思考、从不动工具。这部分准备时间是浪费，用户把它感受为首次响应前的延迟。有了 Managed Agents，Claude 立即开始推理，environment 并行转起，从不动工具的 session 完全跳过容器。用户不必等容器启动就能看到第一个 token，environment 在 agent 需要执行时刚好备好。我们的测试里，首 token 耗时在中位场景（p50）降了约 60%，最慢场景（p95）降了超过 90%。

**3. 可靠、持久的 session，支撑 session 管理、可观察性与记忆。** Managed Agents 不用请求/响应思考，改用事件思考。session 是一条持续的事件流：每一次模型调用、工具调用与结果，都追加进一份住在 agent 进程之外的日志。这个架构下，agent 干活时事件流入，你能拿到实时更新，之后恢复任何 session 都不用管数据库或存档点。历史在交互之间保留，除非你删除 session；session 空闲时它的容器被 checkpoint，你能从暂停处干净接续。整段运行本身就是事件记录，可观察性与记忆随之而来：Claude Developer Console 提供 agent session 的原生可视化时间线视图，以及可深入检查任意记录的调试体验。Managed Agents 还带着 Memory 与 Dreaming 这类同样利用 session 持久性的特性。[Dreaming](https://platform.claude.com/docs/en/managed-agents/dreams) 是一个按计划运行的过程，检视你的 agent session 与记忆存储、提炼模式、整理记忆，让 agent 随时间改进。Dreaming 在 session 之间精炼记忆，靠读取持久化的 session 日志，从反复犯的错误与用户喜好中学习。

**4. Anthropic 托管或自托管云容器的灵活性。** 默认情况下，你可以把编排与工具执行都委托给 Anthropic 托管的云容器，托管与伸缩因此简单，通往生产的路径更快。因为 Managed Agents 里 brain 与 hands 是解耦的，hands 可以待在任何地方，包括你的 Virtual Private Cloud（VPC）内部。所以我们同样为想要掌控工具执行的团队提供 [self-hosted sandboxes](https://platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes)，让 agent 的代码、文件系统与网络出站永不离开你的环境。我们还提供 [MCP tunnels](https://platform.claude.com/docs/en/agents-and-tools/mcp-tunnels/overview)，让 Claude 连上运行在你私有网络内部的 Model Context Protocol（MCP）服务器。self-hosted sandboxes 管住 agent 的代码在哪里执行，MCP tunnels 管住 Anthropic 怎样触达你网络里的 MCP 服务器，你能精确控制什么留在你的边界之内。

![图：内建可观察性控制台记录每个事件的时间线](https://assets.claude.com/0231cd39f02075d990e6ab76b64cadef9fbdf7fe.png)

*图注：Claude Managed Agents 内建的可观察性控制台记录每一个事件，你可以拖动时间线、打开任意一步、读取它的原始 payload。*

这些特性之外还有更多能力：outcomes 让 agent 按 rubric 给自己的工作评分，还有 multiagent 编排、权限策略与 webhooks。在[这里](https://platform.claude.com/docs/en/managed-agents/overview)了解更多。

### 客户今天在 Managed Agents 上的构建

各行业的客户已经在用 Claude Managed Agents 把 agent 送进生产。几个例子：

- [Notion](https://claude.com/customers/notion) 在 Managed Agents 上运行它的 Custom Agents：团队直接从任务板把活派给 Claude，Claude 收集每个任务周边的文档、会议纪要与关联数据，完成的代码、幻灯片与站点回到工作区等待评审。几十个任务并行，他们的团队描述过一个早期原型把大约十二小时的工作压到二十分钟。
- [Rakuten](https://claude.com/customers/rakuten) 用 Managed Agents 在产品、销售、市场与财务条线交付专家 agent，每条线大约一周内上线。
- [Sentry](https://claude.com/customers/sentry) 把它的 Seer 调试 agent 与一个写补丁、开 PR 的 Claude agent 配对，由一名工程师用几周而非几个月建成。
- [Asana](https://claude.com/resources/articles/claude-managed-agents) 构建了在项目里领取任务的 AI Teammates，[Atlassian](https://claude.com/resources/articles/claude-managed-agents) 把开发者 agent 装进了 Jira 工作流。

## 开始使用 Claude Managed Agents

我们构建 Managed Agents 的目标是让你能尽量轻松地通过 Claude Code 与 [platform.claude.com](http://platform.claude.com) 的 Claude Developer Console 起 agent。比如控制台的 quickstart，可以从 agent 模板起步，或用自然语言描述一个 agent，几分钟后把它变成一个可以加固与部署的生产就绪 agent。

![图：agent quickstart 入口：从模板起步或用自然语言描述](https://assets.claude.com/6bc461ffa26f0c016da3ebc70ca51960b1b5f747.png)

*图注：platform.claude.com 的 agent quickstart：从模板起步，或描述你想构建的东西。*

![图：几步之后 agent 创建完成，session 已上线，控制台实时流出运行](https://assets.claude.com/7e0ae5e2a7b2c0fc5d1b44bcb9306e218172379b.png)

*图注：几步之后：agent 创建完成，environment 配置就绪，session 已上线。控制台实时流出运行过程。*

Claude Code 里默认提供 [/claude-api skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill)，给 Claude 一份在 Claude Managed Agents 上构建应用的详细且最新的参考资料。我们强烈建议用它获取搭建 Managed Agents 应用的最佳实践。运行 `/claude-api managed-agents-onboard` 开始一次引导式访谈，从零设置一个新的 Managed Agent。

![图：/claude-api skill 的 managed-agents-onboard 引导式访谈](https://assets.claude.com/7d358403b843547f162c5ca862a1bdad6d500fed.png)

## 托管 agent 构建的未来

随着团队分享他们在 Managed Agents 上的构建，我们看到他们过去花在生产基础设施上的时间，现在流进真正给 agent 带来差异的地方：管理 context，为用户定制体验。如今新模型发布时，你更新 agent 去用它，重跑 evals，发布改进，完全不必触碰底下的架构。

我们期待看到你构建的东西。

[开始使用](https://platform.claude.com/docs/en/managed-agents/overview) Claude Managed Agents。

本文由 Anthropic Applied AI 团队的 Members of Technical Staff Gagan Bhat 与 Isabella He 撰写。他们感谢 Hema Thanki、Jess Yan 与 Molly Vorwerck 的贡献。

> 包内互引：大脑与双手解耦、session 不等于上下文窗口、多大脑多双手的完整论证见 managed-agents.md（本篇是其接口面演进的下篇）；vault 凭据与沙箱隔离机制见 nvidia-agent-security.md。
