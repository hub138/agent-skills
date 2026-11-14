# Google 智能体白皮书：智能体入门（Introduction to Agents）

- 原文：[Introduction to Agents](https://www.kaggle.com/whitepaper-introduction-to-agents)
- 来源：Google 五日 AI Agent 强化课程白皮书之一（kaggle.com），作者 Alan Blount、Antonio Gulli、Shubham Saboo、Michael Zimmermann、Vladimir Vuskovic
- 发布：2025-11
- 译文说明：全文翻译，术语保留英文原词；图表以文字说明代替；Gemini、ADK、Vertex AI 等 Google 产品名保留原名，作为机制示例对待。

## 引言：从预测式 AI 到自主 agent

我们正在经历一次范式转变：AI 从单纯预测或生成内容，走向一类能够自主解决问题、执行任务的新型软件。这条新边界围绕 AI agent 展开。agent 并非静态工作流里的一个 AI model；它是一个完整的应用，会制定计划、采取行动来达成目标。它把 Language Model（LM）的推理能力与实际行动能力结合起来，处理单个 model 无法胜任的复杂多步任务。关键能力在于 agent 能独立工作：自己想清楚通往目标的下一步，无需每一步都有人指挥。

agent 是 Language Model 的自然演化，是让 LM 在软件里真正能干活的形态。

本白皮书是五部曲的第一本，面向从概念验证走向生产级 agentic 系统的开发者、架构师与产品负责人。做原型不难，难的是安全性、质量与可靠性。本书提供四块基础：

- 核心解剖：把 agent 分解为三个本质组件——负责推理的 Model、负责行动的 Tools、负责治理的 Orchestration Layer。
- 能力分级：从简单的互联问题解决者，到复杂的协作式多 agent 系统，给出完整谱系。
- 架构设计：每个组件的实操设计考量，从 model 选型到 tool 实现。
- 面向生产：建立 Agent Ops 纪律，用来评估、调试、加固单个 agent，并扩展到企业级治理下的 agent 舰队。

语言难以精确描述人与 AI 的交互。我们倾向拟人化，用「想」「推理」「知道」这类人类词汇。我们还没有词汇区分「带着语义地知道」与「以高概率最大化某个 reward function 地知道」。这是两种不同的「知道」，但 99.X% 的时间里结果一样。

## 什么是 AI agent：四组件架构

最简单的定义：AI agent 是 models、tools、orchestration layer 与 runtime services 的组合，让 LM 在循环里运转来完成目标。四个要素构成任何自主系统的基本架构。

- **Model（大脑）**：核心 LM 或基础模型，是 agent 的中央推理引擎，处理信息、评估选项、做出决策。model 的类型（通用、微调、多模态）决定 agent 的认知能力。agentic 系统是 LM 输入 context window 的终极策展人。
- **Tools（双手）**：把 agent 的推理连接到外部世界，让能力超出文本生成。包括 API 扩展、代码函数、数据存储（数据库或向量库），用于获取实时、事实性信息。agentic 系统让 LM 规划用哪些 tools，执行 tool，再把 tool 结果放进下一次 LM 调用的输入 context window。
- **Orchestration Layer（神经系统）**：治理进程，管理 agent 的运转循环，处理规划、记忆（state）与推理策略执行。这层用 prompting 框架与推理技术（如 Chain-of-Thought、ReAct）把复杂目标分解为步骤，决定何时思考、何时用 tool。agent 的「记忆」也由这层负责。
- **Deployment（身体与双腿）**：在笔记本上建 agent 适合原型，生产部署才能让它成为可靠、可访问的服务。把 agent 托管到安全可扩展的服务器，接入监控、日志、管理等生产服务。部署后，用户经图形界面访问它，其他 agent 经 Agent-to-Agent（A2A）API 以编程方式访问它。

归根结底，构建生成式 AI agent 是一种新的解题方式。传统开发者像砌砖工人，精确定义每一步逻辑。agent 开发者更像导演：不必为每个动作写显式代码，而是布置场景（指导性 instructions 与 prompts）、挑选演员（tools 与 APIs）、提供必要 context（数据）。主要任务变成引导这位自主「演员」交出预期的表现。

你会很快发现，LM 最大的优势——惊人的灵活——同时也是最大的麻烦。大模型什么都能做，反而很难让它可靠、完美地做好一件特定的事。过去叫「prompt engineering」现在叫「context engineering」的做法，就是引导 LM 产出想要的输出。对 LM 的每次调用，我们输入 instructions、事实、可调用的 tools、示例、session 历史、用户画像等——用刚好正确的信息填满 context window，拿到需要的输出。agent 就是管理 LM 输入来完成工作的软件。

出问题时调试必不可少。Agent Ops 本质上是给熟悉的度量、分析、系统优化循环重新定义。透过 traces 与 logs，你能监视 agent 的「思考过程」，识别它与预期执行路径的出入。随着 model 演进、框架改进，开发者的职责是提供关键组件：领域专长、明确人格、与实用工具的无缝集成。要记住：全面的评估与考察，其影响力常常超过最初的 prompt。

当 agent 配置得当时——清晰的 instructions、可靠的 tools、作为记忆的集成 context、优秀的用户界面、规划与解决问题的能力、常识性的世界知识——它就超越了「工作流自动化」的范畴，开始成为一个协作者：高效、适应力强、能力出众的新队友。

本质上，agent 是一门致力于 context window 策展的学问。它是一个不停歇的循环：组装 context、调用 model、观察结果、为下一步重新组装 context。context 可以包括 system instructions、用户输入、session 历史、长期记忆、来自权威来源的 grounding 知识、可用的 tools、已调用 tools 的结果。对 model 注意力的精细管理，让它的推理能力能够应对全新情境并达成目标。

## agent 解决问题的过程：五步循环

定义说完，agent 从收到请求到交付结果，究竟做了什么？agent 在一个持续循环里运转，可分解为五个基本步骤：

1. **接受使命（Get the Mission）**：由具体的高层目标启动。使命来自用户（「帮我安排团队参加下月会议的差旅」）或自动触发（「一条新的高优先级客户工单到了」）。
2. **扫描现场（Scan the Scene）**：agent 感知环境收集 context。orchestration layer 访问可用资源：用户的请求说了什么？短期记忆里有什么信息？之前做过这个任务吗？上周用户给过什么指示？我的 tools——日历、数据库、API——能访问到什么？
3. **想清楚（Think It Through）**：这是 agent 的核心思考循环，由推理 model 驱动。agent 把使命（第 1 步）对照现场（第 2 步）制定计划。这往往是一条推理链：「要订差旅，先要知道团队有谁。我用 get_team_roster 工具。然后要经 calendar_api 查每个人的空闲时间。」
4. **采取行动（Take Action）**：orchestration layer 执行计划的第一步。选择并调用合适的 tool——调 API、跑代码函数、查数据库。这是 agent 在自身推理之外作用于世界。
5. **观察与迭代（Observe and Iterate）**：agent 观察行动结果。get_team_roster 返回五个名字。新信息加入 agent 的 context 或「记忆」。循环重复，回到第 3 步：「有了名单，下一步是查这五个人的日历。我用 calendar_api。」

这个「思考、行动、观察」循环持续进行——由 Orchestration Layer 管理、Model 推理、Tools 执行——直到 agent 的内部计划完成、最初使命达成。

**实例：客服 agent 走一遍五步循环。**用户问：「我的订单 #12345 到哪了？」

agent 先进入「想清楚」阶段制定完整策略，它推理：「用户要的是物流状态。要给出完整回答，需要多步计划：第一，识别——先在内部数据库找到订单，确认存在并拿到详情。第二，追踪——从详情里提取承运商的 tracking number，再查外部承运商 API 的实时状态。第三，汇报——把收集到的信息组织成清晰有用的回复。」

带着计划进入执行。第一个「行动」阶段执行计划第一步：调用 find_order("12345")。观察结果：完整订单记录，含 tracking number「ZYX987」。orchestration layer 认出计划第一部分完成，立即推进第二步：调用 get_shipping_status("ZYX987")。观察新结果：「派送中」。最后进入「汇报」步骤：感知到全部要素齐备，规划最终消息并行动——生成回复：「您的订单 #12345 正在派送中！」

## agentic 系统分级：Level 0 到 Level 4

理解五步循环只是拼图的第一块。第二块是认识到：这个循环可以按复杂度逐级放大，形成不同类别的 agent。对架构师与产品负责人，最初的关键决策是框定要做哪一级。

- **Level 0：核心推理系统**。先有「大脑」的最基本形态：推理引擎本身。LM 孤立运转，仅凭预训练知识作答，没有 tools、没有记忆、不与实时环境交互。强项是训练覆盖的广度，能深入解释既有概念、规划解题思路。代价是完全没有实时感知：训练数据之外的任何事件与事实，它都「看不见」。它能讲清职业棒球规则与纽约洋基队的全部历史，但你问「昨晚洋基队比分是多少」，它答不出来——那场比赛发生在训练数据收集之后，知识里根本不存在。
- **Level 1：互联问题解决者**。推理引擎接上外部 tools——架构里的「双手」——成为真正的 agent。问题解决不再困在静态预训练知识里。用五步循环，它现在能回答上面那个问题：「使命」是查昨晚比分，「思考」识别出这是实时数据需求，「行动」调用带日期与检索词的 Google Search API，「观察」检索结果（洋基 5 比 3 获胜），把事实组织进最终答案。与世界的交互能力——查比分的搜索工具、查实时股价的金融 API、经 RAG 查数据库——是 Level 1 的核心。
- **Level 2：策略型问题解决者**。能力显著扩张：从执行简单任务到策略性规划复杂多段目标。这里浮现的关键技能是 context engineering——agent 主动筛选、打包、管理每一步计划最相关的信息。agent 的准确性依赖聚焦的高质量 context；context engineering 策展 model 有限的注意力，防止过载、保证高效。例子：使命是「在我山景城的办公室与旧金山客户办公室的中点找一家好咖啡馆」。Level 2 agent 制定计划：先想「必须先找到中点」，调 Maps 工具，观察到「中点是 Millbrae」；再想「现在要在 Millbrae 找咖啡馆，用户要『好的』，那就搜四星及以上」，调 google_places 工具带 query="coffee shop in Millbrae, CA"、min_rating=4.0——这一步就是 context engineering：从上一步输出自动构造出聚焦的新查询——观察返回「Millbrae Coffee」与「The Daily Grind」；最后综合结果呈现给用户。策略性规划还能支撑主动服务：agent 读一封很长的航班确认邮件，提炼关键 context（航班号、日期），行动把日程加进你的日历。
- **Level 3：协作式多 agent 系统**。范式完全转变：放弃建造单一无所不能的「超级 agent」，转向协同作业的「专家团队」，直接对应人类组织形态。系统的集体力量来自分工。agent 把别的 agent 当工具用。想象「项目经理」agent 接到使命：发布新款 Solaris 耳机。它自己不做全部工作，而是给专家 agent 团队创建新使命：委派 MarketResearchAgent「分析降噪耳机竞品定价，明天交摘要文档」；委派 MarketingAgent「用 Solaris 产品规格书当 context，起草三版新闻稿」；委派 WebDevAgent「按附带的设计稿生成新产品页 HTML」。协作模型受限于当今 LM 的推理能力，但代表着端到端自动化完整复杂业务工作流的前沿。
- **Level 4：自进化系统**。从委派跃迁到自主创造。系统能识别自身能力缺口，动态创建新 tools 甚至新 agents 来填补；从使用固定资源转为主动扩张资源。延续上面的例子：项目经理 agent 发现需要监控社交媒体舆情，但团队里没有这种 tool 或 agent。它先想（元推理）：「要追踪 Solaris 的舆论，但我没这个能力」；行动（自主创造）：不失败，而是调用高层 AgentCreator 工具发布新使命「建一个新 agent，监控关键词 Solaris 耳机、做舆情分析、每天汇报摘要」；观察：新的 SentimentAnalysisAgent 被创建、测试、随时入队，为原使命效力。这种自主扩张能力的能力，把 agent 团队变成真正学习与演化的组织。

## 核心架构：Model、Tools 与 Orchestration

知道了 agent 做什么、如何分级，具体怎么建？从概念到代码的过渡，在三个核心组件的架构设计里。

### Model：agent 的大脑

LM 是 agent 的推理核心，选型是关键架构决策，决定认知能力、运营成本与速度。把这个选择当成「挑基准分最高的 model」是常见的失败路径：生产环境里 agent 的成败，很少由通用学术基准决定。

真实成功要求 model 擅长 agentic 基本功：驾驭复杂多步问题的推理能力，与跟世界交互的可靠工具使用。做法：先定义业务问题，再对照直接映射到该结果的指标去测 model。agent 要写代码，就在你的私有代码库上测；处理保险理赔，就测它从你的特定文档格式里提取信息的能力。分析结果再对照成本与延迟的现实约束。特定任务下质量、速度、价格的最优交集，才是那个「最好的」model。

可以选多个 model 组成「专家团队」。砸核桃不必用大锤。健壮的架构可以用前沿 model（如 Gemini 2.5 Pro）承担初始规划与复杂推理的重活，再把简单的高频任务——用户意图分类、文本摘要——智能路由到更快更省的 model（如 Gemini 2.5 Flash）。路由可以自动也可以写定，是同时优化性能与成本的关键策略。

同样的原则适用于处理多样数据类型。原生多模态 model（如 Gemini live 模式）处理图像音频路径更顺；另一条路是用专门的 tools（如 Cloud Vision API、Speech-to-Text API），先把世界转成文字再交给纯语言 model 推理。这带来灵活与最优组件组合，也引入可观的复杂度。

最后，AI 领域持续快速演化。今天选的 model 六个月就会被超越，「设好就不管」的心态不可持续。面向这个现实，要投入一套敏捷的运营框架——Agent Ops 实践。有健壮的 CI/CD 管道持续按关键业务指标评估新 model，就能降低升级风险、加速升级，agent 永远用得上最好的大脑，而不需要推倒架构重来。

### Tools：agent 的双手

model 是大脑，tools 就是连接推理与现实的双手。它们让 agent 越过静态训练数据：检索实时信息、在世界里行动。健壮的工具接口是三段回路：定义 tool 能做什么、调用它、观察结果。

主要工具类型分三路：

- **检索信息：为现实提供 grounding**。最基础的是访问最新信息的能力。RAG 给 agent 一张「图书馆借书卡」，查询外部知识——常存于向量库或知识图谱，从公司内部文档到经 Google Search 的全网知识。结构化数据方面，NL2SQL（自然语言转 SQL）工具让 agent 查询数据库回答分析型问题：「上季度卖得最好的产品是什么？」先查再说——无论查文档还是查数据库——让 agent 立足事实，大幅减少幻觉。
- **执行行动：改变世界**。agent 的真正威力在从读信息走向动手做事。把既有 API 与代码函数包装成 tools，agent 能发邮件、订会议、更新 ServiceNow 里的客户记录。更动态的任务里，agent 能现场写代码并执行：在安全沙箱里生成 SQL 查询或 Python 脚本来解复杂问题或做计算，从博学的助手变成自主的行动者。
- **人机交互**。包括与人类交互的工具。agent 用 Human in the Loop（HITL）工具暂停工作流请求确认（如 ask_for_confirmation()），或从用户界面请求特定信息（如 ask_for_date_input()），保证关键决策有人参与。HITL 可以经短信与数据库里的一条任务实现。

**Function Calling：把 tools 接到 agent 上。**要可靠地做 function calling、用好 tools，需要清晰的 instructions、安全的连接与 orchestration。OpenAPI 规范这类长期标准提供支持，给 agent 一份结构化规约，描述 tool 的用途、必需参数与预期响应。这份 schema 让 model 每次都能生成正确的函数调用并解读 API 响应。为更简单地发现与连接 tools，MCP（Model Context Protocol）这类开放标准因为更方便而流行。此外少数 model 有原生 tools，如 Gemini 的原生 Google Search，函数调用发生在 LM 调用本身之内。

### Orchestration Layer：agent 的神经系统

model 是大脑、tools 是双手，orchestration layer 就是连接两者的中枢神经系统。它是运转「思考、行动、观察」循环的引擎、治理 agent 行为的 state machine、开发者精心设计的逻辑得以实现的地方。这层不只是管道；它是整个 agent 交响乐的指挥，决定何时 model 该推理、哪个 tool 该行动、行动结果如何影响下一乐章。

**核心设计选择。**第一个架构决策是确定 agent 的自主程度，选择分布在一个谱系上：一端是确定性的可预测工作流，把 LM 当作特定任务的工具调用——给既有流程加一点 AI；另一端是 LM 坐上驾驶席，动态适应、规划、执行任务以达成目标。

并行的选择是实现方式。no-code 构建器提供速度与易用性，让业务用户快速自动化结构化任务、搭建简单 agent。更复杂、更关键的系统则用 code-first 框架（如 Google ADK），提供工程师需要的深度控制、定制与集成能力。

无论哪种路线，生产级框架都不可或缺。它必须开放——能接入任何 model 或 tool，防止厂商锁定。它必须提供精确控制——支持混合方式，LM 的非确定性推理由硬编码的业务规则治理。最重要的是，框架必须为可观察性而建。agent 行为异常时，你没法在 model 的「思路」里打断点。健壮的框架生成详细的 traces 与 logs，暴露完整推理 trajectory：model 的内心独白、它选择的 tool、它生成的参数、它观察到的结果。

**用领域知识与 persona 下达指令。**在这套框架里，开发者最有力的杠杆是用领域知识与鲜明 persona 指导 agent，经 system prompt 或核心 instructions 实现。这不止是简单命令；它是 agent 的 constitution（章程）。在这里告诉它「你是 Acme 公司的客服 agent」，并给出约束、期望的输出 schema、行为规则、特定语气，以及何时、为何使用 tools 的明确指引。instructions 里配几个示例场景通常非常有效。

**用 context 增强。**agent 的「记忆」在运行时被编排进 LM 的 context window。短期记忆是 agent 的活动「草稿本」，维护当前对话的进行时历史，跟踪循环中不断累积的（行动，观察）对，为 model 决定下一步提供即时 context；实现形态可以是 state、artifacts、sessions 或 threads 这类抽象。长期记忆提供跨 session 持久化，架构上几乎总是实现为另一个专门的 tool——连着向量库或搜索引擎的 RAG 系统。orchestrator 让 agent 能预取、能主动查询自己的历史，从而「记得」用户的喜好或几周前类似任务的结果，实现真正个性化、连续的体验。

## 多 agent 系统与设计模式

任务复杂度上升后，建造单一「超级 agent」变得低效。更有效的解法是采用「专家团队」，对应人类组织。这是多 agent 系统的核心：复杂流程切成离散子任务，每个子任务交给专职的专门化 agent。分工让每个 agent 更简单、更聚焦、更易构建、测试与维护，天然适合动态或长时运行的业务流程。

架构师可以依赖经过验证的 agentic 设计模式，尽管 agent 能力与模式都在快速演化：

- **Coordinator 模式**：适合动态非线性任务。引入「管理者」agent 分析复杂请求、把主任务分段、把每个子任务智能路由给合适的专家 agent（研究员、写作者、程序员），再聚合各专家的回复形成最终完整答案。
- **Sequential 模式**：适合更线性化的工作流，像数字流水线，上一个 agent 的输出直接成为下一个的输入。
- **Iterative Refinement 模式**：围绕质量构建反馈回路，用「生成器」agent 创作内容、「评审器」agent 对照质量标准评估。
- **HITL 模式**：高风险任务的关键保障，在工作流里设置刻意的暂停点，agent 采取重大行动前必须获得人的批准。

## agent 部署与服务

本地建好 agent 后，要部署到服务器上常驻运行，供其他人与其他 agent 使用。沿用人体类比，部署与服务就是 agent 的身体与双腿。agent 需要多项服务才能有效运转：session 历史与记忆持久化等等。作为构建者，你还要决定记什么日志、为数据隐私、数据驻留与合规采取什么安全措施——部署 agent 进生产时这些都在范围内。

幸运的是，agent 构建者可以依赖几十年的应用托管基础设施。agent 是软件的新形态，很多原则直接适用。可以用专门的 agent 托管方案（如 Vertex AI Agent Engine，一个平台支撑 runtime 与其余一切）；想更直接掌控应用、在既有 DevOps 设施内部署的开发者，任何 agent 与多数 agent 服务都能装进 docker 容器，部署到 Cloud Run 或 GKE 这类行业标准 runtime 上。

不是软件开发者与 DevOps 专家的话，部署第一个 agent 可能令人生畏。很多 agent 框架用一条 deploy 命令或专门平台简化这件事，早期探索与上手应该用它们。要达到安全的生产环境，通常需要更多时间投入与最佳实践，包括针对 agent 的 CI/CD 与自动化测试。

## Agent Ops：给不可预测性立规矩

建头几个 agent 时，你会反复手工测试行为。加个功能，好用吗？修个 bug，有没有引发别的问题？测试对软件开发是常态，但在生成式 AI 这里运作方式不同。

从传统的确定性软件到随机的 agentic 系统，需要新的运营哲学。传统单元测试可以直接断言 output == expected；agent 的回答概率性生成，这条路走不通。而且语言复杂，评估「质量」——agent 的回答该做的全做了、不该做的没做、语气得体——通常也要靠 LM。

Agent Ops 是治理这一新现实的纪律化、结构化方法。它是 DevOps 与 MLOps 的自然演化，为构建、部署、治理 AI agent 的独特挑战量身定制，把不可预测性从负债变成可管理、可度量、可靠的特征。五大实践：

1. **像 A/B 实验一样度量成功**。改进 agent 之前，必须定义在你的业务语境里「更好」是什么。把可观察性策略当成 A/B 测试来设计：哪些 KPI 能证明 agent 在创造价值？指标要越过技术正确性，度量真实影响：目标完成率、用户满意度、任务延迟、单次交互运营成本，以及最重要的——对收入、转化、客户留存这类业务目标的影响。这个自上而下的视角会指引其余全部测试，带你走上 metrics-driven development，能算出投资回报。
2. **用 LM Judge 评质量，替代简单的通过与失败**。业务指标不会告诉你 agent 行为是否正确。简单的 pass/fail 行不通，转为用「LM as Judge」评质量：用一个强力 model 对照预定义 rubric 评估 agent 输出——答案对吗？回答立足事实吗？遵循 instructions 了吗？对 golden dataset 里的 prompts 跑这套自动评估，得到一致的质量度量。建评估数据集——含理想（golden）问题与正确回答——过程繁琐，做法是从既有生产或开发交互里采样场景，覆盖用户会用的全部用例，外加一些意外的。评估投入回报很快，但评估结果被接受为有效前，应经领域专家复核。这些评估的策展与维护，正日益成为产品经理在领域专家支持下的关键职责。
3. **Metrics-driven development：部署的 Go/No-Go**。自动化了几十个评估场景、建立了可信的质量分之后，就能放心测试开发版 agent 的改动：新版跑全量评估数据集，分数与生产版直接对比。这套体系消灭猜测，每次部署都有底气。自动化评估关键之外，别忘延迟、成本、任务成功率这些同样重要的因素。为最大安全，用 A/B 部署缓慢放量新版，把真实生产指标与模拟分数一起对照。
4. **用 OpenTelemetry traces 调试「为什么」**。指标下滑或用户报 bug 时，你要弄明白「为什么」。OpenTelemetry trace 是 agent 完整执行路径（trajectory）的高保真逐步记录，用来调试 agent 的每一步。透过 traces，你能看到发给 model 的确切 prompt、model 的内部推理（如果有）、它选择调用的 tool、它生成的精确参数、作为观察返回的原始数据。第一次看 traces 会觉得复杂，但它们提供诊断与修复任何问题根因所需的细节。重要的 trace 细节可以转成 metrics，但看 traces 主要为了调试，看性能总览用别的。trace 数据可以无缝采集进 Google Cloud Trace 这类平台，跨海量 traces 可视化检索，加速根因分析。
5. **珍惜人类反馈，指引自动化**。人类反馈是要处理的麻烦？它是最有价值、信息最丰富的改进资源。用户提 bug 报告或点「踩」时，是在送你礼物：一个自动化评估没覆盖到的真实边界案例。收集与聚合这些数据至关重要；看到统计上显著的同类报告或指标下滑，必须把发生记录接回分析平台，产出洞察、触发运营告警。有效的 Agent Ops 流程会「闭环」：捕获反馈、复现问题、把该场景转成评估数据集里一条新的永久测试用例。这保证了你修掉 bug 的同时，还给系统打了疫苗，这类错误永不再犯。

## agent 互操作

建好高质量 agent 后，要让它们与用户、与其他 agent 互联。在人体类比里，这是 agent 的脸面。连接 agents 与连接数据和 APIs 有本质不同：agents are not tools——agent 有自己的推理，不是被动等待调用的函数。假设 tools 已接好，现在考虑怎样把 agent 带进更大的生态。

### agent 与人类

最常见的交互形态是用户界面。最简单的是 chatbot：用户输入请求，agent 作为后端服务处理，返回一段文字。更进阶的 agent 能提供结构化数据（如 JSON），支撑富动态的前端体验。HITL 交互模式包括意图精炼、目标扩展、确认与澄清请求。

computer use 是一类特殊工具：LM 接管用户界面，常伴有人类交互与监督。启用 computer use 的 agent 可以判定下一步最优动作是导航到新页面、点亮某个按钮、或用相关信息预填表单。

agent 代替用户使用界面之外，LM 还能反过来改界面来满足当下需要。做法有：经 tools 控制 UI（MCP UI）；专门的事件传递 UI 消息系统，可与 agent 同步客户端 state（AG UI）；甚至按需生成界面（A2UI）。

人类交互当然不限于屏幕与键盘。先进的 agent 正在突破文字屏障，走向实时多模态交流，「live 模式」创造更自然、更像人的连接。Gemini Live API 这类技术支持双向流：用户可以对着 agent 说话、可以打断它，像自然对话一样。这从根本上改变 agent 与人的协作性质：拿到设备的摄像头与麦克风，agent 能看到用户所见、听到用户所说，以接近人类对话的延迟用语音回应。这打开了纯文字做不到的大量场景：技师修设备时获得免提指导、购物时获得实时穿搭建议。agent 成为更直觉、更可及的伙伴。

### agent 与 agent

agent 要连接人类，也要互相连接。企业扩大 AI 使用后，不同团队会建不同的专门 agent。没有共同标准，互联就需要编织一张由脆弱定制 API 集成组成的乱网，无法维护。核心挑战有两面：发现（我的 agent 怎么找到别的 agent、知道它们能做什么？）与通信（怎样保证说同一种语言？）。

Agent2Agent（A2A）协议就是为解决这个问题的开放标准，是 agentic 经济的通用握手。A2A 让任何 agent 发布一张数字「名片」——Agent Card。这个简单的 JSON 文件公示 agent 的能力、网络端点、交互所需的安全凭据，让发现变得简单且标准化。与聚焦事务性请求的 MCP 不同，Agent2Agent 通信典型用于更进一步的问题解决。

发现之后，agent 用任务导向架构通信。交互超出简单的一问一答：框定为异步「tasks」。客户端 agent 向服务端 agent 发送 task 请求，服务端在长连接上边解决问题边提供流式更新。这套健壮、标准化的通信协议是拼图的最后一块，支撑起协作式的 Level 3 多 agent 系统。A2A 把一群孤立 agent 变成真正可互操作的生态。

### agent 与金钱

AI agent 替我们做的事里，有一部分涉及买卖、谈判或促成交易。当今的 web 为人类点「购买」而建，责任在人。自主 agent 去点「购买」就制造了信任危机——出了错，谁负责？这是授权、真实性与可问责的复杂议题。要释放真正的 agentic 经济，需要让 agent 代表用户安全可靠交易的新标准。

这个新兴领域远未定型，两个关键协议正在铺路。Agent Payments Protocol（AP2）是开放协议，目标是成为 agentic 商务的权威语言。它扩展 A2A 这类协议，引入密码学签名的数字「mandates」（委托书），作为用户意图的可验证证明，为每笔交易创建不可抵赖的审计链。这让 agent 能基于用户的授权在全球范围安全地浏览、谈判、交易。与之互补的是 x402，一个用标准 HTTP 402「Payment Required」状态码的开放互联网支付协议，实现无摩擦的机器对机器微支付：agent 按使用量为 API 访问或数字内容付费，无需复杂账户或订阅。两个协议共同构成 agentic web 的基础信任层。

## 单个 agent 的安全：信任的权衡

创建第一个 AI agent，立刻面对一组根本张力：utility（效用）与 security（安全）的权衡。要让 agent 有用，必须给它权力——做决策的自主、执行行动（发邮件、查数据库）的 tools。但每授一分权力，就引入对应的一分风险。首要安全关切是 rogue actions（失控行动：无意或有害的行为）与敏感数据泄露。你要给 agent 的 leash（牵引绳）足够长到能干活，又足够短到不会冲进车流——尤其当「车流」涉及不可逆行动或公司私有数据时。

管理这个张力，不能只靠 AI model 的判断，因为它会被 prompt injection 这类技术操纵。最佳实践是混合的 defense-in-depth（纵深防御）：

- **第一层：传统确定性 guardrails**。一组硬编码规则，作为 model 推理之外的安全咽喉。可以是策略引擎：拦截超过 100 美元的购买，或要求 agent 与外部 API 交互前必须获得用户显式确认。这层提供可预测、可审计的硬性上限。
- **第二层：基于推理的防御**。用 AI 保 AI。包括训练 model 更抗攻击（adversarial training），以及部署小型专门的「guard models」充当安全分析师：在 agent 的计划执行前审查，把有风险或违反策略的步骤标出来送人复核。代码的刚性确定与 AI 的情境感知相结合，为单个 agent 构成健壮的安全姿态，确保它的权力始终服务于它的用途。

**Agent Identity：一类新的 principal。**传统安全模型里，人类用户走 OAuth 或 SSO，服务走 IAM 或 service accounts。agent 增加了第三类 principal。agent 不只是一段代码；它是自主行动者，一类需要自己可验证身份的新 principal。就像员工发工牌，平台上每个 agent 都要发放安全、可验证的「数字护照」。这个 Agent Identity 独立于调用它的用户与构建它的开发者。这是企业 Identity and Access Management（IAM）的一次根本转变。

每个身份都经过验证、每个身份都有访问控制，是 agent 安全的基石。agent 拿到密码学可验证的身份（常经 SPIFFE 这类标准）后，就能获得自己的最小权限：SalesAgent 拿到 CRM 的读写权限，HRonboardingAgent 被明确拒绝。这种粒度控制至关重要：即使单个 agent 被攻陷或行为异常，潜在的 blast radius（波及范围）也被限制住。没有 agent identity 体系，agent 无法在有限授权下代表人类工作。

| Principal 实体 | 认证 / 验证 | 说明 |
|---|---|---|
| Users | OAuth 或 SSO | 人类行动者，对自己的行为有完全自主与责任 |
| Agents（新的 principal 类别） | SPIFFE 验证 | agent 持有授权，代表用户行动 |
| Service accounts | 集成进 IAM | 应用与容器，完全确定性，不承担行为责任 |

**用 policy 约束访问。**policy 是一种授权（AuthZ），区别于认证（AuthN）。典型地，policy 限制 principal 的能力，例如「市场部的用户只能访问这 27 个 API 端点，不能执行 DELETE 命令」。开发 agent 时，要把权限施加到 agent 本身、它们的 tools、其他内部 agents、可共享的 context、以及远程 agents。这样想：把全部 APIs、数据、tools、agents 加进系统后，必须把访问约束到完成任务所需的那一小部分能力。这是推荐做法：应用最小权限原则，同时保持与情境的相关性。

**加固一个 ADK agent。**identity 与 policy 的核心原则确立后，加固 ADK（Agent Development Kit）构建的 agent，就是经代码与配置应用这些概念的实操。过程要求清晰定义身份：用户账号（如 OAuth）、service account（跑代码）、agent identity（行使授权）。认证处理完，下一层防御是建立 policy 约束对服务的访问，常在 API 治理层做，配合对 MCP 与 A2A 服务的治理。再下一层是把 guardrails 建进 tools、models 与 sub-agents 来强制执行 policy：无论 LM 推理出什么、无论恶意 prompt 引导什么，tool 自身的逻辑会拒绝执行不安全或越策略的动作。这提供了可预测、可审计的安全基线，把抽象安全策略翻译成具体可靠的代码。

对需要随 agent 运行时行为动态适应的安全，ADK 提供 Callbacks 与 Plugins。before_tool_callback 在 tool 调用前检查参数，对照 agent 当前 state 校验，防止错配动作。要更可复用的 policy，可以构建 plugins。一个常见模式是「Gemini as a Judge」：用快速便宜的 model（如 Gemini Flash-Lite 或自训 Gemma）实时筛查用户输入与 agent 输出中的 prompt injection 或有害内容。想用全托管企业方案的，可以把 Model Armor 作为可选服务接入，作为专门安全层筛查 prompts 与 responses 的多种威胁：prompt injection、越狱尝试、敏感数据（PII）泄露、恶意 URL。把复杂安全任务交给专门服务，开发者无需自建自维这些 guardrails 也能获得稳定健壮的保护。ADK 内这套组合——强 identity、tool 内确定性逻辑、动态 AI guardrails、可选托管服务——就是构建既有力量又可信的单个 agent 的方法。

## 从单 agent 到企业舰队

单个 AI agent 生产成功是凯旋；扩展到几百个则是架构的挑战。建一两个 agent，操心的是安全；建很多 agent，必须设计能承担更多的系统。与 API sprawl 一样，agent 与 tool 在组织里扩散后，会织出一张新的复杂网络：交互、数据流、潜在安全漏洞。管理这个复杂度需要更高一层的治理——把所有 identity 与 policy 集成起来、汇入中央 control plane。

**安全与隐私：加固 agentic 边疆。**企业级平台必须应对生成式 AI 特有的安全与隐私挑战，哪怕只跑一个 agent。agent 本身成为新的攻击面：恶意行动者可以尝试 prompt injection 劫持 agent 的 instructions，或 data poisoning 污染它训练或 RAG 用的信息。约束不当的 agent 还可能在回答里无意泄漏敏感客户数据或专有信息。健壮的平台提供 defense-in-depth：从数据做起，保证企业专有信息绝不用于训练基础 model，并被 VPC Service Controls 这类控制保护；要求输入输出过滤，像 prompts 与 responses 的防火墙；最后提供合同性保护，如对训练数据与生成输出的知识产权赔偿，给企业生产部署所需的法律与技术信心。

**agent 治理：control plane 代替 sprawl。**agent 与 tool 扩散后形成的复杂交互与漏洞网络，常被称为 agent sprawl。管理它需要超越逐个加固 agent，实施更高层的架构方案：作为全部 agentic 活动 control plane 的中央 gateway。想象一座繁忙都市里成千上万辆自动驾驶汽车——用户、agents、tools——都在有目的地移动。没有红绿灯、车牌与中央控制系统，混乱必然横行。gateway 方案建立的就是那套控制系统：全部 agentic 流量的强制入口，包括用户对 agent 的 prompts 或 UI 交互、agent 对 tool 的调用（经 MCP）、agent 间协作（经 A2A）、对 LM 的直接推理请求。坐镇这个关键路口，组织能检查、路由、监视、管理每一次交互。这个 control plane 承担两个相互关联的职能：

1. **运行时策略执行**：安全的架构咽喉。处理认证（「我认识这个行动者吗？」）与授权（「它有权做这件事吗？」）。集中执行提供可观察性的「单一全景」，为每笔交易生成统一 logs、metrics、traces，把散乱 agent 与工作流的乱麻变成透明、可审计的系统。
2. **集中治理**：有效执行 policy 需要 single source of truth，由中央 registry 提供——agent 与 tool 的企业应用商店。开发者借此发现复用既有资产、避免重复建设，管理员获得完整清单。更重要的是它为 agent 与 tool 建立正式生命周期：发布前的安全评审、版本管理、规定哪些业务单元能用哪些 agent 的细粒度策略。

运行时 gateway 加中央治理 registry，组织把混乱 sprawl 的风险变成受管理、安全、高效的生态。

**成本与可靠性：基础设施的地基。**企业级 agent 必须既可靠又划算。频繁失败或响应缓慢的 agent，ROI 为负；贵到用不起的 agent 无法扩展满足业务。底层基础设施必须管理好这对权衡，兼顾安全、监管与数据主权合规。有些场景需要 scale-to-zero（流量不规则时缩容到零）；关键任务、延迟敏感的负载，平台必须提供专用的保证容量，如 LM 服务的 Provisioned Throughput、Cloud Run 这类 runtime 的 99.9% SLA，保证最重要的 agent 在重压下依然响应。提供这整段基础设施谱系，配齐成本与性能的双重监控，就为 agent 从有前景的创新变成企业核心可靠组件打好最后一块地基。

## agent 如何演化与学习

部署到真实世界的 agent 在动态环境里运转：policy、技术、数据格式持续变化。没有适应能力，agent 的表现会随时间退化——常被称为「aging」——导致效用与信任流失。靠人力更新庞大的 agent 舰队既慢又不经济。更可扩展的方案：设计能自主学习演化的 agent，在工作中以最小工程投入提升质量。

agent 与人类相像，从经验与外部信号学习。学习过程的燃料有几路来源：

- **Runtime Experience**：agent 从运行时产物学习——session logs、traces、memory——它们记录成功、失败、tool 交互与决策 trajectory。关键是其中包括 HITL 反馈，提供权威的纠正与指导。
- **External Signals**：新外部文档同样驱动学习，如更新的企业 policy、公开监管指引、来自其他 agents 的批评。

这些信息接着被用于优化 agent 的未来行为。先进系统创建可泛化的产物来指导未来任务。最成功的适应技术分两类：

- **Enhanced Context Engineering**：系统持续精炼 prompts、few-shot 示例、从 memory 检索的信息。优化每个任务供给 LM 的 context，提高成功率。
- **Tool Optimization and Creation**：agent 的推理能识别能力缺口并行动填补：获得新 tool 的访问权、现场创建新 tool（如一段 Python 脚本）、或修改既有 tool（如更新 API schema）。

其他优化技术——动态重构多 agent 设计模式、RLHF（基于人类反馈的强化学习）——是活跃的研究领域。

**示例：学习新的合规准则。**设想一个在金融或生命科学这类强监管行业的企业 agent，任务是生成必须符合隐私与监管规则（如 GDPR）的报告。可用多 agent 工作流实现：

1. Querying Agent 响应用户请求检索原始数据。
2. Reporting Agent 把数据组织成报告草稿。
3. Critiquing Agent 带着已知合规准则审阅报告；遇到歧义或需要最终签字时，上报人类领域专家。
4. Learning Agent 观察整个交互，特别留意人类专家的纠正反馈，把它泛化为一条新的可复用准则（如更新 critiquing agent 的规则，或精炼 reporting agent 的 context）。

例如人类专家指出某些家庭统计数据必须匿名化，Learning Agent 记录这条纠正。下次生成类似报告时，Critiquing Agent 自动应用新规则，减少人工介入。批评、人类反馈、泛化的循环，让系统自主适应演化的合规要求。

**模拟与 Agent Gym：下一个前沿。**上面的设计模式可归类为 in-line learning——agent 用工程赋予它的资源与设计模式在线学习。更先进的路线正在研究中：专门的离线平台，配高级工具与能力来优化多 agent 系统，这些能力不属于多 agent 的运行时环境。这样一个 Agent Gym 的关键属性有五条：

1. 不在执行路径上。它是独立于生产的平台，因此可以借助任何 LM model、离线工具、云端应用等。
2. 提供模拟环境，让 agent 在新数据上「锻炼」学习。模拟环境极适合大量优化路径下的试错。
3. 能调用高级合成数据生成器，引导模拟尽量真实，对 agent 压力测试（可含 red-teaming、动态评估、一族 critiquing agents 等高级技术）。
4. 优化工具的军火库不固定，可以采用新工具（经 MCP 或 A2A 这类开放协议），更进一步的设定里还能学习新概念并围绕它们打造工具。
5. 最后，连 Agent Gym 这样的构造也可能搞不定某些边界案例（源于企业里众所周知的「tribal knowledge」问题——部门内部口传心授、没写进文档的知识）。这些场景里，Agent Gym 能连接人类领域专家网络，就正确的结果集合向他们咨询，指导下一轮优化。

## 高级 agent 实例

**Google Co-Scientist。**Co-Scientist 是为充当虚拟研究协作者而设计的先进 AI agent，经系统性探索复杂问题空间加速科学发现。研究者定义目标、让 agent 立足于指定的公开与专有知识来源，它随即生成并评估一批新颖假设的图景。为此，Co-Scientist 孕出一整个互相协作的 agent 生态。把系统看成研究项目经理：AI 先把宽泛的研究目标变成详细项目计划；一个「Supervisor」agent 担任经理，把任务委派给专门 agent 团队并分配算力等资源。这个结构保证项目轻松扩容，团队的方法随目标推进持续改进。各 agent 工作数小时甚至数天，持续改进生成的假设，运行改进生成想法的循环与元循环，同时改进评判和创造新想法的方式本身。

**AlphaEvolve agent。**另一个先进的 agentic 系统是 AlphaEvolve：为数学与计算机科学的复杂问题发现并优化算法的 AI agent。它把 Gemini 语言模型的创造性代码生成与自动评估系统结合，用演化过程工作：AI 生成候选解，评估器打分，最有前途的想法成为下一代代码的灵感。已产出一批重要突破：提升 Google 数据中心、芯片设计与 AI 训练的效率；发现更快的矩阵乘法算法；为公开数学问题找到新解。AlphaEvolve 特别擅长「验证解的质量远易于找到解」的问题。它为人类与 AI 的深度迭代协作而设计，协作有两条主线：透明的解——AI 以人类可读的代码生成解，透明性让用户理解逻辑、获得洞察、信任结果、按需直接改代码；专家引导——人类专长对定义问题至关重要，用户经精炼评估指标与导引探索方向来引导 AI，防止系统钻问题定义的空子。这个交互回路保证最终解既有力量又实用。agent 的产出是持续改进的代码，不断逼近人类指定的指标。

## 结语

生成式 AI agent 标志一次关键演化：人工智能从被动的内容创作工具，变成解决问题中主动的自主伙伴。本书为理解与构建这类系统提供了正式框架，越过原型，建立可靠的生产级架构。

我们把 agent 分解为三个本质组件：推理的 Model（大脑）、行动的 Tools（双手）、治理的 Orchestration Layer（神经系统）。三者无缝集成、在持续的「思考、行动、观察」循环里运转，释放 agent 的真正潜力。从 Level 1 互联问题解决者到 Level 3 协作式多 agent 系统的分级，让架构师与产品负责人能按手头任务的复杂度框定野心。

核心挑战与机会都在新的开发者范式里。我们不再是定义显式逻辑的「砌砖工人」；我们是「架构师」与「导演」，必须引导、约束、调试一个自主实体。让 LM 强大的灵活，也正是它不可靠的来源。因此成功不在最初的 prompt 里，而在应用于整个系统的工程严谨里：健壮的工具规约、有韧性的错误处理、精巧的 context 管理、全面的评估。

本书勾画的原则与架构模式是地基蓝图，是航行这片软件新疆界的路标，让我们建造的不止是「工作流自动化」，而是团队里真正能协作、有能力、有适应力的新成员。技术成熟之时，这种纪律化、架构化的路线，将是释放 agentic AI 全部力量的决定因素。

## 原文尾注要点

原文 45 条尾注中与本文机制直接相关的：ReAct（arXiv 2210.03629）、Chain-of-Thought（arXiv 2201.11903）、τ-bench 工具交互基准（arXiv 2406.12045）、Agents 白皮书（kaggle.com/whitepaper-agents）、Agents Companion（kaggle.com/whitepaper-agent-companion）、AI Agent Observability（opentelemetry.io）、Agents are not tools（discuss.google.dev）、prompt injection 系列（simonwillison.net）、defense-in-depth 论文（Google research）、SPIFFE（spiffe.io）、MCP（github.com/modelcontextprotocol）、AI co-scientist（research.google）、MLGym（arXiv 2502.14499）、Self-Evolving-Agents（github.com/CharlesQ9）。系列其余四本分别深入 tools 与 MCP、context 与 memory、quality、prototype to production。
