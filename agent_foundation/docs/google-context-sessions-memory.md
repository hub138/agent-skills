# Google 智能体白皮书：上下文工程：会话与记忆（Context Engineering: Sessions, Memory）

- 原文：[Context Engineering: Sessions, Memory](https://www.kaggle.com/whitepaper-context-engineering-sessions-and-memory)
- 来源：Google 五日 AI Agent 强化课程白皮书之三（kaggle.com），作者 Kimberly Milam、Antonio Gulli
- 发布：2025-11
- 译文说明：全文翻译，术语保留英文原词；图表以文字说明代替；代码为原文 Snippet 逐行忠实保留。与 [面向 AI agent 的高效上下文工程](context-engineering.md)（Anthropic）互补：该篇讲原则（少即是多、just-in-time 检索、注意力预算），本篇讲实现：session 存储细节、Memory 生成全生命周期（ETL 四阶段、provenance、检索时机）、RAG vs Memory 九维对比与 procedural memory。Gemini、ADK、Agent Engine、Vertex AI 等 Google 产品名保留原名，作为机制示例对待。

## 引言：什么是 Context Engineering

LLM 本质上是无状态的：在单次 API 调用的 context window 之外，它对世界没有任何感知。要让它在多轮对话中保持连续，每一轮都必须为它重新构造完整的上下文。Context Engineering（上下文工程）就是这门学科：为每一次 LLM 调用动态组装并管理信息，让模型在生成响应的瞬间拥有恰好需要的知识。

这项学科从 Prompt Engineering（提示词工程）演进而来。prompt 工程优化的是静态的系统指令；context 工程处理的是发给模型的整个载荷：按用户、按历史、按外部数据动态构造一份有状态的 prompt，策略性地选择、总结并注入信息，让相关性最大化、噪声最小化。在今天的 agent 系统里，RAG 数据库、session 存储、memory manager 管理着大部分上下文，agent 框架负责编排这些系统，组装出最终发给 LLM 的 prompt。

法语厨房里有个术语 mise en place，意为「一切就位」：厨师在开火之前，先把食材洗净切好、把专用工具与摆盘备齐，并真正理解每样东西的用途。只递给厨师一份菜谱，只能换来一顿还行的晚餐；备齐优质食材与合手工具、理解到位的厨师，才能稳定产出好菜。Context Engineering 的目标与此一致：让模型拥有不多不少、最相关的信息。

## 上下文的三类组件

发给 LLM 的上下文由三类组件构成：

第一类，Context to guide reasoning（引导推理的上下文）：System Instructions 定义 persona、能力与约束；Tool Definitions 告诉模型可用的 API 或函数 schema；Few-Shot Examples 引导 in-context learning，示例给出输入与期望行为。

第二类，Evidential & Factual Data（作为证据的事实数据）：Long-Term Memory 是跨 session 的持久知识；External Knowledge 经 RAG 从外部来源检索；Tool Outputs 是工具执行的返回结果；Sub-Agent Outputs 是其他 agent 的产出；Artifacts 是文件、图像等非文本材料。

第三类，Immediate conversational information（即时对话信息）：Conversation History 是逐轮对话记录；State/Scratchpad 是临时的进行中信息，例如购物车当前内容；User's Prompt 是本轮用户输入。

记忆并非静态：它需要选择性的检索与更新。few-shot 示例与当前任务相关时效果优于硬编码示例。还要警惕 context rot（上下文腐化）现象：随着上下文增长，模型的注意力会衰减。compaction（压缩）技术通过总结与选择性修剪，在保住关键信息的同时管理 token 总量。

## 每轮对话的四步循环

agent 框架在每一轮对话里执行四个步骤：

1. Fetch Context（取上下文）：检索记忆、RAG 文档、近期事件。按用户查询与元数据识别该检索什么。
2. Prepare Context（备上下文）：框架动态构造完整 prompt。这一步可能成为热路径上的阻塞点。
3. Invoke LLM and Tools（调用 LLM 与工具）：迭代调用直到产出最终响应；工具调用与 model 输出会追加进上下文。
4. Upload Context（回写上下文）：本轮收集到的新信息上传到持久存储；记忆巩固等后处理作为后台过程异步执行。

## Sessions

session 封装单次连续对话的即时对话历史与工作记忆。它绑定特定用户、自包含、有完整记录；一个用户可以有多个 session，各自独立、断连、留存日志。

session 有两个关键组件：events（按时间序排列的完整历史）与 state（结构化的工作记忆，即 scratchpad）。事件类型包括 user input（文本、音频、图像）、agent response、tool call、tool output。随对话推进，事件不断追加，state 按业务逻辑更新。这个结构类似 Gemini API 的 Content 对象列表：每个对象有 role（谁在说：user 或 model）与 parts（实际内容：文本、图像、工具调用）。

```python
contents = [
    {
        "role": "user",
        "parts": [ {"text": "What is the capital of France?"} ]
    }, {
        "role": "model",
        "parts": [ {"text": "The capital of France is Paris."} ]
    }
]
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=contents
)
```

生产 agent 的执行环境通常是无状态的：一次请求完成后不保留任何信息，因此对话历史必须存进持久存储才能维持连续体验。开发阶段用内存存储即可，生产应用应使用健壮的数据库，例如托管的 Agent Engine Sessions。

### 框架差异

agent 框架充当开发者代码与 LLM 之间的通用翻译器：开发者始终面对框架一致的内部数据结构，框架负责转换成具体 LLM 要求的精确格式。这层抽象把 agent 逻辑与具体 LLM 解耦，避免厂商锁定。

ADK 使用显式的 Session 对象，内含 Event 列表与独立的 state 对象，像文件柜里两个文件夹：一个放对话历史（events），一个放工作记忆（state）。

LangGraph 没有正式的 session 对象，state 即 session：这个全包的 state 对象既装对话历史（Message 列表）也装全部工作数据。与传统 session 的只追加日志不同，LangGraph 的 state 可变、可转换，history compaction 等策略可以直接改写记录，适合管理长对话与 token 限制。

### 多 agent 系统的两种历史模式

先区分两个概念：session history 是永久、完整、未删节的对话记录；context 是单轮发给 LLM 的精心构造的载荷，可以只选取相关摘录、加上引导性的前言。多 agent 架构关心的是信息如何在 agent 之间传递。

第一种模式，shared unified history（共享统一历史）：全部 agent 读写同一份日志，每条消息、每次 tool call、每个观察按时间序追加进中央记录。适合紧耦合的协作任务，需要单一事实源，例如多步问题解决中一个 agent 的输出就是下一个 agent 的输入。共享历史下，sub-agent 也可以先处理日志再传给 LLM：过滤出相关事件的子集，或加标签标明每个事件的产生者。ADK 的 LLM-driven delegation 把 sub-agent 的全部中间事件写进 root agent 的同一个 session；sub-agent 还可用 output_key 把最终响应存进指定的 state 键。

```python
from google.adk.agents import LlmAgent
# The sub-agent has access to Session and writes events to it.
sub_agent_1 = LlmAgent(...)
# Optionally, the sub-agent can save the final response text (or structured
# output) to the specified state key.
sub_agent_2 = LlmAgent(
  ...,
  output_key="..."
)

# Parent agent.
root_agent = LlmAgent(
  ...,
  sub_agents=[sub_agent_1, sub_agent_2]
)
```

第二种模式，separate individual histories（分离独立历史）：每个 agent 维护私有历史，对其他 agent 是黑箱——中间思考、工具使用、推理步骤都留在私有日志里，别的 agent 看不见。通信只经显式消息发生：agent 分享最终输出，不分享过程。实现方式通常是 Agent-as-a-Tool（把另一个 agent 当标准工具调用，传入输入、取回自包含的输出）或 A2A Protocol（用结构化协议直接通信）。

### 跨框架互操作

框架使用内部数据表示带来一个关键的架构权衡：把 agent 与 LLM 解耦的那层抽象，也把它与其他框架的 agent 隔离了。这种隔离在持久层被固化：session 的存储模型把数据库 schema 直接耦合到框架内部对象，形成僵硬、难以移植的对话记录。LangGraph 构建的 agent 无法原生解读 ADK agent 持久化的 Session 与 Event 对象，无缝任务交接因此不可能。

A2A 通信是协调这些孤立 agent 的一种模式：它能交换消息，但解决不了共享丰富有状态上下文的核心问题——每个 agent 的对话历史都编码在自家框架的内部 schema 里，任何包含 session 事件的 A2A 消息都需要翻译层才能使用。

更稳的模式是把共享知识抽象进框架中立的数据层，例如 Memory。session 存储保存原始的、框架专属的对象（Events 与 Messages）；memory 层存处理过的规范化信息：摘要、提取的实体、事实，通常以字符串或字典形式存储，数据结构不耦合任何框架的内部表示。这让它成为通用的公共数据层：异构 agent 无需定制翻译器，靠共享同一份认知资源实现真正的协作智能。

### session 的生产考量

安全与隐私：严格隔离是最关键的原则。session 属于单一用户，系统必须用 ACL 强制保证一个用户永远无法访问另一个用户的 session 数据；对 session 存储的每次请求都要完成所有者的认证与授权。PII 应在写入存储前 redact（脱敏），这是基本安全措施，能大幅缩小数据泄露的 blast radius（波及范围）；配合 Model Armor 等工具，也能简化 GDPR、CCPA 合规，建立用户信任。

数据完整性与生命周期：session 不该永生。TTL 策略自动删除不活跃的 session，控制存储成本；保留政策要明确；操作按确定性顺序追加，保证时间序完整。

性能与扩展：session 数据处在每次交互的热路径上，读写必须极快。agent 运行时无状态，每轮开始要从中央数据库取全部历史，这带来网络传输延迟；关键是减小传输数据量，例如在发送给 agent 前过滤或压缩 session history，移除旧的、不再需要的函数调用输出。

## 长对话管理与 compaction

长对话给 agent 带来四项约束：

1. Context Window Limits：超出上限，API 调用直接失败。
2. API Costs：按 token 计费，历史越长 token 越多，成本越高。
3. Latency：文本越多处理越慢；compaction 能保持快速响应的体验。
4. Quality：token 增多，噪声与自回归错误累积，响应质量可能变差。

行李箱是个贴切的比喻：行李箱是有限的 context window，衣物是对话信息。硬塞太多，箱子太重、东西太乱，找不到需要的物品，就像过载的上下文带来高成本与慢响应；装得太少，可能漏带护照或外套，毁了整个行程，就像丢失关键上下文后答非所问。成功的关键在于带多少，在于只带需要的。

compaction 有三种基本策略：

- Keep the last N turns：最简单的滑动窗口，丢弃更早的轮次。
- Token-Based Truncation：从最近的消息往回数 token，在不超预算（例如 4000 token）的前提下尽量多包含，更早的内容直接截断。
- Recursive Summarization：把较旧的部分替换为 AI 生成的摘要；随对话增长，周期性地用一次额外的 LLM 调用总结最旧的消息，摘要作为压缩历史的前缀，接上更近的逐字消息。

ADK 提供内建的插件来限制发给模型的内容，只保留最近 N 轮，且不改动 session 存储里的历史事件：

```python
from google.adk.apps import App
from google.adk.plugins.context_filter_plugin import ContextFilterPlugin
app = App(
    name='hello_world_app',
    root_agent=agent,
    plugins=[
        # Keep the last 10 turns and the most recent user query.
        ContextFilterPlugin(num_invocations_to_keep=10),
    ],
)
```

既然精巧的 compaction 策略目标是降成本降延迟，昂贵操作（如递归总结）就必须异步在后台执行并持久化结果。「后台」保证 client 不必等待；「持久化」保证昂贵计算不被重复执行。通常由 agent 的 memory manager 负责生成并持久化这些递归摘要。agent 还必须记录哪些事件已进压缩摘要，防止原始的冗长事件再被发给 LLM。

触发 compaction 的时机分三类：

- Count-Based Triggers（数量触发）：token 量或轮数超过预设阈值就压缩。管理上下文长度时这种方式往往已经够用。
- Time-Based Triggers（时间触发）：不看对话体量，看活跃度。用户停止交互一段时间（例如 15 或 30 分钟）后，系统在后台运行压缩任务。
- Event-Based Triggers（事件触发）：agent 判定某个任务、子目标或话题已经结束，主动触发压缩。

ADK 的 EventsCompactionConfig 可在配置的轮数后触发基于 LLM 的总结：

```python
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
app = App(
    name='hello_world_app',
    root_agent=agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=5,
        overlap_size=1,
    ),
)
```

session compaction 本身就是记忆生成的一个实例：从冗长嘈杂的逐字记录里蒸馏出关键事实与摘要，丢弃对话填充物。下一节把记忆的创建、存储与检索讲完整。

## Memory

Memory 与 Sessions 深度共生：session 是生成记忆的主要数据源，记忆是控制 session 体量的关键策略。memory 是从对话或数据源提取的有意义信息的快照，是保留重要上下文的浓缩表示，跨 session 持久存在，为用户提供连续、个性化的体验。memory manager 作为专门解耦的服务，是多 agent 互操作的基础：它常用框架中立的数据结构（字符串与字典），让不同框架的 agent 连接同一个 memory store，形成共享知识库。部分框架把 Session 或逐字对话称作 short-term memory（短期记忆）；本白皮书定义的 memories 是提取出来的信息，不是原始对话。

### 记忆解锁的四大能力

1. Personalization（个性化）：记住用户的喜好、事实与历史，定制响应，例如用户最喜欢的球队或机上座位习惯。
2. Context Window Management（上下文体量管理）：长对话的完整历史会超出上限；记忆系统经摘要与关键事实压缩，无需每轮发送几千 token，降低成本与延迟。
3. Data Mining and Insight（数据挖掘与洞察）：聚合且保护隐私地分析多用户的记忆，提取洞察。例如零售 chatbot 发现许多用户在问同一款产品的退货政策，标记出潜在问题。
4. Agent Self-Improvement and Adaptation（自我改进与适应）：从之前的运行创建关于自身表现的 procedural memories，记录哪些策略、工具与推理路径导向成功，构建有效的 playbook，随时间适应改进。

### 记忆系统的五组件分工

1. The User：提供原始源数据，有的系统经表单直接收集。
2. The Agent：开发者用逻辑配置记什么、何时记，编排对 memory manager 的调用。简单架构总是检索、总是触发生成；高级架构用 memory-as-a-tool 让 agent 自己决定。
3. The Agent Framework（如 ADK、LangGraph）：提供结构与管道，定义开发者逻辑如何访问历史、如何与 memory manager 交互；它本身不管长期存储，并定义检索到的记忆如何进 context window。
4. The Session Storage（如 Agent Engine Sessions、Spanner、Redis）：存储逐字对话；原始对话将被摄取进 memory manager 生成记忆。
5. The Memory Manager（如 Agent Engine Memory Bank、Mem0、Zep）：处理存储、检索、压缩的专门服务，四项职责：Extraction（从源数据蒸馏关键信息）、Consolidation（策展记忆、合并重复实体）、Storage（持久化）、Retrieval（取相关记忆供新交互使用）。

memory manager 是主动系统，绝非被动的向量数据库。它可以用相似性搜索检索，但核心价值在于随时间智能地提取、巩固、策展记忆；托管服务把记忆的生成与存储全生命周期自动化。

### RAG 与 Memory 的对比

| 维度 | RAG | Memory |
| --- | --- | --- |
| Primary Goal（首要目标） | 注入外部事实知识 | 创建个性化、有状态的体验：记住事实、适应用户、维持长期上下文 |
| Data source（数据来源） | 静态、预索引的外部知识库：PDF、wiki、文档、API | 用户与 agent 之间的对话 |
| Isolation Level（隔离级别） | 一般共享、全局只读，所有用户可访问，保证一致的事实答案 | 高度隔离，几乎总按用户划分范围，防泄露 |
| Information type（信息类型） | 静态事实：权威领域数据、产品细节、技术文档 | 动态且一般用户特定，源自对话，有内在不确定性 |
| Write patterns（写入模式） | 批处理、离线、由管理动作触发 | 事件驱动：按节奏每轮、session 结束或 memory-as-a-tool |
| Read patterns（读取模式） | 几乎总是 as-a-tool，查询需要外部信息时 | 两种：memory-as-a-tool 需要用户信息时 + static retrieval 每轮开始总检索 |
| Data Format（数据格式） | 自然语言 chunk | 自然语言片段或结构化 profile |
| Data preparation（数据准备） | chunking 与 indexing：文档切块、转 embedding、存储 | extraction 与 consolidation：从对话提取关键细节，确保不重复、不矛盾 |

用比喻讲：RAG 像研究图书管理员，在公共图书馆的百科全书、教科书与官方文档里查既定事实——产品技术规格、历史日期；这是静态、共享、权威的知识库，给出一致的事实答案；管理员精通世界事实，但不认识提问的用户。memory 像私人助理，跟着 agent 带着私人笔记本，记录与特定用户的每次交互；它动态、高度隔离，装着个人喜好、过往对话与演进的目标；需要回想用户最喜欢的球队或上周项目讨论的上下文时找助理，它的专长不在全局事实，而在用户本人。真正智能的 agent 两者都要：RAG 给它关于世界的专家知识，memory 给它关于服务对象的专家理解。

## 记忆的解剖

一条记忆遵循一条规则：memories are descriptive not predictive（记忆是描述性的，不做预测）。单条记忆是原子化的上下文单元，由 memory manager 返回给 agent 使用。它由两部分构成：

- content（内容）：从源数据提取的实质。框架中立的简单数据结构，任何 agent 都能摄取。可以是结构化的字典或 JSON，例如 `{"seat_preference": "Window"}`，schema 由开发者定义；也可以是非结构化的自然语言，例如 The user prefers a window seat。
- metadata（元数据）：给记忆提供上下文，例如唯一标识、所有者标识、内容或数据源的标签。

### 信息类型

记忆的信息类型源自认知科学的二分。declarative memory（陈述性记忆）是「知道什么」：事实、数字、事件，可明确陈述；它涵盖 Semantic memory（一般世界知识）与 Entity/Episodic memory（特定用户的事实）。procedural memory（程序性记忆）是「知道怎么做」：技能与工作流，引导行动，例如订行程的正确工具调用序列。

### 组织模式的三种图案

- Collections（集合）：单用户拥有多条自包含的自然语言记忆，每条是一次独立的观察或事件总结；单主题可以有多条记忆。适合存储与检索更大、较少结构化的信息池。
- Structured User Profile（结构化用户档案）：像一张持续更新的联系人卡，聚合核心事实，支持快速查找姓名、喜好、账户详情。
- Rolling Summary（滚动总结）：把全部信息合并进单一不断演进的记忆，是整个用户与 agent 关系的自然语言总结，由 manager 持续更新这份主文档。常用于压缩长 session，保住关键信息、管住 token。

### 存储架构

向量数据库最常见：按语义相似而非精确关键词检索，记忆转成 embedding 向量后找概念上最近的匹配，擅长非结构化的自然语言记忆（atomic facts）。knowledge graph 把记忆存为实体节点与关系边的网络，检索经遍历图找直接与间接连接，擅长结构化的关系查询（knowledge triples）。混合方案用向量 embedding 充实图的实体，同时支持关系搜索与语义搜索，两全其美。

### 创建机制

explicit memory（显式创建）：用户直接下命令，例如「记住我的纪念日是 10 月 26 日」。implicit memory（隐式创建）：从对话推断提取，没有直接命令，例如「我的纪念日是下周，帮我找礼物」。internal memory（框架内建）：记忆管理内建于框架，方便起步，但缺高级功能。external memory（外部服务）：专门服务如 Agent Engine Memory Bank、Mem0、Zep，框架经 API 调用完成存储与检索，提供语义搜索、实体抽取、自动总结等高级功能。

### 范围三级

- User-Level（用户级）：最常见，绑定 user ID，跨该用户全部 session 持久，例如用户喜欢中间座位。
- Session-Level（session 级）：为压缩长对话而设计，是从单一 session 提取的洞察的持久记录，例如「用户在找 11 月 7 日到 14 日纽约到巴黎的机票，要直飞与中间座位」。它用简洁的关键事实集替换冗长、token 消耗大的逐字稿；与原始 session 日志不同，它只含处理过的洞察，不含对话本身，上下文隔离于该 session。
- Application-Level（应用级）：全局，所有用户可访问，例如代号 XYZ 指某个项目。它提供共享上下文、广播系统信息、建立常识基线；常见用途是 procedural memories——给 agent 的操作指引。关键是对全部敏感内容脱敏，防止用户之间泄露。

### 多模态

区分记忆的来源与存储内容。Memory from a multimodal source（多模态来源的记忆）最常见：处理语音备忘录时，不存音频文件，而是转写后建文本记忆，例如用户对近期发货延迟表达不满。Memory with Multimodal Content（多模态内容的记忆）更高级：直接存非文本媒体，例如用户传图说「记住这个 logo 设计」，记忆里直接含图像文件。当代 manager 聚焦多模态来源产文本内容，因为非结构化二进制的生成与检索需要专门的模型、算法与基础设施，把全部输入转成公共可搜索的文本格式要简单得多。

## Memory Generation：四阶段 ETL

记忆生成可理解为 LLM 驱动的 ETL（Extract、Transform、Load）管道。这条管道是 memory manager 区别于 RAG 引擎与传统数据库的核心：它不要求开发者手动指定数据库操作，而用 LLM 智能决定何时增加、更新、合并记忆；管理数据库内容、串联 LLM 调用、部署后台数据服务的复杂性全部被抽象掉。

1. Ingestion（摄取）：client 向 memory manager 提供原始数据源，通常是对话历史。
2. Extraction & Filtering（提取与过滤）：用 LLM 从源数据提取有意义的内容。关键在于并非什么都提取：只捕获符合预定义 topic definition 的信息；摄取的数据里没有匹配主题的内容，就不建记忆。
3. Consolidation（巩固）：最复杂的一阶段，处理冲突消解与去重。它执行一次「自编辑」过程：用 LLM 对比新提取的信息与既有记忆，为保持用户知识库连贯、准确、随新信息演进，可以决定把新洞察合并进既有记忆、删除已失效的记忆、或在全新主题上新建记忆。
4. Storage（存储）：新的或更新后的记忆持久化到向量数据库或 knowledge graph，供未来检索。

托管 memory manager（如 Agent Engine Memory Bank）把这条管道全自动：开发者一个 API 调用即可触发。

```python
from google.cloud import vertexai
client = vertexai.Client(project=..., location=...)
client.agent_engines.memories.generate(
    name="projects/.../locations/...reasoningEngines/...",
    scope={"user_id": "123"},
    direct_contents_source={
        "events": [...]
    },
    config={
        # Run memory generation in the background.
        "wait_for_completion": False
    }
)
```

数据源支持多种 Part 形态：from_text 传文本，from_bytes 传字节与 MIME 类型，from_uri 传文件地址。

用园丁作比：Extraction 像收到新种子与幼苗；园丁不乱撒，而是做 Consolidation——拔掉杂草（删除冗余与冲突数据）、修剪过密枝条提升既有植物的健康（精炼总结既有记忆）、把新苗栽到最佳位置（合并或新建）。持续用心的策展保证花园健康、有序、持续繁荣，而非长成不可用的荒草。这一切异步在后台进行，保证下次来访时花园总是就绪。

### Extraction 深入

Extraction 回答一个根本问题：这段对话里，什么信息有意义到值得成为记忆。它并非简单总结，而是定向的智能过滤：从噪声、寒暄、填充文本中分离出信号——重要事实、喜好、目标。「有意义」并非通用概念，完全由 agent 的用途定义：客服 agent 要记订单号与技术问题，健康教练要记长期目标与情绪状态，两者根本不同。定制保留什么信息，是构建真正有效 agent 的关键。

manager 的 LLM 按精心构造的程序化 guardrails 与指令工作，通常嵌在复杂的 system prompt 里。三种方法：

- schema 与模板提取：给预定义的 JSON schema 或模板，用 structured output 让 LLM 从对话构造 JSON。
- 自然语言 topic 定义：用简单描述引导提取方向。
- few-shot prompting：给输入文本与理想高保真记忆的示例，让 LLM 学习提取模式，适合难以用 schema 描述的自定义或细微主题。

多数 manager 开箱即找常见主题（用户喜好、关键事实、目标）；多数平台也允许开发者定义自定义主题。Agent Engine Memory Bank 的 customization_configs 是完整示例：memory_topics 数组同时放 managed_memory_topic（内置主题 USER_PERSONAL_INFO）与 custom_memory_topic（自定义主题 business_feedback，描述咖啡店体验的具体用户反馈：饮品、食物、糕点、环境、员工友好度、服务速度、清洁度与改进建议），generate_memories_examples 给出对话与理想生成记忆的 few-shot 示例：

```python
from google.genai.types import Content, Part
memory_bank_config = {
  "customization_configs": [{
    "memory_topics": [
        { "managed_memory_topic": {"managed_topic_enum": "USER_PERSONAL_INFO" }},
        {
    "custom_memory_topic": {
            "label": "business_feedback",
            "description": """Specific user feedback about their experience at the coffee
shop. This includes opinions on drinks, food, pastries, ambiance, staff friendliness,
service speed, cleanliness, and any suggestions for improvement."""
            }
        }
      ],
    "generate_memories_examples": {
      "conversationSource": {
        "events": [
          {
            "content": Content(
                    role="model",
                    parts=[Part(text="Welcome back to The Daily Grind! We'd love to hear
your feedback on your visit.")])
      },{
            "content": Content(
                    role="user",
                    parts=[Part(text= "Hey. The drip coffee was a bit lukewarm today, which
was a bummer. Also, the music was way too loud, I could barely hear my friend.")])
          }]
      },
      "generatedMemories": [
        {"fact": "The user reported that the drip coffee was lukewarm."},
        {"fact": "The user felt the music in the shop was too loud."}
      ]
  }
  }]
}
agent_engine = client.agent_engines.create(
    config={
        "context_spec": {"memory_bank_config": memory_bank_config }
    }
)
```

记忆提取本身虽非「总结」，算法却可借助总结来蒸馏信息。许多 memory manager 为提升效率，把对话的滚动总结直接嵌入提取 prompt：压缩后的历史提供了从最近交互提取关键信息所需的上下文，省去每轮重复处理完整冗长对话的开销。

### Consolidation 深入

Consolidation 把新信息集成进连贯、准确、演进的知识库，可以说是记忆生命周期里最复杂的一阶段：它把简单的事实集合变成对用户的策展理解。没有它，agent 记忆会迅速退化为吵闹、矛盾、不可靠的历次捕获日志。这层自策展由 LLM 完成，正是 memory manager 超越简单数据库之处。

它解决对话数据的四个根本问题：

1. Information Duplication（信息重复）：用户跨对话以多种方式提及同一事实——「我需要去 NYC 的航班」与「我在计划去纽约的旅行」；简单提取会建两条冗余记忆。
2. Conflicting Information（信息冲突）：用户状态随时间变化，否则记忆里会积累矛盾事实。
3. Information Evolution（信息演进）：简单事实变得更细腻——「用户对营销感兴趣」演进为「用户在领导聚焦 Q4 客户获取的营销项目」。
4. Memory Relevance Decay（相关性衰退）：记忆不会永远有用，须主动遗忘，剪除陈旧、低信心的记忆，保持知识库相关且高效。遗忘可经 LLM 在整合时倾向新信息，或 TTL 自动删除。

过程：工作流先检索与新提取记忆相似的既有记忆作为整合候选；被新信息矛盾或充实的候选，或删除或更新。LLM 同时看到既有记忆与新信息，分析该执行什么操作。三个主操作：

- UPDATE：用新信息或修正修改既有记忆。
- CREATE：新洞察全新且与既有无关，新建记忆。
- DELETE/INVALIDATE：新信息使旧记忆完全无关或错误，删除或标记失效。

manager 把 LLM 的决策翻译成对记忆存储的事务性更新。

## Memory Provenance

garbage in, garbage out 这条公理对 LLM 更为关键：结果常是 garbage in, confident garbage out。agent 要做可靠决策、manager 要有效整合记忆，前提是能批判性评估自己记忆的质量。可信度直接来自 provenance（来源与历史的详细记录）。

整合过程把多来源信息合并进单一演进的记忆，血缘追踪因此成为需要：单条记忆可能是多个数据源的混合；单一来源也可能分出多条记忆。评估可信度须为每个来源追踪关键细节，例如来源类型与新鲜度（age）。两个用途：决定整合时各来源的权重；告知推理时该多依赖这条记忆。

source type 分三类：

- Bootstrapped Data（预载数据）：从内部系统（如 CRM）预载的高信任数据。可用来初始化用户记忆，解决冷启动问题——给从未交互过的用户提供个性化体验的挑战。
- User Input（用户输入）：显式提供（如经表单）的信任度高；从对话隐式提取的信任度一般较低。
- Tool Output（工具输出）：外部工具调用返回的数据。一般不建议用它生成记忆：脆弱且容易过期，更适合短期缓存。

血缘管理有两个操作挑战。其一，冲突消解：不同来源的记忆矛盾时，用信任层级策略，常见做法是优先最信任的来源、倾向最新信息、寻找多个数据点佐证。其二，删除派生数据：用户撤销对某数据源的访问时，源自它的派生数据也应删除；删除被它碰过的每条记忆过于激进，更精确但计算代价高的方法是用剩余有效来源从头重生成受影响的记忆。

confidence（信心）必须演进：经 corroboration（多源佐证）增强——多个可信来源提供一致信息时信心上升；随时间衰减——旧记忆变得陈旧；矛盾信息引入时下降。最终系统应能遗忘：归档或删除低信心记忆。

主动策展经 memory pruning（记忆剪枝）识别并遗忘不再有用的记忆，三个触发：Time-based Decay（时间衰退）——两年前的会议记忆大概率不如上周的相关；Low Confidence（低信心）——由弱推断创建且从未被其他来源佐证；Irrelevance（无关）——agent 对用户的理解更精深后，判定旧的琐碎记忆与当前目标无关。反应式的整合管道加上主动剪枝，知识库才会是策展、准确、相关的用户理解，而非一切说过的话的增长日志。

信任度在推理时同样要考虑：对记忆的信心并非静态，须随新信息与时间演进。信心分若与记忆一同注入 prompt 而非展示给用户，LLM 就能评估信息可靠性，做出更细腻的决策。整个信任框架服务于 agent 的内部推理：记忆与信心分通常不直接给用户看，而是注入 system prompt，让 LLM 权衡证据、考虑可靠性，给出更细腻可信的回答。

## 触发记忆生成的四个时机

manager 自动化提取与整合，但系统仍须决定何时尝试生成。这是关键架构选择，平衡数据新鲜度与计算成本、延迟。四个时机：

- Session Completion：多轮 session 结束时。
- Turn Cadence：特定轮数之后，例如每 5 轮。
- Real-Time：每轮之后。
- Explicit Command：用户直接命令，例如「记住这个」。

选择是 cost（成本）与 fidelity（保真度）的直接权衡：高频触发（实时）保证记忆高度细致、新鲜，捕获每个细微差别，但 LLM 与数据库成本最高，处理不当还会引入延迟；低频触发（session 结束）省钱，但 LLM 要一次总结大块对话，保真度下降。还要防止 manager 重复处理相同的事件，否则产生不必要的成本。

## Memory-as-a-Tool

更高级的方式是把记忆生成的决定权交给 agent 自己：生成能力暴露为工具（例如 create_memory），工具定义写清什么类型的信息算有意义；agent 分析对话，自主决定何时调用这个工具、识别值得持久化的信息。这把「识别有意义信息」的责任从外部 manager 转移给 agent 及其开发者。

ADK 的两种实现。第一种，触发式：工具内部调用记忆服务，由 Memory Bank 从对话提取并整合。

```python
from google.adk.agents import LlmAgent
from google.adk.memory import VertexAiMemoryBankService
from google.adk.runners import Runner
from google.adk.tools import ToolContext
def generate_memories(tool_context: ToolContext):
   """Triggers memory generation to remember the session."""
   # Option 1: Extract memories from the complete conversation history using the
   # ADK memory service.
   tool_context._invocation_context.memory_service.add_session_to_memory(
       session)
   # Option 2: Extract memories from the last conversation turn.
   client.agent_engines.memories.generate(
       name="projects/.../locations/...reasoningEngines/...",
       direct_contents_source={
           "events": [
              {"content": tool_context._invocation_context.user_content}
           ]
       },
       scope={
           "user_id": tool_context._invocation_context.user_id,
           "app_name": tool_context._invocation_context.app_name
       },
       # Generate memories in the background
       config={"wait_for_completion": False}
   )
   return {"status": "success"}
agent = LlmAgent(
    ...,
    tools=[generate_memories]
)
runner = Runner(
    agent=agent,
    app_name=APP_NAME,
    session_service=session_service,
    memory_service=VertexAiMemoryBankService(
      agent_engine_id=AGENT_ENGINE_ID,
      project=PROJECT,
      location=LOCATION
    )
)
```

第二种，agent 自提取：agent 主动决定从对话里记什么，提取完成后送 Memory Bank 只做与既有记忆的 consolidation。

```python
def extract_memories(query: str, tool_context: ToolContext):
   """Triggers memory generation to remember information.
   Args:
     query: Meaningful information that should be persisted about the user.
   """
   client.agent_engines.memories.generate(
       name="projects/.../locations/...reasoningEngines/...",
       # The meaningful information is already extracted from the conversation, so we
       # just want to consolidate it with existing memories for the same user.
       direct_memories_source={
           "direct_memories": [{"fact": query}]
       },
       scope={
           "user_id": tool_context._invocation_context.user_id,
           "app_name": tool_context._invocation_context.app_name
       },
       config={"wait_for_completion": False}
   )
   return {"status": "success"}
agent = LlmAgent(
    ...,
    tools=[extract_memories]
)
```

## Background 与 Blocking

记忆生成是昂贵操作：需要 LLM 调用与数据库写入。生产 agent 的记忆生成几乎总应作为异步后台过程处理：agent 给用户发出响应之后，生成管道可以并行运行，不阻塞用户体验。这种解耦对保持快速响应的体验必不可少——阻塞式让用户等记忆写完才收到响应，是不可接受的慢与挫败。这要求记忆生成发生在架构上独立于 agent 核心运行时的服务里。

## Memory Retrieval

检索策略对 agent 性能至关重要：无关记忆会困惑 model、降低响应质量；找到恰到好处的上下文片段，能带来显著更聪明的交互。核心挑战是在严格的延迟预算内平衡记忆的有用性。

组织方式决定检索方式：structured user profile 典型做法是直接 lookup，查全量 profile 或特定属性；collections 则是复杂搜索问题，要从大池的非结构化或半结构化数据里发现最相关的信息。

高级系统在多维度给候选记忆打分：Relevance（相关性，语义上与当前对话的概念关联度）、Recency（时新性，最近何时创建）、Importance（重要度，可在生成时定义）。只依赖向量相关性是常见陷阱：相似度能浮出概念相似但陈旧或琐碎的记忆。三维混合评分最有效。

精度至上的应用可以进一步精炼，但都要付出计算与延迟代价：query rewriting 用 LLM 改善查询本身——把模糊输入改写得更精确，或把单一查询扩展成多个相关查询覆盖话题的不同侧面，显著提升初始搜索质量，但开头多一次 LLM 调用；reranking 让初始检索取宽候选集（例如 top 50），LLM 再评估并重排这个小集合，产出更准确的最终列表；fine-tuning 训练专门 retriever，需要标注数据且显著增加成本。这些方法多数实时应用用不起。记忆变化不快时，缓存层可有效缓解：把昂贵检索的结果临时存起来，后续相同请求绕过延迟。

最终，最优检索始于更好的记忆生成：确保记忆语料高质量、无无关信息，是保证任何检索结果有用的最有效方式。

### 检索时机：proactive 与 reactive

最后一个架构决定是什么时候检索。proactive retrieval（主动检索）在每轮开始自动加载记忆，保证上下文总在，但对不需要记忆的轮次引入不必要的延迟；记忆在单轮内不变，可用高效缓存缓解。

ADK 两种实现：内建的 PreloadMemoryTool 每轮做相似性检索；或自定义 callback 精细控制检索方式，把检索结果格式化后追加进 system_instruction。

```python
# Option 1: Use the built-in PreloadMemoryTool which retrieves memories with
# similarity search every turn.
agent = LlmAgent(
    ...,
    tools=[adk.tools.preload_memory_tool.PreloadMemoryTool()]
)
# Option 2: Use a custom callback to have more control over how memories
# are retrieved.
def retrieve_memories_callback(callback_context, llm_request):
    user_id = callback_context._invocation_context.user_id
    app_name = callback_context._invocation_context.app_name
    response = client.agent_engines.memories.retrieve(
        name="projects/.../locations/...reasoningEngines/...",
        scope={
            "user_id": user_id,
            "app_name": app_name
        }
    )
    memories = [f"* {memory.memory.fact}" for memory in list(response)]
    if not memories:
        # No memories to add to System Instructions.
        return
    # Append formatted memories to the System Instructions
    llm_request.config.system_instruction += "\nHere is information that you have about the user:\n"
    llm_request.config.system_instruction += "\n".join(memories)
agent = LlmAgent(
    ...,
    before_model_callback=retrieve_memories_callback,
)
```

reactive retrieval（响应式检索）即 memory-as-a-tool：给 agent 一个查询记忆的工具，让它自己决定何时检索。更高效健壮，但需要一次额外的 LLM 调用，增加延迟与成本；好在只在必要时才付这笔成本。风险是 agent 可能不知道有相关信息可检索——缓解办法是让 agent 知道有哪类记忆（例如在自定义工具的 description 里写明），让它做出更明智的查询决策。

```python
# Option 1: Use the built-in LoadMemory.
agent = LlmAgent(
    ...,
    tools=[adk.tools.load_memory_tool.LoadMemoryTool()],
)
# Option 2: Use a Custom tool where you can describe what type of information
# might be available.
def load_memory(query: str, tool_context: ToolContext):
    """Retrieves memories for the user.
    The following types of information may be stored for the user:
    * User preferences, like the user's favorite foods.
    ...
    """
    # Retrieve memories using similarity search.
    response = tool_context.search_memory(query)
    return response.memories
agent = LlmAgent(
    ...,
    tools=[load_memory],
)
```

## 推理时的记忆注入

检索到相关记忆后，最后一步是策略性地放进 context window。放置位置显著影响 LLM 的推理、运营成本与最终答案质量。两条主要路径：追加进 system instructions，或注入对话历史。实践上混合策略常最优：system prompt 放应始终在场的稳定全局记忆（如用户 profile）；dialogue injection 或 memory-as-a-tool 放只与当下上下文相关的瞬态 episodic 记忆。这平衡了持久上下文的需要与即时检索的灵活性。

### 注入 system instructions

把检索到的记忆连同前言直接追加到 system prompt，把记忆定位为整个交互的基础性上下文。可用 Jinja 模板动态构建：

```python
from jinja2 import Template
template = Template("""
{{ system_instructions }}}
<MEMORIES>
Here is some information about the user:
{% for retrieved_memory in data %}* {{ retrieved_memory.memory.fact }}
{% endfor %}</MEMORIES>
""")
prompt = template.render(
    system_instructions=system_instructions,
    data=retrieved_memories
)
```

给记忆高权威、干净地把上下文与对话分离，适合稳定的全局信息（用户 profile）。风险是过度影响：agent 可能把每个话题都关联回核心指令里的记忆，即使并不合适。这个架构模式还有三重限制：要求框架支持每次 LLM 调用前动态构造 system prompt，这种能力并非总是现成；与 memory-as-a-tool 不兼容，因为 system prompt 必须在 LLM 决定调用记忆检索工具之前定稿；对非文本记忆处理很差，多数 LLM 的 system instructions 只接受文本，嵌入图像、音频很困难。

### 注入对话历史

把检索到的记忆直接注入逐轮对话：放在完整历史之前，或最新用户查询之前。这个方法可能嘈杂，增加 token 成本；检索到无关记忆时会困惑 model。主要风险是 dialogue injection（对话注入）：model 可能把记忆误当作对话中真正说过的话。注入视角也要小心：用 user 角色注入用户级记忆时，记忆应以第一人称书写。一个特例是经工具调用检索记忆：作为 tool output 的一部分直接进对话。

```python
def load_memory(query: str, tool_context: ToolContext):
    """Loads memories into the conversation history..."""
    response = tool_context.search_memory(query)
    return response.memories
agent = LlmAgent(
    ...,
    tools=[load_memory],
)
```

## procedural memories

本白皮书聚焦 declarative memories，这与当前商业记忆版图一致：多数记忆管理平台按声明式架构构建，擅长提取、存储、检索「什么」——事实、历史、用户数据。

这些系统不为 procedural memories 设计——改进 agent 工作流与推理的机制。存「怎么做」不是信息检索问题，是推理增强问题；管理 knowing how 需要完全独立、专门的算法生命周期，只是高层结构相似，同样三阶段：

1. Extraction：程序式提取需要专门的 prompt，从成功交互中蒸馏可复用的策略或 playbook，而非只捕获事实。
2. Consolidation：声明式整合合并相关事实（「什么」），程序式整合策展工作流本身（「怎么做」）——把新的成功方法与既有最佳实践集成、修补已知计划里有缺陷的步骤、剪除过时无效的程序。这是主动的逻辑管理过程。
3. Retrieval：目标并非检索数据来回答问题；它检索的是一份 plan，用来指导 agent 执行复杂任务；因此 procedural memories 的数据 schema 可以与 declarative 不同。

agent 这种「自我演进」逻辑的能力自然会被拿来与 fine-tuning（常经 RLHF）比较：两者都为改进 agent 行为，但机制与应用根本不同。fine-tuning 是相对慢的离线训练过程，改动 model 权重；procedural memory 提供快速的在线适应——把正确的 playbook 动态注入 prompt，经 in-context learning 引导 agent，无需任何微调。

## 测试与评估

有了记忆增强的 agent，须经验证。评估是多层的：验证记对了东西（质量）、需要时找得到（检索）、用了记忆真能帮完成任务（任务成功）。学界聚焦可复现的基准；业界评估围绕记忆对生产 agent 性能与可用性的直接影响。

记忆生成质量指标评内容本身——记的对吗：对人工创建的 golden set（理想记忆集）对比。Precision 是生成的记忆中准确且相关的百分比，高 precision 防止过度热情的记忆系统用无关噪声污染知识库；Recall 是源数据中应记住的相关事实被捕获的百分比，高 recall 防漏关键信息；F1 是两者的调和平均，给单一平衡的质量度量。

检索性能指标评找对记忆的能力：Recall@K 问需要某条记忆时它是否出现在 top K 检索结果内，是检索准确度的主要度量；Latency 上，检索处在 agent 响应的热路径，整个检索过程须在严格延迟预算内（例如 200ms）完成，否则损害用户体验。

端到端任务成功指标是终极测试——记忆真能帮 agent 干得更好吗：评 agent 用记忆在下游任务上的表现，常用 LLM judge 把 agent 最终输出与 golden answer 对比判定准确性，衡量记忆系统对最终结果的贡献。

评估并非一次性事件，而是持续改进的引擎：指标提供识别弱点的数据，迭代过程是建基线、分析失败、调整系统（精炼 prompt、调检索算法）、复评影响。指标聚焦质量，但生产就绪也靠性能：每个评估领域都要测底层算法的延迟与负载下的扩展能力；热路径检索可能有严格的亚秒预算；生成与整合虽常异步，吞吐也要跟上用户需求。成功的记忆系统须智能、高效，且真实世界健壮。

## 生产考量

从原型到生产，须聚焦企业级架构关切：扩展性、韧性、安全。为了保证用户体验永不被昂贵的记忆生成阻塞，健壮的架构必须把记忆处理与主应用逻辑解耦。这是事件驱动模式，但典型实现是对专用记忆服务的直接非阻塞 API 调用，而非自管消息队列。四步流程：

1. Agent pushes data：相关事件（如 session 结束）后，agent 应用对 memory manager 发起非阻塞 API 调用，推送原始源数据（对话逐字稿）。
2. Memory manager 后台处理：立即确认请求，把生成任务放进自己内部管理的队列；它独立负责异步重活——必要的 LLM 调用、提取、整合、格式化，可以延迟处理到一定的不活动期之后。
3. Memories 持久化：服务把最终记忆（新条目或更新）写进专用持久数据库；托管 manager 内建存储。
4. Agent 检索：主应用需要为新交互取上下文时，直接查询 memory store。

服务化、非阻塞的方式确保记忆管道的失败或延迟不直接影响面向用户的应用，系统更有韧性。它也指导在线（实时）生成与离线（批量）处理的选择：前者保对话新鲜度，后者适合从历史数据填充。

应用增长时，记忆系统必须无失败地处理高频事件。并发请求下须防止多个事件改同一条记忆引发互相阻塞或竞态：可用事务性数据库操作或乐观锁缓解；多个请求改同一记忆时引入排队或限流。健壮的消息队列对缓冲大量事件、防止记忆生成服务被压垮必不可少。瞬态错误要有韧性：LLM 调用失败须配指数退避的重试机制，持续失败的路由到失败消息隔离队列（dead letter queue）供分析。全球应用的 manager 须用内建多区域复制的数据库保低延迟与高可用；客户端复制不可行，因为 consolidation 需要单一事务一致的数据视图防冲突；因此记忆系统须内部处理复制，对开发者呈现单一逻辑 datastore，同时保证底层知识库全球一致。托管记忆系统（如 Agent Engine Memory Bank）应帮开发者解决这些生产考量，让开发者聚焦核心 agent 逻辑。

## 隐私与安全

记忆源自并包含用户数据，须施以严格的隐私与安全控制。类比：把系统记忆想成由专业档案管理员管理的安全企业档案馆，其工作是保存宝贵知识的同时保护公司。

档案馆的首要规则是数据隔离：档案员绝不混合不同部门的机密文件；记忆必须在用户或租户级严格隔离，服务一个用户的 agent 绝不能访问另一个用户的记忆，用限制性 ACL 强制。用户必须有程序化的数据控制：清晰的 opt-out（退出）记忆生成选项，或请求删除档案馆中自己的全部文件。

归档任何文件之前，档案员要做关键的安全步骤。首先逐页细致 redact 敏感个人信息（PII），确保保存知识的同时不制造责任。其次，档案员受过训练，识别并丢弃伪造或故意误导的文件，防 memory poisoning（记忆投毒）；同样，系统必须在提交长期记忆前校验并清洗信息，防恶意用户经 prompt injection 腐蚀 agent 的持久知识；须含 Model Armor 这类保障，在提交长期记忆前完成校验与清洗。

多用户共享同一组记忆时有渗出风险，典型是 procedural memories——教 agent 怎么做某事的记忆。一个用户的程序记忆给另一个用户当示例时（像公司范围的传阅备忘录），档案员必须先做严格匿名化，防敏感信息跨用户边界泄露。

## 结语

Context Engineering 是一门学科：为每一次 LLM 调用动态组装全部必要信息——对话历史、记忆、外部知识——进 context window。整个流程依赖两个不同但互联系统的互动：即时的 Session 与长期的 Memory。

Session 治理当下：它是单次对话的低延迟、按时间序的容器，主要挑战是性能与安全——低延迟访问与严格隔离；防 context window 溢出与延迟，须用 token 截断或递归总结等提取技术压缩 session 历史或单次请求载荷；安全至上要求 session 数据持久化前完成 PII redaction。

Memory 是长期个性化引擎，是跨 session 持久的核心机制：它让 agent 超越 RAG（精通事实）进而精通用户。它是主动的、LLM 驱动的 ETL 管道，负责提取、整合、检索，从对话历史蒸馏最重要的信息。extraction 蒸馏关键记忆点；consolidation 策展整合新信息进既有语料，消解冲突、删除冗余，保知识库连贯。为保持敏捷体验，记忆生成必须在 agent 响应之后作为异步后台过程运行。追踪 provenance、防 memory poisoning，开发者才能构建真正随用户学习成长的、值得信任的自适应助手。
