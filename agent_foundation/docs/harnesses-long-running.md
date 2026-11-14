# 长时运行 agent 的高效 harness（Effective harnesses for long-running agents）

- 原文：[Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents)
- 来源：Anthropic Engineering，作者 Justin Young
- 发布：2025-11-26
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图（gif），地址为原文 CDN 直链；原文的失败模式对照表已重组为连续表格。

随着 AI agent 能力增强，开发者越来越多地要求它们承担跨越数小时乃至数天的复杂任务。然而，让 agent 在多个上下文窗口之间保持稳定的进度推进，仍是一个未解决的问题。

长时运行 agent 的核心挑战在于：它们必须在离散的会话里工作，每个新会话开始时对之前发生的事毫无记忆。想象一个软件项目由轮班的工程师承担，每个新到岗的工程师对上一班发生了什么毫无印象。上下文窗口有限，多数复杂项目又无法在单个窗口内完成，agent 需要一种方式跨越会话之间的缝隙。

我们发展了一套两段式方案，让 [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) 能跨多个上下文窗口有效工作：一个 initializer agent 负责首次运行时搭建环境，一个 coding agent 负责在每个会话里推进增量进展，并为下一个会话留下清晰的产物。代码示例见配套的 [quickstart](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding)。

## 长时运行 agent 的问题

Claude Agent SDK 是一个强力、通用的 agent harness，擅长编码以及其他需要模型用工具收集上下文、规划、执行的任务。它具备 compaction 这类上下文管理能力，让 agent 能持续工作而不耗尽上下文窗口。理论上，凭这套设置，agent 应该能任意长时间地持续做有用的工作。

