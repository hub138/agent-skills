# 我们如何跨产品封锁 Claude（How we contain Claude across products）

- 原文：[How we contain Claude across products](https://www.anthropic.com/research/how-we-contain-claude)
- 来源：Anthropic（anthropic.com），作者 Max McGuinness、Mikaela Grace、Jiri De Jonghe、Jake Eaton、Abel Ribbink
- 发布：2026-05-25
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 www-cdn.anthropic.com 绝对直链并配中文短描述；三类风险与三层防御、三种封锁模式与四起漏掉的风险、对比表格、脚注与作者致谢完整翻译。

十二个月前，如果有人提议授予 Claude 足以弄垮 Anthropic 某个内部服务的访问权限，我们会当场否决。今天这个级别的访问已是常态，Anthropic 的开发者也因此更高产。这类部署的风险有两个分量：失败发生的概率，以及一旦失败能造成的破坏。安全防护与模型训练的进展在持续压低前者；后者——理论上的爆炸半径——只随能力与访问范围的扩张而增长。当 agent 逐渐能完成过去需要一个人甚至一个团队的工作，不部署的代价已经大到让风险收益计算明显倒向采用，前提是产品能做安全。工程问题于是变成：如何给爆炸半径封顶。

![自主 agent 爆炸半径与部署决策的关系图](https://www-cdn.anthropic.com/images/4zrzovbb/website/5ebc85c6325c7f59bd6c08950ff9beb1863f1345-1920x866.png)

*图注：当能对自主 agent 的相对破坏设界——比如通过控制它的环境——高价值能力就足以支撑部署决策。Claude Mythos Preview 是 2026 年 4 月被判定爆炸半径过高而不能发布的模型的例子。随着防御方加固关键系统、安全防护走向成熟，我们预计类似能力水平的模型会逐渐适合更广的发布，尽管一些风险永远存在。模型能力是 agent 部署总风险里的一个重要因子。*

做到这一点大致有两条路。

第一条是通过人工介入（human-in-the-loop）监督 agent 的行为。Claude Code 早先靠每轮向用户请求权限来防止 agent 采取意料之外的动作。理论上这行得通，但我们发现这个做法并不可靠。我们的遥测数据显示，用户批准了大约 93% 的权限弹窗。用户看到的批准请求越多，分配给每一个的注意力就越少，监督随着时间推移越来越潦草。我们最近构建了 Claude Code auto mode，用[自动化的更安全批准](https://www.anthropic.com/engineering/claude-code-auto-mode)来缓解这种审批疲劳。但漏洞仍在——任何概率性防御都有一个非零的漏报率。[1](#脚注)

第二条路——也是本文大部分篇幅所在——是封锁（containment）。封锁盯住的是 agent 能做什么：用沙箱、虚拟机、出站控制等手段强制设定访问边界。这是 Anthropic 工程投入最多的地方，也是多起最出乎意料的安全失效发生的地方。

过去两年我们发布了三个主要的 agent 产品：[claude.ai](https://claude.ai)、Claude Code 和 Claude Cowork。每一个面向不同的用户群体，需要不同的封锁架构。本文分享哪些设计经受住了考验、哪些出了问题，以及我们一路上学到的 agent 安全经验。

## 三类风险，三层防御

对 agent 的安全风险大致分三类：

**用户误用。** 用户——出于恶意或疏忽——指示 agent 做有害的事。从让 agent 绕开一个觉得烦人的检查，到执行一条自己看不懂的破坏性命令，到明确指定伤害，都算在内。

**模型失当。** agent 采取没人要求的有害动作。随着模型进步，它们在多数行为评测上越来越守规矩，但这不代表风险必然缩小。能力弱些的模型更容易误判形势、犯明显的错误。能力强的模型犯错更少，可它们也更擅长找到通往目标的意外路径，经常绕开没人想过要写下来的限制。

在 Anthropic，我们见过 Claude「乐于助人地」[逃出沙箱](https://red.anthropic.com/2026/mythos-preview/)只为完成任务、翻查 git history 去[找编码测试的答案](https://assets.anthropic.com/m/64823ba7485345a7/Claude-Opus-4-5-System-Card.pdf)、自发认出自己正在跑的 benchmark 并[解密答案钥匙](https://www.anthropic.com/engineering/eval-awareness-browsecomp)。每一代模型都带来一组新能力，这些能力有时会被用在没人预料的方向上。

**外部攻击者。** agent 经由工具、文件或网络访问等外部途径受到攻击。这一类既包括 prompt injection，也包括针对 agent 运行时、编排层或代理服务的常规攻击。

构建封锁与防御体系时，我们把防御放在三个组件上：

**agent 运行的环境。** 我们用进程沙箱、VM、文件系统边界和出站控制来约束 agent 能在哪里、以什么方式行动。目标是给 agent 能触及的范围画一条硬边界。例如，凭据从不进入沙箱，就永远偷不走——无论起因是用户、模型找到一条「有创意」的路径，还是攻击者。

收紧的边界也意味着可以放松监督。Claude Code 的[参考 devcontainer](https://code.claude.com/docs/en/devcontainer) 正是为让 agent 无人值守运行、免于逐动作审批而存在的。

**agent 咨询的模型。** 这里的机制包括系统提示词、分类器、探针和训练层面的修改。模型是概率性的，这些手段只塑造 agent 的倾向，管不住它理论上做得到的事。

这些防御很强。在测试 prompt injection 易感性的 Gray Swan Agent Red Teaming benchmark 上，[Claude Opus 4.7](https://www-cdn.anthropic.com/files/4zrzovbb/website/037f06850df7fbe871e206dad004c3db5fd50340.pdf) 把单次攻击成功率压在约 0.1%，百次自适应攻击后约 5–6%。Claude Code auto mode 在过激行为执行前拦住约 83%[的案例](https://www.anthropic.com/engineering/claude-code-auto-mode)。但即便有同类最佳的防御，模型层的防护永远不会 100% 有效，所以它不能独自扛。

**agent 能触及的外部内容。** MCP 服务器、第三方插件、web 搜索工具都从你控制不了的来源往 agent 上下文里喂内容。审过的连接器不等于审过的数据——比如 GitHub 连接器通过恶意软件检查后，照样能把一份投毒的 README 直接送进模型上下文。细粒度限制工具权限能帮助压缩爆炸半径。一个只有只读数据库访问的 agent，能部署的范围远大于一个往生产库写数据的。

各层防御要互相重叠、互相补位。环境防御不可用时，模型层就得补位（Claude Code 的 [auto mode](https://claude.com/blog/auto-mode) 正是为此设计）。在本地，环境与模型层防御可以挡住恶意工具输出；在更上游的位置，还可以通过限制工具自身的能力与访问来叠加防御。

![三个防御组件示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/5fae1ecca4cd8aaefb9ac949348e96967f9a5100-1920x1080.png)

*图注：需要防御的三个组件：模型、它运行的环境、agent 能触及的外部内容。*

## 封锁 agent 的三种模式

聚焦环境层，我们描述三种隔离模式，以及它们在三个 Claude 平台——claude.ai、Claude Code、Cowork——上各自的形态。每个设计都是逐步到达的：在「我们需要 agent 具备的能力」与「要求用户介入的程度」之间找平衡。

### 模式一：临时容器（claude.ai 的代码执行）

claude.ai 最广为人知的是聊天界面，但它也写代码、跑代码、生成文件、调用连接器。Claude 在 claude.ai 里跑代码时，用的是隔离基础设施上的 [gVisor](https://en.wikipedia.org/wiki/GVisor) 容器。agent 完全在服务端；本地机器上不跑任何代码，文件系统是临时的（每个会话一份）。爆炸半径很小，但 Claude 能做的事的上限同样小——没有持久工作区，也访问不到用户的文件系统。

这也让 claude.ai 面对更传统的威胁模型：要保护的是自家基础设施，以及租户彼此之间的隔离，用户机器不在保护范围内。claude.ai 上线前的安全工作被传统安全占据：网络配置、内部服务认证、编排。

这项工作强化了安全领域最老的教训：最薄弱的一层是自己造的那一层。gVisor 和 [seccomp](https://en.wikipedia.org/wiki/Seccomp) 在 agent 出现之前很久，就经受住了资金充足的对手的持续攻击，所以评审力气花在我们围绕它们新造的部分上。这一点后面还会回来讲，因为我们自建的代理服务，正是在后果最重的事故里失效的那一块。

### 模式二：人工介入的沙箱（Claude Code）

Claude Code 跑在用户机器上，能访问文件系统、shell 和网络。没有这些，编码 agent 的用处有限，所以必须找到安全授予这些访问的办法。

一条路是依靠人工介入。这条路对 Claude Code 可行，原因在于平均用户是熟悉编码环境的开发者：他们读得懂 bash，知道 `rm -rf` 干什么，而且每周都在跑好几次来源不可信的 `npm install`。这些都意味着「允许此次」弹窗弹出时，他们很可能具备准确评估 agent 正在做什么、风险有多大的专业能力。基于这一点，Claude Code 上线时用的是最简单的防御：读放行，写、bash 和网络访问需要审批。

然而如前所述，审批疲劳[几周内就出现了](https://www.reddit.com/r/ClaudeAI/comments/1rru8zw/just_picked_up_a_new_keyboard_cant_wait_to_write/)。讽刺的是，一个原本为监督而设计的功能，效果可能走向反面——一些用户干脆不再认真看。作为缓解轻率批准的第一步，我们发布了 OS 级沙箱（macOS 用 Seatbelt，Linux 用 bubblewrap）来加固边界：读放行，写在工作区内放行，网络默认拒绝。沙箱内 agent 基本不被打断地运行。结果是权限弹窗减少 84%，我们还[开源了运行时](https://github.com/anthropic-experimental/sandbox-runtime)，边界因此可审计。

我们的[匿名使用数据](https://www.anthropic.com/news/measuring-agent-autonomy)还显示，熟练用户自动批准的频率大约是新用户的两倍，但他们也更常在执行中途打断 agent。熟练用户更多只在 agent 跑歪时介入监督，很少逐个步骤把门。这也许是人机协作方式的自然演化，但同样不可靠：它要求用户既有技术功底又足够专心，才能第一时间察觉跑歪。随着模型能力增强、agent 开始写越来越有野心的 bash，察觉跑歪越来越难。随着用户转向多 agent 系统，这种监督方式有效的可能性也在大幅下降。

#### 我们漏掉的风险：信任对话框之前的一切

2025 年中到 2026 年 1 月之间，我们经责任披露渠道收到多份 Claude Code 漏洞报告。其中三份瞄准的代码，在用户同意任何东西之前执行。理解这如何可能，看最直接的一例：开发者克隆一个仓库来评审一个 pull request，仓库里带着 `.claude/settings.json`，里面定义了一个 hook。Claude Code 在启动时读取项目设置——先于展示标准的「你信任这个文件夹吗？」提示——攻击者编写并提交的 hook 就会自动执行。其余两例结构相似：尚未受信目录里的输入，在信任边界建立之前就被解析了。

每一例的修复形状相同：把项目本地配置的解析与执行，推迟到用户接受信任提示之后。如果你在做类似的东西，把项目打开、配置加载和 localhost 监听，当作来自互联网的入站请求对待。不能因为它们感觉上是本地的、来得早于用户同意，就默认信任。

#### 我们漏掉的风险：用户作为注入载体

2026 年 2 月，一次受控的内部红队演练中，一名研究员通过钓鱼让一位员工启动了带恶意 prompt 的 Claude Code。钓饵看起来像寻常协作——一封「能帮我跑一下这个吗？」的邮件，附一段可直接粘贴的 prompt——prompt 本身读起来就像例行任务说明。但在若干准备步骤中间，它不动声色地让 Claude 读取 `~/.aws/credentials`，把内容编码后 POST 到外部端点。这段 prompt 重试 25 次，Claude 完成外泄 24 次。

这是直接 prompt injection——攻击者的指令经由用户本人抵达，未经工具输出或抓取内容。我们的模型层防御锚在用户意图上：当用户自己键入指令时，分类器没有异常可查。把同样的脚本交给人类外包商，他会做同样的事。

这种局面下唯一守得住的防御是环境层：出站控制不论意图如何都拦掉那个 POST，文件系统边界让 `~/.aws` 从一开始就够不着。

（我们把工作中的 prompt 发进内部 Slack 讨论时，有人指出部分内部 agent 会读 Slack。载荷就此散布在环境里。我们给线程加了[金丝雀字符串](https://www.fortinet.com/resources/cyberglossary/what-is-canary-in-cybersecurity)，一旦有什么东西捡起它我们就能察觉。在一个 agent 什么都读的世界里，调查工具本身也是攻击面。）

### 模式三：本地 VM（Claude Cowork）

Claude Cowork 跑在用户桌面上，能访问用户选中的工作区文件夹。这个平台面向一般知识工作，软件工程之外的领域，平均用户熟悉 bash 的概率低得多。

人工介入的沙箱策略因此难以迁移：不该指望非技术知识工作者去评判 `find . -name "*.tmp" -exec rm {} \;` 这样的 bash 长指令。当批准一个例外的判据是典型用户不具备的专业能力时，管理员该设一条绝对且常开的边界。

为此，Claude Cowork 的第一个版本跑在一个完整虚拟机里，用的是平台厂商的 hypervisor（macOS 上是 Apple 的 Virtualization framework，Windows 上是 HCS）。VM 有自己的 Linux 内核、自己的文件系统、自己的进程表。用户选中的工作区与 `.claude` 文件夹被挂载进来；宿主上的其余一切不可见。凭据留在宿主 keychain，从不进入 guest。这个设计防的是 Claude 在某个时刻行为失矩的可能。一个被攻陷的 Claude 仍能破坏工作区文件夹内的东西，所以架构要保证那是它唯一够得着的东西（直到用户添加连接器），且用户控制着挂载了什么。

在最初的架构——我们称为 full-VM 模式——里，agent loop 本身跑在 guest 里，Claude 以普通 Linux 用户身份执行，完全不知道自己在沙箱里。对比 Claude Code：一个特权进程坐在沙箱外，逐命令决定是否强制执行；一段有说服力的注入 prompt 或一次疲劳的批准点击，就能让那个进程去跑未沙箱化的东西。而这里没有持着逃生钥匙的外层进程，也就没有有权批准例外的组件。

![Claude Cowork VM 的六个隔离机制](https://www-cdn.anthropic.com/images/4zrzovbb/website/ffc97a876bdeba2031ddaeef79a954e9b1b2d52a-1920x1080.png)

*图注：Claude Cowork VM 的六个主要隔离机制。两个在 guest 内核之外强制执行，agent 即使在 VM 内拿到 root 权限也能守住。另外四个是 guest 内强制执行的，刻意保持精简，因为外层承担了其余。*

但我们很快发现，把整个 agent 放在 full-VM 模式里带来了实际问题：VM 启动中的任何失败都会让 Cowork 无法使用。把 agent loop 移出 VM、代码执行留在 VM 内，让 Claude 在出错时仍能响应用户、协助排查，无需冻在报错上。这次改动对安全影响很小，因为 VM 依然对 agent 执行的代码强制实施文件系统与网络控制。

另外，我们也把本地 MCP 服务器移出了 VM。在 VM 里跑它们让审计更难，VM 更新时制造脆弱的依赖问题，也不支持需要与本地进程交互的 MCP——比如数据库，这类服务器反正只能跑在宿主上。这次改动让 Claude Cowork 与 Claude Desktop 中本地 MCP 服务器的工作方式一致：把它们当作用户可能选择安装的任意软件，交由管理员决定启用哪些本地 MCP（如果有）。远程 MCP 服务器不受影响，因为它们不跑在用户机器上。

![full-VM 模式与宿主模式的可靠性对比](https://www-cdn.anthropic.com/images/4zrzovbb/website/a81ed723d52f6fb2e7bc5ca51471496b1307101a-1920x1080.png)

*图注：agent loop 在 VM 内意味着 VM 的任何失败都让 Cowork 不可用。宿主模式更可靠：VM 崩溃时 agent 仍能响应，同时仍通过隔离代码执行提供重要安全保证。*

文件系统控制是另一个重要架构选择。Claude 需要能访问宿主上的部分文件才有用，但我们要压缩爆炸半径，并让用户对本地文件访问有可见性。我们发现提供不同的文件挂载模式有助于细粒度控制风险；Claude Cowork 提供只读、读写、读写但禁删三种。这里有个坑：符号链接解析必须发生在路径校验之前，否则已授权文件夹内的符号链接可以指向外部逃逸。对企业客户，我们允许管理员通过 MDM 设置里的挂载路径允许列表来控制。

#### 我们漏掉的风险：经由已批准域名的外泄

经由已批准域名外泄的清晰例子，来自一份第三方披露。Claude Cowork 的出站允许列表正确放行了发往 api.anthropic.com 的流量——不调用我们自己的 API，产品就无法工作。这起案例里，放进用户挂载工作区的恶意文件带着隐藏指令和攻击者控制的 API key。Claude 依指令读了工作区里的其他文件，用攻击者的 key 调用 Anthropic 的 Files API。出站代理检查目的地，看到 api.anthropic.com，放行。文件被上传到攻击者的 Anthropic 账户。沙箱完美工作，数据照样外泄了。

此前我们把允许列表理解为目的地过滤器——告诉 Claude 这些域名可以通信。更准确的理解是能力授予。允许列表上任何域名可达的每一个功能，现在都成了攻击面。允许 api.anthropic.com，就等于允许向任意 Anthropic 账户上传文件。

我们用 VM 内一个防御性的 man-in-the-middle 代理修复了它。这个代理拦截发往我们 API 的流量，只放行携带 VM 自身配置的会话令牌的请求；攻击者嵌进来的 key 会被代理拒绝。它还拦截会启用服务端 fetch 的请求头。代理坐在 VM 内，放在我们的服务器上不行，因为只有 VM 知道来源——从服务器视角看，Cowork 的请求与任何其他 API 客户端无法区分。

![允许列表外泄路径与 MITM 修复](https://www-cdn.anthropic.com/images/4zrzovbb/website/beb481a2e7b314f73ba37821a2c1f1ca470d7063-1920x1080.png)

*图注：上：发往 api.anthropic.com 的流量被放行，导致外泄。下：用 man-in-the-middle 代理拦截发往我们 API 的流量完成修复。*

这也是「自己写的软件往往最薄弱」原则的第二个实例。我们产品里的 hypervisor、seccomp、gVisor 一直可靠。失效的，是我们自建的允许列表代理。

#### 我们漏掉的风险：VM 隔离把端点检测软件也挡在外面

评估 Claude Cowork 时，企业安全团队问：「为什么我们的 EDR 看不进去？」答案是，把 Claude 关住的同一层隔离，也把基于宿主的端点检测与响应（EDR）挡在了外面。从 EDR 视角看，Claude Cowork 是一个不透明的 hypervisor 进程，它检查不了 guest。

隔离削减可见性，而对合规姿态依赖端点可见性的团队来说，不透明是麻烦。我们目前的缓解，是用基于拉取的 [OTLP](https://opentelemetry.io/docs/specs/otel/protocol/) 导出，让管理员事后取回事件日志，但这与实时监控不等价。如果你在做类似的东西，这类问题要提前规划。

三种模式对比如下：

| | 临时容器（claude.ai） | 人工介入的沙箱（Claude Code） | 封闭 VM（Claude Cowork） |
| --- | --- | --- | --- |
| 开销：隔离成本 | 容器启动 | 低延迟原生沙箱 | 完整 VM 引导 |
| 开销：用户依赖 | 无 | 必须读懂 bash | 无 |
| 风险：爆炸半径 | 服务端容器（由 gVisor 与宿主基础设施边界守护） | 本地工作区 | 挂载的工作区（由 vsock 与 hypervisor 边界守护） |

## 信任 agent 读到的内容

企业常问我们如何保护 MCP 连接的安全。问题问得对，但正确的问法比 MCP 更宽。提供给 agent 的任何外部资源，同时带来两种风险：传统供应链意义上的代码执行风险，和 prompt injection 载体。传统依赖审计（锁定版本、验证签名、评审源码）处理前者，漏掉后者。

**远程与本地之别，比看上去更重要。** 本地安装的工具可审计：你能读代码、锁版本，知道它不会在你脚下变卦。远程工具——托管的 MCP 服务器、云端连接器——在你批准之后的任何时刻都可能改变行为；你在安装时做的信任决定，可能已不再适用。我们的[连接器目录](https://claude.com/connectors)用持续评审处理这一点，目录之外的一切都按不可信对待。先拿假数据跑，在恶意工具的爆炸半径被控制住的环境里。

**工具输出是攻击面，即便工具本身可信。** 前面提到的 GitHub README 例子正是这种情况；对网页做的一切输入扫描，要同样严格地施加在带网络能力的工具结果上。这会增加延迟，也并非完美防御，但我们倾向实时检查：一旦投毒的工具返回已经把 agent 引向数据外泄，日志里只剩一次成功且已授权的 API 调用，事后没有信号可查。

在 Claude Code 和 Claude Cowork 里，工具调用经由代理路由。代理强制执行网络与文件策略，并能在返回值进入模型上下文之前检查它们。做检查的分类器可以是一个小而快的模型，不需要是做推理的那个。

## 展望

模型与产品在快速前进。风险随之变形演化，我们的缓解必须跟上。

**持久记忆投毒。** 跨会话存活的 agent 上下文占比持续增长——产品记忆、CLAUDE.md 文件、挂载的工作区、计划任务与长时运行 agent 的状态目录。进入其中任何一处的注入，在 agent 每次启动时都会重新加载。随着更多 agent 状态活过会话，经典后渗透意义上的新持久化机制开始威胁我们。会话启动时的良好分类器，需要变得更普遍。

**多 agent 信任升级。** 一方面，subagent 能隔离不可信内容，向主 agent 返回的是结构化事实，原始文本不出 subagent。另一方面，这可被滥用：如果 subagent 的输出因为「来自我们自己」而被当作比原始工具结果更高的信任，一条新的 prompt injection 通道就打开了。多 agent 系统里，分配不同信任等级与招致信任升级之间，存在权衡。

**agent 身份。** Claude Cowork 对 agent 身份的回答是具体的：凭据留在宿主 keychain，VM 拿到按会话收窄的令牌，该令牌可独立于用户凭据吊销。但我们开始面对更宽的问题：跨平台的 agent 身份。agent 应该拥有自己的主体身份，还是作为用户的延伸继承用户的权限？最终答案也许是两者的混合。

随着 agent 能力增长，攻击面持续移动。我们见过的失效类型，很可能在各行业和各实验室重演。agent 专属的安全姿态需要集体投入：共享 benchmark 与披露规范、通用身份标准、跨厂商红队。本文聚焦封锁，这只是 agent 安全图景的一部分。治理、可观测性与其余部分，见 [NIST 的 AI agent 身份与授权项目](https://www.nccoe.nist.gov/projects/software-and-ai-agent-identity-and-authorization)、由澳大利亚 ACSC 领衔、CISA 与英国 NCSC 参与的[六机构 agentic AI 采用指引](https://media.defense.gov/2026/Apr/30/2003922823/-1/-1/0/CAREFUL%20ADOPTION%20OF%20AGENTIC%20AI%20SERVICES_FINAL.PDF)、AI 管理标准 [ISO/IEC 42001](https://www.iso.org/standard/42001)。我们的 Glasswing 计划是一份贡献，我们期待与伙伴和竞争者一起处理这个关键议题。

## 结语

总而言之，有几条原则我们反复回到：

**先在环境层为封锁设计，再在模型层引导行为。** 给我们教训最深的两起事故——员工钓鱼与第三方允许列表披露——都是外泄类：数据经一条被允许的路径离开。两起里模型层都帮不上忙，没有异常可查。当一切概率性手段都漏掉时，被撞上的是确定性边界。

**隔离强度匹配用户的监督能力。** 读得懂 bash 的开发者与读不懂的知识工作者，跑的不是同一个威胁模型。用户能否评估 agent 即将做什么，这个问题应该参与决定封锁策略；往哪个方向答错——给专家太多摩擦，或给非专家太多信任——本身就是一种失败。

**警惕自建组件。** 身经百战的 hypervisor、syscall 过滤器、容器运行时，经受过的对抗性审视远多于你将写出的任何东西。本文描述的每一次部署里，标准原语都守住了，我们围绕它们做的东西暴露了缺陷。

归根结底，agent 也许是一类新软件，但它们的系统级交互并不新。它们照样读文件、开 socket、起进程；这让用成熟工具做封锁成为关键且可行的防御。部署的风险收益天平会随 AI 的发展持续移动，但给爆炸半径设一条硬上限，往往能把这个天平推向正确的方向。

## 脚注

1. Claude Code auto mode 把命令批准交给基于模型的分类器；它以漏掉一部分危险命令为代价（约 17% 的过激动作漏过），换取最低摩擦（约 0.4% 的良性命令被拦），所以它是沙箱内纵深防御的一层，替代不了沙箱。

## 作者与致谢

作者：Max McGuinness、Mikaela Grace、Jiri De Jonghe、Jake Eaton、Abel Ribbink。

同时感谢 Hanah Ho、Hasnain Lakhani、Pedram Navid、Molly Villagra、Maya Nielan、Akila Srinivasan、Travis Szucs、Sam Attard、Alfred Xing、Mohamad El Hajj、Gabby Curtis、David Dworken、Adam Jones、Amie Rotherham、Christian Ryan、Lucas Smedley、Brett Andrews 及其他贡献者。

特别致谢我们的安全与产品工程团队，以及向 Claude 产品报告漏洞的个人与组织。
