# 每个任务都有专属 harness：Claude Code 的动态工作流（A harness for every task: dynamic workflows in Claude Code）

- 原文：[A harness for every task: dynamic workflows in Claude Code](https://claude.dev/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code/)
- 来源：Anthropic（claude.dev Blog），作者 Thariq Shihipar、Sid Bidasaria
- 发布：2026-06-02
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 claude.dev /media/ 绝对直链并配中文短描述；示例 prompt 与六个使用模式完整翻译。

Claude Code 现在可以现场编写并协调自己的多 agent harness。本文介绍动态工作流的运作方式，以及从中获得最大收益的种种模式。

上周，我们在 Claude Code 里发布了[动态工作流](https://code.claude.com/docs/en/workflows)。Claude 现在可以针对手头的任务现场编写自己的 [harness](https://code.claude.com/docs/en/glossary#agentic-harness)，按任务定制。

默认的 [Claude Code](https://claude.com/product/claude-code) harness 为编码而构建，但它对许多其他类型的任务同样有用，因为事实证明，许多任务与编码任务形态相似。不过对某些类别的任务，我们一直需要在 Claude Code 之上构建定制 harness 才能达到最佳表现，例如 [Research](https://support.claude.com/en/articles/11088861-using-research-on-claude)、[安全分析](https://support.claude.com/en/articles/11932705-automated-security-reviews-in-claude-code)、[agent teams](https://code.claude.com/docs/en/agent-teams) 或 [Code Review](https://code.claude.com/docs/en/code-review)。

工作流让你动态构建架在 Claude Code 之上的 harness，让 Claude 更原汁原味地解决上述全部问题。你还可以与他人共享和复用这些工作流。

本文分享我最初的使用体验与心得，帮你充分用好工作流。请记住，最佳实践仍在成形：动态工作流消耗的 token 通常更多，最适合复杂、高价值的任务。

## 示例 prompt

在深入技术细节之前，先给出几组示例 prompt，让你开始思考工作流的可能性：

「这个测试大约 50 次运行里失败 1 次。搭一个工作流去复现它。围绕这场竞争提出多个对立理论，直到只有一个理论经得起证据检验才停手。」

「用一个工作流翻完我最近 50 个会话，挖出我反复做出的纠正，把高频出现的那部分变成 `CLAUDE.md` 规则。」

「用一个工作流翻 Slack 的 #incidents 频道过去六个月的内容，找出反复出现却没人建单的根因。」

「拿我的商业计划跑一个工作流，让不同的 agent 分别从投资人、客户、竞争对手的视角把它批得体无完肤。」

「这里有一份 80 份简历的文件夹，用一个工作流为后端岗位排序，并对前十名复核。用 AskUserQuestion 工具采访我，形成一份 rubric。」

「我需要给这个 CLI 工具起名。用一个工作流头脑风暴出一批候选，再办一场锦标赛选出前 3 名。」

「用一个工作流把我们的 User 模型改名为 Account，改动所有出现位置。」

「用一个工作流逐条核对我这篇博文草稿里的技术声明与代码库，我不想发布任何错误内容。」

## 动态工作流如何运作

动态工作流执行一个 JavaScript 文件，文件里带少数几个特殊函数，负责生成与协调 [subagent](https://code.claude.com/docs/en/sub-agents)：

![agent(prompt, opts) 函数与其选项标注：prompt 是唯一必填项，schema 返回校验过的 JSON，model 可选 opus、sonnet 或 haiku，isolation 可选 worktree 或 remote，agentType 选择某个 subagent。下方 parallel() 并发散开并等待全部完成；pipeline() 让每个条目流过每个阶段。](https://claude.dev/media/405c8b387ec2cc574e6d48edba5431e02e23e4fca7c31d51184fc9738eaef70b.png)

*图注：**FIG A** 工作流脚本的三个构建单元：agent() 生成一个 subagent；parallel() 与 pipeline() 组合多个。*

动态工作流还内置 JSON、Math、Array 等 JavaScript 标准函数，帮助处理数据。

特别值得知道的一点：动态工作流可以决定某个 agent 使用哪个模型，以及 subagent 是否在自己的 worktree 里运行，让 Claude 自行选择所需的智能层级与隔离程度。

如果工作流被中断（例如用户操作或退出终端），恢复会话后工作流会从停止处继续。

## 为什么需要动态工作流

让默认的 Claude Code harness 做任务时，它需要在同一个上下文窗口里既做计划又做执行。对许多编码任务来说这非常高效，但在长时运行、大规模并行、高度结构化或对抗性的任务上会出问题。

原因是 Claude 在单个上下文窗口里做复杂任务越久，就越容易受几种特定失败模式的影响：

- **Agentic laziness（agent 偷懒）**指 Claude 在完成一项复杂的多部分任务之前就停手，并在部分进展后宣布完工，例如 50 项安全审查只处理了 35 项。

- **Self-preferential bias（自我袒护）**指 Claude 倾向于认可自己的结果或发现，在被要求按 rubric 验证或评判自己的产出时尤其如此。

- **Goal drift（目标漂移）**指经过许多轮之后对最初目标的忠实度逐渐丢失，compaction 之后尤其明显。每一步摘要都是有损的，边缘情况要求或「不要做 X」这类边界条件可能被丢掉。

创建工作流有助于对抗这些问题，办法是协调多个各自拥有独立上下文窗口、目标聚焦且相互隔离的 Claude subagent。

## 动态与静态工作流

你以前可能用 Claude Agent SDK 或 `claude -p` 创建过静态工作流，把多个 Claude Code 实例协调在一起。

但静态工作流必须对所有边界情况都适用，所以通常更通用泛化。有了 [Claude Opus 4.8](https://www.anthropic.com/news/claude-opus-4-8) 与动态工作流，Claude 已经聪明到能为你的场景现场写一个量身定制的 harness。

![「我们该把结账服务迁移到新的提供商吗」这个问题用两种方式处理。静态 harness 跑五次网页搜索、抓取结果、验证并汇总成一份通用研究报告。动态工作流则读取计费代码、逐项功能对照新提供商的文档、按真实交易量定价、跑一轮魔鬼代言人评审，最终给出一份具体建议。](https://claude.dev/media/fb7abff3846443de3b59b23208f0019bad6eb2555e5dd945594438ce4ee143c1.png)

*图注：**FIG B** 静态 harness 对每个问题跑同样的步骤；动态工作流按眼前的问题塑形。*

## 使用动态工作流的有用模式

开始用动态工作流很简单：直接让 Claude 建一个，或者使用触发词「`ultracode`」确保 Claude Code 创建工作流。

但为动态工作流的运作方式建立心智模型，能帮你判断何时该用、以及如何通过 prompt 引导 Claude。

Claude 在构建工作流时会用到并组合以下几种常见模式：

![六个工作流模式的小示意图：classify-and-act、fanout-and-synthesize、adversarial verification、generate-and-filter、tournament、loop until done。](https://claude.dev/media/0a60d2d8c1dbddc23694ead5848908e1f2c9ef9e57ed0fbdbf53a0dc11e9ed16.png)

*图注：**FIG C** Claude 组合使用的六个工作流模式。*

### Classify-and-act（先分类再行动）

用一个 classifier agent 判定任务类型，再按类型路由到不同的 agent 或行为。也可以在结尾用 classifier 决定输出。

### Fan-out-and-synthesize（散开再汇总）

把任务分解成许多更小的步骤，每步跑一个 agent，再汇总这些结果。步骤数量庞大，或每步都受益于自己的干净上下文窗口（互不干扰、不交叉污染）时特别有用。汇总一步是一道屏障，它等待全部散开的 agent 完成，再把它们的结构化输出合并成一个结果。

### Adversarial verification（对抗性验证）

对每个生成的 agent，另跑一个专门生成的 agent，按 rubric 或标准对它的输出做对抗性验证。

### Generate-and-filter（生成再过滤）

围绕一个主题生成一批想法，再按 rubric 或验证环节过滤，去重后只返回质量最高、经过检验的想法。

### Tournament（锦标赛）

与其分割工作，不如让 agent 在工作上竞争。生成 N 个 agent，各自用不同方法尝试同一任务。随后由 prompt 或模型驱动裁判 agent 以两两对比较的方式评判结果，直到决出胜者。

### Loop until done（循环直到完成）

对工作量未知的任务，循环生成 agent 直到满足停止条件（没有新发现，或日志里不再有错误），用停止条件替代固定的轮数。

## 使用场景

创造性地想想何时以及如何让 Claude Code 创建动态工作流。我发现工作流对非技术工作有时甚至更有用。

### 迁移与重构

[Bun](https://bun.com/) 用工作流从 Zig 重写为 Rust。更多细节见 [Jarred 的推文串](https://x.com/jarredsumner/status/2060050578026189172)，也可以看我们在百万行代码库上跑 [AI 代码迁移](https://claude.com/blog/ai-code-migration)的方式。

关键在于把任务分解成一系列需要操作的单元，例如调用点、失败的测试、模块等。每个修复在 worktree 里派一个 subagent 去做，再让另一个 agent 做对抗性评审，然后合并。可以考虑告诉 agent 避开资源密集的命令，这样能在机器资源耗尽之前最大程度并行。

### 深度研究

我们在 Claude Code 内部发布了一个用动态工作流实现的深度研究 skill（`/deep-research`）。它散开网页搜索、抓取来源、对抗性验证其中的声明，并汇总出一份带引用的报告。

这类研究未必只针对网页搜索。例如让 Claude 从 Slack 里的上下文汇编一份状态报告，或通过深入探索一个代码库研究某个功能的实现方式。

### 深度验证

![一份报告流入声明提取器，散开到声明检查器 1 至 N，每个后面可选跟一个来源审计器，汇聚成一份已验证的报告。](https://claude.dev/media/14981a07d95b7a4f10f6e995e34ea589c6a87836a753f3ffd70047363adb34dd.png)

*图注：**FIG D** 深度验证：每条事实声明一个检查器 agent，每个后面可选跟来源审计器。*

反过来，如果你手上有一份报告，想核对并溯源其中引用的每条事实声明，可以生成这样一个工作流：先让一个 agent 识别全部事实声明，再给每条声明派一个 subagent 详查。你还可以让一个验证 agent 检查来源 subagent，确认它引用的来源质量足够高。

### 排序

![1000 个条目进入对阵表：第一轮两两配对，每次比较由一个全新 agent 执行，胜者进入第二轮，最后一次比较决出冠军，输出是一份排好序的列表。](https://claude.dev/media/be7b8dc2e6f8a2791efb3c4589fa182f0c90b380bb56d8b41a1f18fc7cb04394.png)

*图注：**FIG E** 锦标赛排序：每次比较都由一个全新 agent 执行，没有任何单个上下文需要装下全部 1000 个条目。*

你可能有这样一份清单，想按某种你确信 Claude Code 擅长评判的定性指标排序，例如按 bug 严重程度排支持工单。但如果你在一条 prompt 里塞 1000+ 行，质量会下降，上下文也装不下。正确做法是跑锦标赛：一条两两比较 agent 的流水线（比较评判比绝对打分更可靠），或并行分桶排名再归并。每次比较是独立的 agent，确定性的循环持有对阵表，上下文里只保留当前的运行顺序。

### 记忆与规则遵守

![一份 +142 行 −87 行的 diff 对照五条规则检查，每条规则一个验证 agent。两条规则在第 42 行与第 90 行标记了问题，其余规则返回干净。一个怀疑者 agent 重新阅读每处标记，把真实违规与误报分开，只留下确认的违规。](https://claude.dev/media/fd6d2a8544c5541442fb2df1c24374ff8e2984274cc2bf796fe5e632bfcc400a.png)

*图注：**FIG F** 逐规则评审：每条规则在干净的上下文里配一个验证器，再用怀疑者过滤标记。*

如果你有一组 Claude 总会遗漏或处理不好的规则，即便写进了 `CLAUDE.md` 也一样，可以创建这样一个工作流：列出必须由验证 agent 检查的规则清单，一条规则一个验证器。再创建一个怀疑者角色的 subagent 复查这些标记，确认它们真实成立，有助于避免过多误报。

反方向也成立：翻挖你最近的会话与代码评审意见，找出你反复做出的纠正，用并行 agent 聚类，对每个候选规则做对抗性验证（这条规则本可以防止一次真实错误吗），再把幸存者提炼回 `CLAUDE.md`。

### 根因调查

调试的最好方式是提出多个独立假设并逐一检验，但如果只用一个上下文窗口，Claude 会陷入自我袒护。

工作流可以从结构上防止这一点：生成多个 agent，从互不重叠的证据各自提出假设。例如日志、文件、数据分别由不同 agent 负责。随后每个假设面对一组验证者与反驳者。

这不止适用于代码。工作流可用于销售（三月销量为什么下滑）、数据工程（这条流水线为什么失败），或任何复盘类工作。

### 大规模 triage

![一批不可信的积压内容，包括支持工单、bug 报告与用户反馈，进入一个只读工具的隔离区，阅读 agent 在其中对每项分类、对照已跟踪内容去重、只输出结构化摘要。持有高权限工具的可信区里有一个行动 agent，只依据摘要行动，能修就尝试修复并开一个 PR，否则升级给人。/loop 让它持续运行。](https://claude.dev/media/ebf352766b6bb484729e8a8c08f9a72f918b19f78d02e998fe3384fcf3fd88e3.png)

*图注：**FIG G** 先隔离再行动：阅读 agent 接触不可信内容时不带任何权限；行动 agent 只见到它们的摘要。*

每个团队都有支持队列、bug 报告或某种人力无法完全消化的积压。

triage 工作流对每项内容分类、对照已跟踪内容去重、并采取行动。行动可以是尝试修复，或升级给人类用户。

triage 工作流的一个有用模式是 quarantine（隔离）。做法是：禁止阅读不可信公开内容的 agent 执行高权限动作，这些动作只交给负责依据信息行动的 agent。

把 triage 工作流与 /loop 配对，让 Claude 持续做这件事。

### 探索与品味

在探索一个问题的多种解法时，工作流很有用，尤其是品味主导的场景，例如设计或命名，且能从 rubric 获益。

试着让 Claude 探索一批方案，并给评审 agent 一份「好方案长什么样」的 rubric。评审 agent 认为标准已满足时任务完成。方案也可以按 rubric 通过锦标赛排序或筛选。

### Evals

你可以为特定任务跑轻量 evals：在 worktree 里派出独立的 agent，再派比较 agent 按 rubric 对具体输出比较打分。例如对你创建的 skill [先评测再改进](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)，对照一套特定标准。

### 模型与智能路由

创建一个针对你任务调校的 classifier agent，由它决定用哪个模型。当任务会涉及大量工具调用、且执行前先做研究能找出最适合的模型时，这很有帮助。

例如「解释 auth 模块如何工作」这个任务，最佳模型取决于 auth 模块有多少文件以及代码库的形态。classifier agent 可以先做这项研究，再按任务预期复杂度[路由到 Sonnet 或 Opus](https://claude.dev/blog/building-with-claude-sonnet-5-5/)。

## 何时不该用动态工作流

工作流是新事物。许多场景里它能创造超额收益，但它并非每个任务都需要，而且可能消耗多得多的 token。

最好把工作流用在创造性的方向上，推动 Claude Code 做以前做不到的事。对常规编码任务，问问自己：它真的需要更多算力吗？例如大多数传统编码任务不需要一个 5 人评审小组。

同样的判断向上一层同样成立，也就是架构层面：[多 agent 与单 agent](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) 的取舍遵循同一逻辑：并行与专门化必须挣回它们的协调成本。

## 构建动态工作流的技巧

### Prompt 写法

用上文中描述的具体技巧写详细的 prompt，动态工作流会产出最好的结果。

工作流不只属于大任务。你可以让模型用「quick workflow」（快速工作流）。例如对某个假设做一次快速的对抗性评审。

### 与 /goal 和 /loop 组合

当工作流可以重复运行，例如 triage、研究或验证，把它与 /loop 配对[定时运行](https://claude.com/resources/articles/getting-started-with-loops)，与 /goal 配对设定硬性的完成要求。

### token 用量预算

你可以为动态工作流设置显式的 token 用量预算，限制任务消耗多少 token。可以在 prompt 里写预算，例如「use 10k tokens」，就会设下上限。

### 保存与共享动态工作流

在工作流菜单里按「s」即可保存。你可以把它们签入 `~/.claude/workflows`，或通过 skill 分发。

![Claude Code 的动态工作流面板列出三次运行，含 agent 数、token 总量与时长：review-changes（14 个 agent、482k token、6m 12s）、find-flaky-tests（6 个 agent、仍在运行）、deep-research（22 个 agent、1.1M token、11m 3s）。底部按键：select、enter 查看、s 保存、esc 关闭。](https://claude.dev/media/c8b4b65c4c43f1d01be880efd0851cdfc50e8bd9c8517a57d16a761ce7d0331a.png)

*图注：**FIG H** 动态工作流面板，按 s 把一次运行保存为可复用的工作流。*

通过 skill 分发时，把你的 JavaScript 工作流文件放进 skill 文件夹并在 `SKILL.md` 里引用。为了更灵活，可以让 Claude 把 skill 里的工作流当作模板看待，按需改写，无需逐字执行。

![位于 ~/.claude/skills/deep-verify/ 的 skill 文件夹，含 SKILL.md、verify-claims.workflow.js 与 rubric.md，旁边是 SKILL.md 的内容，其中引用 ./verify-claims.workflow.js 为每条声明配自己的 subagent。](https://claude.dev/media/d3d1c7dcf59433f5178c509e7510aad3d26c33ab53bddd712a244c00b37e1047.png)

## 发现的新起点

工作流是扩展 Claude Code 的一个有用新方式。我鼓励你把它们当作探索新用法的起点。如何把它们用得最好，还有许多待发现的东西。欢迎告诉我你的发现。

*关于 harness 里究竟该装什么的原理，见我们构建 Claude 的三个 [harness 设计模式](https://claude.com/blog/harnessing-claudes-intelligence)。*

*本文由 Thariq Shihipar 与 Sid Bidasaria 撰写，两人是 Anthropic 负责 Claude Code 的技术团队成员。*
