# 官方文档译文库目录

`docs/` 收 69 篇官方文档的中文译文，按九个主题分组。多数为全文翻译；题材重叠的篇目按增量翻译、略写、合并或压缩成摘要处理，各篇的实际取舍记在该篇来源头的「译文说明」里。分组按读者的问题意图聚类：怎么入门、工具怎么写、上下文怎么管、多 agent 怎么协调、harness 怎么设计、做得好不好怎么知道、安全怎么保、怎么上生产、模型换代怎么办。同一主题下 Anthropic、Google、OpenAI、DeepSeek、NVIDIA 的译文并列，机构视角的差异保留在各篇内部。

每篇译文开头有完整的来源头：原文 URL、来源机构、发布信息与翻译说明，目录不重复这些信息。机制怎么用读 [GUIDE.md](../GUIDE.md)，官方原始论述读译文；每组开头的「配套章节」给出指南里讲同一主题的章。

新增译文的挂载纪律：先判主题归属，挂进对应组的一行；九组覆盖不了的题材，先议新组再收编，不设未分类堆放区。

## 一、构建入门与总纲（7 篇）

配套章节：GUIDE 第 0 章「开箱：新 agent 先装的三样」、第 21 章「开箱骨架：可以直接抄的组装」。

- [构建高效 agent](building-effective-agents.md)：Anthropic 奠基文。agent 与 workflow 的分界、五种基础模式（prompt chaining、routing、parallelization、orchestrator-workers、evaluator-optimizer）、何时该用 agent 何时别用。
- [构建智能体实践指南](openai-practical-guide.md)：OpenAI 面向业务方的指南。agent 设计基础（模型、工具、编排三层）、从单技能 agent 起步的路径、编排与护栏。
- [用 Claude Agent SDK 构建 agent](claude-agent-sdk.md)：给 Claude 一台计算机的构建路径：agent 循环、收集上下文、采取行动、验证工作、测试与改进。
- [Google 智能体白皮书：智能体入门](google-intro-agents.md)：Google 五日课程第一本。agentloop 三层架构、模型-工具-编排层分工、从预测式 AI 到自主 agent。
- [信任从哪里来：Anthropic 的实践](anthropic-trustworthy-agents.md)：Anthropic 官方文。agent 定义与自驱循环、四组件总纲（model/harness/tools/environment，每层既是能力来源也是监督点）、五原则中三条的实践形态（Plan Mode、训练里强化停下来询问、prompt injection 分层防御）、生态三项（基准、证据共享、开放标准）。
- [OpenAI Agents SDK：代码优先的智能体构建](openai-agents-sdk.md)：OpenAI 官方文档总纲页。SDK 与服务器的分工（部署、工具实现、状态存储、审批归服务器，循环归 SDK）、十一个能力入口的选表、推荐阅读顺序、Agents SDK 与 Responses API 八维对照（谁掌握循环、核心抽象、多智能体、状态、审批、追踪）。
- [Claude API 入门总纲](claude-api-primer.md)：Anthropic 官方文档总纲页。模型清单七行表（Opus 5.5 至 Haiku 4.5）、基本请求与响应、多轮对话与无状态（每次发全量历史、合成的 assistant 消息、message threads 5 分钟过期）、预填充 Claude 响应（max_tokens 1 拿单选答案、4.6 后模型不支持）、视觉（base64 与 url 两来源、四媒体类型）、thinking 全模型支持矩阵（adaptive 与 legacy manual 的分界、budget_tokens 与 max_tokens 关系、interleaved 下预算可超上限）、工具使用与 tool_choice 四取值、input_examples 三限制、SSE 流式事件流五阶段与三种 delta 类型。

## 二、工具设计与 skill 体系（11 篇）

配套章节：GUIDE 第 10 章「设计工具：接口、返回与错误文案」。

