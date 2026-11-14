# 找到你的未知：Claude Fable 实战指南（A field guide to Claude Fable: Finding your unknowns）

- 原文：[A field guide to Claude Fable: Finding your unknowns](https://claude.com/resources/articles/a-field-guide-to-claude-fable-finding-your-unknowns)
- 来源：Anthropic（claude.com），作者 Thariq Shihipar
- 发布：2026-07-06
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 assets.claude.com 绝对直链并配中文短描述；未知四象限与三阶段九技术及全部示例 prompt 完整翻译；文末署名保留。

---

使用 Claude Code 时，我经常想起地图与疆域之别。

地图是待办工作的表示，是我的 prompt、skill 与 context，即我交给 Claude 的东西。疆域是工作真正发生的地方：代码库、现实世界、实际存在的约束。

![地图与疆域：prompt 与 skill 是地图，代码库与现实约束是疆域](https://assets.claude.com/0c9ef5f6d0bb96e0267b77ae7ec4ee3249a71778.png)

地图与疆域之间的差距，我称之为 unknowns（未知）。Claude 撞上一个未知时，需要基于对我意图的最佳猜测做决策。工作量越大，Claude 可能撞上的未知越多。

Claude Fable 是第一个让我发现工作质量瓶颈在我澄清未知能力的模型。

重要的是，只提前规划并不总是够用。未知可能藏在实现深处，也可能指向一个事实：这个问题的正确解法其实是另一种完全不同的做法。

我逐渐发现，与 Fable 协作是一个迭代过程：在实施前、实施中、实施后持续发现自己的未知。

## 认识你的未知

你的未知是什么？带着一个问题来找 Claude 时，我倾向于把它分解成四类：

- **Known Knowns（已知的已知）**：本质上是 prompt 里的内容。我告诉了 agent 我要什么？

- **Known Unknowns（已知的未知）**：还没解决、但自己清楚没解决的问题。

- **Unknown Knowns（未知的已知）**：显然到自己根本不会写下来、可是一见就能认出的东西。

- **Unknown Unknowns（未知的未知）**：完全没考虑过的东西。我有哪些不知道自己不具备的知识？我知道一样东西可以好到什么程度吗？

最好的 agentic coder 未知相对少。看 [Boris](https://www.linkedin.com/in/bcherny) 或 [Jarred](https://www.linkedin.com/in/jarred-sumner-a8772425) 写 prompt，我能明显看出他们知道自己要什么，细节到位。他们与代码库和模型行为都深度同步。

![未知四象限示意](https://assets.claude.com/c0977293cee11764842764e05ae2802892000439.png)

但他们也假定未知存在。从很多角度看，减少并规划自己的未知，就是 agentic coding 的技能本身。幸运的是，这项技能可以练，方法是和 Claude 一起工作。

## 帮 Claude 帮你

![帮 Claude 帮你：三阶段九技术总览](https://assets.claude.com/55cc5d145a4c9a517e6bc1e7d94240c230b4120f.png)

给 Claude 下指令是一种微妙的平衡。指令太具体，即使更合适的做法是转向，Claude 也会一路跟随你的指令走下去。指令太含糊，Claude 常会按行业最佳实践做选择与假设，而这些可能不适配你的任务。

不盘点自己的未知，两个方向都会失败。你不知道哪条路会布满障碍，也不知道哪条路会畅通无阻、而你仍想让 Claude 转向。

Claude 能帮你更快发现未知。它能极快检索你的代码库和整个互联网，对多数话题的了解远超你，从失败中迭代的速度也更快。

这个过程最重要的部分，是给 Claude 交代你的起点。例如告诉它你的思考进行到哪一步，说明你对该问题与代码库的熟悉程度，让它像思考伙伴一样和你一起工作。

下文详述我用来揭示这些未知的部分模式，包括：

**实施前：**

- 盲点扫描（Blind spot pass）

- 头脑风暴与原型（Brainstorms and prototypes）

- 访谈（Interviews）

- 参考物（References）

- 实现计划（Implementation Plans）

**实施中：**

- 实施笔记（Implementation Notes）

**实施后：**

- 提案与讲解（Pitches and explainers）

- 测验（Quizzes）

## 实施前

### 盲点扫描

开工时最有用的动作之一，是弄清自己的盲区。比如你要在代码库的一片新区域写功能，或者让 Claude 帮你做不熟悉的工作（迭代一个设计），你大概率有大量 **unknown unknowns**。

你可能不知道该问什么问题，不知道做成什么样算好，不知道这块历史上做过什么，也不知道要避开哪些坑。

这些情况下，可以请 Claude 帮你找出你的 unknown unknowns 并讲解给你。我喜欢直接用「blind spot pass」和「unknown unknowns」这两个字面词。向它交代你是谁、你知道什么，通常对 Claude 理解怎样开始与你协作很重要。

**示例 prompt：**

- 「我要新增一个 auth provider，但对这个代码库的 auth 模块一无所知。能不能做一次 blind spot pass，帮我找出相关的 unknown unknowns，让我能把 prompt 写得更好。」

- 「我不知道什么是 color grading，但需要给这个视频调色。能不能教我理解 color grading 方面的 unknown unknowns，让我能写出更好的 prompt？」

### 头脑风暴与原型

在 **unknown knowns** 密集的区域工作时——也就是那些只有见了才知道如何定义的标准——我喜欢请 Claude 和我一起头脑风暴、做原型。

在原型期识别并说出 unknown knowns 极有价值，因为到实施期才发现它们的代价（相对）昂贵。功能或规格的小改动可能导致代码实现大变，agent 撤销先前改动也更困难。

比如你可能只想看看某个按钮加进某个界面后的样子，不必接好后端路由，也不必在前端维护额外状态。

再比如视觉设计，对我来说难以言表，但见了就知道自己要什么。这类情况我会要求对一个产物给出几种设计方向。

我几乎每个编码会话都以探索或头脑风暴开场。这让我带着定义项目范围的意图启动。Claude 经常找到我本来会错过的高价值方案，有时也会只见树木不见森林。头脑风暴防止我把范围定得过窄或过宽。

**示例 prompt：**

- 「我想为这份数据做一个 dashboard，但我毫无视觉品味，也不知道有哪些可能。给我一个 HTML 页面，放 4 个风格截然不同的设计方向，我来挑。」

- 「先别接任何真实数据，做一个单 HTML 文件，用假数据画出新的编辑器工具栏。我想在你动真实应用之前先对布局表态。」

- 「我的问题大致是：用户在完成 onboarding 后流失。检索代码库，头脑风暴 10 个可以干预的位置，从成本最低到最有雄心排序。我会告诉你哪些打动我。」

### 访谈

头脑风暴做到一定程度，我多半仍有未知。

这时我请 Claude 就任何未知或含糊之处访谈我。请 Claude 访谈你时，尽量给它问题的背景信息，引导它提问的方向。

**示例 prompt：**

- 「一次一个问题地访谈我，问任何含糊的地方，优先问我的回答会改变架构的问题。」

### 参考物

有时你无法详细描述自己要什么。比如缺乏相应的语言，或者内容复杂到要花很久才讲得清。

这时最好的办法是参考物。图示、文档、图片都可以，但绝对最好的参考物是源代码。

如果你有一个以某种方式实现了某功能的库，或一个你特别中意的设计组件，直接把文件夹指给 Fable，告诉它该看什么，即使那是另一种语言。相比截图，这能给 Claude 提供丰富得多的标记与结构细节。

**示例 prompt：**

- 「vendor/rate-limiter 里的这个 Rust crate 实现的正是我要的 backoff 行为。读懂它，在我们的 TypeScript API client 里重新实现同样的语义。」

### 实现计划

觉得自己可以动手时，我通常请 Claude 拟一份实现计划供我审阅。计划聚焦最可能变动的部分，比如数据模型、类型接口、UX 流程。这能让 Claude 把我实际可能需要调整的东西先暴露出来。

**示例 prompt：**

- 「写一份 HTML 格式的实现计划，把我最可能想调整的决策放在最前面：数据模型改动、新的类型接口、一切用户可见的东西。机械重构放最底部，那部分我信任你。」

## 实施中

### 实施笔记

对计划满意后，我新开一个会话，把全部产物传进 prompt。这给 Claude 一个干净的 context window，同时带着规划阶段编译出的全部信息。比如我会传入一份规格文件和一个原型，请一个 agent 实施。

但实情是无论规划多充分，总有 unknown unknowns 潜伏。agent 可能在工作中发现代码里的某个边缘情况，需要换一条路走。

我请 Claude Code 维护一个临时的 implementation-notes.md（或 .html）文件，记录它做的决策，供下一次尝试学习。

**示例 prompt：**

- 「维护一个 implementation-notes.md 文件。遇到迫使你背离计划的边缘情况时，选保守项，把它记在 Deviations 下，然后继续。」

## 实施后

### 提案与讲解

交付一个东西最重要的环节之一，是拿到认同与审批。在最终文档里构建提案与讲解产物有助于：

- 评审者与你带着同样的未知起步时，加速他们理解

- 专家想确认你考虑过他们预期中的未知与常见失败点时，加速审批

**示例 prompt：**

- 「把原型、规格和实施笔记打包成一个文档，让我能直接发到 Slack 赢得认同。以 demo GIF 开头。」

### 测验

一次长会话下来，Claude 做成的东西可能远超我意识到的量。只读代码 diff 只能给我浅层理解，因为许多行为依赖既有代码路径。

给足背景之后请 Claude 就这次改动考我，帮我弄懂发生了什么。测验满分我才合并。

**示例 prompt：**

- 「我要确认自己理解了这次改动的全部内容。给我一份 HTML 报告讲解这些改动，带背景、直觉、做了什么等等，底部放一个测验，我必须通过。」

## 融会贯通：发布 Fable

[Fable 的发布视频](https://x.com/ClaudeDevs/status/2064399512664526853)从始至终用 Claude Code 剪辑。这对我来说是全新领域，我完全算不上内行。

所以我从自己已知的东西出发。我知道 Claude 能用代码剪辑视频、转录语音，但不确定准确度够不够。于是我请 Claude 讲解 Whisper 这类转录的工作原理，以及用 ffmpeg 能不能准确切掉语气词或大段停顿。

我想让 Claude 做一个与我的语音词句同步的 UI，但不确定可行，就请它用 Remotion 加一份转录做一个原型视频，看行不行。

最后，视频画面看起来有点闷，我知道这是 color grading 的结果，但我并不真正懂 color grading。第一轮尝试是让 Claude 做几个变体供我挑，随后我意识到，color grading 的「好」长什么样我并不知道。于是我改请 Claude 教我 color grading，借此发现自己的未知。

## 让地图匹配疆域

模型越强，用对方法能达成的越多。一个长周期任务的结果不对时，多半你需要花更多时间定义自己的未知，或拟一份允许你和 Claude 在未知中随机应变的实现计划。

每一次讲解、头脑风暴、访谈、原型、参考物，都是在修复代价变昂贵之前，廉价找出自己不知道的东西的途径。

所以，下一个项目从请 Claude 帮你找未知开始。

关于与 Fable 世代模型协作中 context 一侧的做法，见[《Claude 5 世代模型的上下文工程新规则》](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)。

*本文由 Thariq Shihipar 撰写，Anthropic 技术团队成员（member of technical staff）。*
