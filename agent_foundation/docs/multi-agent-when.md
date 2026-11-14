# 多 agent 系统：何时用与怎么用（Building multi-agent systems: When and how to use them）
- 原文：[Building multi-agent systems: When and how to use them](https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them)
- 来源：Anthropic，作者 Cara Phillips，贡献者 Paul Chen、Andy Schumeister、Brad Abrams、Theo Chu
- 发布：2026-01-23
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；代码块保留英文原样；本文无插图。

## 什么是多 agent 系统

多 agent 系统是这样一种架构：多个 LLM 实例各自带着独立的对话上下文运行，由代码协调。每个 agent 负责任务的一块——例如一个 subagent 做研究，一个 orchestrator 做规划——这保护了上下文、支持并行工作，也让单个 agent 无法维持的专门化成为可能。

协调模式不止一种（agent swarms、按能力组织的系统、消息总线架构），本文聚焦 orchestrator-subagent 模式：一种分层模型，由一个主 agent 为特定子任务创建并管理专门的 subagent。这个模式的协调模型直观，是多 agent 系统新手团队的好起点。其他模式会在下一篇文章里详细展开。

今天，多 agent 系统经常被用在本该单个 agent 表现更好的场景，不过随着模型进步，这笔账还在变化。在 Anthropic，我们见过团队花几个月构建精细的多 agent 架构，最后发现单个 agent 改进提示词就能达到同样效果。

在构建多 agent 系统、并与在生产环境部署它们的团队合作之后，我们总结出多个 agent 稳定胜过单个 agent 的三种情形：上下文污染拖累性能时、任务可以并行运行时、专门化能改进工具选择或任务专注度时。这三种情形之外，协调成本通常超过收益。参见[何时把 subagent 折回主 agent 循环](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)。本文分享如何识别单 agent 的边界、判定多 agent 系统胜出的三种场景，以及避开常见的实现错误。

## 为什么从单个 agent 起步

一个设计良好、工具合适的单个 agent，能完成的远比很多开发者预期的多。

多 agent 系统自带开销。每多一个 agent，就多一个潜在故障点、多一套要维护的提示词、多一个意外行为的来源。

我们见过团队构建精细的多 agent 系统，规划、执行、审查、迭代各配一个 agent，最后发现每次交接都丢失上下文，协调花的 token 比执行还多。在我们的测试里，多 agent 实现完成同等任务通常消耗 3 到 10 倍于单 agent 方案的 token。这些开销来自三处：上下文跨 agent 重复、agent 之间的协调消息、为交接而做的结果摘要。

## 多 agent 系统的判定框架

