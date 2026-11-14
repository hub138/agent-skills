# 像 agent 一样看：我们在 Claude Code 里如何设计工具（Seeing like an agent: how we design tools in Claude Code）

- 原文：[Seeing like an agent: how we design tools in Claude Code](https://claude.dev/blog/seeing-like-an-agent/)
- 来源：Anthropic（claude.dev Blog），作者 Thariq Shihipar
- 发布：2026-04-10
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 claude.dev /media/ 绝对直链并配中文短描述；三个工具迭代案例与三段式演进完整翻译。

了解 Claude Code 团队如何从模型视角出发设计、测试与演进工具。

构建 agent harness 时最难的环节之一，就是构造它的工具。

Claude 完全通过[工具调用](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)来行动，而在 Claude API 里有多种构造工具的方式，用到的原语包括 [bash](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool)、[skills](https://code.claude.com/docs/en/skills) 与[代码执行](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)。（关于 Claude API 上的程序化工具调用，可读 [@RLanceMartin 的新文章](https://x.com/RLanceMartin/status/2027450018513490419)。）

那么你该怎么给自己的 agent 设计工具？给它一个 bash 或代码执行这样的万能工具？还是五十个专用工具，每个场景一个？

要把自己放进模型的心智，想象你拿到一道难题。你想有什么工具来解决它？这取决于你自己的能力水平！

纸笔是最低配置，但你会被手动计算拖住。计算器更好，但你得会用高级功能。最快最强的选择是计算机，但前提是你会用它写代码并执行。

这是设计 agent 的一个有用框架：你要给它的是与其自身能力相称的工具。但你怎么知道那些能力是什么？关注它、读它的输出、做实验。你要学会像 agent 一样看。

如果你在构建 agent，你会遇到我们遇到过的问题：什么时候加一个工具，什么时候减一个，怎么区分。以下是我们构建 Claude Code 过程中给出的回答，包括我们先做错的地方。

## 用 AskUserQuestion 工具改进引导提问

![标题为「Finding the sweet spot」的示意图：一条从「无结构」到「过于刚性」的谱线。修改 markdown 输出位于「无结构」一端（自由但杂乱，难格式化）。ExitPlanTool 参数位于「过于刚性」一端（计划已经成形，问题来得太晚）。AskUserQuestion 工具被高亮在中间（结构化、可组合、有清晰的界面载体）。](https://claude.dev/media/047bf332e6ff4962c8faee154feb4060e1f5a2b0cc73cf5235f9ce8c1d9e3890.png)

构建 AskUserQuestion 工具时，我们的目标是提升 Claude 的提问能力（通常称为 elicitation，引导提问）。

Claude 当然可以用纯文本提问，但我们发现回答这类问题让人花掉不必要的时间。怎样降低这种摩擦、提高用户与 Claude 之间的沟通带宽？

### 尝试一：修改 ExitPlanTool

我们最先试的办法是给 ExitPlanTool 加一个参数，让它在输出计划的同时附带一组问题。这是最容易实现的修复，但它让 Claude 陷入困惑，因为我们同时在要一份计划、又要一组关于这份计划的问题。万一用户的回答与计划冲突怎么办？Claude 要把 ExitPlanTool 调用两次吗？我们知道这条路走不通，回到原点重来。（关于我们为什么做 ExitPlanTool，可读[我们关于 prompt caching 的帖子](https://x.com/trq212/status/2024574133011673516)。）

### 尝试二：改输出格式

接着，我们试着更新 Claude 的输出指令，让它用一种略作修改的 markdown 格式来提问。例如，让它输出一组带括号备选项的列表问题，我们再解析并渲染成界面给用户。

Claude 通常能产出这个格式，但不可靠。它会追加多余的句子、丢掉选项，或干脆放弃结构。换下一种。

### 尝试三：AskUserQuestion 工具

![Claude Code 终端里的 AskUserQuestion 工具：Paradigm、Theme、Snacks、Indentation 与 Submit 标签页，问题「Which programming paradigm do you prefer for this project?」，编号选项：Functional、Object-Oriented、Procedural、Mixed、Type something 与 Chat about this。](https://claude.dev/media/155e8e285e14309b55a9f5342ffd62d3bfb45be1a66d48c2496818836cb4062a.png)

最后我们确定为：创建一个 Claude 随时可以调用的工具，但在 plan mode 里给特别的提示促使它调用。工具触发时我们显示一个弹窗展示问题，并阻塞 agent 循环直到用户回答。

这个工具让我们向 Claude 要结构化输出，也帮我们确保 Claude 给用户多个选项。它还给了用户组合这个能力的途径，例如在 [Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) 里调用，或在 skills 里引用它。

最重要的是，Claude 看起来喜欢调用这个工具，我们发现它的输出效果很好。说到底，再好的工具设计，Claude 不理解怎么调用也没用。

这是 Claude Code 里引导提问的最终形态吗？我们怀疑不是。Claude 能力越强，服务于它的工具也要跟着演进。下一节就是一个工具曾经帮忙、后来开始碍事的案例。

### 随能力更新：tasks 与 todos

![标题为「From todos to tasks」的示意图：左边是单个 agent 拿着清单（set up project、write tests、implement feature、deploy）。一条标注「models improve」的箭头指向右边，Agent A 与 Agent B 共享带依赖的任务：任务 1 与任务 2 已完成并汇入进行中的任务 3，其后是任务 4。](https://claude.dev/media/6ec2a2426b22bc0a627a34ed01cf7db43d6b9ea3b67f824363f8b3511e4e52e8.png)

Claude Code 刚发布时，我们意识到模型需要一份[todo 清单](https://platform.claude.com/docs/en/agent-sdk/todo-tracking)来保持方向。todos 可以在开始时写下，随模型做事逐项勾掉。为此我们给了 Claude TodoWrite 工具，负责写入或更新 todos 并展示给用户。

但即便如此，我们还是常见 Claude 忘记自己该做什么。为了适应，我们每 5 轮插入一条 system reminder，提醒 Claude 它的目标。

随着模型进步，它们发觉 todo 清单成了限制。反复收到清单提醒，让 Claude 以为自己必须坚守清单，而认识不到需要改道时应当修改清单。我们还看到 Opus 4.5 大幅提升了使用 subagent 的能力，但多个 subagent 怎么共享一份 todo 清单？

看到这些，我们把 TodoWrite 功能替换成[Task 工具](https://x.com/trq212/status/2014480496013803643)。todos 的重心是让模型保持方向，而 tasks 帮助 agent 之间相互沟通。tasks 可以包含依赖、在 subagent 之间共享更新，模型可以修改和删除它们。

模型能力提升时，你的模型曾经需要的工具现在可能正在束缚它们。[不断重审关于需要哪些工具的既有假定](https://claude.dev/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models/)很重要。这也是为什么只支持一小群能力轮廓相近的模型是有用的。

## 设计搜索界面

我们做过的最有影响的工具，是让 Claude 自己找到上下文的那几个。

Claude Code 最初内部发布时，我们用的是 RAG：向量数据库预先索引代码库，harness 在每次响应前检索相关片段递给 Claude。RAG 强大且快，但它需要索引与配置，在大量不同环境里可能很脆弱。最重要的是，Claude 是被塞给这份上下文，而非自己找到它。

但 Claude 既然能在网上搜索，为什么不能也搜你的代码库？给 Claude 一个 Grep 工具，它就能自己搜文件、自己构建上下文。

Claude 越聪明，在给对工具时构建自己上下文的能力就越强。

我们发布 [Agent Skills](https://agentskills.io/home) 时，把 progressive disclosure（渐进式披露）正式化了：agent 可以通过探索逐层发现相关上下文。

Claude 现在可以读 skill 文件，那些文件还可以引用其他文件供模型递归阅读。事实上，skills 的一个常见用途就是给 Claude 加更多搜索能力，例如教它怎么用一个 API 或查一个数据库。

一年下来，Claude 从基本不会构建自己的上下文，成长到能跨好几层文件做嵌套搜索、找到恰好需要的那段上下文。

progressive disclosure 现在是我们常用的技术，用来不新增工具就添加新能力。下一节解释为什么。

## Progressive disclosure：Claude Code Guide agent

Claude Code 目前有约 20 个工具，我们的团队经常重审：要让 Claude 发挥最好，这些工具是否全部必要。新增一个工具的门槛很高，因为这给模型又多了一个要考虑的选项。

例如，我们注意到 Claude 对如何使用 Claude Code 本身了解不够。你问它怎么加一个 MCP、某个斜杠命令是干什么的，它答不上来。

我们本可以把这些信息全部放进 system prompt，但用户很少问到这些，放进去只会增加 context rot（上下文腐化），干扰 Claude Code 的主业：写代码。

于是我们试了 progressive disclosure：给 Claude 一个文档链接，需要时加载并搜索。这可行，但 Claude 会把大段文档拖进上下文去找一个一句话就能回答的问题。

所以我们做了 Claude Code Guide：一个 subagent，用户问到 Claude Code 自身时由 Claude 调用。这个 subagent 在自己的上下文里搜文档，遵循关于怎么搜、提取什么的详细指令，只把答案交回来。主 agent 的上下文保持干净。

这并非完美方案（你问它怎么配置自己时，Claude 仍会犯迷糊），但我们在不新增工具的情况下扩展了 Claude 的行动空间。

### 像 agent 一样看，是手艺也是科学

给模型设计工具，既是科学，也是手艺。它严重依赖你用的模型、agent 的目标与它所处的环境。

我们最好的建议？多做实验，勤读输出，敢于尝试新东西。而最重要的，是试着像 agent 一样看。

*从 [Claude Code](https://claude.com/product/claude-code) 开始。*

***关于作者：*** *Thariq Shihipar 是 Anthropic 的技术团队成员，从事 Claude Code 开发。*
