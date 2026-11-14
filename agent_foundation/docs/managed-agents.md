# 扩展 Managed Agents：大脑与双手解耦（Scaling Managed Agents: Decoupling the brain from the hands）

- 原文：[Scaling Managed Agents: Decoupling the brain from the hands](https://www.anthropic.com/research/managed-agents)
- 来源：Anthropic Engineering，作者 Lance Martin、Gabe Cemaj、Michael Cohen
- 发布：2026-04-08
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图，地址为原文 CDN 直链。

按照我们的[文档](https://platform.claude.com/docs/en/managed-agents/overview)可以上手使用 Claude Managed Agents。

工程博客的一条主线，是如何为[长周期工作](https://www.anthropic.com/engineering/harness-design-long-running-apps)[构建高效 agent](https://www.anthropic.com/engineering/building-effective-agents) 与[设计 harness](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)。这些工作有一条共同线索：harness 编码了对「Claude 自己做不到什么」的假设。这些假设需要经常被质疑，因为模型进步后它们会[过时](http://www.incompleteideas.net/IncIdeas/BitterLesson.html)。

只举一个例子：先前[我们发现](https://www.anthropic.com/engineering/harness-design-long-running-apps)，Claude Sonnet 4.5 在感觉到上下文上限逼近时会提前收尾任务，这个行为有时被称为 "context anxiety"（上下文焦虑）。我们在 harness 里加了 context reset 来处理。但同一套 harness 用在 Claude Opus 4.5 上，这个行为消失了，reset 变成了累赘。

我们预期 harness 会继续演化，于是构建了 Managed Agents：Claude Platform 里的一个托管服务，替你运行长周期 agent。它只暴露一小组接口，这组接口的生命力要长过任何具体实现，包括我们今天自己运行的实现。

构建 Managed Agents 意味着解决计算领域的一个老问题：如何为「[尚未被设想的程序](http://www.catb.org/esr/writings/taoup/html/ch03s01.html)」设计系统。几十年前，操作系统把硬件虚拟化成抽象（process、file），通用到足以支撑当时还不存在的程序。抽象比硬件活得久。`read()` 命令并不关心自己访问的是 1970 年代的磁盘组还是现代 SSD。上层抽象保持稳定，底层实现自由更换。

Managed Agents 沿用同一模式。我们把 agent 的组件虚拟化：session（发生过的一切的只追加日志）、harness（调用 Claude 并把 Claude 的工具调用路由到相应基础设施的循环）、sandbox（Claude 可以运行代码与编辑文件的执行环境）。每个组件的实现都能独立替换，互不干扰。我们对接口形态有主见，对接口背后跑什么没有主见。

![agent 组件虚拟化示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/903b624ada206b10753a24c6a1367e74a869165d-1080x1080.png)

## 别养宠物

最初我们把 agent 的全部组件放进同一个容器：session、agent harness 与 sandbox 共享一个环境。这个做法有好处，比如文件编辑就是直接的 syscall，也不需要设计服务边界。

但把一切都耦合进一个容器，我们撞上一个老的基础设施问题：我们养了一只[宠物](https://cloudscaling.com/blog/cloud-computing/the-history-of-pets-vs-cattle/)。在 pets vs cattle（宠物与牲口）的类比里，pet 是有名字、人工照看、丢不起的个体，cattle 则可以互换。我们的情况里，服务器成了那只 pet：容器一挂，session 就丢了；容器失去响应，我们得把它救回来。

救容器意味着调试失去响应、卡住的 session。我们唯一的入口是 WebSocket 事件流，但它说不出失败出在哪一层，于是 harness 的 bug、事件流的丢包、容器掉线，表现全都一样。要弄清哪里出了问题，工程师得进容器开一个 shell，而那个容器里往往还装着用户数据，这条路实际上等于我们没有调试能力。

第二个问题是 harness 假设 Claude 处理的一切都和它同住一个容器。客户要求把 Claude 接到他们自己的虚拟私有云（VPC）时，只能把他们的网络和我们的打通，或者在我们的环境之外自行运行我们的 harness。写进 harness 的一个假设，在我们想接不同基础设施时就变成了问题。

## 大脑与双手解耦

我们最终的解法，是把「大脑」（Claude 与它的 harness）同「双手」（执行动作的 sandbox 与工具）以及「session」（会话事件日志）分开。每一方都成为对其他方几乎不做假设的接口，可以独立失败、独立替换。

**harness 离开容器。** 大脑与双手解耦后，harness 不再住在容器里。它像调用任何其他工具一样调用容器：`execute(name, input) → string`。容器变成了 cattle。容器挂掉时，harness 把失败捕获为一次工具调用错误，传回给 Claude。Claude 若决定重试，可以用标准配方 `provision({resources})` 重新初始化一个新容器。我们再也不用抢救坏掉的容器。

**从 harness 故障中恢复。** harness 本身也变成了 cattle。session 日志在 harness 之外，harness 里没有任何东西需要在崩溃后幸存。一个 harness 挂了，用 `wake(sessionId)` 启动一个新的，用 `getSession(id)` 取回事件日志，从最后一个事件继续。agent 循环运行期间，harness 用 `emitEvent(id, event)` 持续写 session，保住事件的持久记录。

![harness 崩溃恢复示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/73e900af5b9d6ed8c64db0a8e74d4465963556b7-1640x1596.png)

**安全边界。** 耦合设计里，Claude 生成的任何不受信任的代码都与凭证同住一个容器，prompt injection 只需要说服 Claude 读自己的环境变量。攻击者拿到那些 token 后，可以开出全新的、不受限制的 session，并把工作委派过去。收窄 token 权限是显而易见的缓解手段，但那又编码了一条假设：拿着受限 token 的 Claude 做不了什么。而 Claude 越来越聪明。结构性的修复是保证 token 永远够不到 Claude 生成代码所在的 sandbox。

我们用两个模式保证这一点。认证可以随资源捆绑，也可以放在 sandbox 之外的保险库里。Git 场景：用仓库各自的 access token 在 sandbox 初始化时克隆仓库，并接进本地 git remote。在 sandbox 里 git `push` 与 `pull` 都能用，agent 全程不接触 token 本身。自定义工具场景：我们支持 MCP，把 OAuth token 存在安全保险库里。Claude 通过一个专用代理调用 MCP 工具；代理接收一个与 session 关联的 token，再从保险库取出对应凭证去调外部服务。harness 对凭证永远一无所知。

## session 不等于 Claude 的上下文窗口

长周期任务常常超出 Claude 上下文窗口的长度，标准应对手段全都涉及「保留什么」的不可逆决定。我们在上下文工程的[先前工作](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)里探讨过这些技术：compaction 让 Claude 保存上下文窗口的摘要，memory tool 让 Claude 把上下文写进文件，实现跨会话学习。还可以配合 context trimming，有选择地移除旧工具结果、thinking block 这类 token。

但保留或丢弃上下文的不可逆决定可能引发失败。很难知道未来的轮次会需要哪些 token。消息若被 compaction 步骤改写，harness 会把压缩后的消息从 Claude 的上下文窗口移除，只有在存了底的情况下才能恢复。先前工作[探索过](https://arxiv.org/pdf/2512.24601)应对方式：把上下文存成一个住在上下文窗口之外的对象。比如上下文可以是 REPL 里的一个对象，LLM 用写代码的方式程序化访问它，做过滤或切片。

![getEvents 位置切片示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/cf0719d7832b1f577b7393c84a7c53eecc725ca4-760x200.png)

Managed Agents 里，session 提供同样的好处，充当住在 Claude 上下文窗口之外的上下文对象。只是它不存放在 sandbox 或 REPL 里，而是持久存在 session 日志中。接口 `getEvents()` 让大脑通过选取事件流的位置切片来审阅上下文。这个接口用法灵活：大脑可以从上次读到的地方接着读，可以回退到某个时刻之前多看几条事件了解来龙去脉，也可以在某个动作之前重读上下文。

取回的事件还能先在 harness 里变换，再送进 Claude 的上下文窗口。变换内容随 harness 的设计而定，包括为提高 prompt cache 命中率所做的上下文组织，以及各种上下文工程。我们把「session 里可恢复的上下文存储」与「harness 里任意的上下文管理」作为两个关注点分开，因为预测不了未来的模型需要哪种具体的上下文工程。接口把上下文管理推给 harness，只保证 session 持久、可随时审阅。

## 多个大脑，多双手

**多个大脑。** 大脑与双手解耦，顺带解决了我们最早收到的一批客户抱怨。团队想让 Claude 操作他们自己 VPC 里的资源时，唯一的路径是把他们的网络和我们的打通，因为装着 harness 的容器假设所有资源都近在身边。harness 搬出容器后，这个假设消失了。同一个改动还有性能回报。最初把大脑放进容器，意味着多少个大脑就需要多少个容器。每个大脑都要等到容器配好才能开始推理，每个 session 都要先支付完整的容器启动成本。每个 session，哪怕根本不会用到 sandbox，都要克隆仓库、启动进程、从我们的服务器拉取待处理事件。

这些空转时间体现在 time-to-first-token（TTFT，首 token 时间）上：TTFT 衡量一个 session 从接到工作到产出第一个响应 token 之间等待多久，是用户感受最直接的延迟。

大脑与双手解耦后，容器只在大脑需要时才通过工具调用 `(execute(name, input) → string)` 去申请。不马上需要容器的 session 就不用等容器。编排层从 session 日志拉到待处理事件，推理立刻就能开始。用这套架构，我们的 p50 TTFT 降了大约 60%，p95 降了超过 90%。扩展到多个大脑只是启动多个无状态 harness，需要时才把它们连上双手。

**多双手。** 我们还想让每个大脑能连多双手。实际含义是 Claude 要推理多个执行环境并决定把工作发到哪里，这是比在单一 shell 里操作更难的认知任务。最初把大脑放进单一容器，是因为早期模型做不到这一点。智能上去之后，单一容器反而成了限制：容器一挂，大脑伸进去的每一只手的状态都丢了。

大脑与双手解耦后，每只手都是一个工具 `execute(name, input) → string`：送进名字与输入，返回一个字符串。这个接口支持任何自定义工具、任何 MCP server，以及我们自己的工具。harness 不知道 sandbox 是容器、手机还是 Pokémon 模拟器。而且没有哪只手与任何大脑耦合，大脑之间可以互传双手。

![多大脑与多双手示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/4f67b1c10566552aec514a716ea43544ab330e0b-668x243.png)

## 结论

我们面对的是个老问题：如何为「尚未被设想的程序」设计系统。操作系统靠把硬件虚拟化成足够通用的抽象，稳定运行了几十年。Managed Agents 的目标，是设计一个能容纳未来 harness、sandbox 与 Claude 周边其他组件的系统。

Managed Agents 本身是一个同样精神下的 meta-harness，对 Claude 未来需要哪种具体 harness 不持主见。它是一个带通用接口的系统，允许许多不同的 harness。比如 Claude Code 就是一个出色的 harness，我们在大量任务里广泛使用。我们也展示过面向特定任务的 agent harness 在狭窄领域表现优异。Managed Agents 能容纳其中任何一种，随时间匹配 Claude 的智能水平。

meta-harness 设计意味着对 Claude 周边的接口持有主见：我们预期 Claude 需要操纵状态（session）与执行计算（sandbox）的能力，也预期 Claude 需要扩展到多个大脑与多双手的能力。我们把接口设计成能长期可靠、安全地运行。但对 Claude 需要多少个大脑、多少双手、它们在哪里，我们不做任何假设。

## 作者与致谢

本文由 Lance Martin、Gabe Cemaj 与 Michael Cohen 撰写。感谢 N.T.A. 与 Jeremy Fox 就这些主题的有益讨论。特别感谢 Agents API 团队与 Jake Eaton 的贡献。

> 包内互引：Managed Agents 三代接口面演进、三原语与 context anxiety 案例见 managed-agents-evolution.md；把大脑与双手解耦应用到定时自动化的运行纪律见 claude-agent-automations.md；沙箱隔离与权限收紧的通用原则见 contain-claude.md。