- [为 AI agent 编写工具](writing-tools-for-agents.md)：工具是什么、怎么写、高效工具的原则。
- [进阶工具使用](advanced-tool-use.md)：Tool Search Tool 按需发现工具、程序化工具调用（programmatic tool calling）、成百上千工具下的 token 效率。
- [像 agent 一样看](seeing-like-an-agent.md)：Claude Code 团队从模型视角设计、测试与演进工具，三个工具迭代案例与三段式演进。
- [MCP 代码执行](code-execution-mcp.md)：用 MCP 把代码执行做成工具，让 agent 自己写代码处理数据。
- [Google 智能体白皮书：智能体工具与 MCP 互操作](google-agent-tools-mcp.md)：Google 五日课程第二本。MCP 协议机制、三大原语与集成模式、工具设计 Best Practices、企业级安全风险全景。
- [用 Agent Skills 把 agent 装备进真实世界](agent-skills.md)：skill 的解剖（SKILL.md、渐进披露）、开发与评估、发布为开放标准。
- [Claude Code 构建经验：我们如何使用 skills](claude-code-skills-lessons.md)：Anthropic 内部几百个 skills 的规模化运营：九类技能清单与九条制作要领。
- [改进 skill-creator](skill-creator-evals.md)：给 skill 写 evals、跑 benchmark、在模型演进中保持可用。
- [DeepSeek Tool Calls：从非思考模式到 strict 模式](ds-tool-calls.md)：DeepSeek 官方文档。非思考模式完整调用流、思考模式下工具调用从 V3.2 起支持、三种 API 格式对对话中间插入工具调用的支持差异、strict 模式 JSON Schema 八类型与 $ref/$def 模块化。
- [Claude 工具调用处理：tool_use 与 tool_result 的生命周期](claude-handle-tool-calls.md)：Anthropic 官方文档。tool_use 块三字段与分发、tool_result 编排三格式要求（紧跟、排第一、服务端工具未完成时只含结果块）、不可信内容留在 tool_result 内的注入防线、is_error 三类错误（执行错误写有指导性文案、无效调用 Claude 带修正重试 2-3 次、服务端工具无需处理）、strict: true 彻底消除无效调用。
- [Claude 工具使用故障排查](claude-troubleshooting-tool-use.md)：Anthropic 官方文档。七张症状到修复对照表：调用错误工具、编造参数、并行失效、缓存失效（tool_choice 与 effort 档位变动、工具加数组头部）、四类请求时错误（tool_use 无 tool_result、server_tool_use 无结果块、regex 特性不受支持、全部 defer_loading）、thinking 块被改动报 400、工具结果被标记为提示注入（自家指令不进 tool_result）、模型版本间 JSON 转义差异。

## 三、上下文工程（7 篇）

配套章节：GUIDE 第 11 章「管好上下文：窗口、压缩与外部记忆」。

- [面向 AI agent 的高效上下文工程](context-engineering.md)：上下文工程的定位与原则：少即是多、just-in-time 检索、注意力预算、长时运行的 compaction。
- [Claude 5 世代模型的上下文工程新规则](context-rules-claude5.md)：为更强的模型删掉 Claude Code system prompt 的 80% 以上，新世代模型的上下文规则。
- [Google 智能体白皮书：上下文工程之 session 与 memory](google-context-sessions-memory.md)：Google 五日课程第三本。session 存储细节、每轮四步循环、compaction 三策略、RAG vs Memory 九维对比、Memory 生成 ETL 四阶段与 provenance。
- [用消息线程加速长时运行 agent](claude-message-threads.md)：message threads 公开 Beta：对话只发一次、每轮只传新增、thread 字段三分法、缓存断点与 404 恢复。
- [上下文编辑：清除、保留与压缩](claude-context-editing.md)：Anthropic 官方文档。tool result clearing 与 thinking block clearing 服务端策略、clear_at_least 与缓存失效的权衡、SDK compaction 与 memory 工具的配合。
- [DeepSeek 上下文硬盘缓存与多轮对话](ds-kv-cache.md)：DeepSeek 官方文档。无状态 API 的对话历史拼接纪律、缓存前缀单元三种写入时机（请求结束位置、公共前缀检测、固定 token 间隔）、完整匹配才命中、Sliding Window Attention 的影响、prompt_cache_hit_tokens 与 miss 两个字段。
- [Claude 记忆工具：跨会话的文件式记忆](claude-memory-tool.md)：Anthropic 官方文档。/memories 目录的客户端运作方式（Claude 只请求、应用执行）、六命令全表（view/create/str_replace/insert/delete/rename 的返回值与错误处理）、路径遍历防护（../ 与 URL 编码变体）、自动注入的 MEMORY PROTOCOL、跨会话软件开发模式（初始化会话、读档续作、收尾更新）。

## 四、编排与多 agent（7 篇）

