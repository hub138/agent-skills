# Claude API 入门总纲：模型、消息、思考、工具与流式

- 原文：[API usage primer for Claude](https://platform.claude.com/docs/en/claude_api_primer)
- 来源：Anthropic 官方文档（md 直链抓取，27KB 全文）
- 发布：官方文档页，随 API 持续更新
- 译文说明：原文为英文，本篇为按本包语言规则的合规改写整理，术语保留英文原词。原文自称「给 Claude 的基础指南：模型 ID、基本 Messages API、工具使用、流式、thinking，仅此而已」，收编时保留全部正文结构。

本页是 Claude API 的入门总纲：模型选型、基本请求与响应、多轮对话、预填充、视觉、thinking、工具使用、流式。它是官方给「第一次接 API」场景写的最小知识集，覆盖之外的一切话题都跳转到专门页。

## 模型清单

| 定位 | 模型 | ID |
|---|---|---|
| 多数工作的推荐默认，含复杂 agentic coding | Claude Opus 5.5 | `claude-opus-5-5` |
| 最难的长时 agentic 与研究任务，价格为 Opus 5.5 的 2.5 倍 | Claude Fable 5.1 | `claude-fable-5-1` |
| 上一代 Opus | Claude Opus 5 | `claude-opus-5` |
| smart 模型 | Claude Sonnet 5.5 | `claude-sonnet-5-5` |
| 上一代 Sonnet | Claude Sonnet 5 | `claude-sonnet-5` |
| 快速与成本敏感任务 | Claude Haiku 5.5 | `claude-haiku-5-5` |
| 上一代 Haiku | Claude Haiku 4.5 | `claude-haiku-4-5-20251001` |

## 基本请求与响应

Python SDK 的最小请求只有三要素：`model`、`max_tokens`、`messages`。响应里关注四个字段：`content`（内容块列表）、`stop_reason`（停止原因，`end_turn` 表示自然结束）、`usage`（`input_tokens` 与 `output_tokens` 计数）。

## 多轮对话与无状态

Messages API 是无状态的：每次请求都要发送完整对话历史。早先的对话轮不必真的来自 Claude，可以用合成的 `assistant` 消息构造你想要的对话起点。

message threads（beta）可以让 API 保存对话，后续请求只发新消息。thread 在最后一次请求后 5 分钟过期，最迟在最后一次使用后 1 小时删除。

## 预填充 Claude 的响应

可以在输入 `messages` 列表的最后位置预填充 Claude 响应的一部分，用这个技术塑造响应形态。官方例子用 `max_tokens: 1` 从 Claude 手里拿到单选答案：user 问「蚂蚁的拉丁文是 (A) Apoidea、(B) Rhopalocera、(C) Formicidae」，assistant 预填「The answer is (」，Claude 补出「C)」就到顶停止。

Claude 4.6 及之后模型与 Claude Mythos Preview 不支持 assistant 消息预填充，请求必须以 user 消息结尾。

## 视觉

Claude 能读请求里的文本与图片。图片支持 `base64` 与 `url` 两种来源类型，支持 `image/jpeg`、`image/png`、`image/gif`、`image/webp` 四种媒体类型。

## Thinking

thinking 有时帮助 Claude 处理很难的任务。当前机制是 adaptive thinking（`thinking: {"type": "adaptive"}`）：Claude 自己决定何时思考、思考多少，思考深度用 `effort` 参数调节，没有 token 预算这回事。adaptive thinking 在 Claude 4.6 及之后模型与 Mythos Preview 上支持；Claude 5 及之后模型上省略 `thinking` 参数时默认开启。

支持矩阵（按模型）：Opus 5.5、Fable 5.1、Mythos 5.1、Fable 5、Mythos 5 均为 adaptive only 且 always on；Sonnet 5.5 与 Haiku 5.5 均为 adaptive only 且默认开启（Sonnet 5.5 上 `thinking: {"type": "disabled"}` 返回 400，要关闭前置思考发 `thinking: {"type": "between_tools"}`）；Opus 5 与 Sonnet 5 均为 adaptive only 且默认开启；Opus 4.8 与 4.7 为 adaptive only；Opus 4.6 与 Sonnet 4.6 支持 adaptive 或 legacy manual 两种；Opus 4.5、Sonnet 4.5（已弃用）、Haiku 4.5 仅支持 legacy manual。

Claude 4.7 及之后模型上，manual extended thinking（`type: "enabled"` 带 `budget_tokens`）返回 400 错误，改用 adaptive thinking。

### thinking 怎么运作

thinking 开启时，Claude 生成 `thinking` 内容块输出内部推理，API 响应里 `thinking` 块在前、`text` 块在后。`display: "summarized"` 时拿到的是思考摘要。

manual extended thinking 是旧机制：`budget_tokens` 给内部推理设 token 上限，上限作用于完整 thinking token，不作用于摘要输出。除非用 interleaved thinking，`budget_tokens` 必须小于 `max_tokens`，给思考完成后的响应留空间。

### thinking 与工具并用

两条重要限制：

1. 工具选择限制：manual extended thinking 下只支持 `tool_choice: {"type": "auto"}`（默认）与 `{"type": "none"}`。adaptive thinking 接受强制工具调用（Opus 5.5、Sonnet 5.5、Fable 5.1、Mythos 5.1 四个模型除外，它们返回 400）。接受强制工具调用的场景里，强制调用跳过 thinking：响应直接从工具调用开始，没有 `thinking` 块。
2. 保留 thinking 块：工具使用期间，最后一条 assistant 消息的 `thinking` 块必须原样传回 API。

### interleaved thinking

interleaved thinking 允许 Claude 在工具调用之间思考，先消化工具结果再定下一步。adaptive thinking 的模型上自动启用，无需 beta header。旧模型（Claude 4、4.5、Sonnet 4.6 的 manual extended thinking）要加 `interleaved-thinking-2025-05-14` beta header。

interleaved thinking 且仅在 interleaved thinking 下（普通 manual extended thinking 不行），`budget_tokens` 可以超过 `max_tokens`：此时 `budget_tokens` 代表一个 assistant 回合内全部 thinking 块的总预算。

## 工具使用

### 指定客户端工具

客户端工具在请求顶层 `tools` 参数里指定，每个工具定义三个字段：`name`（须匹配正则 `^[a-zA-Z0-9_-]{1,128}$`）、`description`（说明工具做什么、何时用、行为方式的详细纯文本）、`input_schema`（定义预期参数的 JSON Schema 对象）。

### 工具定义最佳实践

- 提供极详细的 description。这是工具性能最重要的因素。description 要解释工具的全部细节：做什么、何时用（何时不用）、每个参数的含义与对行为的影响、重要的警示与限制。
- 复杂工具考虑 `input_examples`。嵌套对象、可选参数或格式敏感输入的工具，可以用 `input_examples` 字段（beta）提供具体示例，给 Claude 看预期输入形态。示例须通过 input_schema 校验（无效示例返回 400），服务端工具（web search、代码执行）不支持，示例增加 prompt token（简单 20-50、复杂嵌套 100-200）。

官方的范例 description（get_stock_price）：说明工具取当前股价、ticker 必须是 NYSE 或 NASDAQ 上市公司的有效代码、返回美元最新成交价、在用户问当前或最近股价时使用、不提供该股票或公司的任何其他信息。

## 控制 Claude 的输出

### 强制工具使用

`tool_choice` 有四种取值：`auto`（Claude 自己决定是否调用工具，默认）、`any`（必须用所提供的工具之一）、`tool`（强制始终用某个特定工具）、`none`（禁止用任何工具）。

Opus 5.5、Sonnet 5.5、Fable 5.1、Mythos 5.1 四个模型上 `any` 与 `tool` 返回 400 错误。保持 `tool_choice` 为 `auto` 并给工具标 `"strict": true`，保证 Claude 的任何调用都符合 `input_schema`。

### JSON 输出

工具不必是客户端函数。想让模型按给定 schema 返回 JSON 输出时，任何时候都可以用工具实现。

### 并行工具使用

默认情况下 Claude 可能用多个工具回答一个请求。设 `disable_parallel_tool_use=true` 关闭这个行为。

## 处理 tool_use 与 tool_result 内容块

### 处理客户端工具的结果

响应的 `stop_reason` 为 `tool_use`，带一个或多个 `tool_use` 内容块，每块三字段：`id`（本次工具使用的唯一标识）、`name`（工具名）、`input`（传给工具的输入对象）。收到后三步：提取 `name`、`id`、`input`；在代码里运行对应工具；把含 `tool_result` 块的新 user 消息发回去续话。`tool_result` 带 `tool_use_id` 与 `content`。

### 处理 max_tokens 停止原因

工具使用中响应因 `max_tokens` 上限被切断时，加大 `max_tokens` 重试请求。

### 处理 pause_turn 停止原因

用 web search 这类服务端工具时，API 可能返回 `pause_turn` 停止原因。把暂停的响应原样传回后续请求继续对话。

## 错误排查

### 工具执行错误

工具自身执行中抛错时，把错误消息随 `"is_error": true` 返回：

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01A09q90qw90lq917835lq9",
      "content": "ConnectionError: the weather service API is not available (HTTP 500)",
      "is_error": true
    }
  ]
}
```

### 无效工具名

Claude 尝试的工具使用无效（如缺必填参数）时，给工具定义配更详细的 `description` 值重试请求。

## 流式消息

创建 Message 时设 `"stream": true`，用 server-sent events（SSE）增量接收响应。SDK 侧 Python 用 `client.messages.stream` 上下文管理器，逐段拿到 `text_stream`。

### 事件类型

每个 SSE 事件带具名事件类型与关联 JSON 数据。事件流：

1. `message_start`：含空 `content` 的 Message 对象。
2. 一系列内容块，每块 `content_block_start`、一个或多个 `content_block_delta`、`content_block_stop`。
3. 一个或多个 `message_delta` 事件，指示最终 Message 对象的顶层变更。
4. 最终 `message_stop` 事件。

警示：`message_delta` 事件 `usage` 字段里的 token 计数是累计值。

### 内容块 delta 类型

- text delta：`{"type": "text_delta", "text": "Hello frien"}`。
- input JSON delta：`tool_use` 块的 delta 是部分 JSON 字符串，`{"type": "input_json_delta", "partial_json": "{\"location\": \"San Fra"}`，客户端拼接后再解析。
- thinking delta：thinking 流式时 `{"type": "thinking_delta", "thinking": "Let me solve this step by step..."}`。

官方页末尾给了完整的 SSE 事件序列示例（message_start → content_block_start → 两次 text_delta → content_block_stop → message_delta 带 stop_reason 与累计 usage → message_stop），可直接当作客户端解析状态机的参照。

> 包内互引：message threads 的 beta 细节与过期语义见 claude-message-threads.md；adaptive thinking 与 effort 的完整机制见 claude-sonnet-building.md 与 sonnet-prompting.md；strict tool use 与工具故障排查见 claude-handle-tool-calls.md 与 claude-troubleshooting-tool-use.md；模型迁移的 thinking 清单见 claude-sonnet-migration.md。
