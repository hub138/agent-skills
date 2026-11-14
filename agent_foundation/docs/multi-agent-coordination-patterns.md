# 多 agent 协调模式：五种方法与各自的适用场景（Multi-agent coordination patterns: Five approaches and when to use them）

- 原文：[Multi-agent coordination patterns: Five approaches and when to use them](https://claude.com/resources/articles/multi-agent-coordination-patterns)
- 来源：Anthropic，作者 Cara Phillips，贡献者 Eugene Yan、Jiri De Jonghe、Samuel Weller、Erik S.
- 发布：2026-04-10
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 assets.claude.com 绝对直链并配中文短描述；对照表完整翻译；本文是《多 agent 系统：何时用与怎么用》的直接续篇。

在此前的一篇文章里，我们探讨了多 agent 系统何时创造价值、单 agent 何时是更好的选择。本文面向已经做出该判断、接下来需要决定哪种协调模式适合自身问题的团队。

我们见过一些团队依据模式听起来是否复杂高级来选型，没有依据问题本身的形态。我们建议从最简单且可行的模式起步，观察它在哪些地方吃力，再从那里演进。本文考察五种模式的机制与局限：

- **Generator-verifier**：质量关键、评估标准明确的输出
- **Orchestrator-subagent**：任务分解清晰、子任务有界
- **Agent teams**：并行、独立、长时运行的子任务
- **Message bus**：事件驱动管线，agent 生态持续增长
- **Shared state**：agent 相互借鉴发现的协作型工作

## 模式一：Generator-verifier

这是最简单的多 agent 模式，也是部署最广的模式之一。上一篇我们把它作为验证 subagent 模式介绍，本文采用更宽的 generator-verifier 框架，因为生成器并不限定为 orchestrator。

### 运行机制

![Generator-verifier 模式示意图：生成器产出初稿，验证器评估，拒绝时反馈回流形成循环](https://assets.claude.com/5c6e32afcbfc38d375f25ec0f9d187c8cefd49cc.png)

生成器接收任务并产出初始输出，交给验证器评估。验证器检查输出是否满足要求的准则，要么接受它视为完成，要么拒绝并附带反馈。被拒绝时，反馈传回生成器，生成器据此产出修订后的尝试。这个循环持续进行，直到验证器接受输出，或达到最大迭代次数。

### 适用场景

设想一个为客服工单生成邮件回复的支持系统。生成器结合产品文档与工单上下文产出初始回复。验证器对照知识库检查准确性，对照品牌规范评估语气，并确认回复覆盖了工单提出的每一个问题。未通过的检查连同点名确切问题的反馈返回生成器，例如某功能被归到错误的价格档位，或某个工单问题没有得到回应。

输出质量关键、评估标准能明确写清时使用该模式。它对代码生成（一个 agent 写代码，另一个写测试并运行）、事实核查、按 rubric 评分、合规验证都有效，也适用于任何错误输出代价高过一次额外生成循环的领域。

### 失效场景

验证器的上限就是它的标准。只被告知检查输出好不好、没有任何进一步标准的验证器，会给生成器的输出盖橡皮图章。团队最常见的失败形态是把循环实现出来，却没有定义验证的含义，造出只有质量控制表象、没有实质的装置。（提前宣布胜利的问题，我们在上一篇讨论过。）

该模式还隐含一个前提：生成与验证是可分开的技能。评估一个创意方案如果和生成它一样难，验证器就可能无法可靠地抓住问题。

最后，迭代循环可能停滞。生成器无法消化验证器的反馈时，系统会来回震荡、无法收敛。最大迭代上限加回退策略（升级给人处理，或附带保留意见返回最佳尝试）能防止它变成无限循环。

## 模式二：Orchestrator-subagent

层级关系定义了这个模式。一个 agent 担任团队负责人，规划工作、委派任务、汇总结果。subagent 承担具体职责并汇报。

### 运行机制

![Orchestrator-subagent 模式示意图：主 agent 规划并委派，subagent 各自完成后返回结果，主 agent 汇总为最终输出](https://assets.claude.com/c2af5db81717ec0047d62944f960e510860c3dbf.png)

负责人 agent 接收任务并决定处理方式。一部分子任务它直接处理，其余派发给 subagent。subagent 完成工作返回结果，orchestrator 把结果汇总成最终输出。

[Claude Code](https://claude.com/product/claude-code) 就使用这个模式。主 agent 自己写代码、改文件、跑命令，需要搜索大型代码库或调查独立问题时，把 subagent 派到后台，结果回流的同时工作继续推进。每个 subagent 在自己的上下文窗口里运作，返回提炼过的发现。这样 orchestrator 的上下文保持聚焦在主任务上，探索则在并行发生。

### 适用场景

设想一个自动化 code review 系统。pull request 到达时，系统要检查安全漏洞、核实测试覆盖、评估代码风格、评价架构一致性。每项检查各自独立、需要不同上下文、产出明确结果。orchestrator 把每项检查派给专门的 subagent，收集结果并汇总成一份完整的评审。

任务分解清晰、子任务相互依赖少时使用该模式。orchestrator 维持对总体目标的连贯认知，subagent 保持对具体职责的专注。

### 失效场景

orchestrator 会成为信息瓶颈。参见[何时把 subagent 折回主 agent 循环](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)。subagent 发现了与另一个 subagent 工作相关的东西时，信息必须经 orchestrator 中转。安全 subagent 发现一个影响架构 subagent 分析的鉴权缺陷时，orchestrator 必须识别出这个依赖，并把信息传递到位。几次这样的交接之后，关键细节常被丢失或被摘要抹掉。

顺序执行也限制吞吐。没有显式并行化时，subagent 一个接一个运行，系统承担了多 agent 的 token 开销，却没拿到速度收益。

## 模式三：Agent teams

当工作分解出的并行子任务能长时间独立推进时，orchestrator-subagent 可能带来不必要的束缚。

### 运行机制

![Agent teams 模式示意图：协调者派出多个 worker agent，worker 从共享队列认领任务，长期存活并自主推进](https://assets.claude.com/c3208865ee6a6c6c0c7a071d66fa797d72b2dfcc.png)

协调者把多个 worker agent 作为独立进程派生出来。队友从共享队列认领任务，跨多个步骤自主推进，完成时发出信号。

与 orchestrator-subagent 的差别在 worker 的持久性。orchestrator 为一个有界子任务派生 subagent，subagent 返回结果后即终止。队友跨多次任务保持存活，积累上下文与领域专门化，性能随时间提升。协调者分配工作、收集产出，任务之间不重置 worker。

### 适用场景

设想把一个大型代码库从一套框架迁移到另一套。每个队友独立迁移一个服务，连同它自己的依赖、测试套件与部署配置。协调者把每个服务指派给一个队友，队友自主走完迁移全程：更新依赖、修改代码、修复测试、验证。协调者收集完成的迁移，并在全系统范围内跑集成测试。

子任务独立、且能从持续的多步骤工作中受益时使用该模式。每个队友积累自己领域的上下文，每次派发无需从零开始。

### 失效场景

独立性是关键前提。orchestrator-subagent 里 orchestrator 能在 subagent 之间居中传递信息，这里队友自主运作，难以共享中间发现。一个队友的工作影响另一个时，双方都察觉不到，产出可能互相冲突。

完成检测也更难。队友自主工作、耗时各不相同，协调者必须处理部分完成的形态：一个队友两分钟收工，另一个要二十分钟。

共享资源让两个问题都加重。多个队友在同一代码库、数据库或文件系统上操作时，两个队友可能编辑同一个文件，或做出互不兼容的修改。该模式需要谨慎的任务划分与冲突解决机制。

## 模式四：Message bus

agent 数量增加、交互形态变复杂后，直接协调会变得难以管理。message bus 引入一个共享通信层，agent 在上面发布与订阅事件。

### 运行机制

![Message bus 模式示意图：agent 通过 publish 与 subscribe 两个原语经路由器交互，新 agent 订阅话题即可接入](https://assets.claude.com/62e7d3b2ede639843ba270fdba84aa57f446ffad.png)

agent 通过两个原语交互：publish 与 subscribe。agent 订阅自己关心的话题，路由器投递匹配的消息。带新能力的新 agent，无需改动既有连接就能开始接收相关工作。

### 适用场景

安全运营自动化系统展示了该模式的强项。告警从多个来源到达，triage agent 按严重程度与类型逐条分类，把高严重度的网络告警交给网络调查 agent，把凭据相关的告警交给身份分析 agent。每个调查 agent 可以发布补充上下文的请求，由负责收集背景的 agent 兑现。发现流向响应协调 agent，由它决定合适的动作。

这条管线适合 message bus：事件从一阶段流向下一阶段，团队能随威胁类别的演变增加新 agent 类型，各 agent 可以独立开发与部署。

事件驱动管线使用该模式：工作流从事件中浮现，没有预定序列可走，且 agent 生态大概率会增长。

### 失效场景

事件驱动通信的灵活性让追踪变难。一条告警在五个 agent 之间触发一连串事件时，弄清发生了什么需要细致的日志与关联。调试比跟踪 orchestrator 的顺序决策更费力。

路由准确性同样关键。路由器错分或丢掉一个事件，系统会静默失败：什么都没处理，也从不崩溃。基于 LLM 的路由器提供语义灵活性，也引入它们自己的失败形态。

## 模式五：Shared state

![Shared state 模式示意图：多个 agent 直接读写同一个持久存储，没有中央协调者](https://assets.claude.com/f4a221e1b8bc3421162b15f565fa1b46725c0e7c.png)

前几种模式里的 orchestrator、团队负责人与消息路由器，都在中央管理信息流。shared state 撤掉中间人，让 agent 通过一个人人可直接读写的持久存储来协调。

### 运行机制

agent 自主运作，读写同一个共享数据库、文件系统或文档。没有中央协调者。agent 到存储里查相关信息，按所发现的内容行动，再把发现写回去。工作通常由一个初始化步骤向存储放入问题或数据集开始，满足终止条件时结束：时间上限、收敛阈值，或一个专职 agent 判定存储里已包含足够的答案。

### 适用场景

设想一个研究综合系统，多个 agent 调查一个复杂问题的不同侧面。一个探索学术文献，一个分析行业报告，一个考察专利申请，一个跟踪新闻报道。每个 agent 的发现都可能指导其他 agent 的调查。学术文献 agent 可能发现一位关键研究者，其所在公司正值得行业 agent 深入考察。

用 shared state 时，发现直接进存储。行业 agent 立刻就能看到学术 agent 的发现，无需等待协调者传递。agent 在彼此的工作上继续建构，共享存储成为一个持续演进的知识库。

shared state 还消除了协调者这个单点故障。任何一个 agent 停了，其余照常读写。orchestrator 与 message bus 系统里，协调者或路由器失效会让全部停摆。

### 失效场景

缺少显式协调时，agent 可能重复劳动，或追求相互矛盾的路线。两个 agent 可能各自独立调查同一条线索。agent 之间的交互产生系统行为，并非自上而下设计的产物，这让结果更难预测。

更难处理的失败形态是反应循环。例如 agent A 写入一条发现，agent B 读到后写入跟进，agent A 看到跟进又作出回应。系统持续把 token 烧在不收敛的工作上。重复劳动与并发写入有成熟的工程解法（加锁、版本控制、分区）。反应循环是行为层面的问题，需要一等公民地位的终止条件：时间预算、收敛阈值（N 个周期无新发现），或一个专职 agent 负责判定存储何时包含足够的答案。把终止当事后补丁的系统倾向于无限循环，或等某个 agent 的上下文装满时随意停下。

## 模式选择与演进

选哪个模式，取决于系统的几个结构性问题。上一篇我们主张以上下文为中心的分解：按每个 agent 需要什么上下文来划分工作，并非按工作类型划分。该原则在这里同样适用。这些模式的差别，在如何管理上下文边界与信息流。

### Orchestrator-subagent 与 Agent teams

![对照一：核心问题在 worker 需要把上下文维持多久](https://assets.claude.com/742de423f421c12760fb8137e18732fc87dab10d.png)

两者都有协调者把工作派给其他 agent。问题在 worker 需要把上下文维持多久。

- **选 orchestrator-subagent**：子任务短小、聚焦、产出明确时。code review 系统在此合适，每项检查在一次有界调用内完成分析、生成报告并返回，subagent 无需跨多个周期携带上下文。
- **选 agent teams**：子任务能从持续的多步骤工作中受益时。代码库迁移在此合适，每个队友对自己负责的服务培养出真实的熟悉度：依赖图、测试模式、部署配置。积累的上下文带来的性能提升，一次性派发无法复制。

subagent 需要跨调用保留状态时，agent teams 更合适。

### Orchestrator-subagent 与 Message bus

![对照二：核心问题在工作流结构是否可预知](https://assets.claude.com/680a70cf3ec53a3757197be17373e6e1ec814c51.png)

两者都能处理多步骤工作流。问题在工作流结构的可预知程度。

- **选 orchestrator-subagent**：步骤序列预先已知时。code review 系统走固定管线：接收 PR、跑检查、汇总结果。
- **选 message bus**：工作流从事件中浮现、随发现而变化时。安全运营系统无法预知会来什么告警、需要什么调查路径，新的告警类型可能出现、需要新的处理。message bus 通过把事件路由给有能力的 agent 来容纳这种变化，没有预定序列可走。

当 orchestrator 里为应对日益增多的情形而堆积条件逻辑时，message bus 把这种路由做成显式且可扩展的。

### Agent teams 与 Shared state

![对照三：核心问题在 agent 是否需要彼此的发现](https://assets.claude.com/4375086ca2c10edfec16fb20d4c95831d04ab1ad.png)

两者都有 agent 自主工作。问题在 agent 是否需要彼此的发现。

- **选 agent teams**：agent 在互不接触的分区上工作时。代码库迁移在此合适，每个队友管自己的服务，协调者最后合并结果。
- **选 shared state**：工作是协作型的、发现需要实时流动时。研究综合系统更匹配，学术 agent 发现关键研究者这件事，立刻就与行业 agent 的调查相关。

一旦队友需要相互交流、只共享最终结果不够用时，shared state 让这件事更自然。

### Message bus 与 Shared state

![对照四：核心问题在工作是离散事件流动，还是积累成共享知识库](https://assets.claude.com/e35f51e67250164340de169834495f360b8ff295.png)

两者都支持复杂的多 agent 协调。问题在工作以离散事件流动，还是积累成共享知识库。

- **选 message bus**：agent 在管线中对事件作出反应时。安全运营系统逐阶段处理告警，每个事件在完成前触发下一个。该模式把事件路由给有能力的 agent，效率高。
- **选 shared state**：agent 随时间在积累的发现上建构时。研究综合系统持续汇集知识，agent 反复回到存储，查看别人发现了什么，并调整自己的调查。

message bus 仍有路由器，存在一个中央组件决定事件去向。shared state 是去中心的。如果消除单点故障是优先项，shared state 提供得更彻底。

message bus 系统里的 agent 发布事件是为了共享发现、并非触发动作时，shared state 更合适。

## 上手起步

生产系统常组合多种模式。一种常见混合，用 orchestrator-subagent 承担整体工作流，用 shared state 承担协作密集的子任务。另一种用 message bus 做事件路由，用 agent team 形态的 worker 处理每种事件类型。这些模式是积木，彼此并非互斥选项。

下表概括各模式的适用时机。

| 情形 | 模式 |
| --- | --- |
| 输出质量关键，评估标准明确 | Generator-Verifier |
| 任务分解清晰，子任务有界 | Orchestrator-Subagent |
| 并行负载，独立的长时运行子任务 | Agent Teams |
| 事件驱动管线，agent 生态持续增长 | Message Bus |
| 协作研究，agent 共享发现 | Shared State |
| 要求无单点故障 | Shared State |

对多数用例，我们建议从 orchestrator-subagent 起步。它以最少的协调开销覆盖最广的问题范围。观察它在哪里吃力，等具体需求明确后，再向其他模式演进。

*后续文章将逐一深入每种模式，附生产实现与案例研究。多 agent 系统何时值得投入的背景，见[多 agent 系统：何时用与怎么用](https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them)。*

## 致谢

由 Cara Phillips 撰写，Eugene Yan、Jiri De Jonghe、Samuel Weller、Erik S. 贡献。

> 包内互引：本篇是 multi-agent-when.md（《多 agent 系统：何时用与怎么用》）的直接续篇，何时值得从单 agent 转向多 agent 的判定框架见该篇；同一团队的多 agent 研究系统实录见 multi-agent-research.md；把 subagent 折回主循环的反方向判断见 fold-subagents.md。