配套章节：GUIDE 第 6 章「组织并发：车队、资源池与预算准入」、第 20 章「向公开榜样学习：编排模式与系统设计」。

- [多 agent 系统：何时用与怎么用](multi-agent-when.md)：多 agent 的判定框架、为什么从单 agent 起步、以上下文为中心的分解、subagent 模式验证。
- [多 agent 协调模式：五种方法与各自的适用场景](multi-agent-coordination-patterns.md)：generator-verifier、orchestrator-subagent、agent teams、message bus、shared state 五种模式与选型演进。
- [我们如何构建多 agent 研究系统](multi-agent-research.md)：Anthropic Research 能力背后的多 agent 研究系统构建。
- [何时把 subagent 折回主 agent 循环](fold-subagents.md)：大型组织构建 agent 的失败模式、渐进披露的 agent 循环、折回判断与配套工具。
- [Claude Code 的动态工作流](harness-dynamic-workflows.md)：现场编写并协调多 agent harness，六个使用模式。
- [Codex subagents：并行子智能体工作流](codex-subagents.md)：OpenAI 官方文档。上下文污染与上下文腐化的定义、子智能体把嘈杂工作移出主线程、手动触发指令形态、读取密集型任务的并行起点、model 与 model_reasoning_effort 选型。
- [OpenAI 编排与交接：handoffs 与 agents-as-tools 的选型](openai-orchestration.md)：OpenAI 官方 Agents SDK 文档。两模式选型表（交接转移所有权、agents-as-tools 保留所有权）、handoffDescription 简短具体的纪律、仅当接口定义改变才添加专职智能体（过早分设产生更多 prompt、trace 与审批界面）。

## 五、harness 设计与工作法（9 篇）

配套章节：GUIDE 第 1 章「让 agent 真的跑起来：进程监督」、第 3 章「断了怎么接：检查点与重试」。

- [长时运行 agent 的高效 harness](harnesses-long-running.md)：环境管理、进入状态、失败形态与对策。
- [长时运行应用开发的 harness 设计](harness-design-apps.md)：Labs 团队的 harness 设计与 QA 反馈环。
- [Claude 的 harness 设计三模式](claude-harness-design-patterns.md)：用 model 已熟悉的东西、不断追问可以停止做什么、cache 命中五原则与 declarative tools 边界。
- [构建有效的 agent 自动化](claude-agent-automations.md)：无人值守定时自动化的运行纪律：六组件参考实现、书签续读、失败读取三规则、送达确认、只读 preferences、ledger 台账与 budget 上限。
- [Claude Code 最佳实践](claude-code-best-practices.md)：使用总纲：确定性与非确定性指令、引导会话、无人值守运行、可以不再做的事。
- [HTML 产物工作法](html-artifacts.md)：用 HTML 取代 Markdown 产出更丰富输出：五个使用场景与示例 prompt。
- [Harness 工程：在 agent 优先的世界用好 Codex](openai-harness-engineering.md)：OpenAI 工程博客。百万行代码零手写：AGENTS.md 由 agent 自写、Ralph Wiggum Loop、Chrome DevTools Protocol 接入、黄金原则与垃圾回收、自主性门槛。
- [Codex 的 AGENTS.md：给 agent 的持久指导](codex-agents-md.md)：OpenAI 官方文档（agents-md 指南与 customization 概念页合并）。指令链发现顺序（全局范围/项目范围/合并顺序近者覆盖远者）、AGENTS.override.md 覆盖机制、project_doc_max_bytes 32 KiB 上限与 project_doc_fallback_filenames 备用文件名、全局与分层项目指令的完整走查（Working agreements、payments 覆盖示例、目录树）、代码审查规则挂载、CODEX_HOME 自定义主目录、验证与排障五问、五层自定义总览（AGENTS.md/Memories/Skills/MCP/Subagents 分工）、AGENTS.md 更新时机的五个信号（反复错误加规则、阅读过多加路由指导、重复 PR 反馈编码成规则、@codex 云端委托、automations 周期检查）。
- [Codex 最佳实践：把编码 agent 当长期队友配置](codex-best-practices.md)：OpenAI 官方文档。提示词四件套（目标/上下文/约束/完成条件）、Plan mode、AGENTS.md 可复用指导、config.toml 配置层、测试与评审循环、MCP、技能、自动化、会话控制与常见错误。

## 六、评估与质量（7 篇）

