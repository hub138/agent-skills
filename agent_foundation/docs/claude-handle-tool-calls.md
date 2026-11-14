# Claude 工具调用处理：tool_use 与 tool_result 的生命周期

- 原文：[Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- 来源：Anthropic 官方文档（md 直链抓取）
- 发布：官方文档页，随 API 持续更新
- 译文说明：原文为英文，本篇为按本包语言规则的合规改写整理，术语保留英文原词。

本页覆盖工具调用的完整生命周期：从 Claude 响应里读 `tool_use` 块、在回复里编排 `tool_result` 块、用 `is_error` 标记错误。SDK 侧 Tool Runner 自动处理这些环节，需要自己控制工具执行时才按本页手工实现。

Claude 的响应因客户端工具与服务端工具而不同。

## 客户端工具的结果处理

响应的 `stop_reason` 为 `tool_use`，带一个或多个 `tool_use` 内容块，块内字段：

- `id`：这个工具使用块的唯一标识，后续用来配对工具结果。
- `name`：被调用的工具名。
- `input`：传给工具的输入对象，符合工具的 `input_schema`。

computer use 或 browser use 工具集成员的 `tool_use` 块还带 `toolset_name` 字段（`"computer"` 或 `"browser"`），其 `name` 是成员工具名（如 `screenshot`、`navigate`），分发时要同时按这两个字段判断。

```json
{
  "id": "msg_01Aq9w938a90dw8q",
  "model": "claude-opus-5-5",
  "stop_reason": "tool_use",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "I'll check the current weather in San Francisco for you."
    },
    {
      "type": "tool_use",
      "id": "toolu_01A09q90qw90lq917835lq9",
      "name": "get_weather",
      "input": { "location": "San Francisco, CA", "unit": "celsius" }
    }
  ]
}
```

收到客户端工具的调用请求后：

1. 从 `tool_use` 块里提取 `name`、`id`、`input`。
2. 在你的代码库里按工具名运行真实工具，传入 `input`。
3. 发一条 `role` 为 `user` 的新消息继续对话，内容块类型为 `tool_result`，字段如下。

`tool_result` 的字段：

- `tool_use_id`：对应工具使用请求的 `id`。
- `content` 可选：工具结果。字符串形态（`"content": "15 degrees"`）、嵌套内容块列表（`[{"type": "text", "text": "15 degrees"}]`）、文档块列表（`[{"type": "document", "source": {...}}]`）都可以。内容块可用 `text`、`image`、`document`、`search_result` 类型。
- `is_error` 可选：工具执行出错时设为 `true`。

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01A09q90qw90lq917835lq9",
      "content": "15 degrees"
    }
  ]
}
```

回答 computer use 或 browser use 成员块的 `tool_result` 必须回显与 `tool_use` 块相同的 `toolset_name`，缺失即被拒绝。其内容也更窄：成员结果只能含 `text` 与 `image` 块，browser use 结果可多一个 `browser_state` 块（标签页管理成员只返回该块）。

### 格式要求

- 工具结果块在消息历史里必须紧跟着对应的工具使用块。assistant 的工具使用消息与 user 的工具结果消息之间不能插入任何消息。
- 含工具结果的 user 消息里，`tool_result` 块在 content 数组里排第一，任何文本排在全部工具结果之后。
- assistant 轮还调用过尚无结果块的服务端工具时，user 消息只能含 `tool_result` 块。结果之后的文本会提前结束该轮；对 Claude 直接调用的服务端工具，请求随后报 400，指名未解决的那个服务端工具。

收到 `tool_use ids were found without tool_result blocks immediately after` 这类错误时，先检查工具结果格式是否符合上述要求。

带图片的示例：`content` 数组里 `text` 与 `image` 块可以混排，图片用 base64 编码放在 `source` 里。空结果示例：`tool_result` 只带 `tool_use_id`，不带 `content`。文本位置示例：文本放在 `tool_result` 之前会报 400；只在 assistant 轮只调用了客户端工具时，文本放在全部 `tool_result` 之后是正确形态。

### 不可信内容与提示注入

工具结果经常携带你控制不了来源的内容：网页、收件邮件、用户上传、第三方 API。这类内容按不可信对待：能影响它的人可能嵌入试图改写 Claude 行为的指令（间接提示注入）。不可信内容保留在 `tool_result` 块里，不放进 `system` prompt 或普通 user `text` 块。

## 服务端工具的结果处理

Claude 在内部执行工具、把结果直接并入响应，不需要额外的用户交互。

响应可能同时含一个客户端 `tool_use` 块与一个还没有结果块的 `server_tool_use` 块。那个服务端调用尚未完成，其结果块在稍后的响应里到达。回复一条只含客户端工具对应 `tool_result` 块的 user 消息、保持同一份 `tools` 数组；对 Claude 直接调用的服务端工具，API 在该请求上运行它，下一个响应以它的结果块开头。

与其他 API 的差异：Claude API 不单独设工具用角色（如 `tool` 或 `function`），工具直接并入 `user` 与 `assistant` 消息结构。user 消息含客户端内容与 `tool_result`，assistant 消息含 AI 生成内容与 `tool_use`。

## 用 is_error 处理错误

### 工具执行错误

工具自身执行时抛错（例如取天气数据的网络错误），把错误消息放进 `content`、设 `"is_error": true` 返回，Claude 会把错误并入给用户的回复。

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

错误消息要写成有指导性的：不写 `"failed"` 这类笼统错误，写清哪里出错、Claude 下一步该试什么（例如 `"Rate limit exceeded. Retry after 60 seconds."`）。这给 Claude 恢复或调整所需的上下文，省掉它的猜测。

### 无效工具调用

Claude 的工具使用请求无效（例如缺必填参数），通常说明信息不足以让它正确使用工具。开发期最好的做法：改请求里的工具定义，把 `description` 写得更详细再试一次。

也可以继续推进对话：返回标记错误的 `tool_result`，Claude 会补上缺失信息再试一次。

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01A09q90qw90lq917835lq9",
      "content": "Error: Missing required 'location' parameter",
      "is_error": true
    }
  ]
}
```

工具请求无效或缺参时，Claude 会带修正重试 2 到 3 次，之后才向用户致歉。要彻底消除无效调用，用 strict tool use（工具定义上设 `strict: true`），保证工具输入永远精确符合 schema，杜绝缺参与类型不匹配。

### 服务端工具错误

服务端工具出错（例如 web search 的网络问题）时，Claude 透明地处理错误、尝试给用户替代回复或解释。客户端工具之外，服务端工具不需要你处理 `is_error` 结果。

web search 的错误码：`too_many_requests`（超速率限制）、`invalid_input`（搜索查询参数无效）、`max_uses_exceeded`（超最大使用次数）、`query_too_long`（查询超最大长度）、`unavailable`（内部错误）。

> 包内互引：症状到修复对照表见 claude-troubleshooting-tool-use.md；工具描述写法与高效工具原则见 writing-tools-for-agents.md；DeepSeek 侧 tool_calls 流式分块语义见 ds-tool-calls.md；SDK 侧自动化循环见 openai-agents-sdk.md。
