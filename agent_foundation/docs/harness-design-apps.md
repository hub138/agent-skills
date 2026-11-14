# 长时运行应用开发的 harness 设计（Harness design for long-running application development）

- 原文：[Harness design for long-running application development](https://www.anthropic.com/research/harness-design-long-running-apps)
- 来源：Anthropic Labs，作者 Prithvi Rajasekaran
- 发布：2026-03-24
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图，地址为原文 CDN 直链；两条 prompt、QA 反馈与发布博客引文保留英文原文，附录计划作为英文代码块原样保留。

本文由我们 [Labs](https://www.anthropic.com/news/introducing-anthropic-labs) 团队的 Prithvi Rajasekaran 撰写。

过去几个月我在做两个相互关联的问题：让 Claude 产出高质量的前端设计，以及让它在无人介入的情况下构建完整应用。这项工作源于我们在 [前端设计 skill](https://github.com/anthropics/claude-code/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md) 与[长时运行编码 agent harness](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) 上的早期努力，我与同事通过 prompt engineering 与 harness 设计把 Claude 的表现拉到远高于基线，但两者最终都撞上了天花板。

要突破，我寻找能横跨两个截然不同领域的新 AI 工程方法：一个领域由主观品味定义，另一个由可验证的正确性与可用性定义。从[生成对抗网络](https://en.wikipedia.org/wiki/Generative_adversarial_network)（GAN）汲取灵感，我设计了一个带 generator（生成器）与 evaluator（评估器）agent 的多 agent 结构。要构建一个可靠且有品味地为产出打分的 evaluator，先得发展一套标准，把「这个设计好不好」这类主观判断变成具体的、可打分的条目。

随后我把这些技术应用到长时运行自主编码上，并从早前的 harness 工作里带过来两条经验：把构建工作分解成可处理的块，以及用结构化 artifact 在会话之间交接上下文。最终成果是一个三 agent 架构（planner、generator、evaluator），在数小时的自主编码会话里产出功能丰富、前后端完整的应用。

## 朴素实现为什么不够好

我们此前展示过，harness 设计对长时运行 agentic 编码的效果有实质影响。在更早的[实验](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)里，我们用一个 initializer agent 把产品 spec 分解成任务清单，一个编码 agent 每次实现一个功能，然后交接 artifact 让上下文跨会话延续。更广的开发者社区也收敛到了类似认识，比如 "[Ralph Wiggum](https://ghuntley.com/ralph/)" 方法用 hooks 或脚本让 agent 保持连续迭代循环。

但有些问题一直顽固存在。任务更复杂时，agent 随时间推移仍然容易脱轨。分解这个问题时，我们观察到这类任务上的 agent 有两种常见失败形态。

第一种：上下文窗口逐渐填满时，模型在冗长任务上会失去连贯性（见我们的[上下文工程](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)文章）。有些模型还表现出 "context anxiety"（上下文焦虑）：接近它自认为的上下文上限时，就开始提前收尾工作。context reset（上下文重置）——彻底清空上下文窗口、启动一个全新 agent，配合携带上一个 agent 状态与后续步骤的结构化交接——同时解决这两个问题。

这与 compaction 不同：compaction 是把对话的早期部分就地总结，让同一个 agent 带着缩短的历史继续。compaction 保住了连续性，但没给 agent 一个干净的开局，context anxiety 仍可能持续。reset 提供干净的开局，代价是交接 artifact 必须携带足够状态，让下一个 agent 能干净接手。在早前测试中，我们发现 Claude Sonnet 4.5 的 context anxiety 强到单靠 compaction 不足以支撑长任务的强劲表现，所以 context reset 成为 harness 设计的必需件。它解决了核心问题，但给每次 harness 运行增加了编排复杂度、token 开销与延迟。

第二个问题此前没有正面处理过：自我评估。被要求评估自己的产出时，agent 倾向于自信地夸奖这份工作，哪怕在人类观察者眼里质量明显平庸。设计这类主观任务上问题尤其突出：没有类似可验证软件测试的二元检查。一个布局感觉精致还是平庸是主观判断，而 agent 给自己的工作打分时稳定往高了打。

不过，即便在有可验证结果的任务上，agent 有时也会表现出糟糕的判断力，拖累任务完成。把做工作的 agent 与评判它的 agent 分开，被证明是解决这个问题的有力杠杆。分离本身不会立刻消除那种宽容——evaluator 依然是一个 LLM，天然倾向对 LLM 生成的产出手下留情。但把一个独立的 evaluator 调教得挑剔，远比让 generator 对自己的工作苛刻更可行，而一旦外部反馈存在，generator 就有了具体的迭代靶子。

## 前端设计：让主观质量可打分

我先在前端设计上做实验，自我评估问题在那里最显眼。不加干预时，Claude 通常滑向安全、可预期的布局：技术上能用，视觉上平平。

两点认识塑造了我为前端设计构建的 harness。第一，美学没法完全化成一个分数，个人口味永远有差异，但把设计原则与个人口味编码进打分标准，可以带来改善。「这个设计美吗」很难一致地回答，「它是否遵循我们的好设计原则」给了 Claude 一个具体的打分依据。第二，把前端生成与前端评判分开，我们就有了一个反馈循环，推动 generator 产出更强的作品。

据此我写了四条打分标准，同时写进 generator 与 evaluator 两个 agent 的提示词：

- Design quality（设计质量）：设计感觉是一个连贯的整体，还是一堆部件的拼合？这条做得好，意味着颜色、排版、布局、图像与其他细节组合出独特的情绪与身份感。
- Originality（原创性）：有没有自定义决策的痕迹，还是全靠模板布局、库默认值与 AI 生成的套路？人类设计师应当能认出刻意的创意选择。未经修改的现成组件，或者白卡片上铺紫色渐变这类 AI 生成的标志性痕迹，在这条上不及格。
- Craft（工艺）：技术执行：排版层级、间距一致性、色彩和谐、对比度。这是能力检查，与创造力无关。多数合理实现在这条上默认表现不错；不及格意味着基本功坏了。
- Functionality（功能性）：独立于美学的可用性。用户能不看说明就明白界面做什么、找到主要操作、完成任务吗？

我把 design quality 与 originality 的权重放在 craft 与 functionality 之上。Claude 在 craft 与 functionality 上默认已得分不错，所需的技术能力对模型来说近乎天然。但在设计与原创性上，Claude 的产出常常至多算平淡。这些标准明确惩罚高度同质化的 "AI slop" 模式，通过加重设计与原创性的权重，推动模型在审美上敢于冒险。

我用带详细分数分解的 few-shot 示例校准 evaluator。这保证 evaluator 的判断与我的口味一致，也减少跨迭代的分数漂移。

我在 [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) 上构建这个循环，编排保持简单。generator agent 先根据用户提示词创建 HTML/CSS/JS 前端。我给 evaluator 配了 Playwright MCP，让它先与线上页面直接交互，再为每条标准打分并写详细评语。实践中，evaluator 会自己导航页面、截图并仔细研究实现，然后才给出评估。反馈回流到 generator，作为下一轮迭代的输入。每次生成我跑 5 到 15 轮迭代，每轮通常都把 generator 推向更有辨识度的方向，响应 evaluator 的评语。因为 evaluator 是在主动导航页面、给静态截图打分，每一轮都要消耗真实的时钟时间，完整跑一次最长到四小时。我还指示 generator 在每次评估后做战略决定：分数走势好就精炼当前方向，路子走不通就转向一个完全不同的美学。

跨多次运行看，evaluator 的评估随迭代改善，随后进入平台期，仍有提升空间。有的生成渐进精炼，有的在迭代之间发生剧烈的美学转向。

标准的措辞以我没完全预料到的方式引导了 generator。写入「最好的设计是博物馆级别」这类语句后，设计向一种特定的视觉收敛靠拢，说明与标准相伴的提示词直接塑造了产出的性格。

分数总体随迭代上升，但形态不总是干净线性。后面的实现整体更好，但我经常遇到更喜欢中间某轮而非最后一轮的情况。实现复杂度也随轮次增加，generator 响应 evaluator 的反馈时会伸手去够更有野心的方案。即便第一轮迭代，产出也明显好于完全无提示词的基线，说明标准及其语言本身在 evaluator 反馈带来进一步精炼之前，就已引导模型离开了平庸的默认值。

一个值得一提的例子：我让模型为一个荷兰美术馆做网站。到第九轮迭代，它产出了一个虚构美术馆的干净、深色主题首页，页面视觉精致但大体在我的预期之内。第十轮，它彻底推翻原方案，把网站重新构想成一种空间体验：CSS 透视渲染的棋盘格地板 3D 房间，画作以自由位置挂在墙上，展厅之间靠门洞导航，代替滚动或点击。这种创造跳跃，我此前从未在单次生成里见过。

## 扩展到前后端完整的编码

带着这些发现，我把这个受 GAN 启发的模式应用到前后端完整的开发。generator-evaluator 循环天然映射到软件开发生命周期：code review 与 QA 承担着与设计 evaluator 相同的结构角色。

### 架构

在更早的[长时运行 harness](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)里，我们用一个 initializer agent、一个每次只做一个功能的编码 agent、会话间的 context reset，解决了连贯的多会话编码。context reset 是关键的解锁点：那套 harness 用的是 Sonnet 4.5，有前面提到的 "context anxiety" 倾向，构建一套在 context reset 之间依然运转良好的 harness 是让模型保持专注的关键。Opus 4.5 自己就基本消除了那个行为，所以我在这个 harness 里彻底去掉了 context reset。各 agent 作为一次连续会话跑完整个构建，[Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) 的自动 compaction 一路处理上下文增长。

这项工作里，我在原 harness 的基础上构建了一个三 agent 系统，每个 agent 对应我在此前运行中观察到的一个具体缺口。系统包含以下 agent 角色：

**Planner：** 之前的长时运行 harness 要求用户预先提供详细 spec。我想自动化这一步，于是创建了 planner agent：接收 1 到 4 句的简单提示词，扩展成完整产品 spec。我提示它在范围上敢于进取，聚焦产品语境与高层技术设计，而非具体的技术实现。这个侧重出于一个担忧：planner 若预先指定细粒度的技术细节且出了错，spec 里的错误会级联传导进下游实现。更聪明的做法似乎是在交付物上约束 agent，路径让它们边做边摸索。我还让 planner 寻找机会把 AI 功能编织进产品 spec。（例子见文末附录。）

**Generator：** 早前 harness 的每次一个功能做法在范围管理上效果很好。我在这里沿用类似模型，指示 generator 按 sprint 工作，每次从 spec 里取一个功能。每个 sprint 用 React、Vite、FastAPI、SQLite（后来换成 PostgreSQL）这一组技术实现应用，generator 被指示在每个 sprint 结束时先自我评估，再交给 QA。它还有 git 做版本控制。

**Evaluator：** 早前 harness 的应用常常看着惊艳，实际一用却有真 bug。为抓住这些，evaluator 用 Playwright MCP 像用户一样点击穿行运行中的应用，测试 UI 功能、API 端点与数据库状态。然后它对照发现的 bug 与一套模仿前端实验的标准为每个 sprint 打分，这里的标准调整为覆盖产品深度、功能性、视觉设计与代码质量。每条标准有硬性门槛，任何一条低于门槛，sprint 判为失败，generator 收到哪里出了问题的详细反馈。

每个 sprint 开始前，generator 与 evaluator 协商一份 sprint contract：在写任何代码之前，就这块工作的「完成」长什么样达成一致。这一步存在的原因是产品 spec 刻意保持高层，我想要一个桥接用户故事与可测试实现的步骤。generator 提出它要构建什么、成功如何验证，evaluator 审这份提案，确认 generator 在构建正确的东西。双方迭代到达成一致。

通信靠文件完成：一个 agent 写文件，另一个读后在同一文件里回应，或写一个新文件让上一个 agent 再读。generator 随后按谈定的 contract 构建，再把工作交给 QA。这让工作忠于 spec，又不至于过早过度指定实现。

### 运行 harness

这个 harness 的第一版用 Claude Opus 4.5，把用户提示词同时跑在完整 harness 与单 agent 系统上做对比。选 Opus 4.5 是因为开始这些实验时它是我们最强的编码模型。

我写了下面这条提示词生成复古电子游戏制作器：

> Create a 2D retro game maker with features including a level editor, sprite editor, entity behaviors, and a playable test mode.

下表展示 harness 类型、运行时长与总成本。

| Harness | Duration | Cost |
| --- | --- | --- |
| Solo | 20 min | $9 |
| Full harness | 6 hr | $200 |

harness 贵了 20 倍以上，但产出质量的差距一眼可见。

我期待的是一个能构建关卡及其部件（sprite、entity、tile 布局）然后点 play 真正玩关卡的界面。我先打开 solo 运行的产出，初始应用看起来符合预期。

但一路点下去，问题开始浮现。布局浪费空间，固定高度的面板让大半个视口空着。工作流僵硬。想填充关卡时被提示先创建 sprite 与 entity，界面上却没有任何东西引导我按这个顺序走。更要紧的是，游戏本身是坏的：我的 entity 出现在屏幕上，但对任何输入都没有反应。翻代码发现 entity 定义与游戏运行时之间的接线断了，表面上看不出断在哪。

![solo 版应用初始界面](https://www-cdn.anthropic.com/images/4zrzovbb/website/23c98f1d7ae720bfb39190d50e0706c03b177ad8-1999x1320.png)

![solo 版 sprite 编辑器](https://www-cdn.anthropic.com/images/4zrzovbb/website/24472c85629a6c82a092f25def4a659042be1f7c-1999x1010.png)

![solo 版关卡无法游玩](https://www-cdn.anthropic.com/images/4zrzovbb/website/79217dbfce3f31172eb7fd4deee5449023c9b2ac-1999x757.png)

评估完 solo 运行，我转向 harness 运行。这次同样从那一句提示词出发，但 planner 步骤把它扩展成横跨十个 sprint 的 16 项功能 spec，远超 solo 运行尝试的范围。核心编辑器与游玩模式之外，spec 还要求 sprite 动画系统、行为模板、音效与音乐、AI 辅助的 sprite 生成器与关卡设计器，以及带分享链接的游戏导出。我给 planner 配了我们 [frontend design skill](https://github.com/anthropics/claude-code/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md) 的访问权，它读取后为应用创建了一套视觉设计语言，作为 spec 的一部分。每个 sprint，generator 与 evaluator 协商一份 contract，定义该 sprint 的具体实现细节与用于验证完成情况的可测试行为。

应用立刻显出比 solo 运行更多的打磨与顺滑。画布占满整个视口，面板尺寸合理，界面有一致的视觉身份，与 spec 里的设计方向保持一致。solo 运行里的某些笨重感确实还在——工作流仍然没讲清该先建 sprite 与 entity 再填关卡，我只能自己摸索。这更像是基础模型产品直觉上的缺口，而非 harness 设计要解决的问题，不过它也提示了 harness 内部针对性迭代可以进一步提升产出质量的方向。

逐个用过编辑器，新版本对 solo 的优势更明显。sprite 编辑器更丰富、功能更全：更干净的工具面板、更好的取色器、更好用的缩放控制。

因为我让 planner 把 AI 功能编进 spec，应用还内置了 Claude 集成，让我能通过提示词生成游戏的不同部分，工作流明显提速。

![完整 harness 版应用初始界面](https://www-cdn.anthropic.com/images/4zrzovbb/website/a8bef95425966495629095a5cb38bde4a8b13558-1999x997.png)

![完整 harness 版 sprite 编辑器更顺手](https://www-cdn.anthropic.com/images/4zrzovbb/website/c05aa3ef8daaf0ef3d0dba66d6480ab753e9cbaa-1999x1007.png)

![用内置 AI 功能生成关卡](https://www-cdn.anthropic.com/images/4zrzovbb/website/287b35f4683ecb77ac6a8d66bf2b3ed5956d1db9-1999x1008.png)

![用内置 AI 功能生成关卡](https://www-cdn.anthropic.com/images/4zrzovbb/website/8596eab2b4a06124df41ad6b2f7ff4ff9d9f105f-1999x1000.png)

![游玩生成的游戏](https://www-cdn.anthropic.com/images/4zrzovbb/website/f2953550e51957a0a49a3792a0df3bcfed0fde48-1994x1654.png)

差别最大的是游玩模式。我真的能移动自己的 entity、玩这个游戏了。物理还有些毛糙——角色跳上平台后与平台重叠，直觉上不对——但核心的东西能跑，solo 版没做到。四处移动了一阵，我还是撞上了 AI 关卡构建的局限：有一堵大墙我跳不过去，卡住了。这说明还有一些常识性改进与边界情况，harness 可以处理来进一步打磨应用。

读日志可以清楚看到 evaluator 让实现守住了 spec。每个 sprint，它逐条过 sprint contract 的测试标准，用 Playwright 操纵运行中的应用，为任何背离预期行为的东西提 bug。contract 颗粒度很细——仅 Sprint 3 就有 27 条覆盖关卡编辑器的标准——evaluator 的发现具体到无需额外排查即可行动。下表是 evaluator 识别出的几个问题例子：

| Contract criterion | Evaluator finding |
| --- | --- |
| Rectangle fill tool allows click-drag to fill a rectangular area with selected tile | **FAIL** — Tool only places tiles at drag start/end points instead of filling the region. `fillRectangle` function exists but isn't triggered properly on mouseUp. |
| User can select and delete placed entity spawn points | **FAIL** — Delete key handler at `LevelEditor.tsx:892` requires both `selection` and `selectedEntityId` to be set, but clicking an entity only sets `selectedEntityId`. Condition should be `selection \|\| (selectedEntityId && activeLayer === 'entity')`. |
| User can reorder animation frames via API | **FAIL** — `PUT /frames/reorder` route defined after `/{frame_id}` routes. FastAPI matches 'reorder' as a frame_id integer and returns 422: "unable to parse string as an integer." |

让 evaluator 达到这个水平花了功夫。开箱即用时，Claude 是个糟糕的 QA agent。早期运行里，我看着它认出合理的问题，然后自己说服自己这些不算大事，照样批准通过。它还倾向浅层测试，不去探边界情况，更隐蔽的 bug 常常漏网。调优循环是：读 evaluator 的日志，找它的判断与我的判断出现分歧的例子，更新 QA 提示词来解决那些问题。好几轮这样的开发循环之后，evaluator 的打分我才觉得合理。即便如此，harness 产出仍显出模型 QA 能力的上限：小的布局问题、某些地方感觉不直观的交互、evaluator 没彻底测到的深层嵌套功能里未被发现的 bug。显然还有更多验证空间可以靠进一步调优拿到。但对比 solo 运行里应用核心功能干脆不能用的情形，提升是明显的。

### 迭代 harness

第一轮 harness 结果令人鼓舞，但它笨重、缓慢、昂贵。合理的下一步是找办法简化 harness 而不伤性能。这既是常识，也是一个更普遍原则的体现：harness 里的每个组件都编码了一条「模型自己做不到什么」的假设，这些假设值得压力测试——既因为它们可能本来就错，也因为模型进步后它们很快过时。我们 [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) 一文把这个底层思想表述为「找尽可能简单的方案，需要时才增加复杂度」，任何维护 agent harness 的人都会反复遇到这个模式。

第一次简化尝试里，我把 harness 大幅裁减并试了几个有创意的新点子，但没能复刻原版的性能，也变得难以判断 harness 设计里哪些部件真正承重、以何种方式承重。基于这段经历，我改用更讲方法的做法：一次移除一个组件，观察它对最终结果的影响。

在这些迭代周期里，我们发布了 Opus 4.6，进一步推动我削减 harness 复杂度。有充分理由预期 4.6 需要的脚手架比 4.5 少。我们的[发布博客](https://www.anthropic.com/news/claude-opus-4-6)这样描述（原文如下）：

> "[Opus 4.6] plans more carefully, sustains agentic tasks for longer, can operate more reliably in larger codebases, and has better code review and debugging skills to catch its own mistakes."

它在长上下文检索上也有实质提升。这些恰恰是 harness 原本要补足的能力。

### 移除 sprint 结构

我第一步把 sprint 结构整个移除。sprint 结构曾帮助模型把工作分解成块、连贯工作。鉴于 Opus 4.6 的进步，有充分理由相信模型无需这种分解也能原生胜任。

planner 与 evaluator 都保留，各自仍带来明显价值。没有 planner，generator 会把范围做小：拿到原始提示词就直接开建，不做 spec，最终应用的功能丰富度比 planner 参与时低。

sprint 结构移除后，我把 evaluator 改成运行结束时单次评估，不再逐 sprint 打分。模型能力强了，evaluator 对某些运行的承重程度随之改变，它有没有用取决于任务处在模型可靠独立完成范围的哪个位置。在 4.5 上，那条边界很近：我们的构建处在 generator 独立做好的边缘，evaluator 在整个构建中抓到了有意义的问题。在 4.6 上，模型原始能力增强，边界外推。过去需要 evaluator 检查才能实现连贯的任务，现在多数在 generator 独立就能做好的范围之内，边界之内的任务里 evaluator 成了多余开销。但构建中仍处在 generator 能力边缘的部分，evaluator 继续带来真实提升。

实际含义是：evaluator 的取舍没有一个固定答案。任务越出当前模型可靠独立完成的范围时，它的成本才花得值。

结构简化之外，我还加了提示词来改进 harness 往每个应用里构建 AI 功能的方式，具体是让 generator 构建一个真正像样的 agent，用工具驱动应用自身的功能。这花了真功夫迭代，因为相关知识足够新，Claude 的训练数据覆盖得很薄。但调优到位后，generator 能正确构建 agent 了。

### 更新后 harness 的结果

为测试更新后的 harness，我用下面这条提示词生成 DAW（Digital Audio Workstation，数字音频工作站），一个用于作曲、录音与混音的音乐制作程序：

> Build a fully featured DAW in the browser using the Web Audio API.

这次运行依然漫长昂贵：约 4 小时，token 成本 124 美元。

时间大头在 builder 上：它连续连贯跑了两个多小时，无需 Opus 4.5 时代必需的 sprint 分解。

| Agent & Phase | Duration | Cost |
| --- | --- | --- |
| Planner | 4.7 min | $0.46 |
| Build (Round 1) | 2 hr 7 min | $71.08 |
| QA (Round 1) | 8.8 min | $3.24 |
| Build (Round 2) | 1 hr 2 min | $36.89 |
| QA (Round 2) | 6.8 min | $3.09 |
| Build (Round 3) | 10.9 min | $5.88 |
| QA (Round 3) | 9.6 min | $4.06 |
| Total V2 Harness | 3 hr 50 min | $124.70 |

与上一个 harness 一样，planner 把一句提示词扩展成完整 spec。日志里能看到 generator 把应用与 agent 设计规划得不错，接好线、测过之后交给 QA。

话虽如此，QA agent 仍抓到了真实缺口。第一轮反馈里它指出（原文如下）：

> This is a strong app with excellent design fidelity, solid AI agent, and good backend. The main failure point is Feature Completeness — while the app looks impressive and the AI integration works well, several core DAW features are display-only without interactive depth: clips can't be dragged/moved on the timeline, there are no instrument UI panels (synth knobs, drum pads), and no visual effect editors (EQ curves, compressor meters). These aren't edge cases — they're the core interactions that make a DAW usable, and the spec explicitly calls for them.

第二轮反馈里，它又抓到几处功能缺口（原文如下）：

> Remaining gaps:
> - Audio recording is still stub-only (button toggles but no mic capture)
> - Clip resize by edge drag and clip split not implemented
> - Effect visualizations are numeric sliders, not graphical (no EQ curve)

generator 独立做事时仍可能漏细节或用占位实现顶替功能，QA 在抓这类最后一公里问题上继续创造价值，交给 generator 修复。

按提示词的意图，我期待一个能创作旋律、和声与鼓点、编排成曲、全程有集成 agent 帮忙的程序。视频展示了结果。

这个应用离专业音乐制作软件还很远，agent 的作曲水平显然还有大量功课要做。另外，Claude 实际上听不见声音，这让 QA 反馈循环在音乐品味上效果打折。

但最终应用具备一个能用的音乐制作程序的全部核心件：浏览器里运行的 arrangement 视图、mixer 与 transport。不止如此，我完全靠提示词拼出了一段短曲：agent 定好速度与调性，铺了一段旋律，搭了鼓轨，调了 mixer 电平，加了混响。歌曲创作的核心原语都在，agent 能自主驱动它们，用工具端到端做出一个简单作品。你可以说它离完美音准还差得远，但它正在路上。

## 接下来

模型继续进步，大致可以预期它们能工作更久、做更复杂的任务。某些情况下，这意味着模型周围的脚手架随时间越来越不重要，开发者可以等下一个模型，看某些问题自行解决。另一方面，模型越强，就有越大的空间去开发能做到基线能力之上复杂任务的 harness。

带着这个认识，这项工作里有几条经验值得带走。拿你构建所依赖的模型做实验、在真实问题上读它的 trace、调优它的表现以达到你想要的结果，这永远是好实践。做更复杂的任务时，把任务分解并给每个侧面配上专门化 agent，有时确有空间。新模型发布时，复查一遍 harness 通常也是好实践：撤掉对性能不再承重的部件，加上新部件去取得以前不可能的更强能力。

这项工作给我的信念是：有意思的 harness 组合空间不会随模型进步而缩小，它只会移动，AI 工程师有意思的工作就是不断找到下一个新组合。

## 附录

planner agent 生成的计划示例：

```
RetroForge - 2D Retro Game Maker

Overview
RetroForge is a web-based creative studio for designing and building 2D retro-style video games. It combines the nostalgic charm of classic 8-bit and 16-bit game aesthetics with modern, intuitive editing tools—enabling anyone from hobbyist creators to indie developers to bring their game ideas to life without writing traditional code.

The platform provides four integrated creative modules: a tile-based Level Editor for designing game worlds, a pixel-art Sprite Editor for crafting visual assets, a visual Entity Behavior system for defining game logic, and an instant Playable Test Mode for real-time gameplay testing. By weaving AI assistance throughout (powered by Claude), RetroForge accelerates the creative process—helping users generate sprites, design levels, and configure behaviors through natural language interaction.

RetroForge targets creators who love retro gaming aesthetics but want modern conveniences. Whether recreating the platformers, RPGs, or action games of their childhood, or inventing entirely new experiences within retro constraints, users can prototype rapidly, iterate visually, and share their creations with others.

Features
1. Project Dashboard & Management
The Project Dashboard is the home base for all creative work in RetroForge. Users need a clear, organized way to manage their game projects—creating new ones, returning to works-in-progress, and understanding what each project contains at a glance.

User Stories: As a user, I want to:

- Create a new game project with a name and description, so that I can begin designing my game
- See all my existing projects displayed as visual cards showing the project name, last modified date, and a thumbnail preview, so that I can quickly find and continue my work
- Open any project to enter the full game editor workspace, so that I can work on my game
- Delete projects I no longer need, with a confirmation dialog to prevent accidents, so that I can keep my workspace organized
- Duplicate an existing project as a starting point for a new game, so that I can reuse my previous work

Project Data Model: Each project contains:

Project metadata (name, description, created/modified timestamps)
Canvas settings (resolution: e.g., 256x224, 320x240, or 160x144)
Tile size configuration (8x8, 16x16, or 32x32 pixels)
Color palette selection
All associated sprites, tilesets, levels, and entity definitions

...
```

## 作者与致谢

特别感谢 Mike Krieger、Michael Agaby、Justin Young、Jeremy Hadfield、David Hershey、Julius Tarng、Xiaoyi Zhang、Barry Zhang、Orowa Sidker、Michael Tingley、Ibrahim Madha、Martina Long 与 Canyon Robbins 对这项工作的贡献。

同样感谢 Jake Eaton、Alyssa Leonard 与 Stef Sequeira 帮助打磨本文。