配套章节：GUIDE 第 15 章「知道自己做得好不好：感知与评估」、第 17 章「评估器本身也要被评估：自改进系统的防护链」。

- [为 AI agent 解密评估](evals-demystified.md)：三类评分器、四类 agent 评估法、pass@k 与 pass^k、八步路线图。
- [自动化 eval 设计与 hillclimbing](claude-eval-design-hillclimb.md)：好 eval 四要素、adversarial sampling、build-eval 流程、过拟合三对策、客服降本与 skill 提分两实例。
- [Google 智能体白皮书：智能体质量](google-agent-quality.md)：Google 五日课程第四本。四支柱、Outside-In 评估层级、观察三支柱与 Agent Quality Flywheel。
- [Claude Code plugin evals：给插件跑评测](claude-plugin-evals.md)：plugin 级评测的实施方法：case 与 grader 文件布局、六类 grader、双臂 Δ 对比、mock MCP 与 CI 门禁。
- [定义成功标准并构建评估](claude-develop-tests.md)：Anthropic 官方文档。成功标准四性、定量指标与 A/B testing、评估设计三原则、六个带完整代码的示例评估（精确匹配、余弦相似度、ROUGE-L、Likert 量表、PHI 二分类、上下文利用序数量表）、代码/人工/LLM 三层评分与裁判技巧。
- [OpenAI 评估最佳实践](openai-eval-best-practices.md)：OpenAI 官方文档。三类评估、解读结果的小贴士与反面模式、评估流程五组成、摘要与文档问答两示例、四层架构各自的评估点（单轮/工作流/单智能体/多智能体）、评估器三类与 LLM 裁判的位置倾向与长度倾向、边缘情况三类。
- [OpenAI agent 工作流评测：追踪、评分器与数据集](openai-agent-evals.md)：OpenAI 官方文档（agent-evals 与 trace-grading 两页合并）。评测面选型决策路径（还在调试行为时先从追踪开始、需要可重复性时转向数据集与评估运行）、追踪捕获的四类端到端记录（模型调用、工具调用、护栏、handoff）、四个典型追踪评分问题、追踪评分与追踪评估的分工、Logs > Traces 与 Grade all 的操作步骤、transcript 与 trace 是同一载体两机构两个名字的对照、Evals 平台退役时间线（2026-10-31 转只读、2026-11-30 关闭）的环境事实。

## 七、安全与封锁（7 篇）

配套章节：GUIDE 第 14 章「放行之前：风险闸门与运行态一致性」、第 22 章「开源基因：把痕迹挡在发布之前」。

- [超越权限确认：让 Claude Code 更安全也更自主](claude-code-sandboxing.md)：沙箱化替代逐条权限确认的做法与上手路径。
- [我们如何跨产品封锁 Claude](contain-claude.md)：三类风险、三层防御、三种封锁模式与四起漏掉的风险。
- [给企业更多 AI agent 控制权，与 NVIDIA 一起](nvidia-agent-security.md)：brain 与 hands 分开、self-hosted sandboxes、OpenShell 默认拦截与 policy prover 数学证明。
- [Claude Code auto mode：用分类器替代逐条权限确认](claude-code-auto-mode.md)：两层防御与四类威胁、三层权限决策、transcript classifier 固定模板与三槽位、实测 FPR/FNR 与设计决策。
- [Codex 智能体审批与安全](codex-approvals-security.md)：OpenAI 官方文档。沙箱模式与审批策略两层控制、untrusted 策略退役迁移、network_proxy 网络策略与 DNS 重绑定保护、可写根目录受保护路径、auto_review 自动审批审查、OTel 遥测事件类别。
- [Codex 沙箱机制](codex-sandboxing.md)：OpenAI 官方文档。沙箱边界与审批分工、衍生命令继承边界、三类沙箱模式与两类审批策略、bubblewrap 与 AppArmor 前置、替我批准、可写根目录。
- [Claude API 数据保留：零数据保留与 HIPAA 就绪](claude-data-retention.md)：Anthropic 官方文档。ZDR 按组织开通与 CORS 拒绝、覆盖与不覆盖清单（Console、Managed Agents、消费者产品、Covered Models 四模型 30 天保留）、HIPAA 就绪的 BAA 与组织级强制、PHI 禁入 JSON schema（属性名、enum、const、pattern）、400 自动拦截、四张功能资格表三取值制与分组摘要、被标记内容最长保留 2 年。