多 agent 架构在解决单个 agent 无法跨越的具体约束时才有价值。这意味着多 agent 架构应该留给收益明确、足以覆盖额外成本的场景。托管基础设施也可以替你处理这件事（见 [Claude Managed Agents 的多 agent 编排](https://claude.com/resources/articles/new-in-claude-managed-agents)）。

下面这些模式，是我们持续观察到这项投资有正回报的场景。

### 上下文保护

大语言模型的上下文窗口有限，响应质量会随上下文增长而下降。当一个 agent 的上下文里积累了某个子任务的信息、而它对后续子任务无关时，就发生了上下文污染。Subagent 提供隔离：每个在自己的干净上下文里，专注于自己的具体任务。

设想一个客服 agent，需要一边诊断技术问题一边查订单历史。如果每次订单查询都往上下文里加几千 token，agent 推理技术问题的能力就会下降。

**单 agent 做法：**

```
# Single agent accumulates everything in context
conversation_history = [
    {"role": "user", "content": "My order #12345 isn't working"},
    {"role": "assistant", "content": "Let me check your order..."},
    # Tool result adds 2000+ tokens of order history
    {"role": "user", "content": "... (order details, past purchases, shipping info) ..."},
    {"role": "assistant", "content": "Now let me diagnose the technical issue..."},
    # Context is now polluted with order details the agent doesn't need
]
```

agent 必须在上下文里带着 2000+ token 的无关订单历史来推理技术问题，注意力被稀释，响应质量下降。

**多 agent 做法：**

```
from anthropic import Anthropic

client = Anthropic()

class OrderLookupAgent:
    def lookup_order(self, order_id: str) -> dict:
        # Separate agent with its own context
        messages = [
            {"role": "user", "content": f"Get essential details for order {order_id}"}
        ]
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=messages,
            tools=[get_order_details_tool]
        )
        # Returns only essential information
        return extract_summary(response)

class SupportAgent:
    def handle_issue(self, user_message: str):
        if needs_order_info(user_message):
            order_id = extract_order_id(user_message)
            # Get only what's needed, not full history
            order_summary = OrderLookupAgent().lookup_order(order_id)
            # Inject compact summary, not full context
            context = f"Order {order_id}: {order_summary['status']}, purchased {order_summary['date']}"
        
        # Main agent context stays clean
        messages = [
            {"role": "user", "content": f"{context}\n\nUser issue: {user_message}"}
        ]
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            messages=messages
        )
        return response
```

订单查询 agent 处理完整订单历史并提取摘要，主 agent 只收到它真正需要的 50-100 token，上下文保持专注。

上下文隔离在这些情况下最有效：子任务产生大量上下文（超过 1000 token）但其中大部分与主任务无关；子任务定义清晰、要提取什么信息有明确判据；查找或检索类操作，取回的内容需要先过滤再使用。

### 并行执行

并行运行多个 agent，能探索比单个 agent 更大的搜索空间。这个模式在搜索与研究类任务上的价值已被反复验证。

Anthropic 的研究团队在[我们如何构建多 agent 研究系统](https://www.anthropic.com/engineering/multi-agent-research-system)里记录过这一点：一个主 agent 分析查询，创建多个 subagent 并行研究不同侧面；每个 subagent 独立搜索，回传蒸馏后的发现。多 agent 搜索凭借对更大信息空间的探索，在准确性上显著优于单 agent 方案。

核心实现把一个问题分解成独立侧面，并发运行 subagent，再汇总结果。

```
import asyncio
from anthropic import AsyncAnthropic

client = AsyncAnthropic()

async def research_topic(query: str) -> dict:
    # Lead agent breaks query into research facets
    facets = await lead_agent.decompose_query(query)
    
    # Spawn subagents to research each facet in parallel
    tasks = [
        research_subagent(facet) 
        for facet in facets
    ]
    results = await asyncio.gather(*tasks)
    
    # Lead agent synthesizes findings
    return await lead_agent.synthesize(results)

async def research_subagent(facet: str) -> dict:
    """Each subagent has its own context window"""
    messages = [
        {"role": "user", "content": f"Research: {facet}"}
    ]
    response = await client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=messages,
        tools=[web_search, read_document]
    )
    return extract_findings(response)
```

这种覆盖面的提升有代价。多 agent 系统完成同等任务通常消耗单 agent 方案 3 到 10 倍的 token，原因在于：每个 agent 需要自己的上下文，agent 之间必须交换消息协调，结果在 agent 之间传递时必须摘要。并行虽然比全部串行省时间，但总计算量增加太多，多 agent 系统的总耗时往往还是长于单 agent 系统。

并行的首要收益是覆盖面，不是速度。需要在巨大信息空间里搜索、或对复杂问题从多个角度调查时，并行 agent 能覆盖单个 agent 在上下文限制内到不了的地方。交换条件是更高的 token 消耗、常常更长的总执行时间，换更全面的结果。

### 专门化

不同任务有时受益于不同的工具集、system prompt 或领域知识。与其让一个 agent 手握几十个工具，让专门的 agent 带着与职责匹配的精干工具集，可靠性更高。

#### 工具集专门化

agent 能用的工具太多时，性能会受损。三个信号说明工具专门化会有帮助：

1. **数量。** 工具太多（常见 20 个以上）的 agent 挑不出合适的那个。

2. **领域混淆。** 工具横跨多个不相关领域（数据库操作、API 调用、文件系统操作）时，agent 分不清当前任务适用哪个领域。

3. **性能劣化。** 新增工具让既有任务的表现变差，说明 agent 管理工具的能力已到上限。

#### System prompt 专门化

不同任务有时需要不同的人格、约束或指令，合在一起就互相冲突。客服 agent 需要共情与耐心；代码审查 agent 需要精确与挑剔。合规检查 agent 需要严格照章办事；头脑风暴 agent 需要创造的灵活。当一个 agent 必须在互相冲突的行为模式之间切换时，分离成各配专属 system prompt 的专门 agent，产出更稳定。

每个专门 agent 的质量只取决于它的指令——让单 agent 输出变好的[提示词工程最佳实践](https://claude.com/resources/articles/best-practices-for-prompt-engineering)，对每个 subagent 的 system prompt 同样适用。

#### 领域知识专门化

有些任务需要深度的领域上下文，全部塞给通用 agent 会把它压垮。法律分析 agent 可能需要大量判例与监管框架的上下文；医学研究 agent 可能需要临床试验方法学的专门知识。与其把全部领域上下文装进一个 agent，专门 agent 可以只带与自己职责相关的知识。

**示例：多平台集成。** 设想一个集成系统，agent 需要横跨 CRM、营销自动化与消息平台工作，每个平台各有 10-15 个相关 API 端点。一个手握 40+ 工具的 agent 常挑不对工具，把不同平台的相似操作混在一起。分解成各带精干工具集与专属提示词的专门 agent，选择错误就消失了。

```
from anthropic import Anthropic

client = Anthropic()

# Specialized agents with focused toolsets and tailored prompts
class CRMAgent:
    """Handles customer relationship management operations"""
    system_prompt = """You are a CRM specialist. You manage contacts, 
    opportunities, and account records. Always verify record ownership 
    before updates and maintain data integrity across related records."""
    tools = [
        crm_get_contacts,
        crm_create_opportunity,
        # 8-10 CRM-specific tools
    ]

class MarketingAgent:
    """Handles marketing automation operations"""
    system_prompt = """You are a marketing automation specialist. You 
    manage campaigns, lead scoring, and email sequences. Prioritize 
    data hygiene and respect contact preferences."""
    tools = [
        marketing_get_campaigns,
        marketing_create_lead,
        # 8-10 marketing-specific tools
    ]

class OrchestratorAgent:
    """Routes requests to specialized agents"""
    def execute(self, user_request: str):
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system="""You coordinate platform integrations. Route requests to the appropriate specialist:
- CRM: Contact records, opportunities, accounts, sales pipeline
- Marketing: Campaigns, lead nurturing, email sequences, scoring
- Messaging: Notifications, alerts, team communication""",
            messages=[
                {"role": "user", "content": user_request}
            ],
            tools=[delegate_to_crm, delegate_to_marketing, delegate_to_messaging]
        )
        return response
```

这个模式与高效的专业协作同构：工具与角色匹配的专家合作，胜过试图在全部领域维持精通的通才。不过专门化引入路由复杂性：orchestrator 必须正确分类请求并委派给对的 agent，路由错了结果就差；维护多个专门 agent 也增加提示词维护负担。专门化在领域边界清晰、路由判定无歧义时效果最好。

## 单 agent 架构装不下时的信号

在通用框架之外，几个具体信号说明单 agent 模式已经不够用：

**逼近上下文上限。** agent 日常消耗大量上下文且性能在下降时，上下文压力可能就是瓶颈。注意上下文管理的近期进展（[如 compaction](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction)）正在削弱这个限制，让单个 agent 在更长的视野里维持有效记忆。

**管理很多工具。** agent 有 15-20 个以上工具时，模型要花不少上下文与注意力来理解自己的选项。采用多 agent 架构之前，先考虑用 [Tool Search Tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/tool-search-tool)，它让 Claude 按需动态发现工具，无需一次性加载全部定义。这可以[把 token 消耗降低至多 85%](https://www.anthropic.com/engineering/advanced-tool-use)，同时提高工具选择的准确性。

**可并行的子任务。** 任务天然分解成独立部分（跨多个来源的研究、多组件的测试）时，并行 subagent 能带来可观提速。

这些阈值会随模型进步而移动。当前的限制是实用指导，不是根本约束。

## 以上下文为中心的分解

采用多 agent 架构时，最重要的设计决定是如何在 agent 之间划分工作。我们观察到团队经常在这里选错，协调开销吃掉多 agent 设计的收益。

关键在于用**以上下文为中心的视角**分解工作，不用以问题为中心的视角。

**以问题为中心的分解（常常适得其反）。** 按工作类型划分（一个 agent 写功能、一个写测试、第三个审查代码）制造持续的协调开销。每次交接都丢上下文：写测试的 agent 不知道某些实现决定为什么那样做，审查代码的 agent 缺少探索与迭代的过程。

**以上下文为中心的分解（通常有效）。** 按上下文边界划分意味着：负责一个功能的 agent 也该负责它的测试，因为它已经持有必要的上下文。只有上下文能真正隔离时才分开。

这条原则来自对多 agent 失败形态的观察。按问题类型分开的 agent 会玩起「传话游戏」，信息来回传递，每次交接都损失保真度。在一个按软件开发角色专门化（规划者、实现者、测试者、审查者）的实验里，subagent 花在协调上的 token 比花在实际工作上的还多。

**有效的分解边界：**

- **独立的研究路径。** 调查「亚洲市场趋势」与「欧洲市场趋势」可以并行，无需共享上下文。

- **接口干净的独立组件。** 有定义良好的 API 接口时，前端与后端可以并行推进。

- **黑盒验证。** 只需要跑测试并报告结果的验证者，不需要实现的上下文。

**有害的分解边界：**

- **同一工作的顺序阶段。** 同一个功能的规划、实现、测试共享太多上下文。

- **紧耦合的组件。** 需要不断来回沟通的组件属于同一个 agent。

- **需要共享状态的工作。** 必须频繁同步认知的 agent 应该待在一起。

## 验证 subagent 模式

一个跨领域持续有效的多 agent 模式是**验证 subagent**：一个专职 agent，唯一职责是测试或检验主 agent 的工作。

值得说明的是，更强的 orchestrator 模型（如 Claude Opus 4.5）越来越能直接评估 subagent 的工作，不需要单独的验证步骤。但验证 subagent 在这些情况下仍然有价值：orchestrator 能力有限、验证需要专门工具、或你希望在流程里强制显式的验证检查点。

验证 subagent 有效，是因为它绕开了传话游戏。验证天然只需要最少的上下文传递，验证者可以黑盒测试一个系统，不需要它如何构建的完整历史。

### 实现一个多 agent 系统

主 agent 完成一个工作单元后，先不急着继续，而是创建一个验证 subagent，带上要验证的产物、明确的成功判据、执行验证所需的工具。

验证者不需要理解产物为什么这样构建，只需要判定产物是否满足给定的判据。

```
from anthropic import Anthropic

client = Anthropic()

class CodingAgent:
    def implement_feature(self, requirements: str) -> dict:
        """Main agent implements the feature"""
        messages = [
            {"role": "user", "content": f"Implement: {requirements}"}
        ]
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            messages=messages,
            tools=[read_file, write_file, list_directory]
        )
        return {
            "code": response.content,
            "files_changed": extract_files(response)
        }

class VerificationAgent:
    def verify_implementation(self, requirements: str, files_changed: list) -> dict:
        """Separate agent verifies the work"""
        messages = [
            {"role": "user", "content": f"""
Requirements: {requirements}
Files changed: {files_changed}

Run the test suite and verify:
1. All existing tests pass
2. New functionality works as specified
3. No obvious errors or security issues

You MUST run the complete test suite before marking as passed.
Do not mark as passing after only running a few tests.
Run: pytest --verbose
Only mark as PASSED if ALL tests pass with no failures.
"""}
        ]
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            messages=messages,
            tools=[run_tests, execute_code, read_file]
        )
        return {
            "passed": extract_pass_fail(response),
            "issues": extract_issues(response)
        }

def implement_with_verification(requirements: str, max_attempts: int = 3):
    for attempt in range(max_attempts):
        result = CodingAgent().implement_feature(requirements)
        verification = VerificationAgent().verify_implementation(
            requirements,
            result['files_changed']
        )
        
        if verification['passed']:
            return result
        
        requirements += f"\n\nPrevious attempt failed: {verification['issues']}"
    
    raise Exception(f"Failed verification after {max_attempts} attempts")
```

### 多 agent 系统的应用场景

验证 subagent 在这些场景有效：

- **质量保证。** 跑测试套件、给代码做 lint、按 schema 校验输出。

- **合规检查。** 验证文档满足政策要求、按规则检查输出。

- **输出校验。** 交付前确认生成内容满足规格。

- **事实核查。** 让一个独立 agent 核验生成内容里的论断或引用。

### 提前宣布胜利的问题

验证 subagent 最显著的失败形态，是没做充分测试就把输出标记为通过。验证者跑一两个测试、看到通过、宣布成功。

缓解策略：

- **具体标准。** 写「运行完整测试套件并报告全部失败」，不写「确保它能用」。

- **全面检查。** 要求验证者测试多个场景与边界情形。

- **负面测试。** 指示验证者尝试应当失败的输入，确认它们确实失败。

- **显式指令。** 「You MUST run the complete test suite before marking as passed」这条指令不可省。没有对全面验证的显式要求，验证 agent 会走捷径。

## 单 agent 与多 agent 之间怎么选

多 agent 系统强大，但并非处处合适。加上多个协调 agent 的复杂性之前，确认：

1. **存在真实约束**需要多 agent 来解决——上下文限制、并行机会、专门化需求。

2. **分解跟着上下文走，不跟着问题类型走。** 按需要什么上下文归组工作，不按做什么类型的工作归组。

3. **存在清晰的验证点**，subagent 能在不需要完整上下文的情况下验证工作。

我们的建议？从最简单的可行方案开始，仅在证据支持时增加复杂性。

*这是多 agent 系列的第一篇。关于单 agent 模式，见 [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)。关于上下文管理策略，见 [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)。关于我们多 agent 研究系统的深入记录，见 [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)。*

## 致谢

由 Cara Phillips 撰写，Paul Chen、Andy Schumeister、Brad Abrams、Theo Chu 贡献。

> 包内互引：本篇是原文声明的多 agent 系列第一篇。五种协调模式的逐一展开见 multi-agent-coordination-patterns.md（直接续篇）；多 agent 研究系统的构建记录见 multi-agent-research.md；单 agent 的五种基础模式见 building-effective-agents.md；上下文管理原则见 context-engineering.md。
