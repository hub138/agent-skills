# Claude 5 世代模型的上下文工程新规则（The new rules of context engineering for Claude 5 generation models）
- 原文：[The new rules of context engineering for Claude 5 generation models](https://claude.dev/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models/)
- 来源：Anthropic（claude.dev Blog），作者 Thariq Shihipar
- 发布：2026-07-24
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片相对路径 /media/ 转为 https://claude.dev/media/ 绝对 URL 并配中文短描述；命令与工具名保留英文原样。

我们为更强的模型删掉了 Claude Code system prompt 的 80% 以上。这篇文章讲我们学到的经验，以及如何把它们用在你自己的 Claude Code 上下文工程与自建 agent 上。

我此前写过如何[给最新世代的 Claude 5 模型写提示词](https://claude.com/blog/a-field-guide-to-claude-fable-finding-your-unknowns)，以及如何与它们迭代协作、发现你真正想构建的东西。

但你给 Claude 发消息时，提示词只是它收到上下文的一小部分。上下文的很大一部分由 system prompt、Skills、CLAUDE.md 文件、memory 等来源组装而成。我们把这称为[上下文工程](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)，它对你在 Claude Code 里产出的结果、或你构建自己的 agent 时的表现影响很大。

提示词只服务一次请求，上下文则跨大量请求通用，因此它没法写得那么具体。如何为 Claude 构建这些通用提示词与指引，尤其在你不知道用户的提示词会是什么的时候？

这件事难得出乎意料，因为 Claude 自身的能力也在演化。最近我们注意到，给最新世代 Claude 模型写提示词的方式出现了一次大跨越：面向 Claude Opus 5 与 Claude Fable 5 这类模型，我们删掉了 [Claude Code](https://claude.com/product/claude-code) system prompt 的 80% 以上，编码评测没有可测量的损失。

下面是我们给这类新模型写提示词学到的经验，以及如何用它更新你的上下文工程。这些最佳实践已经放进 `claude doctor`；在 Claude Code 里用 `/doctor` 命令，给你的 skills 与 CLAUDE.md 文件重新量体裁衣。

## 给 Claude 松绑

总体上，我们发现自己此前的 Claude Code 约束过头了——system prompt、CLAUDE.md 文件与 skills 三处都存在。

例如，回读自己内部使用 Claude Code 的转录时，我们会在同一次请求里看到互相冲突的消息：system prompt 说「leave documentation as appropriate」，某个 skill 说「DO NOT add comments」，用户请求是「just make it work like the old one」。

![一份组装后的上下文：system prompt 一行写 leave documentation as appropriate，skill 一行写 do not add comments，用户请求一行写 just make it work like the old one](https://claude.dev/media/a0c1f3923f1e92004785e35257d3feed5081264767d0a99fa5eb397e2fb6f2e2.png)

多数情况下，Claude 能解读用户意图抵达正确答案，但它必须先对这些重叠冲突的消息做更仔细的思考，才能决定怎么做。

这些约束曾经是必要的，用来防住最坏情况；而我们后来发现，其中很多可以直接删掉，让模型改用周边上下文与自己的判断。

另外，Claude Code 现在有了多得多的工具。过去 Claude 依赖 CLAUDE.md 作为记忆、信息与指引的来源；现在有了 memory、artifacts 与 skills，Claude 可以用它们创造跨会话加载与共享上下文的新方式。

## 从前与现在

此前不少上下文工程的最佳实践已经变成迷思。包括：

![六条旧规则被划掉，各自指向替代做法：给规则 → 让模型用判断；给示例 → 设计接口；全量前置 → 渐进披露；自我重复 → 简单工具描述；CLAUDE.md 手动 memory → auto-memory；简单 spec → rich references](https://claude.dev/media/aaa82d5934e084f1e509ac1679c26d0d2338d6c995c1c2f349fc12b8a0fd1a9d.png)

### 从前：给 Claude 规则

### 现在：让 Claude 用判断

Claude Code 刚推出时，我们必须确保 Claude 避开最坏情况，例如删除文件。这意味着我们会给出特别强硬的指引，哪怕它并不总是对的。例如，system prompt 里我们曾经这样写：

*In code: default to writing no comments. Never write multi-paragraph docstrings or multi-line comment blocks — one short line max. Don't create planning, decision, or analysis documents unless the user asks for them — work from conversation context, not intermediate files.*

但对一部分提示词来说，这条指引是错的。文档这件事上，用户可能有自己的习惯，或者非常复杂的代码里某些部分就是需要多行注释块。

旧模型没有这些护栏时，Claude 写出的注释在很多场景下是错的，我们只好接受这个取舍。而新模型判断力更好，不需要显式规则也能把这些决定处理好。

新 system prompt 里我们说：*Write code that reads like the surrounding code: match its comment density, naming, and idiom.*

### 从前：给 Claude 示例

### 现在：设计接口

工具使用的头号规则曾经是给 Claude 用法示例。而在最新模型上，我们发现给示例反而会把模型约束在一个特定的探索空间里。

![改造前：TodoWrite 工具描述约 9100 字符，装满何时使用的清单与完整示例。改造后：一句简短描述 Create and update a task list for the current session，status 枚举 pending、in_progress、completed，加一条规则：同一时刻只有一个任务 in_progress](https://claude.dev/media/8bb6f9365532bb8b19443ad00f230444087a452f776232d05045f1c6c63c3de8.png)

与其给示例，多想想你的工具、脚本与文件的设计：Claude 拿到哪些参数，怎么让这些参数更有表达力？

例如 Todo 工具这个例子，仅把 status 列成 pending、in_progress、completed 的枚举，就已经向 Claude 暗示了用法；「同一时刻只保持一个条目 in_progress」这条指令帮忙定义了我们期望的行为。

### 从前：全量前置

### 现在：渐进披露

Claude Code 以编码为主业，我们的 system prompt 里曾经装着如何做 code review 与验证的详细信息。这些内容并非每次都用得上，但用到时它们是关键信息。

从那以后，Claude Code 已经非常擅长渐进披露——在正确的时机加载正确的上下文。例如，我们把验证与 code review 移进了各自的 skills，Claude Code 可以按需选择调用。

渐进披露不只有 skills，工具同样适用。我们的一部分工具是 deferred loading：agent 必须先用 ToolSearch 搜到完整定义才能使用。这让我们可以挂更多的工具（例如我们的 Task 工具），它们在使用之前不占上下文。

同样的思路可以用到你自己的 CLAUDE.md 与 Skill.md 文件上。一个常见迷思是要把这些文件做成万事仓库，装下你*可能*遇到的每条已知实践，理由是 Claude 否则找不到它。正确做法是[考虑维护一棵可按时加载的文件树](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code)。

### 从前：自我重复

### 现在：简单工具描述

早期的 Claude 模型有时需要重复指令，或者更听得进上下文窗口末尾的指令而忽视开头。这意味着我们的 system prompt 里有时在主体部分提到工具，又在工具描述里再写一遍用法。

我们发现这些重复可以删掉，把工具用法的说明放进工具描述，不放 system prompt。

### 从前：memory 放在 CLAUDE.md 文件里

### 现在：auto-memory

我们过去鼓励用户用 # 快捷键把内容写进自己的 `CLAUDE.md`，为 Claude 保存记忆。现在换成 Claude 自动保存与工作相关、与你相关的记忆。

### 从前：简单 spec

### 现在：rich references

在 plan mode 里，Claude Code 重度依赖装着计划的 markdown 文件。把这些文件存成计划，让 Claude 需要时可以引用。另一个类似的做法是把 spec 存进代码库，供 Claude 在较长的项目里随时参照。

但我们发现 Claude 能处理越来越复杂的引用。除了简单 markdown 文件，Claude 还能引用由新 artifacts 功能创建的 [HTML artifacts](https://claude.dev/blog/using-claude-code-the-unreasonable-effectiveness-of-html/)。

你还可以用代码做引用。一份 spec 也可以是一套详尽的测试套件，或另一个代码库里某个 Claude 可以移植的函数。

Rubrics（评分细则）是引用的另一种形态。Rubrics 让 Claude 借助[动态工作流](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code)尝试验证你在某个领域的品味（例如什么样的 API 设计算好），并按这些 rubrics 启动 verifier agent。

## 应用到你的上下文

把以上全部合起来，组装自己的上下文时长什么样？

![上下文窗口的分层画法：最上面是你的 prompt，其下是 references（@ 提及的文件、specs、mockups、代码库与 artifacts），再往下是 system prompt、CLAUDE.md 文件、skills 与 memory](https://claude.dev/media/6c6b396594b664244e31fe5ba0c37619accc4777be823e699906c7a641dfcc60.png)

### System prompt

System prompt 与产品语境深度绑定。它告诉 Claude 自己在什么产品里、在做什么。用 Claude Code 时你几乎不会改动它，但如果你在[构建自己的 agent harness](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)，这里正是你该花大量时间的地方。

### CLAUDE.md

保持 CLAUDE.md 轻量，简短说明仓库是干什么的，把大部分 token 花在代码库内部的 gotchas（易错点）上。例如，你的代码组织方式可能是类型全部集中在一个大文件、别处不出现。避免写那些 Claude 看一眼文件系统或仓库就知道的「显然」内容。

重度使用渐进披露：例如你有几条独特的验证工作的指令，就创建一个 verification skill，从 CLAUDE.md 里引用它。

### Skills

把 [skills 当作轻量指南](https://claude.dev/blog/lessons-from-building-claude-code-how-we-use-skills/)，让 Claude 在需要时找到信息。除高度重要的领域外，避免把它们写得约束过头。

长的 skill 尽量重度使用渐进披露——分解成多个文件分开存放。

skills 编码你自己、你的团队或你的产品特有的观点、知识与最佳实践时，价值最大。

### References

你可以用 @ 提及把文件收进引用。引用让 Claude 随时参照与当前计划相关的深度信息。

这些信息可以在 spec 文件、mockup 里，甚至整个代码库里。一般应优先用代码形态的文件：它以 Claude 非常熟悉的语言提供清晰、高保真的指令。例如，设计的 HTML mockup 通常比一段设计描述或一张截图产出更好的结果。

## 试试做减法

横跨你的 system prompt、skills 与 CLAUDE.md 文件，你可能也需要像我们一样做减法。我们推出了新命令 `claude doctor`，可以帮你自动完成这件事。关于给更先进模型写提示词的更多细节，见我们的 [Fable field guide](https://claude.com/blog/a-field-guide-to-claude-fable-finding-your-unknowns)。

*本文由 Anthropic 技术团队成员 Thariq Shihipar 撰写。*