## 八、生产化与基础设施（7 篇）

配套章节：GUIDE 第 20 章「向公开榜样学习：编排模式与系统设计」。

- [扩展 Managed Agents：大脑与双手解耦](managed-agents.md)：别养宠物、session 与上下文窗口的分界、多个大脑多双手。
- [agentic 接口面的演进](managed-agents-evolution.md)：Claude Managed Agents 三代构建模块：三原语（session、harness、sandbox）、vaults 凭据、context anxiety 案例。
- [Google 智能体白皮书：从原型到生产](google-prototype-production.md)：Google 五日课程第五本。评估关卡两实现、CI/CD 三阶段漏斗、Safe Rollout 四模式、Observe-Act-Evolve 运营循环、A2A 代码级实现。
- [高效 commerce agent 的解剖学](commerce-agents.md)：单 agent 与 Skills 生产架构、延迟与缓存、生产三部分（记忆、安全、evals）。
- [重设计 Anthropic 的源代码控制](scion-source-control.md)：agent 规模基础设施重设计：monorepo 成长的原则与 Scion 运作。
- [OpenAI Batch API：异步批处理](openai-batch-api.md)：OpenAI 官方文档。50% 折扣与专属速率池、jsonl 输入与 custom_id 纪律、七步流程（准备、上传、创建、查状态、取结果、取消、列表）、八种状态机、输出行序与输入不一致、过期与取消的结算语义。
- [OpenAI 速率限制](openai-rate-limits.md)：OpenAI 官方文档。六个限制指标（RPM、RPD、TPM、TPD、IPM、音频分钟数）任一触顶即触发、组织级与项目级定义、共享限制模型系列、六档使用层级表、十个响应头字段（Retry-After 与 x-ratelimit 系列）、带抖动的指数退避与三实现（Tenacity、backoff、手写装饰器）、减小 max_tokens、RPM 触顶但 TPM 有余量时合并请求。

## 九、模型行为与迁移（7 篇）

配套章节：GUIDE 第 2 章「听懂 agent 在说什么：输出解析」、第 16 章「自主循环的骨架：什么时候停」（stop_reason 的处理形态）。

- [给 Claude Sonnet 5.5 写提示词](sonnet-prompting.md)：effort 校准与 per-message effort 缓存保全、主动性与范围四段 system prompt、低 effort 真实检查、宽容工具调用、密集图表裁剪工具。
- [构建 Claude Sonnet 5.5](claude-sonnet-building.md)：Sonnet 与 Opus 选型分界、五项破坏性变更与 between_tools 限制、effort 重校准与缓存下限 512。
- [Claude Sonnet 5.5 新特性与迁移指南](claude-sonnet-migration.md)：双源合并。between_tools 与 disabled 的 400 对照、strict 工具上限 20、thinking block 绑定模型会话与账号、prefill 五种替代、按出发模型四代分组迁移清单。
- [找到你的未知：Claude Fable 实战指南](fable-unknowns.md)：未知四象限、三阶段九技术与示例 prompt。
- [DeepSeek 思考模式：开关、强度与多轮拼接](ds-thinking-mode.md)：DeepSeek 官方文档。思考模式开关与 effort 七档映射、temperature 等参数失效与 top_p 模型差异、reasoning_content 回传纪律（携带 tools 必须回传否则 400）、多轮拼接与流式累加、工具调用 run_turn 完整循环代码（每子轮 append 保留 reasoning_content、role:tool 回传结果、tool_calls is None 终止、跨 Turn 继续携带）。
- [DeepSeek JSON Output：严格 JSON 输出](ds-json-output.md)：DeepSeek 官方文档。response_format 设 json_object、prompt 必须含 json 字样并给样例、max_tokens 防截断、无法识别时非 JSON 内容被替换为空格而 finish_reason 仍为 stop 的兜底。
- [DeepSeek Responses API：兼容性明细](ds-responses-api.md)：DeepSeek 官方文档。为 Codex 兼容而实现的 Responses API 格式：顶层参数全表（27 项支持/部分支持/忽略/不支持四档）、输入 item 归并规则（function_call 归并到相邻 assistant 消息）、custom 仅限 apply_patch、web_search 服务端执行仅 v4-pro、server_tool_use 用量计数语义、不支持参数静默忽略不报错。