然而 compaction 不够。开箱即用的情况下，即使是 Opus 4.5 这样的前沿编码模型在 Claude Agent SDK 里跨多个上下文窗口循环运行，如果只拿到「做一个 [claude.ai](http://claude.ai) 的克隆」这种高层提示词，也做不出生产质量的 web 应用。

Claude 的失败呈现两种形态。其一，agent 倾向于一次做太多：本质上想一口气把整个应用写完。这常导致模型在实现中途耗尽上下文，下一个会话接手时面对一个实现到一半、没有文档的特性。agent 只能去猜之前发生了什么，再花大量时间让基础应用重新跑起来。即便有 compaction，这种情况仍会发生，压缩并不总能把完全清晰的指令传递给下一个 agent。

第二种失败形态常出现在项目后期。一些特性已经建成之后，后一个 agent 实例环顾四周，看到已有进展，就宣布任务完成。

这样问题分解成两部分。第一，需要搭建一个初始环境，为提示词要求的全部特性打好地基，让 agent 从一开始就按步推进、逐特性推进。第二，应提示每个 agent 向目标做增量推进，同时在会话结束时把环境留在干净状态。干净状态指适合合入主分支的代码形态：没有重大 bug，代码整洁、文档齐全，开发者可以直接开始做新特性，无需先清理无关的烂摊子。

内部实验时，我们用两部分方案解决这些问题：

1. initializer agent：第一个 agent 会话使用专门的提示词，要求模型搭建初始环境：一个 `init.sh` 脚本、一个记录 agent 们做过什么的 claude-progress.txt 文件、一个展示新增文件的初始 git commit。
2. coding agent：此后每个会话要求模型做增量推进，然后留下结构化的更新记录。[1](#footnote-1)

这里的关键洞见是找到一种方法，让 agent 在带着全新上下文窗口开始时能快速理解工作状态，办法就是 claude-progress.txt 文件配合 git 历史。这些实践的灵感来自对高效软件工程师日常工作方式的观察。

## 环境管理

在更新后的 [Claude 4 prompting guide](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices#multi-context-window-workflows)里，我们分享了多上下文窗口工作流的一些最佳实践，包括「第一个上下文窗口用不同提示词」的 harness 结构。这个「不同的提示词」要求 initializer agent 把环境搭好，装上后续 coding agent 高效工作所需的全部上下文。这里深入展开这套环境的几个关键组件。

### 特性清单

针对 agent 一口气写完整个应用、或过早认为项目完成的问题，我们提示 initializer agent 写一份全面的特性需求文件，把用户的初始提示词展开。在 [claude.ai](http://claude.ai) 克隆的例子里，这意味着 200 多个特性，比如「用户可以打开新对话、输入查询、按回车、看到 AI 回应」。这些特性初始全部标记为 failing，让后续 coding agent 对「完整功能长什么样」有清晰的轮廓。

```
{
    "category": "functional",
    "description": "New chat button creates a fresh conversation",
    "steps": [
      "Navigate to main interface",
      "Click the 'New Chat' button",
      "Verify a new conversation is created",
      "Check that chat area shows welcome state",
      "Verify conversation appears in sidebar"
    ],
    "passes": false
  }
```

我们提示 coding agent 编辑这个文件时只允许改 passes 字段的状态，并用强硬措辞：「删除或修改测试是不可接受的，因为这可能导致功能缺失或带 bug。」经过一些实验，我们选定用 JSON 承载，与 Markdown 文件相比，模型不恰当改动、覆盖 JSON 文件的可能性更小。

### 增量推进

有了这层初始环境脚手架，coding agent 的下一轮被要求一次只做一个特性。这种增量方式对纠正 agent「一次做太多」的倾向至关重要。

一旦进入增量模式，模型在每次改动代码后把环境留在干净状态仍然关键。实验中，诱发这个行为的最好方式是要求模型用描述性的提交信息把进展提交到 git，并在进度文件里写下总结。这让模型可以用 git 撤销坏的代码改动，恢复代码库的可用状态。

这些做法也提升了效率，agent 不必再猜之前发生了什么，也不必把时间花在让基础应用重新跑起来上。

### 测试

我们观察到的最后一个主要失败形态，是 Claude 倾向于在没有充分测试时就把特性标记为完成。没有显式提示时，Claude 会改代码，甚至用单元测试或对开发服务器的 `curl` 命令做测试，但意识不到这个特性端到端并不工作。

在构建 web 应用的场景里，一旦显式提示 Claude 使用浏览器自动化工具、像人类用户一样做全部测试，它在端到端验证特性上就做得很好。

![浏览器自动化测试示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/f94c2257964fb2d623f1e81f874977ebfc0986bc-1920x1080.gif)

给 Claude 提供这类测试工具大幅改善了表现，agent 能识别并修复只看代码不明显的问题。

仍有一些遗留问题，比如 Claude 的视觉能力与浏览器自动化工具的限制，使识别每一类 bug 变得困难。例如 Claude 通过 Puppeteer MCP 看不到浏览器原生的 alert 弹窗，依赖这类弹窗的特性因此更容易带 bug。

## 进入状态

以上都就位后，每个 coding agent 都被提示先跑一组步骤来定位自己，有些相当基础但仍然有用：

1. 运行 `pwd` 查看自己工作的目录。你只能编辑这个目录里的文件。
2. 读 git 日志与进度文件，了解最近在做什么。
3. 读特性清单文件，挑一个尚未完成的最高优先级特性来做。

这个方式为 Claude 在每个会话里省下 token，它不必再自己摸索怎么测试代码。让 initializer agent 写一个能启动开发服务器的 init.sh 脚本也有帮助，coding agent 在实现新特性前先跑一遍基础的端到端测试。

在 claude.ai 克隆的例子里，这意味着 agent 总是先启动本地开发服务器，用 Puppeteer MCP 开新对话、发消息、收回应。这确保 Claude 能快速识别应用是否被留在损坏状态，并立即修复既有 bug。如果 agent 直接开始实现新特性，问题大概率会恶化。

一切就绪后，一个典型会话的开头是这样的：

```
[Assistant] I'll start by getting my bearings and understanding the current state of the project.
[Tool Use] <bash - pwd>
[Tool Use] <read - claude-progress.txt>
[Tool Use] <read - feature_list.json>
[Assistant] Let me check the git log to see recent work.
[Tool Use] <bash - git log --oneline -20>
[Assistant] Now let me check if there's an init.sh script to restart the servers.
<Starts the development server>
[Assistant] Excellent! Now let me navigate to the application and verify that some fundamental features are still working.
<Tests basic functionality>
[Assistant] Based on my verification testing, I can see that the fundamental functionality is working well. The core chat features, theme switching, conversation loading, and error handling are all functioning correctly. Now let me review the tests.json file more comprehensively to understand what needs to be implemented next.
<Starts work on a new feature>
```

## 失败形态与对策

| 问题 | initializer agent 的行为 | coding agent 的行为 |
| --- | --- | --- |
| Claude 过早宣布整个项目完成 | 搭建特性清单文件：依据输入规格建一个结构化 JSON 文件，列出端到端特性描述 | 会话开始时读特性清单文件，挑单个特性开始做 |
| Claude 把环境留在带 bug 或无进度记录的状态 | 写入初始 git 仓库与进度笔记文件 | 会话开始时读进度笔记与 git 提交日志，对开发服务器跑基础测试抓未记录的 bug；会话结束时写 git 提交与进度更新 |
| Claude 过早把特性标记为完成 | 搭建特性清单文件 | 自行验证全部特性，只在仔细测试后才标记为 passing |
| Claude 得花时间摸索怎么运行应用 | 写一个能启动开发服务器的 `init.sh` 脚本 | 会话开始时读 `init.sh` |

## 未来工作

这项研究展示了长时运行 agent harness 的一套可行方案，让模型能跨多个上下文窗口做增量推进。不过仍有开放问题。

最突出的是：单个通用 coding agent 是否在各场景下都表现最好，还是用多 agent 架构能取得更好成绩。专门的 agent（测试 agent、质量保障 agent、代码清理 agent）在软件开发周期的子任务上可能做得更好，这看起来合理。

此外，这个演示针对全功能 web 应用开发做了优化。把结论推广到其他领域是未来方向。这些经验里的部分或全部，大概率也适用于科研或金融建模等场景所需的长时运行 agentic 任务。

## 注释

1 我们在这里把它们称作不同的 agent，仅仅因为它们的初始用户提示词不同。系统提示词、工具集与整体 agent harness 其他方面完全一致。

## 作者与致谢

本文由 Justin Young 撰写。特别感谢 David Hershey、Prithvi Rajasakeran、Jeremy Hadfield、Naia Bouscal、Michael Tingley、Jesse Mu、Jake Eaton、Marius Buleandara、Maggie Vo、Pedram Navid、Nadine Yasser、Alex Notov 的贡献。

这项工作反映了 Anthropic 多个团队的集体努力，是他们让 Claude 能安全地做长周期自主软件工程，尤其是 code RL 与 Claude Code 团队。有兴趣贡献的候选人欢迎投递 [anthropic.com/careers](http://anthropic.com/careers)。
