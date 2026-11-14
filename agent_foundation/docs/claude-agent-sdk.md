# 用 Claude Agent SDK 构建 agent（Building agents with the Claude Agent SDK）

- 原文：[Building agents with the Claude Agent SDK](https://claude.com/resources/articles/building-agents-with-the-claude-agent-sdk)
- 来源：Anthropic Engineering，作者 Thariq Shihipar
- 发布：2025-09-29
- 译文说明：全文翻译，术语保留英文原词；本文正文无插图；站内相对链接转为绝对 URL；代码与命令保留英文原样。

去年，我们与客户一起分享了[构建高效 agent](https://www.anthropic.com/engineering/building-effective-agents) 的经验。此后，我们发布了 [Claude Code](https://claude.com/product/claude-code)，一个最初为 Anthropic 内部开发者提效而构建的 agentic 编码工具。

过去几个月里，Claude Code 已经远超编码工具的范畴。在 Anthropic，我们把它用于深度研究、视频制作与笔记整理等无数非编码场景。事实上，它已经开始驱动我们几乎所有的主力 agent 循环。

换句话说，[驱动 Claude Code 的那套 agent harness](https://claude.com/resources/articles/harnessing-claudes-intelligence)（Claude Code SDK）也能驱动许多其他类型的 agent。为体现这一更广的愿景，我们把 Claude Code SDK 更名为 Claude Agent SDK。

在这篇文章里，我们会讲清为什么构建 Claude Agent SDK、如何用它构建你自己的 agent，并分享来自我们自己部署实践的最佳经验。

## 给 Claude 一台计算机

Claude Code 背后的[关键设计原则](https://www.youtube.com/watch?v=vLIDHi-1PVU)是：Claude 需要程序员每天使用的那些工具。它需要能在代码库里找到合适的文件、编写与编辑文件、对代码跑 lint、运行、调试、再编辑，有时还要迭代执行这些动作直到代码成功。

我们发现，让 Claude 访问用户的计算机（通过终端），它就具备了像程序员一样写代码所需的全部条件。

这也让 Claude Code 里的 Claude 在非编码任务上同样高效。给它运行 bash 命令、编辑文件、创建文件与搜索文件的工具后，Claude 能读 CSV 文件、搜索网络、构建可视化、解读指标，做各种数字工作——一句话，造出带一台计算机的通用 agent。Claude Agent SDK 背后的关键设计原则就是给你的 agent 一台计算机，让它们像人一样工作。

## 创造新类型的 agent

我们相信，给 Claude 一台计算机解锁了构建比以往更高效 agent 的能力。例如，用我们的 SDK，开发者可以构建：

- **金融 agent**：构建能理解你的投资组合与目标的 agent，通过访问外部 API、存储数据并运行代码做计算，帮你评估投资。
- **个人助理 agent**：构建能帮你订行程与管理日历的 agent，通过连接内部数据源并跨应用跟踪上下文，还能安排会议、整理简报等。
- **客户支持 agent**：构建能处理高模糊度用户请求（如客服工单）的 agent，通过收集与审查用户数据、连接外部 API、回复用户消息，必要时升级转给人工。
- **深度研究 agent**：构建能在大规模文档集合上做综合研究的 agent，通过搜索文件系统、从多来源分析综合信息、跨文件交叉核对数据并生成详细报告。

还有更多。核心在于，SDK 给你构建 agent 的原语，适用于你想自动化的任何工作流。

## 构建你的 agent 循环

在 Claude Code 里，Claude 通常运行在一个特定的反馈循环里：收集上下文 -> 采取行动 -> 验证工作 -> 重复。

这为思考其他 agent 及其应具备的能力提供了有用的框架。为说明这一点，我们用「在 Claude Agent SDK 里构建一个邮件 agent」的例子走一遍。

## 收集上下文

开发 agent 时，你要给它的不只是提示词：它需要能获取并更新自己的上下文。SDK 的这些能力可以帮上忙。

### Agentic search 与文件系统

文件系统代表着可以拉进模型上下文的信息。

当 Claude 遇到大文件（如日志或用户上传的文件）时，它会用 `grep`、`tail` 这类 bash 脚本决定以哪种方式把内容装进上下文。本质上，agent 的文件夹与文件结构本身就成了一种 [context engineering](http://anthropic.com/news/context-management)。

我们的邮件 agent 可以把历史会话存在一个叫 Conversations 的文件夹里。这样被问到相关内容时，它可以搜索这些历史作为自己的上下文。

### Semantic search

[Semantic search](https://www.anthropic.com/news/contextual-retrieval) 通常比 agentic search 快，但准确性更低、更难维护、透明度也更低。它需要把相关上下文做「chunking」、把这些块嵌入为向量，再通过查询向量来搜索概念。考虑到这些限制，我们建议从 agentic search 起步，只有在需要更快结果或更多变化时才加 semantic search。

### Subagents

Claude Agent SDK 默认支持 subagents。[Subagents](https://docs.claude.com/en/api/agent-sdk/subagents) 有两大用处。第一是并行化：可以同时运行多个 subagent 处理不同任务。第二是上下文管理：subagent 使用自己隔离的上下文窗口，只把相关信息发回编排者，而非全部上下文。这让它适合需要从大量信息里筛选、而其中大部分用不上的任务。

设计邮件 agent 时，可以给它「search subagent」能力。邮件 agent 可以并行运行多个搜索 subagent——各自对邮件历史跑不同查询——并让它们只返回相关摘录，而非完整邮件线程。

### Compaction

agent 长时间运行时，上下文维护变得关键。Claude Agent SDK 的 compact 功能在上下文接近上限时自动总结先前的消息，让 agent 不会耗尽上下文。它构建在 Claude Code 的 [compact 斜杠命令](https://docs.claude.com/en/docs/claude-code/sdk/sdk-slash-commands#%2Fcompact-compact-conversation-history)之上。

## 采取行动

收集完上下文后，你要给 agent 灵活的行动方式。

### 工具

[工具](https://www.anthropic.com/engineering/writing-tools-for-agents)是 agent 执行的基本构件。工具在 Claude 的上下文窗口里很显眼，是 Claude 决定如何完成任务时首先考虑的动作。这意味着设计工具时要自觉追求上下文效率。更多最佳实践见我们的博客文章 [Writing effective tools for agents – with agents](https://www.anthropic.com/engineering/writing-tools-for-agents)。

因此，你的工具应该是你想让 agent 采取的主要动作。在 Claude Agent SDK 里学习如何制作[自定义工具](https://docs.claude.com/en/api/agent-sdk/custom-tools)。

邮件 agent 可以定义 `fetchInbox`、`searchEmails` 这样的工具，作为 agent 最主要、最高频的动作。

### Bash 与脚本

Bash 作为通用工具很有用，让 agent 能用计算机做灵活的工作。

邮件 agent 场景里，用户可能把重要信息存在附件中。Claude 可以写代码下载 PDF、转成文本，再在其中检索有用信息。这一串动作由 agent 自己写脚本完成，中间的大量文本不必进入上下文。

### 代码生成

Claude Agent SDK 擅长代码生成，这有充分理由。代码精确、可组合、无限复用，是需要可靠执行复杂操作的 agent 的理想输出。

构建 agent 时想一想：哪些任务适合表达成代码？答案往往能解锁重要能力。

例如我们最近在 Claude.AI 上线的[文件创建](https://www.anthropic.com/news/create-files)功能完全依赖代码生成。Claude 写 Python 脚本来创建 Excel 表格、PowerPoint 演示与 Word 文档，保证一致的格式与复杂功能，这些用其他方式都难以做到。

邮件 agent 里，我们可能想让用户为收到的邮件创建规则。做法是写一段代码挂在该事件上运行，由代码判断新邮件是否命中规则、再触发对应动作。

### MCP

[Model Context Protocol](https://modelcontextprotocol.io/)（MCP）提供标准化的外部服务集成，自动处理认证与 API 调用。这意味着你可以把 agent 连到 Slack、GitHub、Google Drive 或 Asana，无需自己写集成代码或管理 OAuth 流程。

邮件 agent 里，我们可能想搜索 Slack 消息以理解团队上下文，或查 Asana 任务看是否已有人被指派处理客户请求。有 MCP 服务器，这些集成开箱即用——agent 直接调用 search_slack_messages 或 get_asana_tasks 这样的工具，其余交给 MCP。

不断增长的 [MCP 生态](https://github.com/modelcontextprotocol/servers)意味着你可以随预构建集成的出现快速为 agent 加新能力，把精力放在 agent 行为上。

## 验证工作

Claude Code SDK 以评估自己的工作来收尾 agent 循环。能检查并改进自身输出的 agent 从根本上更可靠——错误在累积之前被抓住，跑远了能自我纠正，越迭代越好。

关键是给 Claude 评估自己工作的具体方式。以下是我们发现有效的三种方法：

### 定义规则

最好的反馈形式是为输出定义清晰的规则，再解释哪些规则失败、为何失败。

[代码 lint](https://stackoverflow.com/questions/8503559/what-is-linting) 是极好的规则式反馈，反馈越深入越好。例如，生成 TypeScript 并 lint 通常优于生成纯 JavaScript，因为 TypeScript 提供多层额外反馈。

生成邮件时，你可以让 Claude 检查邮箱地址是否有效（无效则抛错），以及用户此前是否给对方发过邮件（发过则警告）。

### 视觉反馈

用 agent 完成视觉任务（如 UI 生成或测试）时，视觉反馈（截图或渲染图）很有用。例如发送 HTML 格式邮件前，可以对生成的邮件截图并回传给模型做视觉核对与迭代改进。模型随后检查视觉输出是否符合要求。

例如：

- 布局：元素位置是否正确？间距是否合适？
- 样式：颜色、字体与格式是否符合预期？
- 内容层次：信息是否按正确顺序呈现、重点是否恰当？
- 响应性：是否显得破旧或拥挤？（单张截图的视口信息有限）

用 Playwright 这样的 MCP 服务器，可以把这个视觉反馈循环自动化——截取渲染 HTML 的截图、捕获不同视口尺寸、甚至测试交互元素——全部在 agent 的工作流内完成。

### LLM as a judge

你也可以让另一个语言模型按模糊规则「评判」agent 的输出。这种方法通常不算特别稳健，延迟代价可能很重，但对性能提升值得成本的场景有帮助。

邮件 agent 可以让一个单独的 subagent 评判草稿的语气，看是否与用户以往的消息契合。

## 测试与改进你的 agent

走过几轮 agent 循环后，我们建议测试你的 agent，确认它为任务配备了合适装备。改进 agent 最好的方式是仔细看它的输出，特别是失败的场景，并把自己放进它的处境：它有完成工作的[合适工具](https://www.anthropic.com/engineering/writing-tools-for-agents)吗？

评估 agent 是否装备妥当时，还可以问这些问题：

- agent 误解任务时，可能缺关键信息。能否调整搜索 API 的结构，让它更容易找到需要知道的东西？
- agent 反复在同一任务上失败时，能否在工具调用里加一条正式规则来识别并修复这个失败？
- agent 修不了自己的错误时，能否给它更有用或更有创意的工具，换个方式解决问题？
- agent 性能随功能增加而波动时，基于客户使用建一个有代表性的测试集做程序化评估（evals）。

## 开始使用

Claude Agent SDK 通过给 Claude 一台计算机（写文件、跑命令、迭代工作）让构建自主 agent 更容易。

记住 agent 循环（收集上下文、采取行动、验证工作），你可以构建易于部署与迭代的可靠 agent。

今天就可以[开始使用](https://docs.claude.com/en/api/agent-sdk/overview) Claude Agent SDK。已经在 SDK 上开发的，建议按[这份指南](https://docs.claude.com/en/docs/claude-code/sdk/migration-guide)迁移到最新版本。

## 致谢

由 Thariq Shihipar 撰写，Molly Vorwerck、Suzanne Wang、Alex Isken、Cat Wu、Keir Bradwell、Alexander Bricken 与 Ashwin Bhat 提供笔记与编辑。

> 包内互引：agent 与 workflow 的分界、五种基础模式见 building-effective-agents.md（本篇 agent 循环的奠基文）；OpenAI 侧 SDK 与 Responses API 的分工对照见 openai-agents-sdk.md；上下文收集与 compaction 的原则见 context-engineering.md；长时运行的 harness 形态见 harnesses-long-running.md。
