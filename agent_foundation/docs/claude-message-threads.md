# 用消息线程加速长时运行 agent（Make long-running agents faster with message threads）

- 原文：[Make long-running agents faster with message threads](https://claude.com/resources/articles/message-threads)
- 来源：Anthropic（claude.com Resources），机构署名
- 发布：2026-11-02
- 译文说明：全文翻译；机制细节部分取自文章引用的官方文档 [Message threads](https://platform.claude.com/docs/en/build-with-claude/message-threads)（含 thread 参数、字段三分法表、缓存断点上限、恢复与错误表、SDK helper 行为清单），文章正文与文档正文互补、互不重复；术语保留英文原词；站内相对链接转为绝对 URL。

Message threads 现已在 Claude Platform 公开 beta。有了 message threads，agent 不再需要在每一轮都重发整段对话历史，长时会话的延迟显著下降。

## 机制（How message threads works）

一个编码 agent 在一个 session 里可能发出几百个请求，每个请求都重发之前的每条消息与每个工具结果。对话一旦涨到几十万 token，全部重发一遍就会拖慢 Claude 开始回应前的等待。没有 thread 时，每一轮都要把整个对话重新上传，API 要把全部内容重新校验、重新分词一遍。有 thread 时，这部分工作只覆盖新增那一轮。

用了 message threads，agent 只发送自上一轮以来的新增内容，从而降低 time to first token（TTFT，首 token 时间）。

多数 Claude Code 用户已默认开启 message threads。在 50 万到 100 万 token 的请求上，中位 TTFT 下降约 35%。

要使用 message threads，在 Messages API 请求里加 `thread` 参数。第一个请求携带完整对话并开启一个 thread。之后的每个请求只包含新消息与上一条响应的 ID。两轮之间，服务端把每个 thread 保存在内存里，加密、不写硬盘。thread 在最后一次请求后 5 分钟过期，客户端随后重发完整对话开启新 thread。每个请求变小了，但 Claude 每一轮仍然读完整对话，token 用量不变。

Message threads 最适合延迟敏感的活跃会话，包括：

- 长时运行的编码 agent，每个工具结果或文件编辑都会给对话加内容；
- computer use agent，截图留在 thread 里，无需每轮重传；
- 文档与图片密集的工作流，请求体积直接变小。

agent 携带的 context 越多，message threads 能降下来的 TTFT 越多。

## SDK 使用（Use a thread with an SDK）

SDK 里有 thread helper 替你构造 thread 请求。用与 Messages 请求相同的字段创建，之后一轮一轮发送。helper 在内存里持有完整对话。下面这个例子有两轮：第一轮 helper 创建 thread，第二轮续接 thread，并自动加 beta header。

```python
client = anthropic.Anthropic()
# 创建 helper。这一步不发请求。
thread = client.beta.messages.thread(
    model="claude-opus-5-5",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},
    system="You are a support agent for Acme. Keep replies short.",
)
# 第 1 轮：helper 创建 thread 并发送完整对话
thread.send({"role": "user", "content": "Hi! I have a question about an order."})
# 第 2 轮：helper 续接 thread，只发送新消息
second = thread.send(
    {"role": "user", "content": "How long does standard shipping usually take?"}
)
for block in second.content:
    if block.type == "text":
        print(block.text)
```

顶层 `cache_control` 可选。它让每轮都请求 prompt caching（见缓存一节）。没有它，后续每轮仍然只发新消息，但除非你自己加缓存断点，否则不会缓存任何内容。

## 手动构造请求（Send the thread field yourself）

用 cURL、CLI 或 SDK 的常规 create 方法自己构造 thread 请求时，给每个请求加 `thread` 字段。thread 的每个请求都要带 `message-threads-2026-08-12` beta header。下面例子第一轮创建 thread、第二轮续接。顶层 `cache_control` 让每轮请求 prompt caching，对话超过最小可缓存长度后生效。

```python
client = anthropic.Anthropic()
# 第 1 轮：发送完整对话并创建 thread
first = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},
    system="You are a support agent for Acme. Keep replies short.",
    messages=[{"role": "user", "content": "Hi! I have a question about an order."}],
    thread={"type": "create"},
    betas=["message-threads-2026-08-12"],
)
# 第 2 轮：只发送新消息与第 1 轮响应的 id。
# 不带 system 和 tools：thread 会保留它们。
second = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},
    messages=[
        {"role": "user", "content": "How long does standard shipping usually take?"}
    ],
    thread={"type": "continue", "previous_message_id": first.id},
    betas=["message-threads-2026-08-12"],
)
for block in second.content:
    if block.type == "text":
        print(block.text)
```

## 每个请求发送什么（What to send on each request）

| 组别 | 字段 | 规则 |
| --- | --- | --- |
| 仅 create | `system`、`tools` | 只在 create 请求里发送，缓存断点跟着它们放。在 continue 请求里发任意一个，即使值为 null，返回 400 错误。 |
| 固定 | `model`、`tool_choice`、`thinking`、`mcp_servers`（各 server 的 authorization token 除外）、`context_management`、`output_config`、`container` 里的 skills、顶层 `cache_control`、`anthropic-beta` 值集合 | thread 的每个请求都要发，取值与 create 请求一致。取值不同返回 400 错误，错误码 `thread_fingerprint_mismatch`，错误信息会点名不一致的字段。 |
| 自由 | `max_tokens`、`stop_sequences`、`stream`、`metadata`、`service_tier` 及未在本表点名的字段 | 轮与轮之间可以变。 |

API 不存 MCP server URL、MCP authorization token、container id。用到 `mcp_servers` 与 `container` 的每个请求都要重新发送。MCP authorization token 可以在请求之间变化。

SDK thread helper 替你把 system 与 tools 从 continue 请求里去掉，并在每轮重发固定字段。

要改一个仅 create 或固定字段，就开新 thread：把完整对话连同新取值一起发进 create 请求。

Message threads 与 Claude Managed Agents 的 session threads 是两回事。

## continue 请求只发新消息

continue 请求只发新消息。API 不把它们与已有消息核对。重复发送的消息可能在对话里出现两遍，或者请求直接报错。例如从上一条响应开始的 continue 请求会报错。

新消息通常以 user 消息开头：你的下一条 user 轮次，或回应上一响应里 tool_use 的 tool_result 块。如果一条响应以 `stop_reason: "pause_turn"` 结尾，用从该响应 id 出发的 continue 请求加上空 messages 列表（`"messages": []`）恢复它。若该请求返回 404，把完整对话（含暂停的那条响应）重放进新的 create 请求。轮次暂停时不要发新 user 消息：API 会拒绝。SDK thread helper 下调用不带消息的 `send()`：helper 会发这个请求并在 404 时重放。

thread 只可追加，每个 response id 只能被续接一次。永远从 thread 最新的 response id 续接。要编辑或分支更早的消息，用 create 请求开新 thread。要用摘要替换更早的轮次，见压缩一节。

## 缓存（Prompt caching on a thread）

thread 不会替你缓存 prompt。prompt caching 的运作方式与没有 thread 时相同：缓存断点放哪由你选。

要缓存每一轮，在 thread 的每个请求上发顶层 `cache_control`，如前面示例。API 把它应用在每个请求 messages 里最后一个可缓存的块上。之后每轮从缓存读取之前的对话，并把新轮写进缓存。顶层 `cache_control` 是固定字段：每个请求发同样的值。

你也可以自己在块上放 `cache_control` 断点：

- create 请求上的断点，若放在 `tools`、`system` 或非最后一条消息块上，在之后每一轮持续生效。放在一个请求 messages 最后一块上的断点，在该请求写入缓存。要缓存每个新轮，每个请求都发一个断点。没有断点的请求仍可能从缓存读到对话的一部分。
- 断点发出后不能移动或删除，因为 continue 请求不能重发更早的消息。
- 带 thread 的请求最多携带 4 个 `cache_control` 断点。顶层 `cache_control` 算一个。create 请求 system 与 tools 上的断点在每个 continue 请求上重新计数。更早已存消息上的断点不计数。超一个返回 400 错误，错误码 `thread_unsupported_request`。
- 若你自己在消息块上放断点，在重放对话开新 create 请求时，把更早消息上的断点去掉、保留最后一块上的那一个，使请求不超 4 的上限。

thread 省的是上传，prompt caching 省的是钱与计算（命中缓存的部分按更低价格计费），两者独立，官方示例一起用。缓存命中五原则与 harness 层的断点滚动，见[ Claude 官方 harness 设计的模式](claude-harness-design-patterns.md)一文的设计上下文让 cache 命中最大化一节。

## 流式（Streaming）

Threads 与 streaming 兼容。response id 在 `message_start` 事件里到达，但收到 `message_stop` 事件之后才能从它续接。提前发出的 continue 请求可能返回 404。

如果 continue 请求的流在 `message_stop` 之前断开，重发同一个 continue 请求。若那个请求返回 `thread_already_continued` 或 `thread_continue_in_flight` 错误，把完整对话重放进新的 create 请求。

连接断开时，服务器可能仍在生成响应，也可能已经保存。API 因此可以拒绝重试。重放永远安全。

SDK thread helper 在流断开后不会重试 continue 请求。

## 续接不了时恢复（Recover when a thread can't be continued）

continue 请求返回 404 错误、`error.details.error_code` 为 `thread_not_found` 时，说明 API 无法续接这个 thread。响应不说明原因。原因包括：

- thread 已过期；
- API 伺服了上一轮但没存它。例如 API 不存被 `max_tokens` 截断在工具调用中间的响应；
- 上一条响应由 fallback model 写成（见 fallback 一节）；
- 上一条响应仍在生成；
- 请求来自不同的 organization 或 workspace；
- 请求来自与创建 thread 不同的 user 或 service account。用 workspace key（旧式）创建的 thread 绑定该 key，整个 thread 用同一把 key；
- 新消息加进了已存对话装不下的内容。例如对话里从没有图片时第一张图片可能返回这个错误。

恢复时，用你自己留的副本，把完整对话连同 system 与 tools 发进新的 create 请求。SDK thread helper 自己发一次这个 create 请求，并去掉更早轮次的缓存断点。副本里更早的消息带缓存断点时，先去掉（见缓存一节）。然后从新的 response id 续接。若上一条响应由 fallback model 写成，见 fallback 一节。为排除归属原因，thread 的每个请求用同一把 API key 与 workspace。在 Claude Platform on AWS 上，thread 的每个请求用创建它的 IAM role 或 IAM user 的凭据签名。

请求一个不存在的 model 也返回 404，重放前先查 `error.details.error_code`。

如果重放之后 continue 请求紧接着又返回 404，可能是 API 存不了这段对话（例如它过大）。不带 `thread` 直接发。SDK thread helper 在你以 `unsupported_request_behavior` 设为 `continue_unthreaded` 创建时这样处理；不设则每轮重放。自己创建 thread 的 tool runner 默认用这个设置。

## 拒绝之后（After a refusal）

当响应的 `stop_reason` 是 `"refusal"`，不要续接 thread。API 可能已经持有被拒绝的那一轮，continue 请求移除不了它。用 create 请求开新 thread，去掉或改写导致拒绝的那一轮。见 [Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)。SDK thread helper 替你处理：它不保留被拒的那一轮，下一轮从新 thread 开始。

## fallback（Use fallbacks with a thread）

server-side fallback 在 Claude API 上可与 threads 连用。创建 thread 时决定：要么 thread 的每个请求都带 `fallbacks`，要么都不带。`fallbacks` 的值可以在请求之间变化。加进或去掉 fallbacks 的 continue 请求返回 400 错误，错误码 `thread_fingerprint_mismatch`。

一个 thread 只绑定一个 model，所以 API 不存 fallback model 写的轮次。你照常拿到响应，但无法从它的 id 续接。每条响应之后，按下列步骤：

1. 若 `stop_reason` 是 `"refusal"`，按拒绝一节处理。
2. 否则查 `usage.iterations` 里的 `fallback_message` 条目。流式时从最后的 `message_delta` 事件读。没有条目，照常续接 thread。
3. 有条目，说明 fallback model 写了这条响应。把完整对话（含这条响应与你的下一条消息）发进新的 create 请求。保留 `server-side-fallback-2026-07-01` beta header。从两个请求里选一个：
   - 原请求再来一遍。保持 `model`、`fallbacks` 与其他参数不变。若你请求的 model 应答，API 存下新 thread。若又是 fallback model 应答，响应再次带 `fallback_message` 条目且 API 不存它，下一轮重复本步骤。sticky routing 可能把这些请求直接送到 fallback model，于是每轮都可能发完整对话。SDK thread helper 就是这样工作的。
   - 在 fallback model 上开新 thread。把 `model` 设为 `fallback_message` 条目里的 model，去掉 `fallbacks`，用该 model 接受的参数。API 立即存下这个 thread，它从此固定在 fallback model 上。fallback 尝试可能用与你所发不同的设置运行，API 可能拒绝从你第一个请求复制的取值。
4. 回到第 1 步处理该请求的响应。没有 `fallback_message` 条目时，从它的 id 续接新 thread。

sticky routing 从一次 fallback 之后开始（一个 create 请求，或不带 thread 的请求）。大约一小时里，它可能把同一对话后续带 `fallbacks` 的 create 请求直接送给 fallback model，不尝试你请求的 model。API 不存这些轮次，每有一条应答就重启这一小时。continue 请求永远不会启动也不会使用 sticky routing。组织或 workspace 用零数据保留或客户管理密钥时，sticky routing 不适用。

## 压缩（Compact a conversation）

thread 只可追加，无法把它的更早轮次替换成摘要。要压缩对话，从摘要开新 thread。摘要由你的代码写好，作为普通消息发进新的 create 请求，连同 system 与 tools。compaction on demand 与 threads 不连用（见不支持特性一节）。compaction 机制见[面向 AI agent 的高效上下文工程](context-engineering.md)。

## SDK helper 行为（How the SDK helper behaves）

helper 替你做的事：

- 给使用 thread 的每个请求加 `message-threads-2026-08-12` beta header；
- 第一轮创建 thread，之后续接，只发新消息，不带 system 与 tools；
- continue 请求返回 `thread_not_found`、`thread_already_continued` 或 `thread_continue_in_flight` 时，把完整对话在新的 create 请求里重放一次；
- 调用不带消息的 `send()` 时恢复 `pause_turn` 响应；
- 拒绝之后开新 thread。你照常拿到 `stop_reason: "refusal"` 响应，helper 不保留那一轮：收回你交给该次调用的消息。用 `thread.append(...)` 加进的消息，或创建 helper 时给的消息，保持暂存。你的下一轮把它们连同被拒轮次之前的对话，发进新的 create 请求。发一条改写的消息；若是一条暂存消息导致拒绝，就从 params 里去掉它开新 thread；
- fallback model 应答后发新的 create 请求。响应的 `usage.iterations` 带 `fallback_message` 条目时，helper 保留该响应并在下一轮把完整对话发进新的 create 请求。它不等 404 错误。该请求保持你设置的 model 与 fallbacks；
- 重发消息时（例如重放或 fork 的第一轮）去掉更早轮次的缓存断点。你最新的消息、system、tools 与顶层 `cache_control` 照你所发出去。

你自己处理的：

- fallbacks。API 持续从 fallback model 应答时，helper 每轮把完整对话发进新的 create 请求，因为那些轮次 API 都不存。你请求的 model 应答后回到 continue 请求。要把对话移到 fallback model 上，按 fallback 一节从该 model、不带 `fallbacks` 的 params 开新 thread；
- 断流。流在响应中途断开时，helper 保留已完成的块与已到达的文本，下一轮把完整对话发进新的 create 请求。helper 不自行重试：要改为重发被中断的轮次，调用不带消息的 `send()`。保留的部分以工具调用结尾时，在下一条消息里回应它们。你在流显示 `stop_reason: "refusal"` 后停止读取时，helper 把那一轮按拒绝处理；
- 其他错误。`thread_fingerprint_mismatch` 与 `thread_unsupported_request` 错误会到达你的代码。`thread_unsupported_request` 后要脱离 thread 继续，创建 helper 时把 `unsupported_request_behavior` 设为 `continue_unthreaded`。带这个设置时，重放后第一个 continue 请求再次返回 `thread_not_found`，helper 也停止使用 thread——API 可能存不了这段对话。不带该设置，helper 每轮重放。自建 thread 的 tool runner 默认用该设置。

SDK 的 beta tool runner 默认也用 thread，创建 runner 时可关掉。

## 其他 helper 方法（Other helper methods）

| 要做的事 | 用 |
| --- | --- |
| 流式一轮 | `thread.stream(...)` |
| 流式轮的完成响应 | `stream.get_final_message()` |
| 完整对话 | `thread.messages` |
| 下一轮续接用的 response id | `thread.previous_message_id` |
| 只加消息不发送 | `thread.append(...)` |
| 为后续轮改字段 | `thread.update(...)` |
| 复制 thread | `thread.fork()` |
| 开新 thread 用的字段与对话 | `thread.params` |
| 在这个 thread 上的 tool runner | `thread.tool_runner()` |
| 不用 thread 的 tool runner | `tool_runner(..., thread=False)` |

流式：helper 在流到达 `message_stop` 时记录响应，所以把流读到底。提前停止读取时，结束流，让 thread 供下一轮使用：Python 离开 `with` 块；TypeScript 离开循环或调用 `abort()`；Go 调用 `Close`；Java 与 Ruby 调用 `close()`；C# 释放 enumerator，离开 `await foreach` 即完成；PHP 调用 `close()`。

C# 里，请求在你开始读流时发出。

C#、Go、Java、PHP 里，拒绝之后 `thread.LastMessage` 仍返回上一轮的响应，第一轮则什么都没有。从流的事件里读拒绝。

改字段：update 不发送任何内容，应用到之后每一轮。thread 一旦有响应，helper 拒绝改动 system 或 tools 的轮次；改动其他固定字段由 API 拒绝（见每个请求发送什么一节）。要改这些字段，从 params 开新 thread，或 fork 后在 fork 的第一轮之前 update。

fork：复制对话、字段与请求选项，不发送。它的第一轮把完整对话发进新的 create 请求，之后两个 thread 相互独立。fork 永远从完整对话开始，无法从更早的响应开始。

params：持有 helper 的字段与完整对话。把它们传给创建 helper 的方法来开新 thread，例如换一个 system（见每个请求发送什么一节），或把消息裁短丢弃后面的轮次。从 params 开的 thread 按你给的每条消息发送，缓存断点包含在内，注意不超 4 的上限（见缓存一节）。除 Ruby 外，params 不含请求选项，要再传一遍。

structured output：创建 helper 时给输出格式，之后的轮次无法更改。解析结果的获取方式依 SDK 而定：Python 与 TypeScript 调 `thread.parse(...)`；C# 用 `client.Beta.Messages.Thread<T>(...)` 创建；Go 里 `Send` 解进 `Params.OutputConfig.Format.Schema` 指向的 struct；Java 用 `thread(...)` 加 `outputConfig(MyClass.class)` 创建；PHP 里 `outputConfig` 指定 model class 时 `send()` 在文本块上设 parsed；Ruby 给 `thread(...)` 传 `output_config: {format: MyModel}`，随后读 `reply.parsed_output`。

## 错误表（Errors）

API 在 model 运行之前返回下表错误。请求不消耗 token，thread 与其过期时间不变。400 错误的 `error.type` 是 `invalid_request_error`，404 是 `not_found_error`。

| 状态 | error_code | 含义 | 处理 |
| --- | --- | --- | --- |
| 404 | `thread_not_found` | API 无法续接该 thread。 | 用新的 create 请求发完整对话。 |
| 400 | `thread_fingerprint_mismatch` | 一个固定字段与 thread 存的取值不同。错误信息点名该字段。 | 固定字段保持一致，或开新 thread 改。 |
| 400 | `thread_already_continued` | 每个 response id 只能被续接一次。 | 从 thread 最新的 response id 续接。客户端从未收到那条响应时，重放。 |
| 400 | `thread_continue_in_flight` | 同一 response id 的另一个 continue 请求仍在运行。通常是你自己更早的尝试。 | 等它完成并从它的 response id 续接，或重放。 |
| 400 | `thread_unsupported_request` | 请求用了 threads 不支持的特性或组织设置。`error.details.unsupported` 存在时会点名。 | 从请求里去掉该特性，或不带 `thread` 发完整对话。 |

部分 thread 请求的 400 错误不带 `error_code`，例如缺 `previous_message_id` 的 continue 请求，或带 system 或 tools 的那种。

错误响应示例：

```json
{
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "thread: a maximum of 4 blocks with cache_control may be provided when `thread` is set. Found 5.",
        "details": {
            "error_code": "thread_unsupported_request",
            "unsupported": ["cache_control"]
        }
    },
    "request_id": "req_011CSHoEeqs5C35K2UUqR7Fy"
}
```

## 不支持的特性（Features that threads don't support）

Threads 不支持：

- Message Batches。带 thread 的请求项在 batch 结果里以 `invalid_request_error` 结束；
- token 计数。带 thread 的 token counting 请求返回 400 错误。改为对完整对话计数，连同 system 与 tools；
- compaction。compaction on demand 与 threads 不连用。设了 compaction 参数、或带 `compact-2026-09-04` beta header 发 compaction 块的请求，含 thread 时返回 400 错误。见压缩一节；
- context editing，`clear_thinking_20251015` 且 `keep: "all"` 的情形除外；
- 开启 HIPAA readiness 的组织；
- 开启 Inference hooks 的组织。

API 用 400 错误加错误码 `thread_unsupported_request` 拒绝多数 threads 不支持的请求。`error.details.unsupported` 存在时，取值为其中之一：

| 取值 | 含义 |
| --- | --- |
| `context_management` | 请求用了 threads 不支持的 context management 或 compaction。 |
| `cache_control` | 请求的 `cache_control` 断点多于 4 个。见缓存一节。 |
| `fallbacks` | 请求设了 `fallbacks`，而你的组织不能与 threads 连用 fallbacks。 |
| `hipaa` | 组织开启了 HIPAA readiness。 |
| `inference_hooks` | 组织开启了 Inference hooks。 |

API 可以往这个清单里加值。拿到不认识的值时，不带 `thread` 发完整对话。一个请求命中多个条件时，错误只点名一个。

## 限制（Limitations）

- 没有 API 可以列出、读取或删除 thread；
- Threads 可在 Claude API、Claude Platform on AWS、Claude Models on Google Cloud（Anthropic managed）、Microsoft Foundry 里的 Claude 上使用。

## 定价与速率限制（Pricing and rate limits）

Threads 不改变定价，也不改变速率限制。

## 数据保留（Data retention）

Message threads 不满足 ZDR（零数据保留）。使用本特性不影响你使用其他 ZDR 特性。API 把 thread 持有在内存里，用服务端管理的密钥加密，从不写入持久存储，最迟在最后一次使用后 1 小时删除。

thread 持有 API 发给 model 的对话、create 请求里的 system 与 tools，以及固定字段的指纹（用于校验后续请求）。文件按引用持有，使用 thread 期间保持对话用到的每个文件可用。

## 上手（Getting started）

Message threads 现已在原生 Claude Platform，以及 Claude Platform on AWS、Claude in Microsoft Foundry、Claude Models on Google Cloud（Anthropic managed）公开 beta。标准 Claude token 价格与既有速率限制照常适用。见[文档](https://platform.claude.com/docs/en/build-with-claude/message-threads)上手。
