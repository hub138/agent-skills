# DeepSeek Responses API：兼容性明细

- 原文：[使用 Responses API](https://api-docs.deepseek.com/zh-cn/guides/responses_api)
- 来源：DeepSeek 官方 API 文档
- 发布：官方文档页，随 DeepSeek 版本持续更新
- 译文说明：原文为中文，本篇为按本包语言规则的合规改写整理，术语保留英文原词。原文其余部分（接入 Codex 的配置步骤、图片输入与使用限制）单薄或已并入本文相应小节，完整兼容性明细保留全部表格。

为了满足对 Codex 的需求，DeepSeek API 新增了对 Responses API 格式的支持，`base_url` 为 `https://api.deepseek.com`。通过简单配置即可在 Codex 中使用 DeepSeek 模型，接入步骤见官方「接入 Codex」页。

## 基本调用

```python
from openai import OpenAI

client = OpenAI(api_key="<your DeepSeek API Key>", base_url="https://api.deepseek.com")

response = client.responses.create(
    model="该快速模型",
    instructions="You are a helpful assistant.",
    input="Hi, how are you?",
)

print(response.output_text)
```

## 流式输出

设置 `stream: true` 后，响应以语义化的 SSE 事件序列返回。每个事件带表示事件类型的 `event` 字段与递增的 `sequence_number`。流以 `response.completed` / `response.incomplete` / `response.failed` 事件结束，没有 `data: [DONE]` 消息。

```python
stream = client.responses.create(
    model="该快速模型",
    instructions="You are a helpful assistant.",
    input="Hi, how are you?",
    stream=True,
)

for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="")
```

完整事件列表：

| 事件 | 说明 |
|---|---|
| `response.created` | 首个事件；响应已创建，状态为 `in_progress` |
| `response.in_progress` | 响应正在生成中 |
| `response.output_item.added` / `response.output_item.done` | 一个输出 item（`reasoning` / `message` / `function_call` / `custom_tool_call` / `web_search_call` / `tool_search_call`）开始 / 完成 |
| `response.content_part.added` / `response.content_part.done` | 输出 item 中的一个内容块开始 / 完成 |
| `response.reasoning_text.delta` / `response.reasoning_text.done` | 思维链文本增量 / 完整思维链文本 |
| `response.output_text.delta` / `response.output_text.done` | 输出文本增量 / 完整输出文本 |
| `response.function_call_arguments.delta` / `response.function_call_arguments.done` | Function 调用参数增量 / 完整参数 |
| `response.custom_tool_call_input.delta` / `response.custom_tool_call_input.done` | Custom 工具调用（`apply_patch`）输入增量 / 完整输入 |
| `response.web_search_call.in_progress` / `response.web_search_call.searching` / `response.web_search_call.completed` | 服务端 `web_search` 调用开始 / 搜索中 / 完成（仅 `该推理模型`） |
| `response.completed` | 响应正常完成时的最后一个事件，携带包含 `usage` 的完整 `response` 对象 |
| `response.incomplete` | 响应被截断（如达到 `max_output_tokens`）时的最后一个事件，携带完整 `response` 对象 |
| `response.failed` | 响应失败时的最后一个事件，携带含 `error` 详情的完整 `response` 对象 |

## 图片输入

Responses API 支持用 `该快速模型` 传入图片，限制与格式和对话补全的图像理解一致。图片通过 `message` item 中的 `input_image` 内容块提供，`image_url`（http(s) URL 或 base64 data URL）与 `file_id`（Files API 上传的图片文件 ID，形如 `file-api-...`）二选一，互斥：都不传返回 `400`（`input_image must have image_url or file_id`），都传返回 `400`（`input_image cannot have both image_url and file_id`）。`detail` 取 `low` / `high` / `original` / `auto`，`low` 在推理前把图片缩小到 512x512，其余取值保留原图，设置 `file_id` 时被忽略。

`input_image` 内容块也可以出现在 `function_call_output` / `custom_tool_call_output` item 的 `output` 中，让模型接收你的工具生成的图片（例如截图）：

```python
input=[
    {"role": "user", "content": "读取工具返回的截图。"},
    {"type": "function_call", "call_id": "fc1", "name": "take_screenshot", "arguments": "{}"},
    {"type": "function_call_output", "call_id": "fc1",
     "output": [{"type": "input_image", "image_url": "data:image/png;base64,<BASE64_DATA>"}]},
]
```

图片仅允许出现在 `user` / `developer` 消息 item 与 `function_call_output` / `custom_tool_call_output` 的输出中，`system` / `assistant` 消息中的图片返回 `400` 错误。`该快速模型` 会真正处理 `input_image` 内容块。对话补全的图片限制同样适用（内联单张 32 MiB、`file_id` 单张 64 MiB、不含 `file_id` 图片总计 64 MiB、含 `file_id` 图片最高 200 MiB、单请求 600 张等）。

## 兼容性明细

本节罗列 DeepSeek API 对 Responses API 的兼容性细节。Responses API 完整格式定义参考 OpenAI 官方 API 手册。不支持的参数会被静默忽略、不报错，现有 Responses API 客户端无需修改即可接入。

### 顶层请求参数

| 参数 | 支持情况 |
|---|---|
| `model` | 支持。`该快速模型` 与 `该推理模型` |
| `input` | 支持。字符串或输入 item 列表；`input` 与 `instructions` 至少传一个 |
| `instructions` | 支持。作为第一条 system 消息 |
| `stream` | 支持 |
| `temperature` | 支持（范围 [0.0, 2.0]；思考模式下不生效） |
| `top_p` | 支持；行为因模型而异：`该快速模型` 思考模式下生效（下限 0.95）、非思考模式下恒为 1.0；`该推理模型` 思考模式下忽略传入值（启用工具调用时固定为 0.95，否则 1.0）、非思考模式下生效。即使提供 `tools`，把 `tool_choice` 设为 `none` 也会关闭工具调用 |
| `max_output_tokens` | 支持 |
| `top_logprobs` | 支持（范围 [0, 20]） |
| `tools` | 部分支持。`function` 支持；`web_search` 在 `该推理模型` 下支持；其他类型忽略 |
| `tool_choice` | 支持。`none` / `auto` / `required` / 指定某个工具 |
| `reasoning` | 部分支持。`effort` 支持；`summary` 可传入但不生成摘要 |
| `text` | 部分支持。`format` 完整支持；`verbosity` 可传入但不生效 |
| `user` | 支持。参考官方限速与用户隔离 |
| `parallel_tool_calls` | 忽略（并行工具调用始终开启） |
| `max_tool_calls` | 忽略 |
| `previous_response_id` | 不支持（无状态 API） |
| `conversation` | 不支持（无状态 API） |
| `store` | 不支持。响应中恒为 `store: false` |
| `background` | 不支持 |
| `metadata` | 不支持 |
| `include` | 不支持 |
| `prompt` | 不支持 |
| `truncation` | 不支持。输入超出上下文窗口时返回 `400` 错误 |
| `service_tier` | 不支持 |
| `safety_identifier` | 不支持 |
| `prompt_cache_key` / `prompt_cache_retention` | 不支持。上下文缓存自动管理 |
| `context_management` | 不支持 |
| `stream_options` | 不支持 |

### 输入 Items

| 类型 | 支持情况 |
|---|---|
| `message` | 支持。角色支持 `user` / `assistant` / `system` / `developer`（`developer` 视同 `user`）；content 支持字符串和 `input_text` / `output_text` / `input_image` 内容块，`input_image` 会作为真实图片处理（仅允许出现在 `user` / `developer` 消息中）。文件输入不支持 |
| `function_call` | 支持。归并到相邻 assistant 消息 |
| `function_call_output` | 支持。`output` 可以是字符串或内容块列表；输出中的 `input_image` 会作为真实图片处理 |
| `reasoning` | 支持。明文 `content` 归并到相邻 assistant 消息；`summary`、`encrypted_content` 不支持 |
| `custom_tool_call` / `custom_tool_call_output` | 支持（配合 `apply_patch` custom 工具使用，含 `call_id` 配对校验）。`output` 中的 `input_image` 会作为真实图片处理 |
| 其他类型 | 忽略 |

上一次响应返回的 `web_search_call` item 可以回传到 `input`，接口还原对应的搜索结果并拼接进上下文。

### Tools

| 类型 | 支持情况 |
|---|---|
| `function` | 支持 |
| `custom` | 仅支持 `{"type": "custom", "name": "apply_patch"}`（用于 Codex 兼容）；其他名称返回 `400` 错误 |
| `web_search` | `该推理模型` 支持。接口在服务端执行搜索，把结果加入上下文并继续生成响应；`该快速模型` 下忽略 |
| `file_search` / `code_interpreter` / `computer_use` / `mcp` 等内置工具 | 忽略 |

### 响应字段

响应对象与 OpenAI Responses API 的 `response` 结构兼容。依赖未支持能力的字段恒为固定值（`store: false`、`previous_response_id: null`、`parallel_tool_calls: true`）。

Token 用量在 `usage` 中返回：`input_tokens` 为输入 token 数，其中 `input_tokens_details.cached_tokens` 为命中上下文缓存的 token 数；`output_tokens` 为输出 token 数，其中 `output_tokens_details.reasoning_tokens` 为思维链 token 数。

### 服务端工具用量

服务端网页工具执行成功时，`usage.server_tool_use` 返回整个响应的工具用量：

- `tool_search`：成功的网页搜索查询次数。一次搜索调用包含多个查询时可能计为多次。
- `tool_fetch`：成功的网页读取次数，包括打开网页和在网页内查找文本。

这两个值统计工具操作次数，不是 token 数。`tool_search` 统计网页搜索，不统计 `tool_search_call` 输出项表示的客户端工具发现操作。失败操作不计入，搜索没有结果时也不增加 `tool_search`。两项计数均为零时整个 `server_tool_use` 字段被省略；字段出现时两项计数都会返回，包括值为零的项。

`output` 中的 `web_search_call` 项描述单次服务端操作，`usage.server_tool_use` 提供汇总计数。流式请求从最终 `response.completed` / `response.incomplete` / `response.failed` 事件的 `response.usage` 中读取这些计数；接口不单独发送工具用量事件，初始响应事件中的 `usage` 为 `null`。

示例：为 `该推理模型` 启用网页搜索（省略 `tool_choice` 时用默认的自动选择）：

```json
{
  "model": "该推理模型",
  "max_output_tokens": 256,
  "reasoning": {"effort": "none"},
  "tools": [{"type": "web_search"}],
  "input": "Use the web search tool once to search for Python official website. Then reply with only the official site URL."
}
```

用量摘录（成功搜索一次，未读取网页）：

```json
{
  "usage": {
    "input_tokens": 3475,
    "input_tokens_details": {"cached_tokens": 512},
    "output_tokens": 54,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 3529,
    "server_tool_use": {
      "tool_search": 1,
      "tool_fetch": 0
    }
  }
}
```

> 包内互引：OpenAI 侧 Responses API 与 Agents SDK 的分工对照见 openai-agents-sdk.md；缓存前缀的命中机制见 ds-kv-cache.md；思考模式开关与 effort 档位见 ds-thinking-mode.md。
