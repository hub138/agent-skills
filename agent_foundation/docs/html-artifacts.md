# 使用 Claude Code：HTML 出乎意料的有效（Using Claude Code: The unreasonable effectiveness of HTML）

- 原文：[Using Claude Code: The unreasonable effectiveness of HTML](https://claude.dev/blog/using-claude-code-the-unreasonable-effectiveness-of-html/)
- 来源：Anthropic（claude.dev Blog），作者 Thariq Shihipar
- 发布：2026-05-20
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 claude.dev /media/ 绝对直链并配中文短描述；五个使用场景与示例 prompt 完整翻译。

Claude Code 团队成员如何以及为何用 HTML 取代 Markdown，产出更丰富、更可读、更易分享的输出。

Markdown 已经成为 agent 与人类沟通的主流文件格式。它简单、可移植、有一定富文本能力，还容易编辑。Claude 甚至已经出奇地擅长在 Markdown 文件里用 ASCII 画图。

但随着 agent 越来越强大，我发觉 Markdown 成了越来越受限的格式。具体来说：超过一百行的 Markdown 文件我很难读进去；我想让 Claude 生成更丰富的可视化、颜色与图表；我还想更容易地分享这些输出。

我还发现自己越来越多地不再亲自编辑这些文件，而是把它们当作规格说明与参考文件使用。真要改时，通常是让 Claude 去改，这把 Markdown 最大的优势之一也消掉了。

于是我开始更喜欢用 HTML 作为输出格式，并越来越多地看到 Claude Code 团队的其他成员也在应用这个模式。本文分享我们团队为什么以及如何用 HTML 产出更丰富、更可读的 Claude Code 输出。想跟着做的话，也可以直接使用这些常见场景的 [HTML 文件模板](https://thariqs.github.io/html-effectiveness/#code-review)。

## 为什么用 HTML

以下几件事让 HTML 比 Markdown 更适合我如今用 Claude Code 做的工作，包括那些需要或涉及以下能力的任务：

### 信息密度

![一个 HTML 文件能承载的八类信息：表格、设计、插图、代码、交互、工作流、空间布局与图片。](https://claude.dev/media/2adbcc628e8e032bd17f932e46641d462fb8409cc534d8383eff51b578b75c88.png)

HTML 能传达比 Markdown 丰富得多的信息。它当然能做标题、格式这类简单文档结构，还能表达各种各样的其他信息：

- 表格形式的列表数据

- 用 CSS 表达设计数据

- 用 SVG 画插图

- 用 script 标签装代码片段

- 用 HTML 元素加 javascript 与 CSS 做交互

- 用 SVG 与 HTML 表达工作流

- 用绝对定位与 canvas 表达空间数据

- 用图片标签贴图

在我看来，几乎不存在 Claude 能读而你无法用 HTML 高效表达的信息。这使它成为模型向你传达深度信息、以及你审阅这些信息的高效通道。

我发现当表达不了的时候，模型会在 Markdown 里做更低效的替代，例如 ASCII 图，或者我最喜欢的：用 unicode 字符估算颜色。

![一份调色板在 Markdown 代码块里用 ASCII 渲染：十六进制色值旁边是充当色块的阴影字符。](https://claude.dev/media/518a129fc56fba5dedb9a99265322c521997219a152349f2bdb2fd6a8a307425.png)

*图注：**FIG A** 只有 Markdown 可选时，调色板只能长这样。*

### 视觉清晰与易读

![同一份支付服务规格说明的两版形态。Markdown 版：240 行的标题与正文文件，需要一路滚动。HTML 版：带 Overview、API 与 Rollout 标签页的页面，含延迟目标提示块、按地区的流量图表与待定问题清单。](https://claude.dev/media/ba99cabcc8425efafb8240517951542dd40c825d1b902bc4ccdae9cef3981a22.png)

随着 Claude 能承担更复杂的工作，它写出的规格说明与计划也越来越大。我发现自己实际上不会去读超过 100 行的 Markdown 文件，也几乎不可能让组织里的其他人读。

但 HTML 文档读起来容易得多，因为 Claude 可以在视觉上组织结构，用标签页、插图与链接做出理想的导航。它甚至可以做移动端自适应，让你在不同设备形态上有不同的读法。

### 易于分享

Markdown 文件很难分享，因为大多数浏览器不能原生渲染它。你经常得把它作为附件加进邮件或消息。

只要把 HTML 文件上传，就可以[轻松分享链接](https://claude.com/resources/articles/artifacts-in-claude-code)。同事随处打开，也容易引用。

你的规格说明、报告或 PR 说明如果是 HTML，别人真正去读的概率会高得多。

### 双向交互

![一个 checkout-button.html 页面，带悬停动画时长、缩放与阴影模糊的滑块、弹性缓动开关与「复制为 prompt」按钮；复制出的参数粘贴进 Claude Code，更新 CheckoutButton.tsx。](https://claude.dev/media/6bd2866c31e53bad12b2d70bf74e4ad0de4067f464ecc6b33bc00d5d7ae4a8e6.png)

HTML 还允许你[与文档交互](https://x.com/trq212/status/2017024445244924382)。例如，你可以让它加滑块或旋钮来调整设计，或让你微调算法里的不同选项看看会发生什么。你还可以让它提供一个复制按钮，把这些修改复制成 prompt，再粘回 Claude Code。

有用的时候，这能让你为手头的问题创建专门的编辑环境。

### 数据摄取

用 Claude Code 而非 Claude.ai 或 [Claude Design](https://claude.com/product/design) 来生成 HTML 文件，最大的理由之一是 Claude Code 能摄取的上下文。例如写这篇文章时，我让 Claude Code 读我的代码文件夹，找出我生成过的全部 HTML 文件，分组分类，然后生成一个用图表展示每种类型的 HTML 文件。你在本文里看到的图就是那次过程的直接产物。

除了文件系统，Claude Code 还能通过你的 MCP（如 Slack、Linear 等）、你的网页浏览器（用 [Claude in Chrome](https://claude.com/claude-in-chrome)）以及你的 git 历史找到更多上下文。

## 上手起步

值得注意的一点：要让 Claude 生成这样的 HTML，你不需要做多少事。直接在 prompt 里说「做一个 HTML 文件」或「做一个 HTML artifact」就行。关键在于想清楚你要这个 artifact 做什么、你会怎么用它。时间久了，可以考虑[围绕反复出现的模式构建 skill](https://claude.dev/blog/lessons-from-building-claude-code-how-we-use-skills/)，但从裸 prompt 开始摸索，是感受它在不同场景下如何工作的好办法。

## 使用场景

为了让这个方法更具体，下面是我认为用 HTML 文件比 Markdown 更合适的[示例场景](https://thariqs.github.io/html-effectiveness/)。也可以跟着这个 [GitHub 画廊](https://github.com/anthropics/html-effectiveness)看这些场景的实例。

### 规格说明、计划与探索

HTML 是让 Claude 深入问题的丰富画布。我开始处理一个问题时，预期产出的会是一张 HTML 文件网络，而非一份简单的 Markdown 计划。例如，我可以先让 Claude Code 头脑风暴并生成几种不同选项的探索稿。然后让它往其中一个深入展开，也许做出 mockup 或界面形态的示例。最后感觉不错时，再让它写实现计划。计划满意后，我新开一个会话，把这些文件全部传入让它实现。

验证阶段我也会让验证 agent 读入这些文件，它对需要什么会有宽广得多的上下文。

![标题为「Pick an approach」的 HTML 页面，把防抖搜索的三种方案作为 A、B、C 卡片并排铺开，各带代码与利弊；B 被选中。](https://claude.dev/media/d4f2739204ee8c10555643038abdbf5783144dc4da089051100d49efd93da15f.png)

*图注：**FIG B** 探索：几种方案连同取舍并排放在一页里。*

**示例 prompt：**

- 「我不确定入职界面该往哪个方向走。生成 6 种截然不同的方案，布局、语气、密度都要变化，作为一份 HTML 文件用网格铺开，让我并排比较。每个方案标注它做出的取舍。」

- 「用 HTML 文件写一份详尽的实现计划，务必做一些 mockup，展示数据流向，加上我可能想审阅的关键代码片段。让它易读易消化。」

**适用：**

- 探索同一段代码的其他实现方式

- 一次实验多种视觉设计

### 代码评审与理解

代码在 Markdown 文件里很难读，而用 HTML 可以渲染 diff、批注、流程图与模块。用 HTML 理解 agent 写的代码、评审代码，或向评审你代码的人解释一个 PR。

![PR #482 的 HTML 代码评审，展示 lib/session.ts 的 diff，边缘批注附着在具体行上，标记为 blocking、nit 与 nice。](https://claude.dev/media/73ee6f9cc3027b599d59b0c54dce81a62bc02fc9d1c22474d6909f22c68752fe.png)

*图注：**FIG C** 代码评审：diff 渲染出来，边缘是按严重程度标记的批注。*

**示例 prompt：**

「帮我评审这个 PR，做法是创建一个描述它的 HTML artifact。我不太熟悉 streaming/backpressure 逻辑，所以重点放在那里。渲染真实 diff 并带行内边缘批注，按严重程度给发现标色，再加任何有助传达概念的东西。」

**适用：**

- 创建 PR

- 评审 PR

- 理解代码里的某个主题

### 设计与原型

Claude Design 以 HTML 为基础，因为 HTML 在设计上表达力极强，即使你最终的平台不是 HTML。Claude 可以先用 HTML 草拟设计，再用你选择的语言实现，React、Swift 等都行。

你还可以做交互原型，例如动画、动作等。可以考虑让 Claude 做滑块、旋钮等控件，精确调出你要的效果。

![一个 web 应用的设计 token 页面：带名称与十六进制值的色板、字号阶梯、间距阶梯与 primary、secondary、ghost 按钮。](https://claude.dev/media/e63f469938d9231d5081a2a5b0a654d1dfe1e714cca971b71e81781255a99904.png)

*图注：**FIG D** 设计：token 与组件按它们实际的样子渲染。*

**示例 prompt：**

「我想给新的结账按钮做原型，点击后播放一段动画然后快速变紫。创建一个 HTML 文件，带多个滑块与选项让我试不同的动画参数，再给我一个复制按钮，把效果好的参数复制出来。」

**适用：**

- 创建设计系统产物

- 调整组件

- 可视化组件库

- 做动画原型

### 报告、研究与学习

Claude Code 非常擅长跨多个数据源汇总信息并转成可读报告。你可以让 Claude 检索你的 Slack、代码库、git 历史或互联网，用它生成易读的报告。

可以组装成一份长 HTML 文档、一个交互式讲解页，甚至一份幻灯片。让 Claude 用 SVG 画图帮助可视化。

![标题为「How rate limiting works」的讲解页，带目录、TL;DR、四个可折叠的请求路径步骤（链接到源码行）、已读文件清单与标签页式的配置片段。](https://claude.dev/media/8190e029a7a24a3b92f02ec719cd7a76c6d21323abe0a878e34b1bf883dad609.png)

*图注：**FIG E** 报告：带导航、可折叠步骤与标签页片段的讲解页。*

**示例 prompt：**

「我不明白我们的限流器到底怎么工作。读相关代码并产出单个 HTML 讲解页：一张令牌桶流程图、三四段带批注的关键代码片段、底部一个 gotchas 节。为只读一遍的读者优化。」

**适用：**

- 写功能总结

- 生成讲解文档

- 起草周状态报告

- 写事故报告

- 产出 SVG 插图、流程图与技术图表

### 定制编辑界面

有时很难在纯文本框里描述你要什么。对这类场景，我常让 Claude 给我搭一个一次性编辑器，只服务于我正在处理的那件事：它既算不上产品，也算不上可复用工具，只是一个为这一份数据量身定制的单个 HTML 文件。

诀窍总是在结尾加一个导出：一个「复制为 JSON」或「复制为 prompt」按钮，把我在界面里做的修改变回可以粘进 Claude Code 或提交进文件的东西。你保持在循环里，而循环收紧了许多。

![flags.yaml 编辑器渲染成表单，开关按 streaming 与 billing 分组，某个开关上有依赖警告，另有「Copy diff」按钮；剪贴板里只有两个变更的键加上一段可粘进 Claude 的 prompt。](https://claude.dev/media/b8592b3b6ec79401ee1f46ac6aa9da9b96fb4b6ecd630c03eacf255211da9067.png)

**示例 prompt：**

- 「我需要重排这 30 张 Linear 工单。给我一个 HTML 文件，每张工单是可拖动的卡片，分 Now / Next / Later / Cut 四列。先按你的最佳判断预排序。加一个「复制为 Markdown」按钮，导出最终排序，每个桶带一行理由。」

- 「这是我们的 feature flag 配置。为它做一个表单式编辑器，按区域分组，展示开关之间的依赖，我启用一个前置开关未开的 flag 时要警告我。加一个「copy diff」按钮，只给我变更的键。」

- 「我在调这个 system prompt。做一个左右对照编辑器：左边可编辑的 prompt，变量槽高亮；右边三个示例输入，实时重新渲染填好的模板。加字符与 token 计数器，再加复制按钮。」

**适用：**

- 对任何东西重排、triage 或分桶（工单、测试用例、反馈）

- 编辑有约束的结构化配置（feature flags、环境变量、JSON/YAML）

- 带实时预览地调 prompt、模板或文案

- 整理数据集：逐行批准或否决、给示例打标、导出选择

- 给文档、转录或 diff 加批注并导出批注

- 挑选用文字表达很痛苦的那些值：颜色、缓动曲线、裁剪区域、cron 表达式、正则

## 常见问题

这些是我最常被问到的关于在 Claude Code 里用 HTML 的问题，连同我定下的日常习惯：

### 不是更低效吗

Markdown 用的 token 通常更少，但我发现 HTML 增加的表达力、加上我真的会去读它的概率高得多，整体产出更好。在 Opus 4.7 的 1M 上下文窗口下，多出的 token 用量在上下文窗口里并不明显。

### 你现在还什么时候用 Markdown

老实说我几乎在所有事情上都停用 Markdown 了，不过我大概处在 HTML 极端主义者的那一端。

### 这是你取代计划的方式吗

我发现自己不再只有单一计划，而是为计划的不同部分与阶段持有几份不同的 HTML 文件。例如先做一份 HTML 实现计划，再做一个 UI 探索文件，最后做一个列出全部设计的 HTML 组件页。我倾向把这些文件留作将来的参考，也用于验证。

## 与 Claude 保持同步在线

以上的一切归结为一句话：我用 HTML 取代 Markdown 的真正原因是它让我感觉与 Claude 更加同步在线。随着 Claude 承担越来越多，我发觉自己读计划越来越不仔细，我需要一种方式保持对它的选择的参与，而非只是放手。HTML 恰好就是那个答案。我比以往任何时候都更在循环里。

从 [Claude Code](https://claude.com/product/claude-code) 开始。

*本文由 Thariq Shihipar（member of technical staff）撰写，表达他个人对在 Claude Code 里使用 HTML 文件的观点与喜爱。*
