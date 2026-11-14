# 用 Agent Skills 把 agent 装备进真实世界（Equipping agents for the real world with Agent Skills）

- 原文：[Equipping agents for the real world with Agent Skills](https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills)
- 来源：Anthropic Engineering，作者 Barry Zhang、Keith Lazuka、Mahesh Murag
- 发布：2025-10-16
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图，地址为原文 CDN 直链。

> 2025-12-18 更新：我们已把 Agent Skills 发布为开放标准，支持跨平台移植。详见 [agentskills.io](https://agentskills.io/)。

随着模型能力提升，我们现在能构建与完整计算环境交互的通用 agent。比如 [Claude Code](https://claude.com/product/claude-code) 能用本地代码执行与文件系统，完成跨领域的复杂任务。但这些 agent 越来越强的同时，我们需要更可组合、可扩展、可移植的方式，给它们配上领域专门知识。

这促使我们创建了 [Agent Skills](https://www.anthropic.com/news/skills)：由指令、脚本与资源组成的结构化文件夹，agent 可以发现并动态加载它们，在特定任务上表现更好。Skills 把你的专门知识打包成 Claude 可组合的资源，扩展 Claude 的能力，把通用 agent 变成贴合你需求的专门化 agent。

给 agent 构建 skill，就像给新员工编写入职指南。无需为每个用例构建碎片化的定制 agent，任何人现在都能通过捕捉与分享自己的过程性知识，用可组合的能力把自己的 agent 专门化。本文解释 Skills 是什么，展示它们如何工作，并分享构建自己 skill 的最佳实践。

![题图](https://www-cdn.anthropic.com/images/4zrzovbb/website/ddd7e6e572ad0b6a943cacefe957248455f6d522-1650x929.jpg)

## skill 的解剖

要看 Skills 的实际运作，走一个真实例子：支撑 [Claude 新近发布的文档编辑能力](https://www.anthropic.com/news/create-files)的其中一个 skill。Claude 本来就懂很多 PDF 理解知识，但直接操作 PDF（比如填写表单）的能力有限。这个 [PDF skill](https://github.com/anthropics/skills/tree/main/document-skills/pdf) 让我们能把新能力交给 Claude。

最简单的形态下，skill 就是一个包含 `SKILL.md` 文件的目录。这个文件必须以 YAML frontmatter 开头，包含必需的元数据：`name` 与 `description`。启动时，agent 把每个已安装 skill 的 `name` 与 `description` 预加载进系统提示词。

这份元数据是 progressive disclosure（渐进披露）的第一层：它只提供刚好够用的信息，让 Claude 知道每个 skill 该在什么时候用，无需把全部内容装进上下文。文件正文是第二层细节。Claude 认为 skill 与当前任务相关时，会读取完整的 `SKILL.md` 载入上下文。

![SKILL.md 结构示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/6f22d8913dbc6228e7f11a41e0b3c124d817b6d2-1650x929.jpg)

skill 复杂起来后，内容可能多到放不进单个 `SKILL.md`，或者包含只在特定场景才相关的上下文。这些情况下，skill 可以在目录里捆绑更多文件，从 `SKILL.md` 按名字引用它们。这些额外的关联文件是第三层（及更深）的细节，Claude 可以只在需要时才去导航与发现。

下面这个 PDF skill 里，`SKILL.md` 引用了两个额外文件（`reference.md` 与 `forms.md`），作者选择把它们与核心 `SKILL.md` 捆在一起。把填表单的指令挪到单独文件（`forms.md`）后，skill 的核心保持精炼，作者可以放心 Claude 只在填表单时才会去读 `forms.md`。

![PDF skill 文件组织示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/191bf5dd4b6f8cfe6f1ebafe6243dd1641ed231c-1650x1069.jpg)

Progressive disclosure 是让 Agent Skills 灵活、可扩展的核心设计原则。像一本组织良好的手册：先看目录，再看具体章节，最后才是详细附录，skill 让 Claude 只在需要时加载信息：

![渐进披露的手册类比示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/a3bca2763d7892982a59c28aa4df7993aaae55ae-2292x673.jpg)

带文件系统与代码执行工具的 agent，处理特定任务时不需要把 skill 的全部内容读进上下文窗口。这意味着一个 skill 能捆绑的上下文量实际上不设上限。

### Skills 与上下文窗口

下图展示用户消息触发 skill 时，上下文窗口的变化。

![skill 触发时的上下文窗口变化示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/441b9f6cc0d2337913c1f41b05357f16f51f702e-1650x929.jpg)

图中操作顺序：

1. 开始时，上下文窗口里有核心系统提示词、每个已安装 skill 的元数据，以及用户的初始消息；
2. Claude 调用 Bash 工具读取 `pdf/SKILL.md` 的内容，触发 PDF skill；
3. Claude 选择读取 skill 捆绑的 `forms.md` 文件；
4. 最后，Claude 已从 PDF skill 加载了相关指令，继续处理用户的任务。

### Skills 与代码执行

Skills 还可以包含代码，由 Claude 自行决定当作工具执行。

大语言模型擅长很多任务，但某些操作更适合传统代码执行。比如靠 token 生成的方式排序列表，远比直接运行排序算法昂贵。效率之外，许多应用还要求只有代码能提供的确定性可靠。

我们的例子里，PDF skill 捆绑了一个预先写好的 Python 脚本，读取 PDF 并抽取全部表单字段。Claude 可以运行这个脚本，既不用把脚本也不用把 PDF 装进上下文。代码是确定性的，这个工作流一致且可重复。

![skill 中的代码执行示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/c24b4a2ff77277c430f2c9ef1541101766ae5714-1650x929.jpg)

## 开发与评估 skills

上手编写与测试 skills 的几条指南：

- 先做评估：把 agent 放到代表性任务上运行，观察它们在哪里卡壳、哪里需要额外上下文，找出能力缺口。然后增量构建 skills，补足这些短板。
- 为规模化组织结构：`SKILL.md` 文件变得臃肿时，把内容切分成独立文件并引用。某些上下文互斥或很少一起用到时，分开存放能减少 token 用量。代码既可以充当可执行工具，也可以充当文档。应当写清楚脚本是让 Claude 直接运行，还是读进上下文当参考。
- 从 Claude 的视角思考：观察 Claude 在真实场景里怎么用你的 skill，基于观察迭代；留意意外的轨迹或对某些上下文的过度依赖。特别留意 skill 的 `name` 与 `description`，Claude 靠它们判断是否针对当前任务触发这个 skill。
- 与 Claude 一起迭代：和 Claude 共同做任务时，让 Claude 把成功的做法与常见错误沉淀成 skill 里可复用的上下文与代码。如果它用 skill 做任务时走错了方向，就让它自我反思哪里出了问题。这个过程帮你发现 Claude 真正需要的上下文，无需提前凭空设想。

### 使用 Skills 时的安全考量

Skills 通过指令与代码给 Claude 新能力。这带来了力量，也意味着恶意 skill 可能在使用环境中引入漏洞，或者诱导 Claude 外泄数据、执行意外动作。

我们建议只从可信来源安装 skills。从可信度存疑的来源安装时，使用前要彻底审计。先读 skill 捆绑的每个文件，理解它做什么，特别留意代码依赖与捆绑的图片、脚本这类资源。同样要留意 skill 里指示 Claude 连接潜在不受信任外部网络来源的指令或代码。

## Skills 的未来

Agent Skills 今天已在 [Claude.ai](http://claude.ai)、Claude Code、Claude Agent SDK 与 Claude Developer Platform [得到支持](https://www.anthropic.com/news/skills)。

未来几周，我们会继续添加功能，覆盖创建、编辑、发现、分享与使用 Skills 的完整生命周期。我们尤其期待 Skills 帮助组织与个人把他们的上下文与工作流分享给 Claude。我们还会探索 Skills 与 [Model Context Protocol](https://modelcontextprotocol.io/)（MCP）server 的互补：教 agent 掌握涉及外部工具与软件的更复杂工作流。

更远一点，我们希望让 agent 自己创建、编辑与评估 Skills，把自身的行为模式固化成可复用的能力。

Skills 概念简单，格式也相应简单。这种简单让组织、开发者与最终用户更容易构建定制 agent、赋予它们新能力。

我们期待看到人们用 Skills 构建出什么。今天就上手：看我们的 Skills [文档](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)与 [cookbook](https://github.com/anthropics/claude-cookbooks/tree/main/skills)。

## 作者与致谢

本文由 Barry Zhang、Keith Lazuka 与 Mahesh Murag 撰写，他们仨都非常喜欢文件夹。特别感谢 Anthropic 内部许多推动、支持与构建 Skills 的同事。
