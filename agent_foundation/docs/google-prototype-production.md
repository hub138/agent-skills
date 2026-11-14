# Google 智能体白皮书：从原型到生产

- 原文：[Prototype to Production](https://www.kaggle.com/whitepaper-prototype-to-production)
- 来源：Google 五日 AI Agent 强化课程白皮书之五（kaggle.com），作者 Sokratis Kartakis、Gabriela Hernandez Larios、Ran Li、Elia Secchi、Huang Xia
- 发布：2025-11
- 译文说明：增量翻译，术语保留英文原词；图表以文字说明代替；代码为原文 Snippet 逐行忠实保留。评估方法部分（golden dataset、LLM-as-a-Judge、CI/CD 闸门评估）与 [为 AI agent 解密评估](evals-demystified.md)（Anthropic）、[Google 智能体白皮书：智能体质量](google-agent-quality.md) 重叠，本篇该部分只列定位与操作形态；本篇增量在评估关卡两实现、CI/CD 三阶段漏斗、Safe Rollout 四模式、全组件版本化、Observe-Act-Evolve 运营循环与 contain-triage-resolve 安全 playbook，以及 A2A 代码级实现（Agent Card、`to_a2a`、`RemoteA2aAgent`、层级组合）、A2A 与 MCP 分层协作与 Registry 架构决策框架。A2A 协议部分与 [GUIDE.md](../GUIDE.md) 第 20 章（向公开榜样学习）互补：第 20 章有 Task 生命周期七态、rejected 与 failed 的区分、Agent Card 签名验证与令牌交换 RFC 8693，本篇增量在代码级实现与层级组合模式。ADK、Vertex AI、Cloud Run、Agent Engine 等 Google 云产品名保留原名，作为机制示例对待，产品细节过滤为背景。

## 生产的三大痛点与三支柱

agent 上生产后有三个专属运营难题：Dynamic Tool Orchestration（agent 的 trajectory 在运行中即时组装，每次挑的工具组合都不同，要求版本化、访问控制与观察系统能跟住一个每次行为都不同的系统）；Scalable State Management（agent 跨交互记住东西，session 与 memory 在规模下安全一致地管理是复杂的系统设计问题）；Unpredictable Cost & Latency（agent 走哪条路径找答案不可预测，没有智能预算与缓存，成本与响应时间极难控制）。

应对这三难题的地基是三支柱：Automated Evaluation、Automated Deployment（CI/CD）、Comprehensive Observability。白皮书把这五日课程收束成一本从预生产到在产运营的完整 playbook。

## People and Process

技术之外先谈人与流程：世界上最好的技术，没有对的团队来建设、管理与治理也会失效。客服 agent 不会天然拒绝送出免费商品——是 AI Engineer 与 Prompt Engineer 设计并实现了 guardrails；机密数据库不会因为一个抽象概念而安全——是 Cloud Platform 团队配置了认证。每个成功运行的生产级 agent 背后都是一个分工明确的专家团队。

传统 MLOps 里的关键角色：Cloud Platform Team（云架构师、管理员与安全专家，管理底层基础设施与访问控制，给工程师与服务账号授最小权限角色）；Data Engineering Team（建设维护数据管道，负责摄取、准备与质量标准）；Data Science and MLOps Team（data scientist 实验训练 model，ML engineer 用 CI/CD 把端到端 ML 管道在大规模下自动化）；Machine Learning Governance（集中治理职能，product owner 与审计者监督 ML 生命周期，作为 artifact 与指标的知识库，保证合规、透明与可追责）。

生成式 AI 在此之上加了一层新角色：Prompt Engineers（把 prompt 技巧与领域专业深度结合的人，定义 model 该问的问题与期望答案；行业里这个头衔仍在演化，实际可能由 AI Engineer、领域专家或专职人员承担）；AI Engineers（负责把 GenAI 方案扩展到生产，建设带大规模评估、guardrails、RAG 与工具集成的健壮后端）；DevOps/App Developers（建设前端组件与接入 GenAI 后端的用户界面）。组织规模影响角色形态：小公司一人多角，成熟组织分工更专。

## 评估关卡：Evaluation-Gated Deployment

预生产的核心原则只有一句：任何 agent 版本在通过证明质量与安全的全面评估之前，不得触达用户。用自动化确定性置换手工不确定性。三个组成：严格的评估流程当质量闸门、自动化 CI/CD 管道强制执行、安全发布策略给最后一步降低风险。

为什么需要专属闸门：传统软件测试对会推理与适应的系统不够用；评估 agent 与评估 LLM 不同——只看最终答案不够，要评完成任务的整条推理与行动 trajectory。agent 的工具可以通过 100 个单元测试，却因选错工具或幻觉一个响应而惨败。要评的是行为质量，超出功能正确性。闸门有两种实现：

1. 手工 Pre-PR 评估：给寻求灵活性或刚起步的团队。提交 pull request 之前，AI Engineer 或 Prompt Engineer（组织内对 agent 行为负责的人）在本地跑评估套件，把新版本与生产基线的对比报告链接进 PR 描述，评估结果成为人工评审的必备 artifact。评审者（通常是另一位 AI Engineer 或 Machine Learning Governor）职责扩大到对照 guardrail 违规与 prompt injection 漏洞，评审 agent 的行为变化。
2. 管道内自动闸门：给成熟团队。Data Science and MLOps Team 建设维护的评估 harness 直接集成进 CI/CD 管道，评估失败自动阻断部署，用刚性程序化执行 Machine Learning Governance 定下的质量标准。管道可配置成自动触发评估 job，把新 agent 的响应与 golden dataset 对比；关键指标（如 tool call success rate、helpfulness）低于预设阈值时，部署被程序化阻断。

评估方法本身的细节（golden dataset 建设、LLM-as-a-Judge、评估服务化）在 [Google 智能体白皮书：智能体质量](google-agent-quality.md) 与 [为 AI agent 解密评估](evals-demystified.md) 已覆盖，此处只列操作形态。

## CI/CD 三阶段漏斗

AI agent 是复合系统：除源代码外还有 prompt、工具定义与配置文件。这带来专属难题：怎么确保改一个 prompt 不会让某个工具性能退化？怎么在这些 artifact 的互相作用触达用户之前全部测过？

答案是 CI/CD 管道。它超出自动化脚本的定位，是一条结构化流程：分阶段测试改动，逐步建立信心，最终发布给用户。设计形态是漏斗，尽早尽便宜地拦住错误（业内叫 shifting left），把快的 pre-merge 检查与更重资源的 post-merge 部署分开。三阶段：

1. Phase 1: Pre-Merge Integration（CI）。第一职责是给开 PR 的 AI Engineer 或 Prompt Engineer 快速反馈。自动触发，充当主分支的守门人：跑单元测试、代码 lint、依赖扫描。关键动作：这一阶段是跑 Prompt Engineer 设计的 agent 质量评估套件的理想位置——合入之前就立刻知道改动对关键场景是提升还是退化，防止污染主分支。
2. Phase 2: Post-Merge Validation in Staging（CD）。改动通过全部 CI 检查（含性能评估）合入后，重心从代码与性能正确性转向集成系统的运营就绪。CD 过程（通常由 MLOps Team 管理）打包 agent 部署到 staging 环境——生产的高保真复制品——跑更重资源的测试：负载测试、对远程服务的集成测试。这也是内部用户测试（dogfooding）的关键阶段：公司内部的人先与 agent 交互给出定性反馈，确认集成系统在生产级条件下可靠高效，再考虑发布。
3. Phase 3: Gated Deployment to Production。staging 充分验证后进入最终部署。这一步几乎从不全自动，通常需要 Product Owner 最终签核，保住 human-in-the-loop。批准后，staging 里测试验证过的同一部署 artifact 被晋升到生产环境，配适当防护。

支撑这套三阶段流程的两项自动化技术：Infrastructure as Code（Terraform 一类工具用程序定义环境，保证环境一致、可重复、有版本控制）；Automated Testing Frameworks（Pytest 一类框架在各阶段执行测试与评估，处理 agent 专属 artifact：对话历史、工具调用日志、动态推理 trace）。敏感信息（工具的 API key）用 Secret Manager 一类服务安全管理，运行时注入 agent 环境，仓库里不留硬编码。

## Safe Rollout 四模式

预生产检查再全面，真实世界必然暴露未预见的问题。与其一次性切换 100% 用户，用渐进发布加监控把风险压低。四个成熟模式：

- Canary：从 1% 用户开始，监控 prompt injection 与异常工具使用，逐步放量或即时回退。
- Blue-Green：跑两套同一生产环境。流量走「蓝」环境的同时向「绿」环境部署，然后瞬时切换；出问题切回来，零停机、即时恢复。
- A/B Testing：在真实业务指标上对比 agent 版本，支撑数据驱动决策；内部或外部用户皆可。
- Feature Flags：先部署代码、动态控制发布，先给选定用户测新能力。

四模式共同地基是严格版本化：代码、prompt、model endpoint、工具 schema、memory 结构、甚至评估数据集，全部版本化。防护失效出问题时，这保证即时回退到已知良好状态——生产的「撤销」按钮。

## 安全三层防御

安全发布策略挡的是 bug 与故障；agent 面对独特挑战：它会自主推理与行动。完美部署的 agent 若没内置安全与责任措施，仍能造成伤害。治理要从第一天嵌入，不能事后补。

agent 自主性带来的三类专属风险：Prompt Injection & Rogue Actions（恶意用户诱骗 agent 执行非预期动作或绕过限制）；Data Leakage（agent 可能经响应或工具使用不经意暴露敏感信息）；Memory Poisoning（存进 agent memory 的假信息会污染全部后续交互）。

三层防御：

1. 策略定义与 System Instructions（agent 的 constitution）：先定义期望与非期望行为的策略，工程化进 System Instructions，作为 agent 的核心准则。
2. Guardrails、Safeguards 与 Filtering（执行层）：硬性拦截机制。Input Filtering 用分类器在恶意输入触达 agent 之前拦住；Output Filtering 在响应发出前做最终检查，可配置拦截特定 PII、有害语言或违规内容；Human-in-the-Loop（HITL）Escalation 给高风险或含糊动作暂停并升级人工审批。
3. 持续保障与测试：安全从未一次成型。模型或安全系统的任何改动必须触发评估管道全量重跑；用专属数据集或模拟 agent 做专项 RAI 测试（含 NPOV 与 Parity 评估）；主动 red teaming——用创造性手工测试与 AI 驱动的 persona 模拟主动尝试攻破安全系统。

## 运营循环：Observe → Act → Evolve

agent 上产后，重心从开发转向一个根本不同的挑战：在与数千用户交互中保持系统可靠、成本可控、安全。传统服务按可预测逻辑运行；agent 是自主行动者，能走未预见的推理路径、涌现新行为、在无人直接监督下累积成本。

管理这种自主性要用运营循环替代静态监控：Observe 实时观察系统行为，Act 维持性能与安全，Evolve 基于生产所学改进 agent。

### Observe：感觉系统

要信任并管理一个自主 agent，先要理解它的过程。observability 是后续 Act 与 Evolve 的感觉系统，三支柱（Logs 事实日记、Traces 因果叙事、Metrics 聚合报告卡）与具体产品化形态在 [Google 智能体白皮书：智能体质量](google-agent-quality.md) 的观察三支柱已全述，此处不重复。

### Act：运营控制杆

只有观察没有动作，只是昂贵的仪表盘。Act 阶段做实时干预——按观察结果拉动管理性能、成本与安全的控制杆。把 Act 当系统的自动反射（维持实时稳定），Evolve 则是后续的战略过程（从行为中学习、造出根本更好的系统）。

agent 是自主的，无法预编程每种结果，要建影响其行为的健壮机制。控制杆分两类。

#### Managing System Health：性能、成本与规模

传统微服务的负载可预测；agent 的负载动态且有状态。管理要点：

- 为规模设计：地基是把 agent 逻辑与状态解耦。
- Horizontal Scaling：把 agent 设计成无状态容器化服务，状态外置后任意实例可处理任意请求，serverless 平台自动扩缩。
- Asynchronous Processing：长任务用事件驱动模式卸载——agent 保持响应，复杂任务后台处理。
- Externalized State Management：LLM 无状态，memory 外部持久化无可商量；架构选择在托管服务（内置持久 session 与 memory）与直接集成数据库之间权衡。
- 平衡三个竞争目标：Speed（延迟）——并行设计、积极缓存、常规任务用更小更高效的 model；Reliability（韧性）——自动重试失败调用（理想用 exponential backoff 给服务恢复时间），把工具设计成 safe-to-retry（idempotent）防止重复扣款这类 bug；Cost——缩短 prompt、简单任务用更便宜的 model、请求成批发送（batching）。

#### Managing Risk：安全响应 playbook

agent 能自主行动，就需要一份快速控制局面的 playbook。威胁检出后按明确序列响应：contain、triage、resolve。

第一步即时控制：优先止损，典型手段是 circuit breaker——用一个 feature flag 即时停用受影响的工具。下一步 triage：威胁受控后，可疑请求路由进 HITL 评审队列，调查漏洞的范围与影响。最后永久解决：团队开发补丁（更新的输入过滤器或 system prompt），经自动化 CI/CD 管道部署，修复在全量测试后才永久封堵漏洞。

### Evolve：从生产学习

Act 提供即时战术反射；Evolve 做长期战略改进。起点是看 observability 数据里的模式与趋势，问关键问题：「怎么修根因，让这个问题永远不再发生？」从响应生产事件转向主动让 agent 更聪明、更高效、更安全——把 Observe 阶段的原始数据变成 agent 架构、逻辑与行为上的持久改进。

#### 进化的引擎：自动化上产路径

生产洞察只有在能快速兑现时才有价值。观察到 30% 用户在某个任务上失败，若团队要六个月才能部署修复，观察就白做了。预生产建设的自动化 CI/CD 管道在运营循环里成为最关键组件：它驱动快速进化，让观察与改进之间的闭环以小时或天计，不是周或月。

识别出潜在改进（精炼的 prompt、新工具、更新的安全 guardrail）后的流程：Commit the Change（改进提交进版本控制仓库）→ Trigger Automation（提交自动触发 CI/CD 管道）→ Validate Rigorously（管道跑全量单元测试、安全扫描与 agent 质量评估套件）→ Deploy Safely（验证通过后用安全发布策略上产）。自动化把进化从缓慢高风险的手工项目变成快速、可重复、数据驱动的过程。

#### 进化工作流：从洞察到部署的改进

1. Analyze Production Data：从生产日志识别用户行为、任务成功率与安全事件的趋势。
2. Update Evaluation Datasets：把生产失败转化成明天的测试用例，扩充 golden dataset。
3. Refine and Deploy：提交改进触发自动化管道——精炼 prompt、加工具、更新 guardrails。

由此形成 virtuous cycle：agent 随每次用户交互持续改进。

零售 agent 实例：日志显示 15% 用户问「相似商品」时报错（Observe）；产品团队建高优先级工单（Act）；Evolve 启动——生产日志用来给评估数据集新建一个失败的测试用例，AI Engineer 精炼 agent 的 prompt 并加一个更健壮的相似检索工具；改动提交后在 CI/CD 管道里通过更新后的评估套件，经 canary 发布安全上产，48 小时内解决用户问题。

#### Evolving Security：生产安全反馈环

安全在预生产建立框架，但工作从未完成。安全没有静态清单，是持续适应的动态过程；生产环境是终极测试场，那里的洞察对加固 agent 至关重要。Observe → Act → Evolve 循环用于安全时是进化工作流的直接延伸：Observe（监控与日志系统检出新威胁向量——绕过现有过滤器的新型 prompt injection，或导致轻微数据泄露的意外交互）；Act（安全响应团队即时控制，见前述 playbook）；Evolve（安全洞察回馈开发生命周期：新攻击向量作为永久测试用例加入评估套件，Prompt Engineer 或 AI Engineer 精炼 system prompt、输入过滤器或工具使用策略以封堵新攻击向量，工程师提交改动触发完整 CI/CD 管道，更新后的 agent 对扩充后的评估集严格验证后部署上产，漏洞关闭）。

由此每个生产事件都让 agent 更强韧，安全姿态从防御转向持续主动的改进。

## A2A：复用与标准化

组织内建了几十个专业 agent：客服团队的支撑 agent、分析团队的预测系统、风控的反欺诈检测。问题是它们互相之间说不上话——不同框架、不同项目甚至不同云上建的。这种孤立造成大量低效：每个团队重复建设同样的能力，关键洞察困在孤岛里。需要的是互操作性——任何 agent 能调用任何其他 agent 的能力，无论谁建的、什么框架。

方案建立在两个互补协议上。MCP（详见 [Google 智能体白皮书：智能体工具与 MCP 互操作](google-agent-tools-mcp.md)）提供工具集成的通用标准，但对智能体之间复杂的有状态协作不够用；这由 Agent2Agent（A2A）协议解决，现由 Linux Foundation 治理。

区分很关键：需要简单无状态函数（取天气数据、查数据库）时用 MCP 工具；需要委派复杂目标（「分析上季度客户流失并推荐三个干预策略」）时用 A2A 找一个能推理、规划、自主行动的智能伙伴。一句话：MCP 让你说「做这件具体的事」，A2A 让你说「达成这个复杂目标」。

### A2A 协议：从概念到实现

场景：反欺诈 agent 发现可疑活动，要理解全部上下文需要另一个交易分析 agent 的数据。没有 A2A，人类分析师手工补位——可能耗时数小时；有 A2A，agent 自动协作，几分钟内解决。

协作第一步是找到该委派给哪个 agent，靠 Agent Card 实现——标准化的 JSON 规格，每个 agent 的名片。Agent Card 描述这个 agent 能做什么、安全要求、技能与联系方式（url），让生态里任何其他 agent 动态发现同伴。check_prime_agent 的样例卡片：

```json
{
  "name": "check_prime_agent",
  "version": "1.0.0",
  "description": "An agent specialized in checking whether numbers are prime",
  "capabilities": {},
  "securitySchemes": {
     "agent_oauth_2_0": {
        "type": "oauth2",
  }
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["application/json"],
  "skills": [
    {
      "id": "prime_checking",
      "name": "Prime Number Checking",
      "description": "Check if numbers are prime using efficient algorithms",
      "tags": ["mathematical", "computation", "prime"]
    }
  ],
  "url": "http://localhost:8001/a2a/check_prime_agent"
}
```

采用这个协议不需要架构大改。ADK 一类框架大幅简化：一次函数调用就能让既有 agent 变成 A2A 兼容，自动生成 AgentCard 并在网络上可用。

```python
# Example using ADK: Exposing an agent via A2A
from google.adk.a2a.utils.agent_to_a2a import to_a2a
# Your existing agent
root_agent = Agent(
    name='hello_world_agent',
    # ... your agent code ...
)
# Make it A2A-compatible
a2a_app = to_a2a(root_agent, port=8001)
# Serve with uvicorn
# uvicorn agent:a2a_app --host localhost --port 8001
# Or serve with Agent Engine
# from vertexai.preview.reasoning_engines import A2aAgent
# from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
# a2a_agent = A2aAgent(
#    agent_executor_builder=lambda: A2aAgentExecutor(agent=root_agent)
# )
```

agent 暴露后，任何其他 agent 引用其 AgentCard 即可消费它。例如客服 agent 现在能查询一个远程产品目录 agent，无需知道它的内部运作。

```python
# Example using ADK: Consuming a remote agent via A2A
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
prime_agent = RemoteA2aAgent(
    name="prime_agent",
    description="Agent that handles checking if numbers are prime.",
    agent_card="http://localhost:8001/a2a/check_prime_agent/ 
               .well-known/agent-card.json"
)
```

这解锁了强大的层级组合：一个 root agent 可以编排本地 sub-agent（做简单任务）与经 A2A 的远程专业 agent（做复杂任务），组成更有能力的系统。

```python
# Example using ADK: Hierarchical agent composition
# ADK Local sub-agent for dice rolling
roll_agent = Agent(
    name="roll_agent",
    instruction="You are an expert at rolling dice."
)
# ADK Remote A2A agent for prime checking
prime_agent = RemoteA2aAgent(
    name="prime_agent",
    agent_card="http://localhost:8001/.well-known/agent-card.json"
)
# ADK Root orchestrator combining both
root_agent = Agent(
    name="root_agent",
    instruction="""Delegate rolling dice to roll_agent, prime checking 
to prime_agent.""",
    sub_agents=[roll_agent, prime_agent]
)
```

这种自主协作带来两项无可商量（non-negotiable）的技术前提。第一是 distributed tracing：每个请求携带唯一 trace ID，对跨多 agent 的调试与保持连贯审计链必不可少。第二是健壮的 state 管理：A2A 交互天然有状态，需要成熟的持久层来追踪进度并保证事务完整性。

A2A 最适合需要持久服务规格（durable service contract）的正式跨团队集成；单应用内紧耦合的任务，轻量本地 sub-agent 往往仍是更高效的选择。生态成熟过程中，新 agent 应原生支持两种协议，让每个新组件即刻可发现、可互操作、可复用，整个系统的价值复利增长。

### A2A 与 MCP 如何协作

A2A 与 MCP 并非竞争标准，是互补协议，工作在不同的抽象层级。区分取决于 agent 在与什么交互：MCP 是工具与资源的领域——输入输出定义清晰的基元，如计算器或数据库 API；A2A 是其他 agent 的领域——能推理、规划、使用多工具、维护状态以达成复杂目标的自主系统。

最强大的 agentic 系统用两种协议组成分层架构：应用主要用 A2A 编排多个智能体间的高层协作，每个 agent 内部各自用 MCP 与自己那套工具资源交互。

一个汽车修理店的类比，店员全是自主 AI agent：

1. User-to-Agent（A2A）：顾客用 A2A 与「店长」agent 沟通，描述高层问题：「我的车有咔哒异响。」
2. Agent-to-Agent（A2A）：店长进行多轮诊断对话，然后把任务委派给专业的「技师」agent，仍用 A2A。
3. Agent-to-Tool（MCP）：技师 agent 现在要执行具体动作，用 MCP 调自己的专业工具：在诊断扫描仪上跑 `scan_vehicle_for_error_codes()`，用 `get_repair_procedure()` 查维修手册数据库，用 `raise_platform()` 操作举升机。
4. Agent-to-Agent（A2A）：诊断后技师确定需要零件，用 A2A 与外部「零件供应商」agent 沟通询价下单。

这条工作流里，A2A 承载顾客、店内 agent 与外部供应商之间高层、对话式、任务导向的交互；MCP 提供标准化管道，让技师 agent 可靠地用自己的结构化工具干活。

### Registry 架构：何时建与怎么建

为什么有的组织建 Registry、有的不需要？答案在规模与复杂度。五十个工具时手工配置没问题；五千个工具分布在多个团队与环境时，就面对一个需要系统化解决的发现问题。

Tool Registry 用 MCP 一类协议编目全部资产（从函数到 API）。与其给 agent 访问几千个工具，不如做精选清单，三种常见模式：Generalist agents（访问全目录，用速度与准确度换覆盖面）；Specialist agents（用预定义子集换更高性能）；Dynamic agents（运行时查询 registry 以适应新工具）。首要收益是人的发现——开发者建设前先搜有没有现成工具，安全团队审计工具访问，product owner 了解自己 agent 的能力。

Agent Registry 把同一概念用于 agent，用 A2A 的 AgentCard 一类格式，帮团队发现与复用既有 agent，减少重复建设；这也为自动化 agent 间委派打了地基，不过仍是涌现中的模式。

Registry 用维护成本换发现与治理。可以先不建，等生态规模真正需要集中管理时再建。决策框架：Tool Registry 在工具发现成为瓶颈或安全需要集中审计时建；Agent Registry 在多团队需要发现复用专业 agent 而又不能紧耦合时建。

## AgentOps 生命周期

把全部支柱装进一个连贯的参考架构：生命周期从开发者的 inner loop 开始——快速本地测试与原型阶段，塑造 agent 的核心逻辑；改动就绪后进入正式预生产引擎，自动化评估闸门对照 golden dataset 验证质量与安全；随后 safe rollout 发布上产，全面 observability 捕获真实世界数据，燃料般驱动持续进化循环，把每个洞察变成下一次改进。

结论：把 AI 原型搬上生产是一次组织变革，要求新的运营纪律——AgentOps。多数 agent 项目失败在「最后一公里」，败因不是技术，是自主系统的运营复杂度被低估。路径：People and Process 做治理地基 → 评估关卡的预生产策略自动化高风险发布 → 在产后 Observe → Act → Evolve 循环把每次用户交互变成潜在洞察 → 互操作协议把孤立 agent 变成协作的智能生态，完成规模化。即时收益（挡住安全漏洞、快速回退）证明投入合理；真正的价值是速度——成熟的 AgentOps 让团队以小时为单位部署改进，静态部署变成持续进化的产品。起步者先建第一个评估数据集、CI/CD 管道与全面监控；规模化者把生产洞察到部署改进的反馈环自动化，在可互操作协议上标准化，造连贯生态。
