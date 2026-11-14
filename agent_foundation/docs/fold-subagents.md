# 何时把 subagent 折回主 agent 循环（Building agents: When to fold subagents into your main agent loop）
- 原文：[Building agents: When to fold subagents into your main agent loop](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)
- 来源：Anthropic Applied AI，作者 Diane Sarkis
- 发布：2026-10-22
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 assets.claude.com 直链并配中文短描述；命令与工具名保留英文原样。

*如果你在 Claude Platform 上构建的 agent 里包含多个 subagent，可以用我们的 [migration kit](https://github.com/anthropics/single-agent-loop-kit) 检查哪些适合折回主 agent 循环。它运行一套引导式工作流，识别你的模式、评估替代方案、验证最优方案，还带一个可以先在模拟系统上试运行的演示。*

Subagent 是有独立上下文窗口、独立工具与独立指令、[由协调者编排](https://claude.com/resources/articles/multi-agent-coordination-patterns)的 agent，是 agent 设计的核心组件。它们在验证、并行工作、模块化权限方面很有效。我们用 Claude Platform 构建的很多自用 agent 都在使用，例如[多 agent 研究系统](https://www.anthropic.com/engineering/multi-agent-research-system)。

但近期 Applied AI 团队发现一种模式：把路由器、规划器与领域 subagent 折回主 agent 循环，让一批企业 agent 部署受益。在[跨多个企业部署的对比](https://claude.com/resources/articles/the-anatomy-of-effective-commerce-agents)里，[带 skills 的单个 agent](https://claude.com/resources/articles/building-agents-with-skills-equipping-agents-for-specialized-work) 在质量上经常同时胜过「一个 prompt 包办一切」的设计与 subagent 设计，且单任务成本与延迟往往更低。

例如，一家公司发现其面向客户的 agent 里有十来个专家 subagent，让品牌一致的体验难以维持，还增加了拖累用户体验的延迟。

我们也经常看到提议的 agent 设计遵循一条熟悉的演进路径：意图分类器、固定多步推理流水线、用户分群、各自独立的推荐分支、顶层再加一个多 agent 编排者。

这些场景下我们给出的反馈往往是：这套结构里的大部分工作是在替模型做模型已经不需要别人替它做的事，一个清晰的 system prompt、四五个轻量数据工具、加上严格的输出护栏，就能覆盖大多数用例。

![多 agent 设计：编排者协调多个专家 subagent](https://assets.claude.com/a7cb2cf08bfcef461166310c0c55f28b72c33b0d.gif)

先说清楚，subagent 仍然有自己的位置，包括在研究前沿。以下情况该用：

- 单个 agent 循环因上下文膨胀出现可量测的性能下滑
- 多个任务需要并行处理，各自用全新上下文窗口，任务完成即可丢弃
- 单个 agent 难以选对工具，或 system prompt 里的指令互相冲突

但太常见的情况是：企业给每个团队或每种问题类型各配一个 subagent，agent 架构成了组织架构图的复制品（Conway 定律在起作用）。

本文讲的是何时应考虑把 subagent 折回主 agent 循环，以及我们在大型组织里构建 agent 学到的最佳实践。

## 大型组织构建 agent 的失败模式

公司常想构建一个把多个产品与能力聚合进单一客户界面的 agent。

典型情况是每种能力由一个独立团队负责，于是公司先让各团队自建 agent，再由中央平台团队在顶层搭编排者。形态可以是编排者-subagent，或单个 agent 把特定 agent 暴露为 MCP 工具。

这看起来最简单，却立即引入几类复杂性：

- **上下文管理**：需要决定 agent 之间交换什么上下文，来回传递中经常丢失细节。
- **Subagent 蔓延**：每个团队都发布自己的 subagent，公司最后有几百个互相重叠的 subagent，没有强制标准，没有明确主人。
- **Frankenprompt**：每个团队往 system prompt 里加一句话，结果是规则互相冲突、口吻不一致。
- **未审查的局部化 eval**：人人加自己的 eval，且过度优化自己的子任务。整套 eval 没人拥有没人维护，管理层基于被稀释的局部分数做决策。
- **延迟**：多 agent 架构的复杂性增加延迟。一位客户把多 agent harness 与单 agent 循环对比评估，后者运行时间约快一倍。

## 使用带渐进披露的 agent 循环

上文描述的编排者-subagent 设计对协调跨团队构建的专家而言是合理路线，但更有效的做法常常是**通过 skills 渐进披露上下文**与**通过 tool search 渐进披露工具**。也就是说，agent 看到的是 skills 与工具的简短描述，完整内容只在需要时才加载。

这个做法成立有三个理由：

- **共享上下文产出更好的回答**：对运行时间较长的 agent，我们希望多个任务的上下文都放在主上下文窗口里。见过前面每步结果的 agent 能把它们关联起来，产出比 subagent 回传的一组摘要更丰富、洞见更好的输出。这也意味着[更少的上下文窗口与更少的有损交接](https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them)。
- **渐进披露防止上下文膨胀**：这项技术让团队可以构建能完成多种任务的单 agent，无需把全部上下文一次性塞进一个长 system prompt。这消除了团队此前把工作分散到 subagent 的主要理由。实际上我们把 Claude Code 面向更强模型的 [system prompt 削减了 80% 以上](https://claude.dev/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models/)，其中就包含渐进披露 skills 与工具带来的削减。
- **模型能力更强**：从 Opus 4.5 起，模型在单循环里能管理的东西远超多数团队的预期。Opus 5.5 与 Fable 5.1 无法关闭 thinking，近期模型越来越多地边做边叙述进展、边检查自己的工作，这让一些 harness 元素变得多余。每个新模型都让你把更多决策从 harness 移进模型本身。更简单的循环也更容易迁移到下一个模型；在我们协助客户的迁移里，僵化的多 agent 结构经常正是阻碍新模型承担更多工作的东西。

单 agent 循环设计需要纪律：精心管理的 system prompt、在正确时机触发的 skill 与工具描述、对上下文窗口、记忆与笔记的刻意管理。后文各节深入讨论迁移与设计考量。

一个中央团队应当拥有端到端质量与 system prompt 的所有权，在每个新工具与 eval 发布前审查。保持这个中央团队精小，能让迭代更快，也降低大型组织里的协调成本。

如果走多 agent 路线，从最简单的可行模式开始（generator-verifier、orchestrator-subagent 或其他）。有效划分边界的方法是按上下文划分：给每个 subagent 一块对系统其余部分依赖很少的工作，让它回传一个紧凑结果（好的候选是独立的研究路径、接口干净的独立组件、黑盒验证）。按问题类型切分 agent 时，它们会玩起「传话游戏」，信息来回传递，每次交接都损失保真度。

![按问题类型切分 agent 导致传话游戏](https://assets.claude.com/cd4b9c4417d5ba31776e8aa79e204966c08c6a43.png)

## 如何把 subagent 折回主 agent 循环

很多团队已在生产环境里有编排者与一组专家 agent。以下是我们建议逐步趋近的单循环设计：

- 一个模型与一个上下文窗口，跑开放式工具循环，限额（轮次与成本预算、写入门禁）由 harness 设定。
- 每轮模型发出一批工具调用。harness 并行执行并把原始结果返回给同一模型，由它决定下一步：再发一批、向用户提问、或给出答案。
- 模型给出答案或触达[预算](https://platform.claude.com/docs/en/build-with-claude/task-budgets)时循环停止。答案之后可选地跑一个目标或验证检查。
- 模型在第一轮把计划写进上下文，随结果到来不断修订。这是与编排者加专家 agent 结构的主要差异：写计划的模型同时是执行计划的模型，所以它可以在执行中途改变计划。
- 上下文仍然会被加载，但由 agent 自己管理：从规则目录里改写计划的代码步骤不再需要，因为模型自己决定每一步；顺序与领域流程移入 skills；硬性限制（校验、审批门禁）与会话中途出现的其他需求（如记忆查询）移入工具；代码仍可用来加载便宜且几乎总是相关的东西（如实体消解步骤），以及处理循环调用的工具内部的机械部分（载荷构造、流解析、恢复澄清）。

单循环设计也有助于许多团队追求的终态（一个理解用户高层目标并代表用户行动的 agent），因为它把 agent 学到的一切都留在同一上下文里。

下面这些建议讲的是团队如何分阶段从多 agent 系统走到单 agent 循环，以及多个团队如何在此过程中持续给这个 agent 做贡献。

### 任务完成度 eval

第一步是建一个能帮你判断是否该把某个 subagent 折回主循环的 eval 集。我们见过有效的结构是：一个由中央团队拥有的共享端到端集合，加上每个 skill 附带的小 eval 集（由拥有该 skill 的团队随 skill 一起发布）。哪怕 10 个黄金样例就足够起步。

按评分量规给 agent 最终消息打分是跟踪回答质量的好起点。还有编排者的时候，还应跟踪路由准确率（它选对 subagent 了吗）。subagent 折回后，改为检查 agent 是否加载了正确的 skill 或调用了正确的工具。随时间推移向任务完成度 eval 努力，因为比较架构时这一项最重要。

在内部系统难以重放、用户互动难以模拟的环境里，这会很难。我们内部有效的一个做法是给重要事件记录时间戳，之后可以重放它们作为有针对性的 eval。

### 逐步减少 subagent

向单 agent 循环演进涉及把 subagent 折回工具与 skills。做法可以是合并领域 subagent、把它们当工具调用、或用 skills 与工具替换。

![把 subagent 逐步折回主循环的过程](https://assets.claude.com/ed6bd97496ffdab88763806d9e14f1ec61ed9255.gif)

### 合并领域 agent

第一次合并前先建一个小型端到端 eval。然后**从使用最多的 subagent 开始，按共享上下文逐步折回**。

[合并](https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them)那些输出互相衔接、触碰同一份数据、或经常被连续调用的专家。例如，生产流量里相当比例是一个专家紧接第二个专家，那这就是紧耦合对，是合并成一个领域 agent 的候选。

### 把 subagent 当作工具调用

当上述三个条件之一成立而你保留某个 subagent 时，让主 agent 把 subagent 当工具调用往往有效，这样它能继续与用户保持对话。

我们只在 subagent 需要直接与用户交谈时才推荐完全交接（subagent 接管对话）。其余一切都可以是主循环里的 skill 加工具。

这让你可以为 subagent 定义共享响应 schema、让主 agent 对照真实数据核实结论、裁剪进入最终综合步骤的输入。这是好的第一步，因为不需要重写 subagent。它还能在决定把任何 subagent 折回主 agent 之前，给你任务完成度 eval 上的基线。

不过有些失败模式仍然存在：

- 每个专家有自己的 prompt、上下文、归属团队与 eval
- 每次调用仍回传有损摘要
- 每次调用都是嵌套模型循环，增加延迟

### 通过 skills 与工具把 subagent 折回主 agent

一次折回一个：把每个 subagent 的 prompt 转成 skill，API 调用转成 MCP 工具。对比有该 subagent 与没有时的 eval 表现，再决定保留哪个。

对比时不要只看总分，要看哪些任务发生了翻转。我们在一个示例客服 agent 上测试时，把一个 subagent 折进另一个降低了延迟，却也弄坏了一个此前一直通过的流程：主 agent 握着订单查询工具自己作答，没有向物流专家询问送达日期。

每次改动前，确认你的 eval 覆盖了生产环境中一起运行的每条 agent 链与每条 agent 不能违反的规则，且每个任务跑多次——这类破坏在两次运行里只出现过一次。

## 多个团队如何共同贡献给单个 agent

领域推理可以从知识库、skills 与 MCP 工具获取。各团队可以把所有权从 agent 转向 skills 与工具，一个小型中央团队保留 system prompt 与端到端质量的所有权，包括在发布前审查新的 skills、工具与 eval。

### MCP 工具

agent 需要采取行动、从系统读取实时数据、或返回固定形态结果时，工具是正确选择。迁移期间也可以用工具继续调用 subagent。我们推荐按用户意图分组工具（并非每个 API 各一个工具），因为 system prompt 里的工具定义一旦超过 30-50 个，工具选择就会开始劣化。

用带延迟加载的 [tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)，限制硬性前置条件，把必需的前置条件移进工具。例如 Y 需要 X 的输出，Y 的工具自己检查这一点并返回一条模型可执行的指令。按用户的权限同理：每个工具检查调用用户能看到或能做什么，返回一段模型能读懂的明确拒绝，这样一个循环就能服务不同权限的用户，无需每个权限级别一个单独 agent。

### Skills

agent 需要知道一个团队怎么做事时——比如专家 subagent 的 prompt 里承载的步骤、规则与判断——skill 是正确选择。

我们让 skill 库增长的做法是把维护工作交还给写 skill 的人。Claude 可以承担重活：有些 skill 能构建、测试、修剪其他 skill。

为防止 skill 蔓延，可以让每个团队的 DRI 拥有自己的 skills，确保它们做工良好、彼此独立、随附合适的 eval。

- **/skill-creator** 用于编写从良好形态起步的新 skill，以及审计现有 skill，修剪、去重、重构它们。
- **/skill-doctor** 用于查看库里每个 skill 的成本与实际使用频率，删掉无用内容。

### 知识库

agent 只在部分时间需要的参考材料，知识库是正确选择。事实与参考材料（政策、指标定义、产品规格）可以放在模型调用的搜索或查询工具后面，或作为参考文件随 skill 一起发布。避免[用代码检索这些上下文再粘贴进 prompt](https://claude.com/resources/articles/seeing-like-an-agent)。

## 加速这项工作的工具

我们最近[发布](https://code.claude.com/docs/en/commands)了一组 Claude API skills，能帮上上述大部分工作。我们的 [migration kit](https://github.com/anthropics/single-agent-loop-kit) 把这些 skills 串成一条引导式工作流，用于评估多 agent 系统并迁移到单 agent 循环，附带一个可以先试再真跑的演示：

- **/claude-api build-eval**：帮中央团队创建首个端到端集合，或帮各团队随 skill 发布小 eval。
- **/claude-api prompt-audit**：能标记你的 prompt、skill 与工具描述里为旧模型写的指令，并以 diff 形式提出修复。可以在 system prompt 上跑，找出那些为更早的模型添加、如今拖慢或僵化 agent 的规则。各团队的 DRI 也可以在自己的 skills 与工具描述上跑。
- **/claude-api hillclimb**：针对既有 eval 迭代改进应用。可用于「折回 vs 保留」对比（把一个 subagent 折成 skill 加工具后，让它迭代 skill 与工具描述，看折回版本是否追平或胜过 subagent），也可用于你的 system prompt。
- **/claude-api cost-optimize**：分析你的调用都去哪了，并逐项提议省钱选项，如 prompt caching、裁剪多余输入输出 token、effort 与模型选择。可以帮助在给定设计上把成本与延迟降下来。

随着模型演进，我们对如何用好它们的理解与最佳实践指引也在演进。这让任何一种具体架构都不如其背后的原则重要：量测，一次改一件事，留下经得起验证的部分。

这就是其中一例。随着模型能力增强、agent 运行时间变长，你的 subagent 里会有更多可以变成 skills 与工具。不必一步到位：建一个小型端到端 eval，折回一个 subagent，只有折回版本得分更差时才保留它为 subagent，然后重复这个循环。
