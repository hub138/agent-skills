# 为 AI agent 解密评估（Demystifying evals for AI agents）

- 原文：[Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
- 来源：Anthropic（anthropic.com），作者 Mikaela Grace、Jeremy Hadfield、Rodrigo Olivares、Jiri De Jonghe
- 发布：2026-01-09
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 www-cdn.anthropic.com 绝对直链并配中文短描述；三类评分器对比表、四类 agent 各自评估法、pass@k 与 pass^k、八步路线图、六种理解方法对比表与附录评估框架完整翻译。

## 引言

好的评估帮助团队更有信心地发布 AI agent。缺少评估，很容易陷进被动循环——只在生产里发现问题，修一个故障又引出别的。evals 让问题与行为变化在影响用户之前就可见，其价值在 agent 的生命周期里不断累积。

正如《[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)》一文所述，agent 在多个回合里运转：调用工具、修改状态、依据中间结果调整。正是这些让 AI agent 有用的能力——自主性、智能、灵活——也让它们更难评估。

经由内部工作与 agent 开发前沿客户的合作，我们学到了怎样为 agent 设计更严格、更有用的 evals。以下是在真实部署中跨多种 agent 架构与用例都行之有效的做法。

## 评估的结构

一次评估（eval）是对 AI 系统的测试：给 AI 一个输入，然后对输出应用评分逻辑来度量成功率。本文聚焦可以在开发期无需真实用户就能运行的自动化 evals。

单轮评估直截了当：一个 prompt、一个回应、一份评分逻辑。对早期 LLM，单轮非 agentic 评估是主要的评估方法。随着 AI 能力进步，多轮评估越来越常见。

![图：简单评估中 agent 处理 prompt，评分器检查输出是否符合预期](https://www-cdn.anthropic.com/images/4zrzovbb/website/bd42e7b2f3e9bb5218142796d3ede4816588dec0-4584x2834.png)

*图注：简单评估中，agent 处理一个 prompt，评分器检查输出是否匹配预期。更复杂的多轮评估里，编程 agent 拿到工具、任务（此处是构建一个 MCP 服务器）与环境，执行 agent 循环（工具调用与推理），用实现更新环境。评分再用单元测试验证 MCP 服务器是否工作。*

agent 评估还要更复杂。agent 跨多个回合使用工具，边做边修改环境状态、随时调整——这意味着错误会传播与累积。前沿模型还能找到超出静态评估限制的创造式解法。比如 Opus 4.5 解一道 [𝜏2-bench](https://github.com/sierra-research/tau2-bench) 订机票题时[发现](https://www.anthropic.com/news/claude-opus-4-5)了政策里的一个漏洞。按题面它「评估失败」，实际却给出了对用户更好的解法。

构建 agent 评估时，我们使用以下定义：

- task（也叫 problem 或 test case）是带明确输入与成功标准的单个测试。
- 对 task 的每次尝试是一次 trial。模型输出在多次运行间有差异，我们跑多个 trial 得到更稳定的结果。
- grader 是给 agent 表现某方面打分的逻辑。一个 task 可以有多个 grader，每个 grader 含多条断言（有时叫 checks）。
- transcript（也叫 trace 或 trajectory）是一次 trial 的完整记录，含输出、工具调用、推理、中间结果与其他全部交互。对 Anthropic API，这是评估运行结束时完整的 messages 数组——涵盖评估期间对 API 的全部调用与全部返回回应。
- outcome 是 trial 结束时环境中的最终状态。订机票的 agent 可能在 transcript 末尾说「你的机票已订好」，但 outcome 是环境的 SQL 数据库里是否存在一条预订记录。
- evaluation harness 是端到端跑评估的基础设施：提供指令与工具、并发跑任务、记录全部步骤、给输出评分、汇总结果。
- agent harness（或 scaffold）是让模型以 agent 身份行动的系统：处理输入、编排工具调用、返回结果。我们评估「一个 agent」时，评估的是 harness 与模型协同工作的整体。比如 [Claude Code](https://claude.com/product/claude-code) 是一个灵活的 agent harness，我们通过 [Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) 用它的核心原语构建了[长时间运行 agent 的 harness](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)。
- evaluation suite 是一组为度量特定能力或行为而设计的 task 集合。同一 suite 里的 task 通常共享一个宽泛目标。比如客户支持评估 suite 可能测试退款、取消与升级处理。

![图：agent 评估的组成部分示意](https://www-cdn.anthropic.com/images/4zrzovbb/website/0205b36f9639fc27f2f6566f73cb56b06f59d555-4584x2580.png)

*图注：agent 评估的组成部分。*

## 为什么要构建评估

团队刚起步构建 agent 时，靠手动测试、[dogfooding](https://en.wikipedia.org/wiki/Eating_your_own_dog_food) 与直觉的组合能走得意外地远。更严格的评估甚至显得像拖慢发布的负担。但过了早期原型阶段，agent 进入生产开始规模化后，没有 evals 的构建方式开始失效。

失效点常出现在用户反馈 agent 改动后感觉变差，团队只能瞎猜乱试，没有别的核实手段。没有 evals，调试是被动的：等投诉、手动复现、修 bug、祈祷别处没有回归。团队分不清真实回归与噪音，发布前无法在几百个场景上自动测试改动，也无法度量改进。

这个进程我们见过很多次。比如 Claude Code 起步靠 Anthropic 员工与外部用户的反馈快速迭代。后来我们补上 evals——先测简练度与文件编辑这类窄面，再测过度工程这类更复杂的行为。这些 evals 帮助定位问题、指引改进方向、聚焦研究与产品的协作。与生产监控、A/B 测试、用户研究等手段相加，evals 为 Claude Code 的持续改进提供信号。

写 evals 在 agent 生命周期的任何阶段都有用。早期，evals 逼产品团队讲清楚 agent 的成功是什么；后期，它们帮助维持一致的质量标准。

[Descript](https://www.descript.com/) 的 agent 帮用户剪视频，所以他们围绕成功剪辑工作流的三个维度建 evals：别弄坏东西、按我说的做、做得好。他们从人工评分演进到由产品团队定标准、定期人工校准的 LLM 评分器，如今常态化跑两套独立的 suite 分别做质量基准与回归测试。[Bolt](https://bolt.new/) 的 AI 团队起步更晚，是在 agent 已被广泛使用后才建 evals。三个月内他们建起一套评估系统：跑 agent 用静态分析给输出评分，用浏览器 agent 测试应用，用 LLM 裁判评指令遵循这类行为。

有些团队在开发一开始就建 evals；有些等到规模化、评估成为改进 agent 的瓶颈时才补。evals 在 agent 开发初期尤其有用，能把预期行为显式写下来。两位工程师读同一份初始规格，可能对 AI 该怎样处理边界情况得出不同理解。一份 eval suite 能消除这种含糊。无论何时创建，evals 都帮助加速开发。

evals 还决定你换新模型的速度。更强的模型发布时，没有 evals 的团队要面对数周测试；有 evals 的竞对可以快速摸清模型强弱、调好 prompt、几天内完成升级。

evals 一旦存在，基准与回归测试白送：延迟、token 用量、单任务成本、错误率都能在一组固定任务上跟踪。evals 还能成为产品与研究团队之间带宽最高的沟通渠道，定义研究者可以对着优化的指标。显然，evals 的收益远超跟踪回归与改进。成本的可见在前、收益的累积在后，复利价值容易被错过。

## 如何评估 AI agent

我们观察到当下规模化部署的几类常见 agent：编程 agent、研究 agent、computer use agent 与对话 agent。每类可部署在众多行业，但评估技术是相通的。你不需要从零发明评估。下面几节描述几类 agent 经验证的方法。把这些方法当基座，再扩展到你的领域。

### agent 的评分器类型

agent 评估通常组合三类评分器：代码、模型与人工。每类评分器评 transcript 或 outcome 的某一部分。有效评估设计的关键一环，就是为工作选对评分器。

## 代码评分器

方法：字符串匹配检查（精确、正则、模糊等）；二值测试（fail-to-pass、pass-to-pass）；静态分析（lint、类型、安全）；outcome 验证；工具调用验证（用了哪些工具、参数）；transcript 分析（回合数、token 用量）。

长处：快、便宜、客观、可复现、容易调试、验证特定条件。

短处：对不精确匹配预期模式的有效变体过于脆弱；缺少细微判断；对一些更主观的任务能力有限。

## 模型评分器

方法：rubric 打分；自然语言断言；成对比较；基于参照的评估；多裁判共识。

长处：灵活、可伸缩、捕捉细微差别、处理开放式任务、处理自由格式输出。

短处：非确定性；比代码贵；需要与人工评分校准才能准确。

## 人工评分器

方法：SME 评审；众包判断；抽查采样；A/B 测试；标注者间一致性。

长处：黄金标准的质量；匹配专家级用户判断；用于校准模型评分器。

短处：贵、慢、常常需要大规模接触到人类专家。

每个 task 的计分可以是加权制（多个评分器分数合计须过阈值）、二值制（全部评分器须通过）或混合制。

### 能力评估与回归评估

能力评估或「质量」评估问：「这个 agent 擅长做什么？」它们应该从低通过率起步，瞄准 agent 还做不好的任务，给团队一座可以爬的山。

回归评估问：「agent 是否仍然能处理过去会的全部任务？」应该接近 100% 通过率。它们防止退步，分数下滑说明有东西坏了需要修。团队在能力评估上爬坡时，同步跑回归评估很重要，确保改动没有在别处引发问题。

agent 发布并优化后，通过率很高的能力评估可以「毕业」为持续运行的回归 suite，捕捉任何漂移。当初测「我们能不能做到」的任务，此后测「我们还能不能稳定做到」。

### 评估编程 agent

编程 agent 写代码、测代码、调代码，像人类开发者一样穿行代码库、跑命令。现代编程 agent 的有效 evals 通常依赖定义清楚的任务、稳定的测试环境、给生成代码的充分测试。

确定性评分器对编程 agent 是天然选择，因为软件通常易于评估：代码能跑吗？测试过吗？两个广泛使用的编程 agent 基准，[SWE-bench Verified](https://www.swebench.com/SWE-bench/) 与 [Terminal-Bench](https://www.tbench.ai/)，都走这条路。SWE-bench Verified 给 agent 流行 Python 仓库的 GitHub issue，靠跑测试套件给解法评分；解法只有在修好失败测试且不破坏既有测试时才算通过。一年间 LLM 在这个评估上从 40% 进到超过 80%。Terminal-Bench 走另一条线：测试端到端技术任务，比如从源码构建 Linux 内核或训练一个 ML 模型。

一旦有了验证编程任务关键 outcome 的一组过/不过测试，给 transcript 评分也常有价值。比如基于启发式的代码质量规则可以基于通过测试之外再评生成代码，带清晰 rubric 的模型评分器可以评估 agent 怎样调用工具、怎样与用户交互这类行为。

**示例：编程 agent 的理论评估**

设想一个编程任务：agent 必须修复一处认证绕过漏洞。如下面的示意 YAML 文件所示，可以用多个评分器与指标来评估这个 agent。

```yaml
task:
  id: "fix-auth-bypass_1"
  desc: "Fix authentication bypass when password field is empty and ..."
  graders:
    - type: deterministic_tests
      required: [test_empty_pw_rejected.py, test_null_pw_rejected.py]
    - type: llm_rubric
      rubric: prompts/code_quality.md
    - type: static_analysis
      commands: [ruff, mypy, bandit]
    - type: state_check
      expect:
        security_logs: {event_type: "auth_blocked"}
    - type: tool_calls
      required:
        - {tool: read_file, params: {path: "src/auth/*"}}
        - {tool: edit_file}
        - {tool: run_tests}
  tracked_metrics:
    - type: transcript
      metrics:
        - n_turns
        - n_toolcalls
        - n_total_tokens
    - type: latency
      metrics:
        - time_to_first_token
        - output_tokens_per_sec
        - time_to_last_token
```

注意，这个示例为展示目的列出了全部可用评分器。实践中，编程评估通常靠单元测试验证正确性，靠 LLM rubric 评整体代码质量，额外的评分器与指标只在需要时再加。

### 评估对话 agent

对话 agent 在支持、销售、辅导这类领域与用户交互。与传统聊天机器人不同，它们维护状态、使用工具、在对话中途采取行动。编程与研究 agent 也会与用户多轮交互，但对话 agent 带来独特挑战：交互本身的质量就是评估对象的一部分。对话 agent 的有效 evals 通常依赖可验证的终态 outcome 与同时覆盖任务完成和交互质量的 rubric。与多数其他 evals 不同，它们常需要第二个 LLM 模拟用户。我们在 [alignment 审计 agent](https://alignment.anthropic.com/2025/automated-auditing/)里就用这个办法，经延长、对抗性的对话给模型加压测试。

对话 agent 的成功可以多维：工单是否解决（state check）、是否在 10 回合内完成（transcript 约束）、语气是否得体（LLM rubric）。纳入多维度的两个基准是 [𝜏-Bench](https://arxiv.org/abs/2406.12045) 与后继 [τ2-Bench](https://arxiv.org/abs/2506.07982)。它们模拟零售支持与航空订票等领域的多轮交互，一个模型扮演用户角色，agent 穿行真实场景。

**示例：对话 agent 的理论评估**

设想一个支持任务：agent 必须为一位不满的客户处理退款。

```yaml
graders:
  - type: llm_rubric
    rubric: prompts/support_quality.md
    assertions:
      - "Agent showed empathy for customer's frustration"
      - "Resolution was clearly explained"
      - "Agent's response grounded in fetch_policy tool results"
  - type: state_check
    expect:
      tickets: {status: resolved}
      refunds: {status: processed}
  - type: tool_calls
    required:
      - {tool: verify_identity}
      - {tool: process_refund, params: {amount: "<=100"}}
      - {tool: send_confirmation}
  - type: transcript
    max_turns: 10
tracked_metrics:
  - type: transcript
    metrics:
      - n_turns
      - n_toolcalls
      - n_total_tokens
  - type: latency
    metrics:
      - time_to_first_token
      - output_tokens_per_sec
      - time_to_last_token
```

与编程 agent 示例一样，这个任务为展示目的用了多种评分器。实践中，对话 agent 评估通常用模型评分器同时评估沟通质量与目标完成，因为很多任务——比如回答一个问题——可能有多个「正确」解法。

### 评估研究 agent

研究 agent 收集、综合、分析信息，然后产出答案或报告这类输出。与编程 agent 用单元测试给二值信号不同，研究质量只能相对任务来评判。什么算「全面」「来源扎实」甚至「正确」取决于上下文：市场扫描、收购尽调与科学报告各有各的标准。

研究评估面临独特挑战：专家之间可能对综合是否全面意见不一；参考内容持续变化导致真值漂移；更长更开放的输出留出更多出错空间。像 [BrowseComp](http://arxiv.org/abs/2504.12516) 这样的基准，测试 AI agent 能否在开放网络的草堆里找针——题目设计得容易验证、难以求解。

构建研究 agent 评估的一个策略是组合评分器。groundedness 检查验证论断有检索到的来源支撑；coverage 检查定义好答案必须包含的关键事实；source quality 检查确认所查来源权威，避免只取最先检索到的。对有客观正确答案的任务（「X 公司三季度营收是多少？」），精确匹配即可。LLM 能标记无来源支撑的论断与覆盖缺口，也能验证开放式综合的连贯与完整。

鉴于研究质量的主观性，LLM rubric 应频繁对照专家人工判断做校准，才能有效给这类 agent 评分。

### computer use agent

computer use agent 通过与人相同的接口和软件交互——截图、鼠标点击、键盘输入、滚动——经由 API 或代码执行。它们能用任何带图形界面（GUI）的应用，从设计工具到老旧企业软件。评估需要让 agent 在真实或沙箱环境里使用软件应用，检查它是否达成预期 outcome。比如 [WebArena](https://arxiv.org/abs/2307.13854) 测试浏览器任务，用 URL 与页面状态检查验证 agent 导航正确，对修改数据的任务再加后端状态验证（确认订单真的下了，而非只看到确认页出现）。[OSWorld](https://os-world.github.io/) 把它扩展到完整操作系统控制，任务完成后的评估脚本检查多样的工件：文件系统状态、应用配置、数据库内容与 UI 元素属性。

浏览器使用 agent 需要在 token 效率与延迟之间找平衡。基于 DOM 的交互执行快但耗 token 多；基于截图的交互更慢但更省 token。比如让 Claude 总结 Wikipedia，从 DOM 提取文本更高效。在 Amazon 上找一款新笔记本内胆包，截图更高效（提取整个 DOM 很耗 token）。在 Claude for Chrome 产品里，我们开发了 evals 检查 agent 是否在每种场景选对工具。这让我们更快更准地完成浏览器任务。

### 怎样理解 agent 评估中的非确定性

无论哪类 agent，agent 行为在多次运行间都有变化，评估结果比第一眼看上去更难解读。每个 task 有自己的成功率——这个 90%，那个 50%——一次评估通过的 task 下次可能失败。有时我们想度量的，恰是 agent 对一个 task 的成功率（trial 中成功的比例）。

两个指标帮助捕捉这种细微差别：

[pass@k](https://proceedings.neurips.cc/paper/2019/file/7298332f04ac004a0ca44cc69ecf6f6b-Paper.pdf) 度量 agent 在 k 次尝试中至少得到一个正确解的可能性。k 增大，pass@k 上升：射门次数越多，至少进一球的概率越高。pass@1 是 50% 意味着模型首次尝试就能完成一半的评估任务。编程里我们最关心的常是 agent 首次就找到解——pass@1。另一些场景里，提出多个解法只要有一个有效就算数。

[pass^k](https://arxiv.org/abs/2406.12045) 度量全部 k 次 trial 都成功的概率。k 增大，pass^k 下降，因为要求更多 trial 保持一致是更难达成的标准。agent 单次成功率 75%，跑 3 次 trial，三次全过的概率是 (0.75)³ ≈ 42%。这个指标对面向客户的 agent 尤其重要，用户期待每次都可靠。

![图：pass@k 与 pass^k 随 trial 数增加而分道扬镳](https://www-cdn.anthropic.com/images/4zrzovbb/website/3ddac5be07a0773922ec9df06afec55922f8194a-4584x2580.png)

*图注：pass@k 与 pass^k 随 trial 数增加而分道扬镳。k=1 时两者相同（都等于单次成功率）。到 k=10，它们讲出相反的故事：pass@k 接近 100%，pass^k 掉向 0%。*

两个指标都有用，选哪个取决于产品要求：一次成功就够的工具用 pass@k，一致性至上的 agent 用 pass^k。

## 从零到一：给 agent 造好 evals 的路线图

本节给出我们经实地检验的建议：从没有 evals 到可以信任的 evals。把它当作评估驱动 agent 开发的路线图：早定义成功、清晰度量、持续迭代。

### 为初始评估数据集收集任务

**第 0 步：尽早开始。** 我们看到团队推迟建 evals，是因为以为要几百个任务才行。实际上，从真实故障里选 20 到 50 个简单任务就是很好的起点。毕竟 agent 开发早期，系统的每次改动常有清晰可感的影响，这个大的效应量意味着小样本就够。更成熟的 agent 可能需要更大更难的评估来探测更小的效应，但起步阶段最好走 80/20 路线。等得越久，evals 越难建。早期，产品需求自然翻译成测试用例；等太久，你就是在从线上系统反向猜成功标准。

**第 1 步：从你已手动测试的内容开始。** 从开发期跑的手动检查开始——每次发布前验证的行为、最终用户常试的任务。已在生产中的，看你的 bug 跟踪器与支持队列。把用户上报的故障转成测试用例，保证 suite 反映真实使用；按用户影响排序，把力气花在要紧处。

**第 2 步：写带参照解的无歧义任务。** 把任务质量做对比看上去难。好任务是两位领域专家各自独立得出相同过/不过判断的任务。他们自己能通过吗？不能，任务就需要改进。任务规格里的含糊会变成指标里的噪音。模型评分器的标准同理：含糊的 rubric 产出不一致的判断。

每个任务都应该让正确遵循指令的 agent 能通过。这一点可以很隐蔽。比如审计 Terminal-Bench 时发现，任务要求 agent 写一个脚本但没指定文件路径，而测试假设脚本在某个路径，agent 可能因为无关自身的失误而失败。评分器检查的每件事都应从任务描述里看得清楚；agent 不该因规格含糊而失败。对前沿模型，多次 trial 全部 0% 通过（即 0% pass@100）多数时候是任务坏了的信号，说明该复查任务规格与评分器。给每个任务建一份参照解也很有用：一份已知可工作、能通过全部评分器的输出。它证明任务可解，并核实评分器配置正确。

**第 3 步：构建平衡的问题集。** 既测某个行为应该发生的场景，也测它不应该发生的场景。单侧的评估造出单侧的优化。比如只测 agent 该搜索时是否搜索，你可能养出一个什么都搜的 agent。尽量避免[类别失衡](https://developers.google.com/machine-learning/crash-course/overfitting/imbalanced-datasets)的评估。我们为 [Claude.ai](http://claude.ai) 的 web 搜索建 evals 时有切身教训。难点是阻止模型在不该搜的时候搜，同时保住它该深挖时的能力。团队建了双向覆盖的 evals：应该搜索的查询（如查天气）与应该用既有知识回答的查询（如「谁创立了 Apple？」）。在不触发（该搜没搜）与过触发（不该搜却搜了）之间找准平衡很难，prompt 与 eval 都打磨了很多轮。随着新问题案例出现，我们持续给 evals 加题扩大覆盖。

### 设计评估 harness 与评分器

**第 4 步：构建带稳定环境的健壮评估 harness。** 评估里的 agent 必须与生产中使用的 agent 大致相同，环境本身不能引入更多噪音。每次 trial 应从干净环境启动实现隔离。运行之间多余的共享状态（残留文件、缓存数据、资源耗尽）会因基础设施不稳定而非 agent 表现引发关联失败。共享状态也会虚增表现。比如一些内部评估里，我们观察到 Claude 靠检视先前 trial 留下的 git 历史在某些任务上拿到不公平优势。如果多个不同 trial 因环境的同一限制（如 CPU 内存不足）而失败，这些 trial 并不独立，评估结果对度量 agent 表现就不可靠。

**第 5 步：用心设计评分器。** 如上所述，好的评估设计在于为 agent 与任务选最好的评分器。我们建议能选确定性评分器就选，必要时或要更灵活时用 LLM 评分器，人工评分器审慎地用于额外验证。

有一个常见本能：检查 agent 是否遵循了非常具体的步骤，比如按正确顺序的一串工具调用。我们发现这条路过于僵硬，产出过分脆弱的测试，因为 agent 常找到评估设计者没预料到的有效路径。为了不惩罚创造性，更好的做法是评 agent 产出了什么，而非它走的路径。

对多组件任务，内置部分得分。一个正确识别问题、验证了客户身份但没处理退款的支持 agent，明显好过一个立刻失败的 agent。在结果里呈现这种成功的连续谱很重要。

模型评分常需仔细迭代验证准确性。LLM-as-judge 评分器应与人类专家紧密校准，建立人工评分与模型评分基本一致的信心。为避免幻觉，给 LLM 留退路，比如指示它在信息不足时返回「Unknown」。给任务的每个维度建清晰、结构化的 rubric，再用互相隔离的 LLM-as-judge 分别评每个维度，也常有帮助，好过用一个裁判评全部维度。系统稳健后，人工复查偶尔做一次就够。

有些评估有隐蔽的失败模式：agent 表现良好分数却低，因为评分 bug、agent harness 限制或任务含糊导致 agent 无法解题。强团队也会踩这些坑。比如 [Opus 4.5 在 CORE-Bench 上最初只得 42%](https://x.com/sayashk/status/1996334941832089732?s=46&t=c5pEvnVdVbMkcR_rcCHplg)，直到一位 Anthropic 研究员发现多个问题：僵硬评分把「96.12」当错而期望「96.124991…」；任务规格含糊；随机性任务无法精确复现。修好 bug、换用更少约束的 scaffold 后，Opus 4.5 的分数跳到 95%。类似地，[METR 发现](https://x.com/metr_evals/status/2001473506442375645?s=46)其时间视野基准里多个配置错误的任务：要求 agent 优化到某个声明的分数阈值，评分却要求超过该阈值。这惩罚了 Claude 这类遵循指令的模型，而无视声明目标的模型反而得高分。仔细复查任务与评分器可以避开这些问题。

让评分器抵抗绕过与作弊。agent 不该能轻易「骗过」评估。任务与评分器应设计成：通过真正需要解出问题，利用无意漏洞行不通。

### 长期维护与使用评估

**第 6 步：读 transcript。** 不去读多次 trial 的 transcript 与评分，你不会知道评分器工作得好不好。Anthropic 为查看评估 transcript 投入了工具建设，我们定期花时间读它们。任务失败时，transcript 告诉你是 agent 真犯了错，还是你的评分器拒掉了有效解法。它也常带出 agent 与评估行为的关键细节。

失败应该显得公平：agent 错在哪里、为什么，看得清楚。分数不涨时，我们需要确信原因在 agent 表现而非评估。读 transcript 就是核实评估度量了真正要紧之物的方式，这是 agent 开发的关键技能。

**第 7 步：监视能力评估饱和。** 100% 的评估跟踪回归但对改进没有信号。评估饱和发生在 agent 通过全部可解任务、没有改进空间时。比如 SWE-Bench Verified 今年从 30% 起步，前沿模型已逼近超过 80% 的饱和区。评估逼近饱和，进步也会放缓，因为只剩最难的任务。这会让结果变得迷惑：大幅能力进步显示为分数的小幅上涨。比如代码评审创业公司 [Qodo](https://www.qodo.ai/) 起初对 Opus 4.5 不满意，因为他们的单次编程评估没捕捉到更长更复杂任务上的提升。作为回应，他们开发了新的 agentic 评估框架，对进步的图景清晰得多。

按惯例，我们不把评估分数照单全收，直到有人深挖评估细节、读一些 transcript。评分不公平、任务含糊、有效解法被罚或 harness 束缚模型时，该修订的是评估。

**第 8 步：靠开放贡献与维护保持评估 suite 长期健康。** 评估 suite 是活物，需要持续关注与清晰归属才能保持有用。

Anthropic 尝试过多种评估维护方式。最有效的是设立专职 evals 团队拥有核心基础设施，领域专家与产品团队贡献大多数评估任务并自己运行评估。

对 AI 产品团队，拥有并迭代评估应该像维护单元测试一样日常。团队可能浪费数周在早期测试「能用」、却满足不了未言明期望的 AI 功能上——一份设计良好的评估能把这些早早暴露出来。定义评估任务是压力测试产品需求是否具体到可以开工的最好方式之一。

我们推荐评估驱动开发：在 agent 能做到之前先建 evals 定义计划中的能力，然后迭代到 agent 表现良好。内部我们常构建今天「够用」的功能，实际是对几个月后模型能力的押注。从低通过率起步的能力评估把这一点摆到台面上。新模型发布时，跑一遍 suite 立刻看出哪些押注兑现了。

离产品需求与用户最近的人最适合定义成功。以当前模型能力，产品经理、客户成功经理或销售都能用 Claude Code 以 PR 形式贡献一个评估任务——让他们做！或者更进一步，主动帮他们扫清障碍。

![图：创建一份有效评估的流程](https://www-cdn.anthropic.com/images/4zrzovbb/website/0db40cc0e14402222a179fc6297b9c8818e97c8a-4584x2580.png)

*图注：创建一份有效评估的流程。*

## 评估如何与其他方法配合形成对 agent 的整体理解

自动化评估可以在数千个任务上针对 agent 运行，不必部署到生产、不影响真实用户。但这只是理解 agent 表现的多种方式之一。完整图景包括生产监控、用户反馈、A/B 测试、人工 transcript 评审与系统性人类研究。

## 理解 AI agent 表现的方法总览

**自动化评估（无真实用户地程序化跑测试）**：长处——迭代更快；完全可复现；不影响用户；每次提交都能跑；无需生产部署即可规模化测场景。短处——前期投入更大；随产品与模型演进需持续维护防漂移；与真实使用模式不符时制造虚假信心。

**生产监控（跟踪线上系统的指标与错误）**：长处——大规模揭示真实用户行为；抓到合成评估漏掉的问题；提供 agent 实际表现的真实基准。短处——被动，问题先到用户那里你才知道；信号可能嘈杂；需要在埋点上投入；缺少评分所需的真实基准。

**A/B 测试（用真实用户流量对比变体）**：长处——度量真实的用户结果（留存、任务完成）；控制混杂因素；可伸缩且系统化。短处——慢，到显著需要数天或数周且需要足够流量；只测已部署的改动；无法彻底读 transcript 时对指标变化背后的「为什么」信号较少。

**用户反馈（点踩、bug 报告这类显式信号）**：长处——暴露你没预料到的问题；带着真实人类用户的实例；反馈常与产品目标相关。短处——稀疏且自选；集中于严重问题；用户很少解释为什么失败；非自动化；主要靠用户抓问题可能造成负面用户影响。

**人工 transcript 评审（人通读 agent 对话）**：长处——建立对失败模式的直觉；抓到自动检查漏掉的细微质量问题；帮助校准「好」的样子并把握细节。短处——耗时；无法伸缩；覆盖不一致；评审疲劳或评审者更替影响信号质量；通常只给定性信号而非清晰的定量评分。

**系统性人类研究（受训评分者结构化地评 agent 输出）**：长处——多位人类评分者给出黄金标准的质量判断；处理主观或含糊任务；为改进模型评分器提供信号。短处——相对贵且周期长；难以高频运行；评分者分歧需要调和；复杂领域（法律、财务、医疗）需要人类专家做研究。

这些方法映射到 agent 开发的不同阶段。自动化评估在发布前与 CI/CD 里尤其有用，每次 agent 改动与模型升级都跑，作为质量问题的第一道防线。生产监控在发布后介入，探测分布漂移与未预料的真实失败。A/B 测试在流量足够后验证重大改动。用户反馈与 transcript 评审是填补空隙的日常实践：持续分拣反馈，每周抽样读 transcript，需要时深挖。系统性人类研究留给校准 LLM 评分器或评估以人类共识为参照标准的主观输出。

![图：像安全工程里的 Swiss Cheese Model，多层方法组合让漏过一层的失败被另一层抓住](https://www-cdn.anthropic.com/images/4zrzovbb/website/b77b8dbb7c2e57f063fbc8a087a853d5809b74b0-4584x2580.png)

*图注：像安全工程里的 [Swiss Cheese Model](https://en.wikipedia.org/wiki/Swiss_cheese_model)，没有单一评估层能抓住全部问题。多层方法组合时，漏过一层的失败被另一层抓住。*

最有效的团队组合这些方法：自动化评估求快，生产监控求真实，定期人工评审做校准。

## 结语

没有 evals 的团队陷进被动循环——修一个故障又引出另一个，分不清真实回归与噪音。早投入的团队见到相反情形：故障变成测试用例，测试用例防止回归，指标取代猜测，开发随之加速。evals 给整个团队一座清晰可爬的山，把「agent 感觉变差了」变成可行动的东西。价值是复利的，前提是你把 evals 当核心组件，而非事后补丁。

模式因 agent 类型而异，这里的基法则不变。尽早开始，别等完美的 suite。从你见到的故障里取真实任务。定义无歧义、健壮的成功标准。用心设计评分器并组合多种类型。确保问题对模型足够难。迭代评估本身以提高信噪比。读 transcript！

AI agent 评估仍是年轻、快速演进的领域。随着 agent 承担更长任务、在多 agent 系统里协作、处理越来越主观的工作，我们的技术也要跟着调整。我们会在学到更多时继续分享最佳实践。

## 附录：评估框架

若干开源与商业框架能帮团队实现 agent 评估，免去从零建基础设施。选择取决于你的 agent 类型、既有技术选型，以及你需要离线评估、生产可观察性还是两者都要。

[Harbor](https://harborframework.com/) 为在容器化环境里跑 agent 而设计，带跨云厂商规模化跑 trial 的基础设施与定义任务和评分器的标准格式。Terminal-Bench 2.0 这类流行基准经 Harbor registry 发行，让既有基准与自定义评估 suite 一起跑变得容易。

[Braintrust](https://www.braintrust.dev/) 是一个把离线评估与生产可观察性、实验跟踪结合的平台——适合既要在开发期迭代、又要在生产中监控质量的团队。它的 `autoevals` 库含事实性、相关性等常见维度的预构建评分器。

[LangSmith](https://docs.langchain.com/langsmith/evaluation) 提供追踪、离线与在线评估、数据集管理，与 LangChain 生态深度集成。[Langfuse](https://langfuse.com/) 提供类似能力，是有数据驻留要求团队的自托管开源替代。

[Arize](https://arize.com/) 提供 Phoenix，一个 LLM 追踪、调试与离线在线评估的开源平台，以及 AX，一个为规模、优化与监控扩展 Phoenix 的 SaaS 服务。

很多团队组合多个工具、自建评估框架，或先用简单评估脚本起步。我们发现框架虽能加速进度与标准化，但它的好坏取决于你在其中跑的评估任务。通常最好快速挑一个合手的框架，然后把精力投在评估本身上，迭代高质量测试用例与评分器。

## 作者与致谢

本文由 Mikaela Grace、Jeremy Hadfield、Rodrigo Olivares 与 Jiri De Jonghe 撰写。我们同样感谢 David Hershey、Gian Segato、Mike Merrill、Alex Shaw、Nicholas Carlini、Ethan Dixon、Pedram Navid、Jake Eaton、Alyssa Baum、Lina Tawfik、Karen Zhou、Alexander Bricken、Sam Kennedy、Robert Ying 等人的贡献。特别感谢在评估协作中让我们学习的客户与伙伴，包括 iGent、Cognition、Bolt、Sierra、Vals.ai、Macroscope、PromptLayer、Stripe、Shopify、Terminal Bench 团队等。这项工作反映了多个团队共同发展 Anthropic 评估实践的努力。
