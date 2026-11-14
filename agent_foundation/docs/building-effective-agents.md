# 构建高效 agent（Building effective agents）

- 原文：[Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- 来源：Anthropic Engineering，作者 Erik S. 与 Barry Zhang
- 发布：2024-12-19
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图，地址为原文 CDN 直链。

> 注：本文描述的工具生态自 2024 年 12 月以来已有很大变化。当前做法见 [how we built Claude Managed Agents](https://www.anthropic.com/engineering/managed-agents) 与 [Managed Agents documentation](https://platform.claude.com/docs/en/managed-agents/overview)。

过去一年，我们与数十个跨行业团队合作构建大语言模型（LLM）agent。一个稳定的观察是：最成功的实现没有依赖复杂框架或专用库，它们用简单、可组合的模式搭建而成。

本文分享我们服务客户与自建 agent 过程中积累的经验，并为开发者给出构建高效 agent 的实用建议。

## 什么是 agent

「agent」这个词有多种定义。一些客户把 agent 理解为长期独立运行的全自主系统，用各种工具完成复杂任务；另一些客户用它指代按预定义工作流程执行的规范化实现。在 Anthropic，我们把所有这些形态统称为 agentic system，并在架构上做一个重要区分：workflow 与 agent：

- workflow：LLM 与工具经由预定义代码路径编排的系统。
- agent：LLM 动态指挥自身流程与工具使用的系统，对任务的完成方式保有控制权。

下文会详细展开这两类系统。附录 1（「agent 的实践应用」）描述两个客户从中收获巨大价值的领域。

## 何时该用 agent（以及何时不该用）

用 LLM 构建应用时，我们建议先寻找最简单的可行方案，只在确有需要时再增加复杂度。这可能意味着完全不必构建 agentic system。这类系统常用延迟与成本换取更好的任务表现，你需要判断这种交换何时划算。

确需更高复杂度时，workflow 为定义清晰的任务提供可预测性与一致性；当需要大规模的灵活性与模型驱动的决策时，agent 是更合适的选择。但对多数应用而言，用检索与上下文内示例优化单次 LLM 调用通常已经足够。

## 何时以及如何使用框架

许多框架能让 agentic system 更容易实现，包括：

- [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview)；
- AWS 的 [Strands Agents SDK](https://strandsagents.com/latest/)；
- [Rivet](https://rivet.ironcladapp.com/)，一个拖拽式的图形化 LLM 工作流构建器；
- [Vellum](https://www.vellum.ai/)，另一个构建与测试复杂工作流的图形化工具。

这些框架简化了调用 LLM、定义与解析工具、串联调用等标准底层工作，让起步变得容易。不过，它们常常引入额外的抽象层，遮蔽底层的提示词与响应，增加调试难度；它们也容易诱导你在简单方案已经够用时追加复杂度。

我们建议开发者从直接使用 LLM API 开始：许多模式用几行代码即可实现。如果确实要用框架，务必理解其底层代码。对框架内部实现的错误假设，是客户报错的常见来源。

部分示例实现见我们的 [cookbook](https://platform.claude.com/cookbook/patterns-agents-basic-workflows)。

## 基础构件、workflow 与 agent

本节探讨我们在生产环境中见过的 agentic system 常见模式。从基础构件（增强版 LLM）开始，逐步增加复杂度，从简单的组合式工作流一直到自主 agent。

### 基础构件：增强版 LLM

agentic system 的基本构件是经过检索、工具、记忆等增强的 LLM。当前模型已经能主动使用这些能力：自行生成搜索查询、挑选合适的工具、决定保留哪些信息。

![增强版 LLM 示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/d3083d3f40bb2b6f477901cc9a240738d3dd1371-2401x1000.png)

实现上建议聚焦两点：把这些能力按具体场景做定制；确保它们为 LLM 提供简单、文档完善的接口。实现这些增强的方式很多，其中之一是新发布的 [Model Context Protocol](https://www.anthropic.com/news/model-context-protocol)，开发者用一个简单的 [client 实现](https://modelcontextprotocol.io/tutorials/building-a-client#building-mcp-clients)即可接入不断壮大的第三方工具生态。

本文余下部分假设每次 LLM 调用都能使用这些增强能力。

### 工作流：提示词链（prompt chaining）

提示词链把任务分解成一系列步骤，每次 LLM 调用处理上一步的输出。可以在任意中间步骤加程序化检查（见下图中的 gate），确认流程仍在正轨上。

![提示词链示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/7418719e3dab222dccb379b8879e1dc08ad34c78-2401x1000.png)

适用场景：任务能干净地分解成固定子任务时最理想。核心目标是用延迟换更高的准确率，方式是让每次 LLM 调用都承担更简单的任务。

提示词链有用的例子：

- 先生成营销文案，再翻译成另一种语言。
- 先写文档大纲，检查大纲是否满足给定标准，再依据大纲写出文档。

### 工作流：路由（routing）

路由对输入做分类，把它送往专门化的后续任务。这种工作流支持关注点分离，可以构建更专门化的提示词。缺少这一层时，针对某类输入的优化会损害其他输入上的表现。

![路由示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/5c0c0e9fe4def0b584c04d37849941da55e5e71c-2401x1000.png)

适用场景：任务存在界限分明的类别、分开处理效果更好，且分类本身能被准确完成（无论用 LLM 还是更传统的分类模型或算法）时，路由表现良好。

路由有用的例子：

- 把不同类型的客服请求（一般咨询、退款申请、技术支持）送往不同的下游流程、提示词与工具。
- 简单常见问题送往更小、更具成本效率的模型（如 Claude Haiku 4.5），困难罕见问题送往能力更强的模型（如 Claude Sonnet 4.5），以取得最佳效果。

### 工作流：并行化（parallelization）

LLM 有时可以同时处理一个任务，再由程序汇总输出。并行化工作流有两种关键形态：

- 分段（sectioning）：把任务分成可并行运行的独立子任务。
- 投票（voting）：同一任务运行多次，得到多样化输出。

![并行化示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png)

适用场景：子任务能并行提速，或需要多视角、多次尝试以获得更高置信度的结果时有效。对包含多个关注点的复杂任务，让每个关注点由单独的 LLM 调用处理、各自集中注意力，通常表现更好。

并行化有用的例子：

- 分段：实现防护机制时，一个模型实例处理用户查询，另一个筛查不当内容或请求，这比让同一次 LLM 调用同时负责防护与核心回答效果更好；自动化评估 LLM 表现时，每次调用评估模型在给定提示词上的一个不同维度。
- 投票：审查代码漏洞时，多个不同提示词各自审查，发现问题就标记；判断内容是否恰当时，多个提示词评估不同侧面，或设置不同投票阈值，以平衡误报与漏报。

### 工作流：编排者-工作者（orchestrator-workers）

编排者-工作者工作流里，中央 LLM 动态分解任务，委派给工作者 LLM，再汇总它们的结果。

![编排者-工作者示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/8985fc683fae4780fb34eab1365ab78c7e51bc8e-2401x1000.png)

适用场景：适合无法预测所需子任务的复杂工作（例如编码任务里，要改多少文件、每个文件怎么改，往往取决于具体任务）。它与并行化在结构形态上相似，关键差异在于灵活性：子任务没有预先定义，由编排者按具体输入决定。

编排者-工作者有用的例子：

- 每次都对多个文件做复杂修改的编码产品。
- 需要从多个来源收集并分析信息、寻找潜在相关内容的搜索任务。

### 工作流：评估者-优化者（evaluator-optimizer）

评估者-优化者工作流里，一次 LLM 调用生成回答，另一个在循环中提供评估与反馈。

![评估者-优化者示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png)

适用场景：评估标准清晰、迭代打磨能带来可度量的价值时特别有效。两个适配信号：其一，人类把反馈讲清楚时，LLM 的回答有可见的改进；其二，LLM 自己能给出这类反馈。这类似于人类作者打磨一篇成熟文稿的迭代写作过程。

评估者-优化者有用的例子：

- 文学翻译：译者 LLM 初译可能漏掉细微之处，评估者 LLM 能给出有用的批评。
- 复杂搜索任务：需要多轮搜索与分析才能收集齐全面信息，由评估者决定是否还要继续搜。

### Agent

随着 LLM 在关键能力上成熟（理解复杂输入、进行推理与规划、可靠使用工具、从错误中恢复），agent 正在生产环境中兴起。agent 的工作从人类用户的指令或交互式讨论开始。任务明确后，agent 规划并独立运行，必要时回到人类这里获取更多信息或判断。执行过程中，agent 必须在每一步从环境拿到真实依据（ground truth，如工具调用结果或代码执行结果）来评估自身进展。agent 可以在检查点或遇到阻塞时暂停等待人类反馈。任务通常在完成时结束，也常设置停止条件（如最大迭代次数）以保持可控。

agent 能处理复杂任务，实现却往往简单直白：它们通常只是 LLM 在循环里基于环境反馈使用工具。因此，清晰、周到地设计工具集及其文档至关重要。工具开发的最佳实践见附录 2（「为工具做提示词工程」）。

![Agent 示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/58d9f10c985c4eb5d53798dea315f7bb5ab6249e-2401x1000.png)

何时使用 agent：适合开放性问题，即步数难以预测、无法把固定路径预先写进代码的问题。LLM 可能连续运行很多轮，你必须对它的决策有一定信任。agent 的自主性使它很适合在受信任环境中规模化执行任务。

自主性同时意味着更高成本与错误累积的可能。我们建议在沙箱环境里充分测试，并配置适当的防护机制。

agent 有用的例子（来自我们自己的实现）：

- 解决 [SWE-bench 任务](https://www.anthropic.com/research/swe-bench-sonnet)的编码 agent，根据任务描述修改多个文件；
- 我们的[「computer use」参考实现](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo)，Claude 通过操作电脑完成任务。

![computer use 示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/4b9a1f4eb63d5962a6e1746ac26bbc857cf3474f-2400x1666.png)

## 组合与定制这些模式

这些构件没有强制性。它们是常见模式，开发者可以塑造、组合以适配不同场景。与所有 LLM 功能一样，成功关键是度量表现、迭代实现。再强调一次：只有当复杂度能被证明改善结果时，才考虑增加它。

## 总结

LLM 领域的成功在于为自己的需求构建正确的系统，与系统的复杂精巧程度无关。从简单提示词开始，用全面的评估优化它们，只有简单方案不够用时才引入多步 agentic system。

实现 agent 时，我们遵循三条核心原则：

1. 保持 agent 设计的简单性。
2. 优先保证透明性：显式展示 agent 的规划步骤。
3. 通过完善的工具文档与测试，精心打造 agent 与计算机之间的接口（ACI）。

框架能帮你快速起步，但走向生产时，不要犹豫削减抽象层、用基础组件构建。遵循这些原则，你能造出既强大又可靠、可维护、被用户信任的 agent。

## 附录 1：agent 的实践应用

与客户的合作揭示了两个特别有前景的 agent 应用，它们展示了上述模式的实用价值。两个应用都说明：当任务同时需要对话与行动、有清晰的成功标准、能形成反馈闭环、并纳入有意义的人类监督时，agent 创造的价值最大。

### A. 客户支持

客户支持把熟悉的聊天界面与工具集成带来的增强能力结合在一起，天然适合更开放的 agent，原因如下：

- 支持交互天然遵循对话流程，同时需要访问外部信息与执行外部动作；
- 可以集成工具拉取客户数据、订单历史与知识库文章；
- 退款、更新工单等动作可以程序化处理；
- 成功与否可以通过用户定义的「问题解决」清晰度量。

一些公司用按效果计价的模式证明了这条路可行：只有成功解决才收费，这显示了对自家 agent 有效性的信心。

### B. 编码 agent

软件开发领域展现了 LLM 功能的巨大潜力，能力已从代码补全进化到自主解决问题。agent 在这里特别有效，原因如下：

- 代码方案可以通过自动化测试验证；
- agent 能把测试结果当作反馈，迭代改进方案；
- 问题空间定义清晰、结构良好；
- 输出质量可以客观度量。

在我们自己的实现里，agent 现在仅凭 pull request 描述就能解决 [SWE-bench Verified](https://www.anthropic.com/research/swe-bench-sonnet) 基准里的真实 GitHub issue。自动化测试帮助验证功能，人类评审仍然关键，它确保方案与更广泛的系统需求一致。

## 附录 2：为工具做提示词工程

无论构建哪种 agentic system，工具大概率是 agent 的重要组成部分。[工具](https://www.anthropic.com/news/tool-use-ga)通过在 API 中指定确切的结构与定义，让 Claude 与外部服务及 API 交互。当 Claude 打算调用某个工具时，它的回答会在 API 响应里包含一个 [tool use block](https://docs.anthropic.com/en/docs/build-with-claude/tool-use#example-api-response-with-a-tool-use-content-block)。工具定义与规格值得投入与整体提示词同等程度的提示词工程精力。本附录简述如何为工具做提示词工程。

指定同一动作往往有多种方式。例如，描述一次文件修改可以写 diff，也可以整文件重写；结构化输出的代码可以放在 markdown 里，也可以放在 JSON 里。在软件工程里，这类差异只是表现形式，可以无损互转。但对 LLM 而言，有些格式写起来困难得多：写 diff 要求在写新代码之前就先知道 chunk header 里改动的行数；把代码放进 JSON（对比 markdown）要对换行与引号做额外转义。

我们对工具格式的建议：

- 给模型留足 token 让它「思考」，避免它在写到一半时无路可走。
- 让格式贴近模型在互联网自然文本里见过的形态。
- 确认格式没有额外负担，比如要精确数清几千行代码的行数，或对写出的代码做字符串转义。

一个经验法则：想想人机界面（HCI）上投入了多少精力，就计划在为 agent 设计的计算机接口（ACI）上投入同等精力。具体做法：

- 站在模型的角度想：只看描述与参数，这个工具的用法一目了然吗？如果你自己都要仔细琢磨，模型大概率也一样。好的工具定义常包含用法示例、边界情况、输入格式要求、与其他工具的清晰界限。
- 怎样调整参数名或描述能让用法更显眼？把这当成给团队里新来的初级开发者写一份出色的 docstring。工具数量多且彼此相似时尤其重要。
- 测试模型怎么使用你的工具：在 [workbench](https://console.anthropic.com/workbench) 里跑大量示例输入，观察模型犯什么错，然后迭代。
- 给工具做防呆设计（[Poka-yoke](https://en.wikipedia.org/wiki/Poka-yoke)）：调整参数形式，让错误更难发生。

构建 [SWE-bench](https://www.anthropic.com/research/swe-bench-sonnet) agent 时，我们在优化工具上花的时间实际超过了整体提示词。例如，我们发现 agent 离开根目录后，模型在使用相对路径的工具上会出错。修复方式是把工具改成一律要求绝对路径，之后模型的使用再无差错。

## 作者与致谢

本文由 Erik S. 与 Barry Zhang 撰写。内容来自我们在 Anthropic 构建 agent 的经验，以及客户分享的宝贵洞见，我们对此深表感谢。
