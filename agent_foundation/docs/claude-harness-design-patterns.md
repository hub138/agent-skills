# Claude 的 harness 设计三模式（Agent harness design: 3 patterns for harnessing Claude's intelligence）

- 原文：[Agent harness design: 3 patterns for harnessing Claude's intelligence](https://claude.com/resources/articles/harnessing-claudes-intelligence)
- 来源：Anthropic（claude.com Blog），作者 Lance Martin（Claude Platform 团队 member of technical staff），致谢 Thariq Shihipar、Barry Zhang、Mike Lambert、David Hershey、Daliang Li
- 发布：2026-04-02
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 assets.claude.com 绝对直链并配中文短描述；基准数字与两个 memory folder 代码片段逐行忠实保留。Programmatic tool calling 的机制详解见[进阶工具使用](advanced-tool-use.md)，skills 渐进披露机制见[用 Agent Skills 把 agent 装备进真实世界](agent-skills.md)与[何时把 subagent 折回主 agent 循环](fold-subagents.md)，compaction 作为上下文管理手段见[面向 AI agent 的高效上下文工程](context-engineering.md)，context anxiety 案例见[长时运行应用开发的 harness 设计](harness-design-apps.md)。本篇独有增量在三模式框架本身、编排决策从 harness 移交 model 的论证、compaction 与 subagent 的跨模型能力对比数字、cache 命中五原则表、declarative tools 三用途与 auto-mode 安全判定。

Anthropic 联合创始人之一 Chris Olah [说过](https://darioamodei.com/post/the-urgency-of-interpretability)，Claude 这样的生成式 AI 系统与其说是构建出来的，不如说是生长出来的。研究者设定引导生长的条件，但最终涌现的确切结构与能力并不总是可以预测。

这给用 Claude 构建产品带来一个挑战：[agent harness 会把假设编码进去](https://www.anthropic.com/engineering/harness-design-long-running-apps)——假设 Claude 自己做不了什么，而随着 Claude 能力增强，这些假设会过时。

agent harness 是围绕 model 的软件脚手架：循环、工具、上下文管理与安全护栏，它们把原始智能变成一个能干活的 agent。[agent harness 设计](https://claude.com/resources/articles/harnessing-claudes-intelligence)就是决定哪些东西属于这层脚手架，以及随着模型进步，哪些东西可以拿走的实践。

本文分享三个模式，构建应用时使用它们，可以在跟上 Claude 不断演进的智能的同时平衡延迟与成本：用 Claude 已经熟悉的东西、不断追问可以停止做什么、在 harness 里谨慎设定边界。

## 模式一：依靠 model，不依靠 harness——用 Claude 已经熟悉的东西

我们建议用 Claude 理解透彻的工具来构建应用。

2024 年底，Claude 3.5 Sonnet 只凭一个 [bash 工具](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool)和一个[文本编辑器工具](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool)（查看、创建与编辑文件），在 SWE-bench Verified 上拿到 49%——当时的[最优成绩](https://www.anthropic.com/engineering/swe-bench-sonnet)。Claude Code 就建立在这两个工具之上。[bash](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool) 当初的定位并非构建 agent，它是 Claude 会用、而且随着时间越用越好的工具。

![SWE-bench Verified 基准上各代 Claude 模型的得分曲线，展示模型能力的演进。](https://assets.claude.com/9ff0af45fd385dc84e3043c0646dd4b98ceba256.png)

*图注：SWE-bench Verified 基准上各代 Claude 模型的得分，突显其演进。*

我们见过 Claude 把这些通用工具组合出解决不同问题的形态。例如 [Agent Skills](https://agentskills.io/home)、[programmatic tool calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling) 与 [memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)，全部由 bash 与文本编辑器工具组合而成。

![Programmatic tool calling、skills 与 memory 都是 bash 与文本编辑器工具的组合形态。](https://assets.claude.com/4f2f17a50558ff747a3cc161f845023ab21a9f21.png)

*图注：programmatic tool calling、skills 与 memory 是 bash 与文本编辑器工具的组合。*

## 模式二：给 harness 瘦身——不断追问可以停止做什么

[agent harness 会把假设编码进去](https://www.anthropic.com/engineering/harness-design-long-running-apps)：假设 Claude 自己做不了什么。随着 Claude 能力增强，这些假设应当被重新检验。

### 让 Claude 编排自己的动作

一个常见假设是：每个工具结果都应回流进 Claude 的[上下文窗口](https://platform.claude.com/docs/en/build-with-claude/context-windows)，用来指导下一个动作。把工具结果按 token 处理可能又慢又贵，如果结果只需要传给下一个工具，或者 Claude 只关心输出里的一小部分，这种处理就不必要。

![Claude 调用工具，工具在环境里执行。](https://assets.claude.com/846ce7bdd3af066b26f3eb238cce8df7302b9ccb.png)

*图注：Claude 调用工具，工具在一个环境里执行。*

考虑读一张大表却只推理其中一列：整张表进入上下文，Claude 为每一行用不到的行支付 token 成本。可以在工具设计里处理这个问题，用[硬编码的过滤器](https://platform.claude.com/docs/en/about-claude/models/migration-guide#additional-recommended-changes)。但这没有触及要点：agent harness 正在做一个编排决策，而这个决策由 Claude 来做更合适。

给 Claude 一个[代码执行](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)工具（例如 [bash 工具](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool)或[语言专属的 REPL](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)）解决了这个问题：Claude 可以写代码来表达工具调用以及调用之间的逻辑。harness 不再决定每个工具调用结果都按 token 处理，Claude 自己决定哪些结果直接传递、过滤或管道进下一个调用，全程不触碰上下文窗口。只有代码执行的输出才进入 Claude 的上下文窗口。

![Claude 写代码，代码表达工具调用与调用之间的逻辑。](https://assets.claude.com/bd8453083ea472d1e2af60252a9ec47d7d429249.png)

*图注：Claude 可以写代码表达工具调用及其间的逻辑。*

编排决策从 harness 移交给 model。既然代码是 Claude 编排动作的通用方式，一个强编码 model 同时也是一个强的通用 agent。Claude 用这个模式在[非编码评估](https://claude.com/resources/articles/improved-web-search-with-dynamic-filtering)上表现出色：在 BrowseComp（一个[测试](https://arxiv.org/abs/2504.12516) agent 浏览网页能力的基准）上，给 Opus 4.6 过滤自己工具输出的能力，把准确率从 45.3% 提到 61.6%。

### 让 Claude 管理自己的上下文

任务专属的上下文引导 Claude 使用 bash 与文本编辑器工具这类通用工具。一个常见假设是：[system prompts](https://platform.claude.com/docs/en/release-notes/system-prompts) 应当手工填满任务专属指令。问题在于，用指令预载 prompt 在大量任务之间不成立：每加一个 token 都在消耗[Claude 的注意力预算](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)，用很少用到的指令预载上下文是一种浪费。

给 Claude 访问 [skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) 的能力解决了这个问题：每个 skill 的 YAML frontmatter 是一小段预载进上下文窗口的简短描述，提供 skill 内容的概览。任务需要时，Claude 可以调用读文件工具把完整 skill 渐进披露出来。

![Claude 用 skills 渐进披露与任务相关的上下文。](https://assets.claude.com/606dbffc4fe38a3a1a05c4d88650c2a2e160766d.png)

*图注：Claude 可以用 skills 渐进披露与任务相关的上下文。*

skills 给 Claude 自由组装自己上下文窗口的能力，[context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing) 是它的反向操作：有选择地移除已经过时或无关的上下文，例如旧的工具结果或思考块。

有了 [subagents](https://code.claude.com/docs/en/sub-agents)，Claude 越来越擅长判断何时分叉出一个全新上下文窗口，把特定任务的工作隔离起来。[在 Opus 4.6 上](https://www-cdn.anthropic.com/0dd865075ad3132672ee0ab40b05a53f14cf5288.pdf)，生成 subagents 的能力让 BrowseComp 成绩比最好的单 agent 运行提高 2.8%。

### 让 Claude 持久化自己的上下文

长时运行的 agent 可能超出单个[上下文窗口](https://platform.claude.com/docs/en/build-with-claude/context-windows)的限制。一个常见假设是：记忆系统应当依赖围绕 model 的检索基础设施。我们的很多工作聚焦在给 Claude 简单的方式，让它为自己选择要持久化什么内容。

例如 [compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) 让 Claude 总结自己过去的上下文，在长周期任务上保持连贯。经过几次发布，Claude 越来越擅长选择记住什么。[在 BrowseComp](https://www-cdn.anthropic.com/14e4fb01875d2a69f646fa5e574dea2b1c0ff7b5.pdf)（一个 agentic 搜索任务）上，无论给 Sonnet 4.5 多大的 compaction 预算，它都恒定在 43%。而 Opus 4.5 在同一设置下达到 68%，Opus 4.6 达到 84%。

[memory folder](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) 是另一条路，让 Claude 把上下文写进文件，之后按需读取。我们见过 Claude 用它做 agentic 搜索。在 BrowseComp-Plus 上，给 Sonnet 4.5 一个 memory folder [把准确率从 60.4% 提到 67.2%](https://www-cdn.anthropic.com/bf10f64990cfda0ba858290be7b8cc6317685f47.pdf)。

![Claude 把上下文持久化进 memory folder。](https://assets.claude.com/2ac581337b2050f448e2a22b9a8e4a1451e0d72c.png)

*图注：Claude 可以把上下文持久化到 memory folder。*

[长周期游戏](https://www.youtube.com/watch?v=CXhYDOvgpuU)，例如 Pokémon，展示了 Claude 使用 memory folder 能力的进步。Sonnet 3.5 把记忆当逐字记录，写下非玩家角色（NPC）说过的话，而没写要紧的内容。14,000 步之后它有 31 个文件——其中两个几乎重复，都在讲毛毛虫 Pokémon——人还停在第二个城镇：

```
caterpie_weedle_info:
- Caterpie and Weedle are both caterpillar Pokémon.
- Caterpie is a caterpillar Pokémon that does not have poison.
- Weedle is a caterpillar Pokémon that does have poison.
- This information is crucial for future encounters and battles.
- If our Pokémon get poisoned, we should seek healing at a Pokémon
  Center as soon as possible.
```

后来的模型写战术笔记。Opus 4.6 在同样步数下有 10 个按目录组织的文件、三枚道馆徽章，以及一份从自己失败里蒸馏出来的经验文件：

```
/gameplay/learnings.md:
- Bellsprout Sleep+Wrap combo: KO FAST with BITE before Sleep
  Powder lands. Don't let it set up!
- Gen 1 Bag Limit: 20 items max. Toss unneeded TMs before dungeons.
- Spin tile mazes: Different entry y-positions lead to DIFFERENT
  destinations. Try ALL entries and chain through multiple pockets.
- B1F y=16 wall CONFIRMED SOLID at ALL x=9-28 (step 14557)
```

## 模式三：在 harness 设计里谨慎设定边界

agent harness 在 Claude 周围提供结构，执行 UX、成本或安全的约束。

### 设计上下文让 cache 命中最大化

[Messages API](https://platform.claude.com/docs/en/build-with-claude/working-with-messages) 是无状态的。Claude 看不见之前轮次的对话历史。这意味着 agent harness 每轮都要把新上下文连同全部过去的动作、工具描述与指令一起打包给 Claude。

prompt 可以按设定的[断点](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)缓存。换句话说，Claude API 把上下文写到断点为止的内容写入缓存，再检查上下文是否匹配任何先前的缓存条目。

既然缓存 token 的[成本是基价输入 token 的 10%](https://platform.claude.com/docs/en/about-claude/pricing)，以下几条原则帮助 agent harness 最大化 cache 命中：

| 原则 | 说明 |
|---|---|
| 静态内容在前，动态内容在后 | 排列请求，让稳定内容（system prompt、tools）排在前面。 |
| 用 messages 传递更新 | 在 messages 里追加一个 <system-reminder>，不编辑 prompt 本身。 |
| 不中途更换 model | 缓存按 model 区分；会话中途切换会破坏缓存。需要更便宜的 model 时，用 subagent。 |
| 谨慎管理 tools | tools 位于缓存前缀里。增删一个工具都会使前缀失效。动态发现工具时用 **tool search**，它以追加方式进入而不破坏缓存。 |
| 更新断点 | 对多轮应用（例如 agent），把断点移到最新消息，让缓存保持最新。用 **auto-caching** 实现这一点。 |

### 用 declarative tools 执行 UX、observability 或安全边界

Claude 未必知道应用的安全边界或 UX 界面。Claude 发出工具调用，由 harness 处理。bash 工具给 Claude 广泛的程序化操作能力，但交给 harness 的只有一个命令字符串——每个动作都是同一个形状。把动作提升为专属工具，harness 就得到一个动作专属的钩子，带类型化参数，可以拦截、门控、渲染或审计。

需要安全边界的动作是专属工具的天然候选。可逆性是常用的判据，外部 API 调用这类难以撤销的动作可以用用户确认来门控。`edit` 这类写工具可以带 staleness check，防止 Claude 覆盖自上次读取后已被修改的文件。

![专属工具可以按安全、UX 或 observability 的考量用于特定动作。](https://assets.claude.com/ed3130dafac3f6d95a73485c34751ac8461625ca.png)

*图注：专属工具可以基于安全、UX 或 observability 的考量用于特定动作。*

动作需要呈现给用户时，工具同样有用。例如把工具调用渲染成 modal，向用户清晰地展示一个问题、给出多个选项，或在用户提供反馈之前暂停 agent 循环。

最后，工具对 observability 有用。当动作是一个带类型的工具时，harness 拿到结构化参数，可以记录、追踪与回放。

把动作提升为工具的决策应当持续重估。例如 Claude Code 的 [auto-mode](https://www.anthropic.com/engineering/claude-code-auto-mode)（发文时处于 research mode）给 bash 工具提供了一道安全边界：让第二个 Claude 读命令字符串，判定它是否安全。这个模式可以减少对专属工具的需要，只应在你信任大方向的任务上使用。专属工具在高风险动作上仍然挣得自己的位置。

## agent harness 设计的未来

Claude 智能的前沿一直在变。关于 Claude 做不了什么的假设，需要在每次能力跳变时重新检验。

我们看到这个模式反复上演。在一个[为长周期任务构建的 agent](https://www.anthropic.com/engineering/harness-design-long-running-apps) 里，Sonnet 4.5 在感觉到上下文上限逼近时会提前收尾。我们加了 context resets 清空上下文窗口来处理这个「context anxiety」。到了 Opus 4.5，这个行为消失了。我们为补偿它而建的 context resets 成了 agent harness 里的 dead weight。

移除这类 dead weight 很重要，因为它可能成为 Claude 表现的瓶颈（参见 [The Bitter Lesson](http://www.incompleteideas.net/IncIdeas/BitterLesson.html)）。随着时间推移，应用里的结构与边界应当按照这个问题来修剪：我可以停止做什么？

要使用本文讨论的全部工具与模式，可参考[我们的 claude-api skill](https://github.com/anthropics/skills/tree/main/skills/claude-api)。

## 致谢

本文由 Claude Platform 团队 member of technical staff Lance Martin 撰写。特别感谢 Thariq Shihipar、Barry Zhang、Mike Lambert、David Hershey 与 Daliang Li 对主题讨论的帮助。感谢 Lydia Hallie、Lexi Ross、Katelyn Lesse、Andy Schumeister、Rebecca Hiscott、Jake Eaton、Pedram Navid 与 Molly Vorwerck 的编辑评审与反馈。
