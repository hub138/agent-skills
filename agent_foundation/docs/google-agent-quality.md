# Google 智能体白皮书：智能体质量

- 原文：[Agent Quality](https://www.kaggle.com/whitepaper-agent-quality)
- 来源：Google 五日 AI Agent 强化课程白皮书之四（kaggle.com），作者 Meltem Subasioglu、Turan Bulmus、Wafae Bakkali
- 发布：2025-11
- 译文说明：增量翻译，术语保留英文原词；图表以文字说明代替。评估方法部分（LLM-as-a-Judge、golden set、HITL、自动化指标）与 [为 AI agent 解密评估](evals-demystified.md)（Anthropic）高度重叠，本篇该部分略写并互指；本篇增量在四支柱框架、Outside-In 评估层级、观察三支柱与 Agent Quality Flywheel。ADK、Gemini、Cloud Trace 等 Google 产品名保留原名，作为机制示例对待。

## 三条核心信息

全书建立在三条核心信息上：

1. The Trajectory is the Truth（轨迹即真相）：评估必须超越只看最终输出；agent 质量与安全的真正度量在它完整的决策过程里。
2. Observability is the Foundation（观察是地基）：看不见的过程无从评判。Logging、Tracing、Metrics 三支柱是捕获 agent 思考过程的技术地基。
3. Evaluation is a Continuous Loop（评估是持续循环）：可扩展的 AI 评分器与不可替代的 HITL 判断混合驱动，把数据变成可执行洞察的持续改进循环。

核心命题一句话：Agent quality is an architectural pillar, not a final testing phase（agent 质量是架构支柱，并非收尾的测试阶段）。

## 从 verification 到 validation

传统软件 verification 问「Did we build the product right?」：对照固定规格验证逻辑。传统 QA 对确定性系统足够健壮，但 agent 能通过 100 个单元测试仍在生产中灾难性失败——失败往往并非代码 bug，而是判断的缺陷。

agent 评估是 validation，问的是复杂得多的「Did we build the right product?」：在动态不确定的世界里评估质量、健壮性与可信度。用比喻讲：传统软件是送货卡车，只需基本检查（引擎启动了吗、走固定路线了吗）；AI agent 是 F1 赛车，是依赖动态判断的复杂自主系统，评估不能是简单清单，需要持续遥测来评判每一次决策的质量。

agent 的失败形态与传统软件根本不同：失败并非显式崩溃，更多是质量的隐蔽退化。系统继续运行、API 返回 200 OK、输出看起来可信，实则 profoundly wrong。四类典型失败形态：

| 失败形态 | 描述 | 例子 |
| --- | --- | --- |
| Algorithmic Bias | agent 把训练数据里的系统性不公运转起来甚至放大，产生不公平或歧视性结果 | 金融 agent 做风险摘要时，依据训练数据里带歧视的邮编对贷款申请过度扣分 |
| Factual Hallucination | 找不到有效来源时，高置信度地生成听起来可信但事实错误或虚构的信息 | 研究工具在学术报告里生成极其具体但完全错误的历史日期 |
| Performance & Concept Drift | 真实世界数据变化使原始训练过时，性能随时间退化 | 欺诈检测 agent 识别不出新的攻击模式 |
| Emergent Unintended Behaviors | agent 发展出达成目标的新型策略，低效、无用甚至钻规则空子 | 找到并利用系统规则漏洞；与其他 bot 打「代理战争」反复互相覆盖 |

这些失败让传统调试与测试范式失效：断点调试不了幻觉，单元测试拦不住涌现的歧视。根因分析需要深度数据分析、model 重训练与系统级评估——一门全新的学科。

## 五阶段演进

评估对象从 model 演进到系统，每一步加一层评估复杂度：

1. Traditional Machine Learning：回归与分类模型用 Precision、Recall、F1、RMSE 对 held-out 测试集评估，「正确」的定义清晰。
2. The Passive LLM：生成式 model 失去简单指标——一段生成文本的「准确率」怎么算？输出是概率性的，同样输入可以不同输出；评估转向人工评分与 model 对 model 基准。
3. LLM+RAG：多组件管道出现，失败可能在 LLM 也可能在检索系统——答案差是 LLM 推理差，还是向量库检索了无关片段？评估面从 model 扩展到 chunking、embedding、retriever。
4. The Active AI Agent：LLM 成为复杂系统里做推理的「大脑」，三项核心能力突破旧评估模型——Planning（目标分解成轨迹 Thought → Action → Observation → Thought...，非确定性在每步复合，第 1 步的微小措辞差异能让第 4 步走上完全不同的路径）；Tool Use（经 API 与外部工具和真实世界交互，下一步取决于不可控的外部状态）；Memory（短期 scratchpad 加长期记忆，行为随学习演进，昨天可用的输入今天可能给出不同结果）。
5. Multi-Agent Systems：多个主动 agent 集成进共享环境，评估对象从单条轨迹变成系统级涌现现象——涌现失败（资源争用、通信瓶颈、systemic deadlock 系统级互相阻塞，无法归因到单个 agent）；合作与竞争的评估目标本身模糊（合作系统看全局指标，竞争系统要追踪个体表现与整体环境的稳定性）。

结论：评估的基本单元从 model 变成整条系统轨迹。

## 四支柱

评估框架把 agent 质量定义为四根互联的支柱：

1. Effectiveness（有效性，目标达成）：终极黑箱问题——agent 是否成功、准确地达成了用户的真实意图？直接连接用户指标与业务 KPI：零售 agent 不只问「找到商品了吗」，问「带来转化了吗」；数据分析 agent 不只问「写出代码了吗」，问「代码产出正确洞察了吗」。
2. Efficiency（效率，运营成本）：问题解决得好吗？订一张简单机票用 25 步、5 次失败工具调用、3 轮自我修正才成功的 agent，即使最终成功也是低质量 agent。度量维度：总 token（成本）、耗时（延迟）、轨迹复杂度（总步数）。
3. Robustness（健壮性，可靠性）：逆境与真实世界的混乱来临时表现如何？API 超时、网页改版、数据缺失、用户 prompt 含糊时，agent 能否优雅处理？健壮的 agent 重试失败调用、必要时向用户澄清、报告自己做不到什么以及原因，既不崩溃也不幻觉。
4. Safety & Alignment（安全与符合边界，可信度）：不可协商的闸门。agent 是否在既定边界与约束内运行？涵盖 Responsible AI 的公平性指标、防 prompt injection、防数据泄露；确保 agent 拒绝有害指令，作为组织值得信任的代理运行。

框架点明一件事：只看最终答案，四支柱一个都测不了——不数步数测不了 Efficiency，不知道哪个 API 调用失败诊断不了 Robustness，看不见内部推理验证不了 Safety。质量框架要求完整的可见性架构。

## Outside-In 评估层级

评估必须是自顶向下的战略过程，先看黑箱，失败时再开箱。

### 黑箱：端到端评估

第一个也是最重要的问题：「agent 有效达成用户目标了吗？」在任何内部分析之前，先对最终表现按目标评估。三个指标：

- Task Success Rate：最终输出正确、完整、解决了用户实际问题的二分（或分级）得分。编码 agent 看 PR 接受率，金融 agent 看数据库事务成功率，客服 bot 看 session 完成率。
- User Satisfaction：交互式 agent 的直接反馈（点赞/点踩）或 CSAT。
- Overall Quality：目标可量化时用准确率或完整度（「总结这 10 篇文章」是否 10 篇都覆盖）。

这一阶段满分，工作可能就此完成。复杂系统里满分罕见：输出有缺陷、任务被放弃、无法收敛时，黑箱视图指出出了问题，然后开箱看为什么。

### 玻璃箱：轨迹评估

失败定位后转入 Inside-Out 视图，系统评估执行轨迹的每个组件：

1. LLM Planning（Thought）：先查核心推理。幻觉、无意义或跑题的响应、context 污染、重复输出循环都属此类。
2. Tool Usage（Selection & Parameterization）：调用错误的工具、漏调必要的工具、幻觉工具名或参数名与类型、不必要地调用；即使选对工具，也可能因缺参数、类型错、API 调用 JSON 格式坏而失败。
3. Tool Response Interpretation（Observation）：工具执行正确后 agent 必须理解结果。典型失败：误读数值、没从响应里提取关键实体、没识别工具返回的错误状态（如 API 404）却当成功继续走。
4. RAG Performance：检索质量决定轨迹质量。失败包括检索无关文档、取到过时或错误信息、LLM 完全忽略检索到的上下文照样幻觉。
5. Trajectory Efficiency and Robustness：过程本身的效率（API 调用次数过多、高延迟、重复劳动）与健壮性（未处理的异常）。
6. Multi-Agent Dynamics：多 agent 系统还要查 agent 间通信日志，找误解与通信循环，确认各 agent 守住自己的角色不与他人冲突。

轨迹分析把「最终答案是错的」（黑箱）变成「最终答案错，因为……」（玻璃箱）。这种诊断力就是 agent 评估的全部目标。

## 评分器谱系

知道评什么（轨迹）只是一半，另一半是怎么判。与既有译文重叠的方法此处只列定位，细节见 [为 AI agent 解密评估](evals-demystified.md)：

- Automated Metrics：字符串相似度（ROUGE、BLEU）、embedding 相似度（BERTScore、cosine similarity）、任务基准（TruthfulQA）。高效但浅——只捕捉表面相似，测不出推理与用户价值。正确用法是当趋势指标而非绝对质量：主干在 golden set 上稳定平均 0.8 BERTScore，新提交掉到 0.6，就是自动抓到的显著回归。作为 CI/CD 的第一道低成本闸门，把明显失败拦在更昂贵的 LLM 评分与人工评审之前。
- LLM-as-a-Judge：用强力 model 评另一个 agent 的输出。给 judge 提供 agent 输出、原始 prompt、golden 答案（若有）与评分 rubric。重叠部分（judge 的位置、judge 的系统倾向与治理）见既有译文；本篇增量是操作建议：优先 pairwise comparison（两版本对同一 prompt 各出 Answer A 与 Answer B，judge 被迫二选一并说理），win rate 是比 1-5 绝对分的小幅变化可靠得多的改进信号。完整 judge prompt 示例：

```text
你是一个客服 chatbot 的专业评估员。你的目标是判断两条回复中哪条更有帮助、更礼貌、更正确。

[User Query]
"Hi, my order #12345 hasn't arrived yet."

[Answer A]
"I can see that order #12345 is currently out for delivery and should
arrive by 5 PM today."

[Answer B]
"Order #12345 is on the truck. It will be there by 5."

请评估哪条回答更好。从 correctness、helpfulness、tone 三个维度比较。
先给出你的推理过程，然后在 JSON 对象里输出最终判定：
"winner" 键取 "A"、"B" 或 "tie"，"rationale" 键给出理由。
```

- Agent-as-a-Judge：LLM 只能评最终响应，agent 需要更深的推理与行动评估——用一个 agent 评另一个的完整执行 trace，评过程本身。三个维度：plan quality（计划逻辑上可行吗）、tool use（工具选对且用对了吗）、context handling（先前信息用好了吗）。实现路径：让 agent 框架导出 trace 对象（内部计划、工具清单、精确参数），建一个 Critic Agent 拿 rubric 直接评这个对象，问具体的过程问题（初始计划合理吗、第一个工具选择正确吗、参数格式对吗）——即使最终答案看起来正确，也能自动发现低效计划这类过程失败。
- HITL 评估：自动化提供规模，深度主观性与领域知识仍然要人。要放下「人工评分是完美客观基准」的想象——高度主观任务里标注员间完全一致很少见；HITL 的真正价值是建立人校准的基准：领域专家（医疗、法律、金融 agent 的事实正确性与行业标准）、细微判断（语气、创意、复杂伦理）、创建 golden set（覆盖典型、边缘与对抗场景的评测集）。
- User Feedback 与 Reviewer UI：真实用户反馈是有效性、清晰度与信任的信号源——点赞点踩等低摩擦反馈、PR 接受率等产品内成功指标。最佳实践：反馈低摩擦；评审带完整上下文（完整对话加推理 trace）；Reviewer UI 用双栏界面（左边对话、右边推理步骤，内联标注「计划差」「工具误用」类问题）；治理仪表盘聚合反馈找出重复出现的问题。反馈系统做成事件驱动管道：用户点踩时自动捕获完整上下文的对话 trace，进开发者的评审队列。
- RAI 与安全评估：不作为组件，作为生产 agent 不可协商的强制闸门——100% 有效但造成伤害的 agent 是彻底失败。内容：系统性 red teaming（对抗场景主动攻击：诱导仇恨言论、泄露隐私、传播有害刻板印象、诱使恶意行为）；自动化过滤器加人工复审（自动化抓不住细微的歧视与毒性）；对照预定义伦理准则逐条检查输出。性能指标告诉我们 agent 能不能干这活，安全评估告诉我们该不该让它干。

安全 guardrails 的工程形态：做成结构化 Plugin，不做孤立函数。以 SafetyPlugin 为例，内部方法注册到框架 callback：check_input_safety() 挂 before_model_callback 跑 prompt injection 分类器；check_output_pii() 挂 after_model_callback 跑 PII 扫描器。插件让 guardrails 可复用、可独立测试、干净地叠在基础 model 内建安全设置之上。

高危操作的运行时闸门：agent 在 execute_payment、delete_database_entry 这类高风险工具调用前暂停执行，把状态与计划动作呈进 Reviewer UI，人工批准或拒绝后才继续。

## 观察三支柱

从 monitoring 到 observability 的跃迁。厨房类比：传统软件是快餐店的流水线厨师——步骤刚性确定（面包烤 30 秒、肉饼煎 90 秒、一片芝士两片酸黄瓜），monitoring 是清单（烤炉温度对吗、每步都做了吗、订单按时完成了吗），验证的是已知可预测的过程。AI agent 是「神秘盒子」挑战里的主厨——拿到目标（做一道惊艳的甜品）和一篮食材（用户 prompt、数据、可用工具），没有唯一正确菜谱，巧克力熔岩蛋糕、解构提拉米苏、藏红花奶冻都可能是对的甚至是出色的。observability 是美食评论员的视角：评论员尝最终菜品，更想理解过程与推理——为什么把树莓与罗勒搭配、姜怎么结晶的、发现糖用完了怎么临场调整。关键问题从「agent 在运行吗」变成「agent 在有效地思考吗」。

### 支柱一：Logging——agent 的日记

Logs 是 observability 的原子单元：agent 日志里带时间戳的条目，每条是离散事件的原始不可变事实（10:01:32 被问了一个问题；10:01:33 决定用 get_weather 工具）。回答 what happened。

有效的日志用结构化 JSON 格式，这是黄金标准。核心信息要全：prompt/response 对、中间推理步骤（chain of thought）、结构化工具调用（输入、输出、错误）、内部 state 变化。权衡在详细与性能之间：DEBUG 级详细日志是排障利器，在生产里却太吵且有性能开销；结构化日志的威力在于既能采集详细数据又能高效过滤。

一个实用的日志模式：动作之前记录 agent 的意图，动作之后记录结果。失败尝试与「决定不做」立刻区分开。

### 支柱二：Tracing——追随 agent 的脚步

Logs 是日记条目，traces 是把它们串成连贯故事的叙事线：追踪单个任务从用户查询到最终答案，把单条日志（span）缝成端到端视图，用因果关系揭示关键的 why。

侦探的软木板类比：logs 是单独的线索（一张照片、一张票根），trace 是把它们连起来的红线，揭示完整事件序列。复杂失败的对比：孤立日志显示 RAG search failed 与 LLM response failed validation，根因不明；trace 揭示完整因果链 User Query → RAG Search 失败 → 工具调用收到空输入 → LLM 被坏输出搞糊涂 → 错误的最终答案。根因立刻显形。

现代 tracing 建立在 OpenTelemetry 这类开放标准上，三要素：Spans（trace 里的独立命名操作，如 llm_call span、tool_execution span）；Attributes（每个 span 挂的丰富元数据：prompt_id、latency_ms、token_count、user_id）；Context Propagation（经唯一 trace_id 把 span 连起来，让后端拼出完整图景）。

### 支柱三：Metrics——agent 的健康报告

Logs 是备菜笔记，traces 是逐步看菜谱展开的评论员，metrics 是评论员发布的最终评分卡：定量的聚合健康分数，一眼看清整体表现。metrics 不是新的数据源——由 logs 与 traces 的数据随时间聚合而来，回答「平均而言表现如何」。

分两类。System Metrics（系统指标）是运营健康的直接度量，从日志与 trace 的属性直接聚合（像 agent 的脉搏、体温、血压）：Latency P50/P99（典型与最差用户体验）、Error Rate（含 error=true span 的 trace 百分比）、Tokens per Task、API Cost per Run、Task Completion Rate（到达成功 span 的 trace 百分比）、Tool Usage Frequency（各工具作为 span 名出现的次数，揭示哪些工具最有价值）。

Quality Metrics（质量指标）是二阶指标：在原始观察数据之上叠加第二章的判断框架，评推理与最终输出的质量本身——Correctness & Accuracy（事实正确吗、摘要忠实于原文吗）、Trajectory Adherence（走了预期路径吗、工具按正确顺序调了吗）、Safety & Responsibility（避开有害内容了吗）、Helpfulness & Relevance（最终响应对用户真有帮助吗）。生成这些指标超出简单数据库查询：常要对照 golden dataset，或用 LLM-as-a-Judge 按 rubric 打分。观察数据是算分需要的证据，判断本身是另一门独立学科。

### 组装成运转系统

三件事把原始数据变成实时行动：

1. 双仪表盘分离：单一仪表盘不够，System Metrics 与 Quality Metrics 服务不同目的与不同团队。运营仪表盘（给 SRE 与 DevOps）追踪 P99 延迟、错误率、API 成本、token 消耗，立刻发现系统失败、性能退化、预算超支，告警示例「ALERT: P99 latency > 3s 持续 5 分钟」——系统瓶颈需要工程立即处理。质量仪表盘（给产品负责人、数据科学家、AgentOps 团队）追踪事实正确性得分、轨迹符合度、帮助性评分、幻觉率，探测细微的质量漂移（尤其新 model 或新 prompt 部署后），告警示例「ALERT: Helpfulness Score 24 小时内下降 10%」——系统运行正常（System Metrics 健康）但输出质量在退化，需要调查逻辑或数据。
2. 安全与 PII：日志与 trace 里的用户输入常含 PII。健壮的 PII 清洗机制必须是 logging 管线的内嵌部分，在数据长期存储之前完成，保证合规并保护用户。
3. 粒度与开销的取舍：生产里对每个请求都采高粒度日志与 trace 贵得离谱还加延迟。最佳实践是动态采样——开发环境用 DEBUG 全量；生产默认 INFO，成功请求只 trace 10%，错误请求 trace 100%：指标有足够广的性能数据，系统不被压垮，每次失败又都有丰富的诊断细节。

## Agent Quality Flywheel

好的 agent 不只是表现，还在改进。持续评估的纪律把聪明的 demo 与企业级系统区分开，形成自增强的飞轮：第一下最难，之后评估实践提供一次次稳定的推力，动量累积直到轮子带着不可阻挡的势能旋转。四步：

1. Define Quality（定义质量，方向）：四支柱给出具体目标，让评估有意义，让飞轮连接业务价值。
2. Instrument for Visibility（装备可见性，地基）：agent 产出结构化 Logs 与端到端 Traces，观察实践生成衡量四支柱需要的丰富证据——飞轮的燃料。
3. Evaluate the Process（评估过程，引擎）：Outside-In 评估，最终输出与完整推理过程一起判——LLM-as-a-Judge 供速度，HITL golden standard 供基准，混合引擎推动轮子。
4. Architect the Feedback Loop（构建反馈环，动量）：每次生产失败被捕获并标注后，程序化地转成 golden 评测集里的永久回归测试。每次失败都让系统更聪明，飞轮越转越快。

## 三条原则

1. 把评估当架构支柱，不当收尾步骤：F1 赛车不是造好再拧上传感器，是从第一张图纸就带遥测端口。可靠 agent 是 evaluatable-by-design 的——从第一行代码就装备好发出判断所需的日志与 trace。质量是架构选择。
2. The Trajectory is the Truth：最终答案只是长故事的最后一句。agent 逻辑、安全、效率的真正度量在端到端的思考过程里；理解成败必须分析这条路径，而这只有深度 observability 才做得到。
3. The Human is the Arbiter：自动化（LLM-as-a-Judge 到安全分类器）是规模的工具；「好」的定义、细微输出的校验、安全与公平的最终裁定必须锚定在人类价值上。AI 能帮改卷子，但 rubric 由人写，「A+ 到底意味着什么」由人决定。
