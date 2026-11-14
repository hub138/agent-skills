# 自动化 eval 设计与 hillclimbing（Automating eval design and hillclimbing with Claude）

- 原文：[Automating eval design and hillclimbing with Claude](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)
- 来源：Anthropic（claude.dev Blog），作者 Lance Martin
- 发布：2026-09-28
- 译文说明：evals 的通用方法论（三类评分器、四类 agent 评估法、pass@k 与 pass^k、八步路线图）见 evals-demystified.md；skill 的 evals 与 benchmark 体系见 skill-creator-evals.md；留出测试集与过拟合风险在 writing-tools-for-agents.md 有提及级覆盖。本文独有增量在自动化工作流层面：好 eval 的四要素判据（生产镜像、更强 model 应更强、前沿留空间、低方差）、adversarial sampling（按人力判难采样，防止测出单个 model 的失败指纹）、build-eval 的输入采样顺序与评分器验证流程、hillclimb 的三条件选址（廉价可迭代、可归因、目标范围清晰）、过拟合三对策（train/test 划分、失败内容绝不粘进 prompt、答案结构性隔离）、每轮一个 patch 与 stall 后按根因归类、以及客服 benchmark 降本与 claude-api skill 提分两个实例的全部数字。

evals 为你的应用或 skill 在特定任务上的表现提供信号。但设计 evals、并在不骗自己的前提下改进其表现，很难。我们为这两件事都加了指引，进了 [claude-api skill](https://github.com/anthropics/skills/tree/main/skills/claude-api)。

用这个 skill，你可以运行 `/claude-api build-eval` 在你的代码库里构建一个评估，再运行 `/claude-api hillclimb` 对着它逐次改动地改进你的应用，同时用一个留出的样本集来抓过拟合。

本文先讲好 eval 设计与 hillclimbing 的原则，再展示 [Claude Code](https://claude.com/product/claude-code) 配合 `claude-api` skill 如何把这些原则用起来，最后给几个命令实例。

## EVAL 设计

设计良好的 evals 有几个共同要素（图 1）：

1. **eval 任务镜像生产。** 从你在意的「production」——也就是你测试的能力或应用将要使用的场景——里采样任务。有些任务之所以被选进来，只是因为它们容易生成或容易打分。但要确保任务分布代表你真正在意的场景。
2. **更强的 model 与更多思考应该带来更高分。** 更强的 model 与[更高的 effort 档位](https://claude.dev/blog/spending-your-effort/)在 eval 上通常应该表现更好。如果没有，往往是含糊的任务或标定失准的评分器在拖累表现。
3. **前沿处留有「可达」的空间。** 最强 model 在最高 effort 下应该远低于 100%，否则你无法可靠判断改动如何影响表现。重要的是，这个差距不应由不可能或含糊的任务解释：一个常见信号是某个任务每次评估都失败，无论重复多少次。好任务是两位领域专家会得出同一判定的任务，且评分器检查的每一点都在任务文本里写明。
4. **轮与轮之间方差低。** 高方差往往来自设计不当的含糊任务，或一个对相同输出给出不同判定的评分器。方差也可能藏在配置里：比如 effort 没有一致地施加。另外环境也会影响 eval 结果：上一次尝试的残留状态（一个文件、一段 git 历史）可能把答案直接递给 agent。

图 1 的要点：横轴为每次尝试的 action tokens（对数刻度），纵轴为分数，三种模型尺寸在低、中、高三档 effort 下画曲线。一个好 eval 同时满足四点：更强大的 model 得分更高（1）；更多 effort 得分更高（2）；完美分数之下留有空间（3）；轮与轮之间方差低（4）。

### 对抗性采样

model 的能力是锯齿状的。如果你因为今天的 model 在某些案例上失败而把它们挑出来，你采样的是单个 model 能力表面的谷底（图 2）。这样的 eval 最终测出的是那个 model 的失败指纹，对你的应用而言什么本质上难、什么有价值，一概测不出。

![两个面板画能力随任务空间的分布，今天的 model 都是锯齿曲线，下一个 model 是更平滑的高于它的曲线。左面板：按今天的 model 失败挑出的案例只处于它的谷底；右面板：人力判定困难的案例分布在峰与谷之间，还带几条不应触发的案例。](https://claude.dev/media/6a014fa959cbc13b3026ca0f2ac1cb8754d541bd07da79bb4c61d81af428024a.png)

因为人力判定困难而挑难案例：一条有用的检验是，收录一条任务前你能说出它为什么难。收录那些源自生产流量、bug 报告或工单的、你应用的具体失败。但不要盲信用户流量：用户有时只尝试他们预期会成功的事，严格从用户流量画出的任务分布可能整体简单化。

## /CLAUDE-API BUILD-EVAL

claude-api skill 里的 `build-eval` 命令把这些原则变成一个引导式工作流。在 Claude Code 里运行 `/claude-api build-eval`，Claude 会采访你，在你的代码库里构建 eval，并在特定节点停下来等你批准。

### 设计案例

Claude 帮你按以下顺序采样输入构建评估：

1. 生产记录，先询问留存期与敏感数据。
2. bug 报告与支持工单。
3. 你手写的五到十条案例。
4. 从你的代码库合成的案例。

skill 优先使用生产流量，但它也能基于你提供的几条真实示例生成锚定的合成数据。skill 指示 Claude 生成一个简单页面，展示每一条输入，并等你确认它们。作为示意，下面是一个邮件路由应用的输入集，skill 可能请用户审阅（图 3）。

![skill 的审阅页面，收件箱路由 eval 共 24 条输入，逐条列出邮件文本并带 billing、easy、ambiguous 之类的标签。旁边 Claude 在聊天里询问这些输入是否有代表性，用户回答是。](https://claude.dev/media/bccc92050c6361924330ef504796ca2c0ce9208d8837356472373f8957b9fdd5.png)

### 验证评分器

输入之后，Claude 为你应用的输出提议最便宜的评分器：

- **程序化验证**：输出可能性受限时用代码检查（精确匹配、固定集合里的标签、匹配 schema 的 JSON、通过的测试）。
- **LLM-as-judge**：输出空间开放、有效答案多但质量标准清晰时默认用它。此时第二个 model 读输入、输出与一份写成可核查断言的 rubric（评分标准），返回分数与理由；不是 1 到 5 的量表。有基线可比时，评审 model 改读随机顺序的两份输出，不告诉它哪份是基线，让它选出更好的一份。评审 model 由你选，且不应该是你正在测试的那个 model。

Claude 给一小把案例打分，然后问你是否会给其中某几条打出不同的分（图 4）。一般而言，在相信你的评估器之前先[读一批打过分的记录](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)；打分失准是 eval 配置错误最常见的方式之一。

评分器验证过后，skill 告诉你评估集的规模（案例数 × 重复数 × model，以及大约耗时），跑基线，打印分数与置信区间。你拿回的东西：案例、评分器、runner、每案例一行 JSON 加一份完整记录，还有一个列出每案例分数并带记录链接的朴素页面。想要页面之外的东西（比如一张图），直接开口，Claude 会把它作为附加页面建在旁边。默认这些附加页面是本地打开、不从网络加载任何东西的静态文件。

![skill 的结果页面，收件箱路由 eval：基线在 24 案例上均分 0.681，下面是逐案例分数表，每行带指向各次重复的链接。重复链接打开该案例的原始 JSON trace，并排展示。](https://claude.dev/media/9c7c2f00ebdd0f9e6b8ad0d3de8cdcc6ebb162c9d2fa5b4f4950ac36b736aef8.png)

### 诊断检查

在上面提到的基线运行期间，Claude 会检查几件事：

- **评分器**：Claude 对同一输出把评分器跑两遍，报告判定是否变了。
- **管线**：Claude 检查超时、API 错误与被截断的回答，确保基础设施噪声不会被当成 model 方差。
- **空间**：基线已到 95% 或更高时，skill 会警告用户，并提示 hillclimb 应转向探索成本或延迟而非质量。

## HILLCLIMBING

现在你有了给应用表现打分的可靠手段，可以试着改进它。Hillclimbing 是调 effort、prompt 这类参数的有效方法，它们在成本与表现之间取平衡。选在哪里应用它，有几条一般性建议：

- **廉价迭代**。修改你聚焦的那个面（surface）应该在时间、成本、精力上都很便宜。许多内部团队与客户把 hillclimbing 聚焦在文本上，比如 prompt 与 skills，它们容易改也容易撤销。相比之下，hillclimbing 期间对 agent harness 的开放式修改可能牵动大量代码改动。
- **可归因**。eval 分数的变化应该能归因到 hillclimbing 期间你修改的那个面。例如几个成功的应用把 hillclimbing 聚焦在 [skill 触发](https://claude.com/resources/articles/improving-skill-creator-test-measure-and-refine-agent-skills)上：评估指标（skill 的触发率）与被修改的 skill 描述直接耦合。
- **目标范围清晰**。一个常见失败形态是不看 eval 里剩多少空间就开放式地要求「提升表现」；接近饱和的 eval 或范围不清的面（比如开放式地要求改 harness）更容易原地停摆。跨各团队都强的一个目标是成本：即便 eval 已饱和，也可以让 Claude 去[找降本的办法](https://claude.com/blog/reducing-cost-and-improving-performance-with-claude-platform)，同时表现保持持平。

### 过拟合

再好的 eval 也几乎匹配不上你在生产中真正在意的任务分布。于是「过拟合」到 eval 是常见问题：系统在 eval 上表现更好，在生产流量上没有。

eval 有很多方式「泄漏」进你的 harness（model 周围的代码，含 prompt、tools 与调用 Claude 的 loop）。例如，某个 eval 任务受益于 OCR，而你的生产任务几乎用不上 OCR；eval harness 可能给你的应用加一个 OCR 工具，在 benchmark 上提分，对生产毫无影响。更广地说，hillclimbing 可能往 harness 里加应对你挑的那批 eval 案例边缘情况的功能。这些 harness 增量提高你的 eval 分数，却转化不成生产改进（图 5）。

![左列 benchmark 的特征，右列与之对应的 harness 增量：任务组合需要 OCR 就加 OCR 工具、任务在 /app 就加「总是 cd /app 跑 pytest」、独特措辞得到一条调优 prompt、你读过的失败各得一枚补丁；虚线箭头标出彻底的泄漏：带答案的公开仓库让 harness curl 参考答案。](https://claude.dev/media/a328a3f4d5bfd0967174ef2ca79bc8f094d8db3c12af71be3189891bf40d0e53.png)

三件事可以应对：

- **划分案例**。用一个 hillclimber 可读的 train 集与一个永不示人的 test 集。train 集分数在涨而 test 集分数纹丝不动，是过拟合的常见预警。
- **失败内容绝不粘进 prompt**。如果 hillclimber 读失败的记录，它绝不能把失败内容粘进 prompt。
- **答案结构性隔离在 model 够不到的地方**。model 有时能「reward hack」，直接找到 eval 的答案。

如下所述，claude-api skill 替你执行这些原则。

## /CLAUDE-API HILLCLIMB

claude-api skill 里的 `hillclimb` 命令把这些原则变成引导式工作流。在 Claude Code 里运行 `/claude-api hillclimb`，Claude 对一个给定 eval 迭代改进。你选择它可以改什么，包括：

- 你的 system prompt
- skills 或指令文件
- 工具描述
- model 选择、effort 档位与其他 API 参数
- 你的 harness 代码

开始之前，Claude 问你要优化什么（表现，或表现持平下的成本），然后把评估集随机划分成 test 与 train。以成本为目标时，它会考虑[几个常见成本项](https://claude.com/blog/reducing-cost-and-improving-performance-with-claude-platform)，包括 prompt caching、审计 prompt 与所选 model 的兼容性、选 model 与 effort 档位。

第一轮之前，Claude 检查 eval 的噪声（分数单凭运气能挪动多远）是否小于你会据以行动的最小改进量；如果不满足，它会说明并建议增加重复数或案例数。

每一轮，Claude 读上一轮的 train 记录，以 patch 形式提议一个改动。它让每一轮瞄准一个效果能盖过 eval 噪声的改动：从根上修失败行为（重写引发它的那一段或补一条缺失的规则），而非改写一行措辞。然后把带 patch 的改动跑一遍评估。此时 Claude 应用一道检查：`train` 集涨而 `test` 集平，怀疑过拟合，撤销 patch。出现回归，撤销。train 与 test 都涨，保留 patch（图 6）。

![hillclimbing 循环：被编辑的东西（如 prompt）喂进固定的 model 与 harness，在留出的 test 划分与 train 划分上打分。analyzer 只读 train 失败、每轮提议一个 diff；diff 在 train 与 test 同涨时保留，只在 train 涨或任一分数下跌时撤销。](https://claude.dev/media/dafbc5fb0edf5aeed96af8984ec09f6a0f8ebd753274c305ccf3043e1640d75a.png)

分数连停两三轮时，Claude 逐条读剩余的 train 失败并按原因归类。如果从一开始就没有单个修复能挣到超过 eval 噪声的分数，它也会提前做这件事，并建议增加重复数或案例数，而非把轮数花在太小测不出的改动上。这一步能抓出含糊的 eval 案例、harness 错误或轮间方差。

只有正当的失败才进入后续 hillclimbing 轮。

hillclimbing 完成时，Claude 把你的代码留在针对你的目标在 test 集上表现最好的版本。它报告 test 结果对基线，附置信区间（图 7）。如果增益在噪声以内，它会说明并建议不要合并。

![收件箱路由 hillclimbing 之后的结果页，对比三个变体的 train 与 test 分数。变体 v1（定义每个队列并加一条平局规则）在两边都拿到最佳 0.875；变体 v2（加两个示例）因 train 涨而 test 平被撤销。](https://claude.dev/media/8c9b0ffdf9d75df81ec451ccb55feb091693fb7eb88ad9c20f3911387e3ec4e1.png)

## 实例

### 以降本为目标的 hillclimbing

我们在一个[内部客服 benchmark](https://claude.com/blog/reducing-cost-and-improving-performance-with-claude-platform) 上跑了 `/claude-api hillclimb`，目标是降本并提升表现。benchmark 含 44 张工单，30 张用于搜索、14 张留出。起点是 Opus 4.8 默认（high）effort：搜索工单上判定准确率 74.4%，token 成本每张 4.6 美分。

hillclimb 先审计 prompt，[删掉](https://claude.com/blog/reducing-cost-and-improving-performance-with-claude-platform)强制工具调用仪式、scratchpad 步骤与互相矛盾的规则。然后试了 Opus 5.5 低 effort。它越过了基线准确率门槛，87.8%，成本降到每张 1.9 美分，不到起点的一半。

部分节省来自 [Opus 5.5 的定价](https://claude.dev/blog/getting-the-most-out-of-opus-5-5/)：输入与输出 token 比 Opus 4.8 便宜 20%，缓存读取便宜 60%。因为 Opus 5.5 过了门槛，hillclimb 接着往下一档走，看更便宜的 model 能不能也过。Sonnet 5 低 effort 拿到约同样的 88.9%，成本约一半，每张 1 美分（图 8）。

图 8 的要点：横轴为每张工单成本（对数刻度）、纵轴为判定准确率，路径四站——起点线标出基线准确率；第 1 站 Opus 4.8 high effort，基线 74.4% at 4.6¢；第 2 站 Opus 5.5 low effort，审计过的 prompt，87.8% at 1.9¢；第 3 站 Sonnet 5 low effort，同一 prompt，88.9% at 1¢；第 4 站 Sonnet 5 low effort，改进 prompt，98.9% at 1¢。

最后，Claude 用路由规则与退款上限交叉核对改进 prompt，把 Sonnet 5 推到 98.9%，成本大致不变。在搜索过程从未见过的 14 张留出工单上，最终配置拿到 90.5%，对照原始配置的 78.6%，成本约五分之一。

### 以提分为目标的 hillclimbing

另一个实例是我们的 [claude-api](https://github.com/anthropics/skills/tree/main/skills/claude-api) skill 本身，它提供使用我们 API 的指引与操作 Claude 的一般建议（含本文讨论的子命令）。我们希望这个 skill 能正确实现用我们 API 的代码，于是基于文档建了一套评估集来测它。

在我们的 eval 上，skill 起点是 66%。我们给 hillclimber 访问文档与 SDK 的权限，让 Claude 能发现错误并自我修正（图 9）。Claude 发现 skill 缺了八个特性的覆盖，给它们在 skill 里加章节后，表现升到 74%。随后它发现 C# 与 Java 类型表里的错误，升到 77%。

图 9 的要点：横轴为 hillclimbing 轮数（0 是基线）、纵轴为通过率；三个阶段：第 1 阶段补缺失章节与类型表（66.1% → 74.3% → 74.0% → 77.5%）；第 2 阶段修正 skill 指导 Claude 写代码的方式（→ 80.1%）；第 3 阶段修评分器加更多 skill 编辑（84.0% → 87.9%），另有一次中段降至 77.2%。

分数连停两轮后，Claude 分析剩余失败并按根因归类。正常一轮只针对最常见的失败做一个编辑。这一步不做编辑，只把全部剩余失败按原因排序。这个反思步骤在几处派上用场：

- 跨失败集合反思后，hillclimber 发现 skill 内容明明在，Claude 写的却是更旧的 API 形态（出自它的训练先验）。对策是 hillclimber 在 skill 顶部附近加了一张表，引导 Claude 从它记得的形态走到当前形态：比如从带固定 token 预算的 extended thinking（近版 Opus model 上 API 已拒绝）走到 adaptive thinking，从旧版 web search 与 web fetch 工具走到当前版本；还把 C# 与 Java 对固定预算 thinking 的警告移到它们的 adaptive-thinking 示例之前。这一步把表现推到 80%。
- 补齐明显的内容缺口后表现仍不动的任务，是示例或评分器有缺陷的信号。一个任务要求代码捕获一种错误类型，它的评分器却要一条至少三个的链。Claude 改写了任务措辞。另一个评分器的指令与我们的文档矛盾，实测真实 API 显示文档是对的。处理这些，加上更多 skill 编辑，把表现推到约 88%。

## 上手

**注意**：先运行 `claude update`。claude-api skill 随 Claude Code 一起发布，更新后拿到的就是这些命令的最新版。

```
claude update
```

然后在 Claude Code 里：

```
/claude-api build-eval
/claude-api hillclimb
```

这些子命令可以在 Claude Code 里经 [claude-api skill](https://github.com/anthropics/skills/tree/main/skills/claude-api) 直接使用：

想为某个问题生成评估集，运行 `/claude-api build-eval`。你可以给它提供示例（如 traces）来引导方向。Claude 会按本文的指引设计案例与评分器，并确保案例与评分器都经你批准。

已有 eval、想让 Claude 对它改进时，运行 `/claude-api hillclimb`，由你的目标引导（更好的表现，或表现持平下更低的成本）。Claude 会按本文的指引，在爬山过程中检查过拟合，也检查 eval 自身的 bug——比如把看起来正确的答案判错的评分器，或 harness 错误——第一轮之前与分数停摆时都会查。

特别感谢 Misha Khalman 的 skill 开发。感谢 Misha Khalman、Michael Segner、Matt Bell、Matt Thanabalan、Punit Shah 的评审、贡献与产品支持。
