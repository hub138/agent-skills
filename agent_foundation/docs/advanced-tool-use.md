# 进阶工具使用：Tool Search Tool、程序化工具调用与工具使用示例（Advanced tool use）

- 原文：[Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- 来源：Anthropic Engineering，作者 Bin Wu，贡献者 Adam Jones、Artur Renault、Henry Tay、Jake Noble、Noah Picard、Sam Jiang 及 Claude Developer Platform 团队
- 发布：2025-11-24
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；代码块保留英文原样；配图转为 www-cdn.anthropic.com 绝对直链并配中文短描述。

AI agent 的未来是模型在成百上千个工具之间顺畅工作。一个 IDE 助手同时集成 git 操作、文件处理、包管理器、测试框架与部署管线。一个运维协调器同时连接 Slack、GitHub、Google Drive、Jira、公司数据库与几十个 MCP 服务器。

要[构建有效的 agent](https://www.anthropic.com/research/building-effective-agents)，就需要让它们使用不限量的工具库，无需把每个定义都预先塞进上下文。我们关于[MCP 与代码执行](https://www.anthropic.com/engineering/code-execution-with-mcp)的文章讨论过，工具结果与工具定义有时会在 agent 读到请求之前就消耗 50000+ token。agent 应当按需发现与加载工具，只保留与当前任务相关的部分。

agent 还需要能从代码里调用工具。自然语言工具调用里，每次调用都要一次完整的推理过程，中间结果无论有用没用都堆积在上下文里。代码天生适合编排逻辑：循环、条件分支与数据变换。agent 需要能依据手头任务，在代码执行与推理之间自由选择。

agent 还需要能从示例学习正确的工具用法，只靠 schema 定义不够。JSON schema 定义结构上合法的内容，表达不了使用模式：什么时候带上可选参数、哪些组合有意义、你的 API 约定是什么。

今天我们发布三个特性让这一切成为可能：

- **Tool Search Tool**：让 Claude 通过搜索工具访问几千个工具，不消耗上下文窗口
- **Programmatic Tool Calling**：让 Claude 在代码执行环境里调用工具，降低对模型上下文窗口的影响
- **Tool Use Examples**：为演示如何有效使用某个工具提供通用标准

内部测试中，这些特性帮我们做出了传统工具使用模式做不出来的东西。例如 [Claude for Excel](https://www.claude.com/claude-for-excel) 用 Programmatic Tool Calling 读写几千行的电子表格，不让模型的上下文窗口过载。

基于我们的经验，这些特性为你在 Claude 上构建的东西打开了新的可能。

[配套演示视频](https://www.youtube.com/watch?v=2MJDdzSXL74)

## Tool Search Tool

### 挑战

MCP 工具定义提供重要的上下文，但接入的服务器越多，这些 token 加起来越多。看一个五服务器的配置：

- GitHub：35 个工具（约 26K token）
- Slack：11 个工具（约 21K token）
- Sentry：5 个工具（约 3K token）
- Grafana：5 个工具（约 3K token）
- Splunk：2 个工具（约 2K token）

58 个工具在对话开始之前就消耗约 55K token。再接入 Jira（单它一家约 17K token）这类服务器，很快就逼近 100K+ token 的固定开销。在 Anthropic，我们见过优化前工具定义就消耗 134K token 的情形。

token 成本并非唯一问题。最常见的失败是选错工具与参数写错，工具名字相近时尤其如此，比如 `notification-send-user` 与 `notification-send-channel`。

### 我们的方案

Tool Search Tool 按需发现工具，不预先加载全部工具定义。Claude 只看到当前任务真正需要的工具。

![Tool Search Tool 示意图：传统方式全量前置加载，Tool Search Tool 按需发现，保留 191300 token 上下文对比传统的 122800](https://www-cdn.anthropic.com/images/4zrzovbb/website/f359296f770706608901eadaffbff4ca0b67874c-1999x1125.png)

传统方式：

- 全部工具定义预先加载（50+ MCP 工具约 72K token）
- 对话历史与 system prompt 争夺剩余空间
- 任何工作开始前总消耗约 77K token

用 Tool Search Tool：

- 只预加载 Tool Search Tool 本身（约 500 token）
- 需要时按需发现工具（3-5 个相关工具，约 3K token）
- 总消耗约 8.7K token，保住 95% 的上下文窗口

token 用量降低 85%，同时保持完整工具库的可访问性。内部测试显示，大型工具库上的 MCP 评测准确率显著提升：开启 Tool Search Tool 后，Opus 4 从 49% 提升到 74%，Opus 4.5 从 79.5% 提升到 88.1%。

### Tool Search Tool 的工作原理

Tool Search Tool 让 Claude 动态发现工具。你把全部工具定义都交给 API，但用 `defer_loading: true` 标记工具使其可按需发现。被标记的工具一开始不进入 Claude 的上下文。Claude 只看到 Tool Search Tool 本身加上 `defer_loading: false` 的工具（你最关键、最高频的工具）。

Claude 需要某种能力时，它搜索相关工具。Tool Search Tool 返回匹配工具的引用，这些引用在 Claude 的上下文里展开成完整定义。

例如 Claude 需要操作 GitHub，它搜索 "github"，只有 `github.createPullRequest` 与 `github.listIssues` 被加载，另外 50+ 个来自 Slack、Jira、Google Drive 的工具不进来。

这样 Claude 能访问完整工具库，只为真正用到的工具付 token 成本。

**prompt caching 说明**：Tool Search Tool 不破坏 prompt caching，因为被标记为 deferred 的工具完全不进初始 prompt。它们只在 Claude 搜索之后才进入上下文，所以 system prompt 与核心工具定义保持可缓存。

实现方式：

```json
{
  "tools": [
    // Include a tool search tool (regex, BM25, or custom)
    {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},

    // Mark tools for on-demand discovery
    {
      "name": "github.createPullRequest",
      "description": "Create a pull request",
      "input_schema": {},
      "defer_loading": true
    }
    // ... hundreds more deferred tools with defer_loading: true
  ]
}
```

对 MCP 服务器，可以推迟整个服务器的加载，同时保留个别高频工具常驻：

```json
{
  "type": "mcp_toolset",
  "mcp_server_name": "google-drive",
  "default_config": {"defer_loading": true},
  "configs": {
    "search_files": {"defer_loading": false}
  }
}
```

Claude Developer Platform 开箱提供 regex 与 BM25 两种搜索工具，你也能用 embeddings 或其他策略实现自定义搜索工具。

### 何时使用 Tool Search Tool

与任何架构决策一样，启用 Tool Search Tool 有取舍。该特性在工具调用前增加一个搜索步骤，当上下文节省与准确率提升超过额外延迟时，回报最好。

**适用情形：**

- 工具定义消耗超过 10K token
- 遇到工具选择准确率问题
- 构建接入多个 MCP 服务器的系统
- 可用工具达到 10 个以上

**收益不大的情形：**

- 工具库很小（少于 10 个工具）
- 每次会话都会用到全部工具
- 工具定义本身很紧凑

## Programmatic Tool Calling

### 挑战

传统工具调用在工作流变复杂后带来两个根本问题：

- **中间结果污染上下文**：Claude 分析一个 10MB 日志文件找错误模式时，整个文件进入它的上下文窗口，尽管它只需要错误频率的汇总。跨多张表取客户数据时，每条记录无论相不相关都堆积在上下文里。这些中间结果消耗大量 token 预算，还可能把重要信息整体挤出上下文窗口。
- **推理开销与人工综合**：每次工具调用都要一次完整的模型推理。收到结果后，Claude 要靠自然语言处理来解读数据、推理各部分如何组合、决定下一步。五个工具的工作流意味着五次推理，外加 Claude 逐条解析结果、比对数值、综合结论。又慢又容易错。

### 我们的方案

Programmatic Tool Calling 让 Claude 用代码编排工具，代替逐次 API 往返。Claude 写代码调用多个工具、处理输出、控制哪些信息真正进入它的上下文窗口，每一步的结果不再逐条返回给它。

Claude 擅长写代码，让它用 Python 表达编排逻辑，比用自然语言工具调用得到更可靠、更精确的控制流。循环、条件分支、数据变换与错误处理全部在代码里显式存在，没有藏进 Claude 的推理里。

#### 例子：差旅预算合规检查

一个常见业务任务：「哪些成员超出了 Q3 差旅预算？」

有三个工具可用：

- `get_team_members(department)`：返回成员列表，含 ID 与级别
- `get_expenses(user_id, quarter)`：返回某人的费用明细
- `get_budget_by_level(level)`：返回某级别的预算上限

**传统方式**：

- 取成员列表 → 20 人
- 逐人取 Q3 费用 → 20 次工具调用，每次返回 50-100 条明细（机票、酒店、餐饮、发票）
- 按级别取预算上限
- 以上全部进入 Claude 的上下文：2000+ 条费用明细（50KB+）
- Claude 手工逐人汇总费用、查预算、比对是否超限
- 更多往返、大量上下文消耗

**用 Programmatic Tool Calling**：

工具结果不再逐条返回给 Claude，Claude 写一个 Python 脚本编排整个工作流。脚本在 Code Execution 工具（沙箱环境）里运行，需要某个工具的结果时暂停。你通过 API 返回工具结果时，结果由脚本处理，模型不消费它。脚本继续执行，Claude 只看到最终输出。

![Programmatic Tool Calling 流程图：Claude 写编排代码，代码在 Code Execution 沙箱里并行调用工具，中间结果不进模型上下文，只有最终输出返回](https://www-cdn.anthropic.com/images/4zrzovbb/website/65737d69a3290ed5c1f3c3b8dc873645a9dcc2eb-1999x1491.png)

预算合规任务里 Claude 的编排代码长这样：

```python
team = await get_team_members("engineering")

# Fetch budgets for each unique level
levels = list(set(m["level"] for m in team))
budget_results = await asyncio.gather(*[
    get_budget_by_level(level) for level in levels
])

# Create a lookup dictionary: {"junior": budget1, "senior": budget2, ...}
budgets = {level: budget for level, budget in zip(levels, budget_results)}

# Fetch all expenses in parallel
expenses = await asyncio.gather(*[
    get_expenses(m["id"], "Q3") for m in team
])

# Find employees who exceeded their travel budget
exceeded = []
for member, exp in zip(team, expenses):
    budget = budgets[member["level"]]
    total = sum(e["amount"] for e in exp)
    if total > budget["travel_limit"]:
        exceeded.append({
            "name": member["name"],
            "spent": total,
            "limit": budget["travel_limit"]
        })

print(json.dumps(exceeded))
```

Claude 的上下文只收到最终结果：超预算的那两三个人。2000+ 条明细、中间汇总、预算查询全部不经过它的上下文，消耗从 200KB 原始费用数据降到 1KB 结果。

效率收益可观：

- **token 节省**：中间结果不进上下文，平均用量从 43588 降到 27297 token，复杂研究任务上降幅 37%。
- **延迟降低**：每次 API 往返都要模型推理（几百毫秒到几秒）。Claude 在一个代码块里编排 20+ 次工具调用时，省掉 19+ 次推理过程。API 处理工具执行，不必每次回到模型。
- **准确率提升**：编排逻辑显式写在代码里，Claude 比用自然语言整理多个工具结果时出错更少。内部知识检索从 25.6% 提升到 28.5%；[GIA 基准](https://arxiv.org/abs/2311.12983)从 46.5% 提升到 51.2%。

生产工作流里有脏数据、条件逻辑与需要规模化的操作。Programmatic Tool Calling 让 Claude 以程序化方式处理这种复杂度，把注意力放在可执行的结果上，无需消耗在原始数据处理上。

### Programmatic Tool Calling 的工作原理

#### 1. 把工具标记为可从代码调用

在 tools 里加入 code_execution，并为选择加入程序化执行的工具设置 allowed_callers：

```json
{
  "tools": [
    {
      "type": "code_execution_20250825",
      "name": "code_execution"
    },
    {
      "name": "get_team_members",
      "description": "Get all members of a department...",
      "input_schema": {},
      "allowed_callers": ["code_execution_20250825"]
    },
    {
      "name": "get_expenses",
      "description": "...",
      "input_schema": {},
      "allowed_callers": ["code_execution_20250825"]
    },
    {
      "name": "get_budget_by_level",
      "description": "...",
      "input_schema": {},
      "allowed_callers": ["code_execution_20250825"]
    }
  ]
}
```

API 把这些工具定义转换为 Claude 可调用的 Python 函数。

#### 2. Claude 写编排代码

Claude 不再逐个请求工具，而是生成 Python 代码：

```json
{
  "type": "server_tool_use",
  "id": "srvtoolu_abc",
  "name": "code_execution",
  "input": {
    "code": "team = get_team_members('engineering')\n..."
  }
}
```

#### 3. 工具执行不经过 Claude 的上下文

代码调用 `get_expenses()` 时，你收到带 caller 字段的工具请求：

```json
{
  "type": "tool_use",
  "id": "toolu_xyz",
  "name": "get_expenses",
  "input": {"user_id": "emp_123", "quarter": "Q3"},
  "caller": {
    "type": "code_execution_20250825",
    "tool_id": "srvtoolu_abc"
  }
}
```

你提供结果，结果在 Code Execution 环境里被处理，Claude 的上下文不消费。代码里每个工具调用都重复这个请求-响应循环。

#### 4. 只有最终输出进入上下文

代码运行结束后，只有代码的结果返回给 Claude：

```json
{
  "type": "code_execution_tool_result",
  "tool_use_id": "srvtoolu_abc",
  "content": {
    "stdout": "[{\"name\": \"Alice\", \"spent\": 12500, \"limit\": 10000}...]"
  }
}
```

这就是 Claude 看到的全部，途中处理的 2000+ 条费用明细它一无所见。

### 何时使用 Programmatic Tool Calling

Programmatic Tool Calling 给工作流加了一个代码执行步骤。当 token 节省、延迟改善与准确率收益足够大时，这点开销值得。

**收益最大的情形：**

- 处理大数据集，只需要汇总或摘要
- 运行三个以上依赖性工具调用的多步工作流
- 在 Claude 看到结果之前做过滤、排序或变换
- 中间数据不应影响 Claude 推理的任务
- 对大量条目并行操作（例如检查 50 个端点）

**收益不大的情形：**

- 简单的单工具调用
- Claude 应当看到并推理全部中间结果的任务
- 响应很小的一次性查询

## Tool Use Examples

### 挑战

JSON Schema 擅长定义结构：类型、必填字段、允许的枚举值。它表达不了使用模式：什么时候带上可选参数、哪些组合有意义、你的 API 约定是什么。

看一个工单 API：

```json
{
  "name": "create_ticket",
  "input_schema": {
    "properties": {
      "title": {"type": "string"},
      "priority": {"enum": ["low", "medium", "high", "critical"]},
      "labels": {"type": "array", "items": {"type": "string"}},
      "reporter": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "contact": {
            "type": "object",
            "properties": {
              "email": {"type": "string"},
              "phone": {"type": "string"}
            }
          }
        }
      },
      "due_date": {"type": "string"},
      "escalation": {
        "type": "object",
        "properties": {
          "level": {"type": "integer"},
          "notify_manager": {"type": "boolean"},
          "sla_hours": {"type": "integer"}
        }
      }
    },
    "required": ["title"]
  }
}
```

schema 定义了什么是合法的，关键问题却悬而未决：

- **格式歧义**：`due_date` 用 "2024-11-06"、"Nov 6, 2024" 还是 "2024-11-06T00:00:00Z"？
- **ID 约定**：`reporter.id` 是 UUID、"USR-12345" 还是纯数字 "12345"？
- **嵌套结构的用法**：什么时候该填 `reporter.contact`？
- **参数关联**：`escalation.level` 与 `escalation.sla_hours` 跟 priority 是什么关系？

这些歧义导致工具调用格式错误、参数用法不一致。

### 我们的方案

Tool Use Examples 让你在工具定义里直接提供调用示例。给 Claude 看具体的使用模式，不单靠 schema：

```json
{
  "name": "create_ticket",
  "input_schema": {},
  "input_examples": [
    {
      "title": "Login page returns 500 error",
      "priority": "critical",
      "labels": ["bug", "authentication", "production"],
      "reporter": {
        "id": "USR-12345",
        "name": "Jane Smith",
        "contact": {
          "email": "jane@acme.com",
          "phone": "+1-555-0123"
        }
      },
      "due_date": "2024-11-06",
      "escalation": {
        "level": 2,
        "notify_manager": true,
        "sla_hours": 4
      }
    },
    {
      "title": "Add dark mode support",
      "labels": ["feature-request", "ui"],
      "reporter": {
        "id": "USR-67890",
        "name": "Alex Chen"
      }
    },
    {
      "title": "Update API documentation"
    }
  ]
}
```

从这三个示例，Claude 学到：

- **格式约定**：日期用 YYYY-MM-DD，用户 ID 是 USR-XXXXX，labels 用 kebab-case
- **嵌套结构模式**：reporter 对象连同嵌套的 contact 对象怎么构造
- **可选参数关联**：critical 级别的 bug 带完整联系信息与紧 SLA 的 escalation；feature request 有 reporter 但没有 contact 与 escalation；内部任务只有 title

我们自己的内部测试里，复杂参数处理上的准确率从 72% 提升到 90%。

### 何时使用 Tool Use Examples

Tool Use Examples 给工具定义增加 token，当准确率提升超过这份成本时最有价值。

**收益最大的情形：**

- 复杂嵌套结构，合法的 JSON 不等于正确的用法
- 可选参数多、是否携带有讲究的工具
- schema 捕捉不到领域约定的 API
- 相近工具靠示例才能区分（如 `create_ticket` 与 `create_incident`）

**收益不大的情形：**

- 用法一目了然的单参数简单工具
- Claude 已经认识的标准格式（URL、邮箱）
- 该交给 JSON Schema 约束处理的校验问题

## 最佳实践

构建在真实世界里执行动作的 agent，意味着同时应对规模、复杂度与精确性。三个特性解决工具使用工作流里不同的瓶颈，下面讲怎么有效组合。

### 按层次布置特性

一个 agent 完成某个任务并非三个特性全都要用。从最大的瓶颈起步：

- 工具定义把上下文撑大 → Tool Search Tool
- 大量中间结果污染上下文 → Programmatic Tool Calling
- 参数错误与调用格式问题 → Tool Use Examples

聚焦的做法让你先解决真正限制 agent 性能的那一项，避免一上来就增加全部复杂度。

然后按需要叠加。三者互补：Tool Search Tool 保证找对工具，Programmatic Tool Calling 保证高效执行，Tool Use Examples 保证正确调用。

### 配置 Tool Search Tool 改善发现效果

工具搜索匹配的是名字与描述，清晰、有信息量的定义能提高发现准确率。

```json
// Good
{
  "name": "search_customer_orders",
  "description": "Search for customer orders by date range, status, or total amount. Returns order details including items, shipping, and payment info."
}

// Bad
{
  "name": "query_db_orders",
  "description": "Execute order query"
}
```

在 system prompt 里写明有哪些类别的工具，让 Claude 知道可搜索什么：

```
You have access to tools for Slack messaging, Google Drive file management,
Jira ticket tracking, and GitHub repository operations. Use the tool search
to find specific capabilities.
```

把最高频的 3-5 个工具保持常驻，其余全部推迟加载。常见操作立即可用，其余按需发现。

### 配置 Programmatic Tool Calling 保证执行正确

Claude 要写代码解析工具输出，所以返回格式要写清楚，帮它写对解析逻辑：

```json
{
  "name": "get_orders",
  "description": "Retrieve orders for a customer.
Returns:
    List of order objects, each containing:
    - id (str): Order identifier
    - total (float): Order total in USD
    - status (str): One of 'pending', 'shipped', 'delivered'
    - items (list): Array of {sku, quantity, price}
    - created_at (str): ISO 8601 timestamp"
}
```

适合选择加入程序化编排的工具：

- 可以并行运行的工具（操作相互独立）
- 可以安全重试的操作（幂等）

### 配置 Tool Use Examples 保证参数准确

示例要为行为清晰而写：

- 用真实感数据（真实城市名、合理价格，别用 "string" 或 "value"）
- 展示多样性：最小、部分、完整三种填写形态
- 保持精炼：每个工具 1-5 个示例
- 聚焦歧义点：只在 schema 看不出正确用法的地方加示例

## 上手起步

这些特性目前处于 beta。启用方法是加 beta header 并带上所需工具：

```python
client.beta.messages.create(
    betas=["advanced-tool-use-2025-11-20"],
    model="claude-sonnet-4-5-20250929",
    max_tokens=4096,
    tools=[
        {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},
        {"type": "code_execution_20250825", "name": "code_execution"},
        # Your tools with defer_loading, allowed_callers, and input_examples
    ]
)
```

详细的 API 文档与 SDK 示例见：

- Tool Search Tool 的[文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)与[cookbook](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/tool_search_with_embeddings.ipynb)
- Programmatic Tool Calling 的[文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)与[cookbook](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/programmatic_tool_calling_ptc.ipynb)
- Tool Use Examples 的[文档](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use#providing-tool-use-examples)

这些特性把工具使用从简单的函数调用推向智能编排。当 agent 处理跨越几十个工具与大数据集的复杂工作流时，动态发现、高效执行与可靠调用成为地基。

我们期待看到你构建的东西。

## 作者与致谢

由 Bin Wu 撰写，Adam Jones、Artur Renault、Henry Tay、Jake Noble、Noah Picard、Sam Jiang 与 Claude Developer Platform 团队贡献。本文基于 Chris Gorgolewski、Daniel Jiang、Jeremy Fox 与 Mike Lambert 的基础研究。我们还从 AI 生态中汲取了灵感，包括 [Joel Pobar 的 LLMVM](https://github.com/9600dev/llmvm)、[Cloudflare 的 Code Mode](https://blog.cloudflare.com/code-mode/) 与 [Code Execution as MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)。特别感谢 Andy Schumeister、Hamish Kerr、Keir Bradwell、Matt Bleifer 与 Molly Vorwerck 的支持。
