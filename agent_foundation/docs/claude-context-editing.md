# 上下文编辑：清除、保留与压缩（Context editing）

- 原文：[Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- 来源：Anthropic 官方文档（Claude Platform Docs）
- 发布：文档未标注日期（2026-11-04 抓取版本）
- 译文说明：全文翻译，术语保留英文原词，代码块逐行保留英文；文档内相对链接已转为 platform.claude.com 绝对地址。

## 概览

上下文编辑允许你在对话历史增长的过程中，选择性地清除其中的特定内容。这件事的价值超出优化成本与守住上下文上限：它是在主动策展 Claude 收到的信息。上下文是边际收益递减的有限资源，无关内容会削弱模型的专注度，上下文编辑把这层策展变成运行时可以精细控制的操作。上下文管理背后的整体原则见[面向 AI agent 的高效上下文工程](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)。本页覆盖：

- **工具结果清除（tool result clearing）**：最适合工具调用密集的 agentic 工作流，旧的工具结果在 Claude 处理完之后就不再需要
- **thinking block 清除（thinking block clearing）**：管理早前轮次的 thinking block，可选择保留近期 thinking 维持推理连贯
- **客户端 SDK 压缩（client-side SDK compaction）**：基于摘要管理上下文的 SDK 方案（多数场景推荐服务端压缩）

| 方案 | 运行位置 | 策略 | 工作方式 |
| --- | --- | --- | --- |
| 服务端 | API | 工具结果清除（`clear_tool_uses_20250919`）、thinking block 清除（`clear_thinking_20251015`） | 在 prompt 到达 Claude 之前生效，从对话历史中清除特定内容，每个策略可独立配置。 |
| 客户端 | SDK | Compaction（压缩） | [TypeScript 与 Ruby SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/overview) 配合 [`tool_runner`](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner) 时可用：生成一份摘要并替换整个对话历史。见下文「客户端压缩」一节。 |

## 服务端策略

### 工具结果清除

`clear_tool_uses_20250919` 策略在对话上下文增长超过你配置的阈值后清除工具结果。这对工具调用密集的 agentic 工作流特别有用：旧的工具结果（例如文件内容或搜索结果）在 Claude 处理完之后就不再需要。

策略激活后，API 按时间顺序自动清除最老的工具结果，并在每个被清除的位置替换为一段占位文字，向 Claude 说明该内容已被移除。默认只清除工具结果；把 `clear_tool_inputs` 设为 true，可以连工具调用本身（工具入参）一起清除。

### thinking block 清除

`clear_thinking_20251015` 策略管理早前 assistant 轮次的 `thinking` block。这个策略把 thinking 的保留程度交给你控制：可以多保留一些 thinking block 维持推理连贯，也可以更激进地清除以节省上下文空间。

assistant 的一个对话轮次可能包含多个内容 block（例如使用工具时），也可能包含多个 thinking block（例如开启 [interleaved thinking](https://platform.claude.com/docs/en/build-with-claude/thinking#interleaved-thinking) 时）。

### 上下文编辑发生在服务端

上下文编辑在服务端执行，先于 prompt 到达 Claude。你的客户端应用继续保存完整、未被修改的对话历史，无需把客户端状态同步成被编辑过的版本，照常在本地管理完整对话即可。

在 Claude 5.1 与更新的模型上，服务端上下文管理不会让 thinking block 失效。客户端对早前轮次的编辑则可能让其后每一个 assistant 轮次的 thinking block 全部失效，见[保持前缀不变](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking#prefix-check)。

### 上下文编辑与 prompt caching

上下文编辑与 [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) 的交互随策略不同：

- **工具结果清除**：清除内容会让已缓存的 prompt 前缀失效。为了让每次缓存失效都值得，一次要清除足够多的 token，用 `clear_at_least` 参数保证每次激活至少清除这个数量。每次清除都会产生一次缓存写入成本，之后的请求可以复用新缓存的前缀。
- **thinking block 清除**：thinking block 保留在上下文中（未被清除）时，prompt 缓存保持有效，可以命中缓存、降低输入 token 成本；thinking block 被清除时，缓存从清除发生的位置起失效。按「优先缓存性能还是优先上下文窗口空间」来决定 `keep` 参数的取值。

### 支持的模型

上下文编辑在全部受支持的 Claude 模型上可用。

## 工具结果清除的用法

启用工具结果清除最简单的方式是只写策略类型，其余配置项全部使用默认值：

```
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=4096,
    messages=[{"role": "user", "content": "Search for recent developments in AI"}],
    tools=[{"type": "web_search_20250305", "name": "web_search"}],
    betas=["context-management-2025-06-27"],
    context_management={"edits": [{"type": "clear_tool_uses_20250919"}]},
)
```

### 进阶配置

可以用更多参数定制工具结果清除的行为：

```
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=4096,
    messages=[
        {
            "role": "user",
            "content": "Create a simple command line calculator app using Python",
        }
    ],
    tools=[
        {
            "type": "text_editor_20250728",
            "name": "str_replace_based_edit_tool",
            "max_characters": 10000,
        },
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
    ],
    betas=["context-management-2025-06-27"],
    context_management={
        "edits": [
            {
                "type": "clear_tool_uses_20250919",
                # Trigger clearing when threshold is exceeded
                "trigger": {"type": "input_tokens", "value": 30000},
                # Number of tool uses to keep after clearing
                "keep": {"type": "tool_uses", "value": 3},
                # Optional: Clear at least this many tokens
                "clear_at_least": {"type": "input_tokens", "value": 5000},
                # Exclude these tools from being cleared
                "exclude_tools": ["web_search"],
            }
        ]
    },
)
```

## thinking block 清除的用法

在携带早前轮次 thinking block 的对话里，用 thinking block 清除管理上下文与 prompt caching：

```
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    messages=[{"role": "user", "content": "Hello"}],
    betas=["context-management-2025-06-27"],
    context_management={
        "edits": [
            {
                "type": "clear_thinking_20251015",
                "keep": {"type": "thinking_turns", "value": 2},
            }
        ]
    },
)
```

### thinking block 清除的配置项

`clear_thinking_20251015` 策略支持以下配置：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `keep` | 按模型而定 | 定义保留最近多少个带 thinking block 的 assistant 轮次。`{type: "thinking_turns", value: N}` 中 N 必须大于 0，表示保留最近 N 个轮次；填 `"all"` 保留全部 thinking block。Opus 4.5+、Sonnet 4.6+、Haiku 5.5+ 默认保留全部轮次；Fable 与 Mythos 模型保留全部轮次；更早的 Opus/Sonnet 与到 Claude Haiku 4.5 为止的 Haiku 默认只保留最近一个轮次。 |

保留最近 3 个 assistant 轮次的 thinking block：

```
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    messages=[{"role": "user", "content": "Hello"}],
    betas=["context-management-2025-06-27"],
    context_management={
        "edits": [
            {
                "type": "clear_thinking_20251015",
                "keep": {"type": "thinking_turns", "value": 3},
            }
        ]
    },
)
```

保留全部 thinking block（最大化缓存命中）：

```
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    messages=[{"role": "user", "content": "Hello"}],
    betas=["context-management-2025-06-27"],
    context_management={
        "edits": [
            {
                "type": "clear_thinking_20251015",
                "keep": "all",
            }
        ]
    },
)
```

### 组合两个策略

thinking block 清除与工具结果清除可以同时使用：

```
client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    messages=[
        {
            "role": "user",
            "content": "Search for the latest developments in quantum error correction and summarize the key breakthroughs.",
        }
    ],
    tools=[
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
        }
    ],
    betas=["context-management-2025-06-27"],
    context_management={
        "edits": [
            {
                "type": "clear_thinking_20251015",
                "keep": {"type": "thinking_turns", "value": 2},
            },
            {
                "type": "clear_tool_uses_20250919",
                "trigger": {"type": "input_tokens", "value": 50000},
                "keep": {"type": "tool_uses", "value": 5},
            },
        ]
    },
)

print(response)
```

## 工具结果清除的配置项

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `trigger` | 100,000 input tokens | 定义策略何时激活。prompt 超过这个阈值后开始清除。取值可以按 `input_tokens`，也可以按 `tool_uses`。 |
| `keep` | 3 tool uses | 清除发生后保留最近多少组工具调用与结果。API 先移除最老的工具交互，保留最近的。 |
| `clear_at_least` | None | 保证每次激活至少清除这个数量的 token。API 做不到时，本次不应用清除。这个参数用来判断「为了清除而打破 prompt 缓存」是否值得。 |
| `exclude_tools` | None | 永不清除其调用与结果的工具名列表，用于保住重要上下文。 |
| `clear_tool_inputs` | `false` | 控制工具调用参数是否随工具结果一起清除。默认只清除工具结果，保留 Claude 原始的工具调用。 |

## 上下文编辑的响应

用响应里的 `context_management` 字段可以看到本次请求实际应用了哪些编辑，以及被清除的内容与输入 token 统计：

```
{
  "id": "msg_013Zva2CMHLNnXjNJJKqJ2EF",
  "type": "message",
  "role": "assistant",
  "content": [
    // ...
  ],
  "usage": {
    // ...
  },
  "context_management": {
    "applied_edits": [
      // When using `clear_thinking_20251015`
      {
        "type": "clear_thinking_20251015",
        "cleared_thinking_turns": 3,
        "cleared_input_tokens": 15000
      },
      // When using `clear_tool_uses_20250919`
      {
        "type": "clear_tool_uses_20250919",
        "cleared_tool_uses": 8,
        "cleared_input_tokens": 50000
      }
    ]
  }
}
```

流式响应里，上下文编辑信息包含在最后的 `message_delta` 事件中：

```
{
  "type": "message_delta",
  "delta": {
    "stop_reason": "end_turn",
    "stop_sequence": null
  },
  "usage": {
    "output_tokens": 1024
  },
  "context_management": {
    "applied_edits": [
      // ...
    ]
  }
}
```

## token 计数预览

[token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) 端点支持 context management，可以在发送前预览上下文编辑生效后 prompt 会占用多少 token：

```
response = client.beta.messages.count_tokens(
    model="claude-opus-5-5",
    messages=[{"role": "user", "content": "Continue our conversation..."}],
    betas=["context-management-2025-06-27"],
    context_management={
        "edits": [
            {
                "type": "clear_tool_uses_20250919",
                "trigger": {"type": "input_tokens", "value": 30000},
                "keep": {"type": "tool_uses", "value": 5},
            }
        ]
    },
)

print(f"Original tokens: {response.context_management.original_input_tokens}")
print(f"After clearing: {response.input_tokens}")
print(
    f"Savings: {response.context_management.original_input_tokens - response.input_tokens} tokens"
)
```

```
{
  "input_tokens": 25000,
  "context_management": {
    "original_input_tokens": 70000
  }
}
```

响应同时给出应用上下文管理之后的最终 token 数（`input_tokens`）与清除发生前的原始 token 数（`original_input_tokens`）。

## 与 memory tool 配合使用

上下文编辑可以与 [memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool) 组合。对话上下文接近你配置的清除阈值时，Claude 会收到一条自动提醒，提示它保存重要信息。这让 Claude 可以在工具结果被清除前，先把其中的重要内容写进 memory 文件。

这个组合带来三个能力：

- **保住重要上下文**：Claude 可以在工具结果被清除前，把其中的关键信息写进 memory 文件。
- **维持长时运行的工作流**：把信息转移到持久存储后，agentic 工作流可以继续跑下去，不会撞上上下文上限。
- **按需取回信息**：需要时 Claude 从 memory 文件查回先前被清除的信息，无需把一切常驻在活动上下文窗口里。

例如在文件编辑工作流中，Claude 执行大量操作时可以随上下文增长，把已完成的改动摘要写进 memory 文件；工具结果被清除后，它仍能通过自己的记忆系统访问这些信息并继续工作。

两个特性一起启用：

```
response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=4096,
    messages=[{"role": "user", "content": "Hello"}],
    tools=[{"type": "memory_20250818", "name": "memory"}],
    betas=["context-management-2025-06-27"],
    context_management={"edits": [{"type": "clear_tool_uses_20250919"}]},
)
```

完整的 memory tool 参考（命令与示例）见 [Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)。

## 客户端压缩（SDK）

Compaction 是 SDK 的一个特性：token 用量增长过大时，自动生成摘要来管理对话上下文。服务端的上下文编辑策略直接清除内容，compaction 的做法是让 Claude 为对话历史生成一份摘要，随后用这份摘要替换整个历史。这让 Claude 能在长时任务上继续工作，不会超出[上下文窗口](https://platform.claude.com/docs/en/build-with-claude/context-windows)。

### compaction 的工作方式

启用后，SDK 在每次模型响应后检查 token 用量：

1. **阈值检查**：SDK 按 `input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens` 计算总 token（缓存相关字段的含义见 [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)）。
2. **生成摘要**：超过阈值后，一条摘要提示词作为 user 轮次注入，Claude 生成一份结构化摘要，包裹在 `<summary></summary>` 标签里。
3. **替换上下文**：SDK 提取摘要，用替换掉整个消息历史。
4. **继续执行**：对话从摘要恢复，Claude 从停下的地方继续。

### 启用 compaction

在 `tool_runner` 调用里加上 `compaction_control`，token 用量超过阈值时自动触发摘要。

### compaction 过程中的变化

随着对话增长，消息历史不断累积。

压缩前（接近 100k token）：

```
[
  { "role": "user", "content": "Analyze all files and write a report..." },
  { "role": "assistant", "content": "I'll help. Let me start by reading..." },
  {
    "role": "user",
    "content": [{ "type": "tool_result", "tool_use_id": "...", "content": "..." }]
  },
  { "role": "assistant", "content": "Based on file1.txt, I see..." },
  {
    "role": "user",
    "content": [{ "type": "tool_result", "tool_use_id": "...", "content": "..." }]
  },
  { "role": "assistant", "content": "After analyzing file2.txt..." }
  // ... 50 more exchanges like this ...
]
```

token 超过阈值后，SDK 注入摘要请求，Claude 生成摘要，随后整个历史被替换。

压缩后（回到约 2-3k token）：

```
[
  {
    "role": "assistant",
    "content": "# Task Overview\nThe user requested analysis of directory files to produce a summary report...\n\n# Current State\nAnalyzed 52 files across 3 subdirectories. Key findings documented in report.md...\n\n# Important Discoveries\n- Configuration files use YAML format\n- Found 3 deprecated dependencies\n- Test coverage at 67%\n\n# Next Steps\n1. Analyze remaining files in /src/legacy\n2. Complete final report sections...\n\n# Context to Preserve\nUser prefers markdown format with executive summary first..."
  }
]
```

Claude 把这份摘要当作原始对话历史继续工作。

### 配置项

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `enabled` | boolean | 是 | - | 是否启用自动 compaction |
| `context_token_threshold` | number | 否 | 100,000 | 触发 compaction 的 token 数 |
| `model` | string | 否 | 与主模型相同 | 生成摘要使用的模型 |
| `summary_prompt` | string | 否 | 见默认摘要提示词 | 自定义摘要生成提示词 |

#### 阈值怎么选

阈值决定 compaction 何时发生。低阈值意味着更频繁的压缩与更小的上下文窗口；高阈值保留更多上下文，但更接近上限风险。

#### 换一个模型生成摘要

可以用更快或更便宜的模型生成摘要，配置方式见上表 `model` 参数。

#### 自定义摘要提示词

可以为特定领域写自定义提示词，提示词要指示 Claude 把摘要包在 `<summary></summary>` 标签里。

### 默认摘要提示词

内置的摘要提示词要求 Claude 生成结构化的续作摘要，包含五部分：

1. **Task Overview（任务概览）**：用户的核心请求、成功标准与约束。
2. **Current State（当前状态）**：已完成的内容、修改过的文件、产出的工件。
3. **Important Discoveries（重要发现）**：技术约束、做过的决策、解决过的错误、试过但失败的路线。
4. **Next Steps（下一步）**：完成任务的具体动作、阻塞项与优先顺序。
5. **Context to Preserve（要保留的上下文）**：用户喜好、领域细节、对用户做过的承诺。

这个结构让 Claude 能高效恢复工作，既不丢重要上下文，也不重复犯错。

### 默认提示词全文

```
You have been working on the task described above but have not yet completed it. Write a continuation summary that will allow you (or another instance of yourself) to resume work efficiently in a future context window where the conversation history will be replaced with this summary. Your summary should be structured, concise, and actionable. Include:

1. Task Overview
The user's core request and success criteria
Any clarifications or constraints they specified

2. Current State
What has been completed so far
Files created, modified, or analyzed (with paths if relevant)
Key outputs or artifacts produced

3. Important Discoveries
Technical constraints or requirements uncovered
Decisions made and their rationale
Errors encountered and how they were resolved
What approaches were tried that didn't work (and why)

4. Next Steps
Specific actions needed to complete the task
Any blockers or open questions to resolve
Priority order if multiple steps remain

5. Context to Preserve
User preferences or style requirements
Domain-specific details that aren't obvious
Any promises made to the user

Be concise but complete—err on the side of including information that would prevent duplicate work or repeated mistakes. Write in a way that enables immediate resumption of the task.

Wrap your summary in <summary></summary> tags.
```

### 限制

#### 服务端工具

使用服务端工具时，SDK 可能算错 token 用量，导致 compaction 在错误的时机触发。

例如一次 web search 之后，API 响应可能是：

```
{
  "usage": {
    "input_tokens": 63000,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 270000,
    "output_tokens": 1400
  }
}
```

SDK 把总用量算成 63,000 + 0 + 270,000 + 1,400 = 334,400 token。但 `cache_read_input_tokens` 里累计的是服务端工具内部多次 API 调用的读取量，并非你真实的对话上下文。真实上下文长度可能只有 63,000 的 `input_tokens`，SDK 却按 334k 计算并过早触发了 compaction。

应对方式：

- 用 [token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) 端点获取准确的上下文长度。
- 大量使用服务端工具时避免开启 compaction。

#### 工具调用的边界情况

SDK 在一个工具调用响应尚未返回时触发 compaction，会在生成摘要前把该工具调用 block 从消息历史里移除。恢复后如果仍需要该调用，Claude 会重新发起。

### 监控 compaction

了解 compaction 何时触发，有助于调整阈值与验证行为是否符合预期。

### 什么时候用 compaction

适合的场景：

- 处理大量文件或数据源的长时 agent 任务
- 累积大量信息的研究工作流
- 有清晰可度量进展的多步骤任务
- 产出物（文件、报告）在对话之外持久存在的任务

不太适合的场景：

- 需要精确取回早前对话细节的任务
- 大量使用服务端工具的工作流
- 需要在大量变量之间维持精确状态的任务

## 后续步骤

- 用服务端 compaction 管理长对话，这是多数场景推荐的策略。
- 用 prompt 前缀缓存降低成本与延迟，了解上下文编辑与缓存的交互。

## 可用性

上下文编辑在全部模型上处于 beta，且符合零数据保留（zero data retention）条件。

### API 支持

- Claude API
- [Claude Platform on AWS](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws)
- [Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- [Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy) InvokeModel
- [Claude Models on Google Cloud](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed) Google managed
- [Microsoft Foundry](https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry)

### 必需的 beta header

Beta header 让你在实验特性与新模型能力进入标准 API 之前使用它们：

- `context-management-2025-06-27`

### 数据处理

适用端点：

- 带 `context_management` 的 `/v1/messages`

不适用于[受覆盖模型](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention#model-specific-data-retention-requirements)。

上下文编辑（工具结果清除与 thinking 清除）实时应用。

> 包内互引：同日发布的配对能力（跨会话文件式记忆、/memories 目录六命令）见 claude-memory-tool.md；compaction 与 just-in-time 的原则见 context-engineering.md；SDK 侧消息线程见 claude-message-threads.md；ZDR 合格声明与保留例外见 claude-data-retention.md。
