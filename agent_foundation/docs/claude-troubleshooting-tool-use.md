# Claude 工具使用故障排查：症状到修复对照表

- 原文：[Troubleshooting tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/troubleshooting-tool-use)
- 来源：Anthropic 官方文档（md 直链抓取）
- 发布：官方文档页，随 API 持续更新
- 译文说明：原文为英文，本篇为按本包语言规则的合规改写整理，术语保留英文原词。

针对最常见的工具使用错误，官方给出症状到修复的对照表。每条修复交叉引用负责该功能的页面。本篇是排查手册形态：先对症状，再查原因列，按修复列处理。

## Claude 调用了错误的工具

| 症状 | 可能原因 | 修复 |
|---|---|---|
| 你想要工具 B，Claude 却调用了工具 A | 描述含糊 | 把描述写精确。用「何时使用」区分工具，仅说明「做什么」不够。见官方 Define tools 页。 |
| Claude 从不调用你的工具 | 工具名冲突或 schema 过于笼统 | 检查工具列表里有没有重复的名字。加 `input_examples` 让预期用法具体化。 |
| Claude 调用时参数类型错误 | schema 有歧义 | 加 `strict: true`（schema 在受支持子集内时），或加 `input_examples`。 |

## Claude 编造工具参数

| 症状 | 可能原因 | 修复 |
|---|---|---|
| 出现了 schema 里不存在的参数 | 未开严格模式时模型过度生成 | schema 在受支持子集内时加 `strict: true`。 |
| 参数值超出 enum 范围 | 缺严格模式或 enum 过大 | 缩小 enum，或加 `input_examples` 展示有效取值。 |

## 并行工具调用不起作用

| 症状 | 可能原因 | 修复 |
|---|---|---|
| 并行更合适，Claude 却按顺序调用工具 | 消息历史格式问题 | 把多个 `tool_result` 块放进同一条 user 消息，不要每轮发一条。见官方 Parallel tool use 页。 |
| `disable_parallel_tool_use` 似乎被忽略 | 在对话中设置得太晚 | 在返回 `tool_use` 的那条请求上设置。在后续请求上设置对先前的工具调用没有影响。 |

## 缓存不断失效

| 症状 | 可能原因 | 修复 |
|---|---|---|
| 每个请求都是缓存未命中 | 请求之间 `tool_choice`、thinking 配置或 `output_config.effort` 变动 | 保持 `tool_choice` 稳定，或把 `cache_control` 断点放在变动点之前；缓存对话的整个生命周期里保持 thinking 配置与 effort 档位不变。见官方 Tool use with prompt caching 与 Thinking and prompt caching 页。 |
| 对话中途加工具破坏了缓存 | 工具被加到 tools 数组开头 | 配合工具搜索用 `defer_loading: true`，把工具内联追加，不修改数组头部。 |

## 请求时报错

| 错误 | 原因 | 修复 |
|---|---|---|
| `tool_use ids were found without tool_result blocks immediately after` | 某些 `tool_use` ID 缺 `tool_result`，或 `tool_result` 没排在 user 消息内容的第一位 | assistant 响应里每个 `tool_use` 块都返回一个 `tool_result`。`tool_result` 块放在任何文本之前。见官方 Handle tool calls 与 Parallel tool use 页。 |
| `was found without a corresponding <name>_tool_result block` | 上一轮 assistant 有 `server_tool_use` 块但没有结果块（最常见：Claude 把它与客户端工具一起调用），且你的下一条 user 消息提前结束了该轮（例如 `tool_result` 块之后跟了文本），或 resume 请求不再定义那个服务端工具（错误消息以 `but no <name> tool was provided` 结尾） | 发一条只含客户端 `tool_use` ID 对应 `tool_result` 块的 user 消息，保持同一份 `tools` 数组。见官方 Stop reasons and fallback 页。 |
| `Unsupported regex feature in pattern field: ...` | 严格工具 `input_schema` 里的 `pattern` 用了严格模式编译不了的 regex 特性，如反向引用、环视、词边界、过大的 `{n,m}` 区间 | 简化 pattern。锚定 pattern 搭配基础量词、字符类与分组是受支持的；见官方 JSON Schema limitations 页。 |
| `All tools have defer_loading: true` | 模型侧没有任何可见工具 | 至少一个工具必须立即加载。工具搜索工具自身永远不能设 `defer_loading: true`。 |

## 错误：thinking blocks cannot be modified

工具调用后继续对话时，请求报 400 `invalid_request_error`，消息含 `` `thinking` or `redacted_thinking` blocks in the latest assistant message cannot be modified ``，说明你的应用在回传前改动了 assistant 的 thinking 块。把整条 assistant 消息原样发回，再追加你的 `tool_result`。完整错误与修复步骤见官方 API errors 页。

## Claude 把工具结果标记为提示注入

| 症状 | 可能原因 | 修复 |
|---|---|---|
| Claude 拒绝按工具结果行动，或要求用户确认来自工具结果的指令 | 你自己的指令被放进了 `tool_result` 内容里 | Claude 被训练为把工具结果内的指令当作可能不可信的第三方内容。把指令移出工具结果：在 `tool_result` 块之后的 `user` 轮里发，或在受支持模型上用会话中途 system message。工具结果里只留数据。见官方 Mitigate jailbreaks and prompt injections 页。 |

## 模型版本之间的 JSON 转义差异

| 症状 | 原因 | 修复 |
|---|---|---|
| 新模型上工具输入的字符串比对失败 | 模型版本之间 Unicode 与正斜杠的转义不同 | 用 `json.loads()` 或 `JSON.parse()` 解析后再比对。对序列化输入做原始字符串匹配永远不要做。 |

> 包内互引：tool_result 的格式要求与 is_error 三类错误见 claude-handle-tool-calls.md；描述怎么写、上下文举例的纪律见 writing-tools-for-agents.md 与 sonnet-prompting.md；缓存断点与工具加载顺序见 claude-memory-tool.md 的配合章节与 ds-kv-cache.md 的前缀缓存纪律。
