# Claude Sonnet 5.5 新特性与迁移指南（What's new in Claude Sonnet 5.5 & Sonnet 5.5 migration guide）

- 原文一：[What's new in Claude Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5)
- 原文二：[Sonnet 5.5 migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide)
- 来源：Anthropic（Claude Platform 文档），机构署名
- 发布：文档页未标注发布日期
- 译文说明：两页互相引用、内容高度交叠（What's new 页是迁移指南的要点摘要加新特性公告），按双源合并惯例并成一份译文；全文翻译；术语保留英文原词；站内相对链接转为绝对 URL。

本指南列出从 Claude Sonnet 5、Claude Sonnet 4.6、Claude Sonnet 4.5、Claude Sonnet 4、Claude 3.7 Sonnet 或 Claude Haiku 4.5 迁到 Claude Sonnet 5.5 需要的代码改动。先读前两节，再顺着读到你的出发模型那一节；迁移清单按出发模型列出全部改动。文档页同时提示可用 Claude Code 代为完成迁移。

五项破坏性变更会影响已在 Claude Sonnet 5 上运行的代码：关闭前置 thinking 的方式换成 `between_tools`；强制工具调用返回错误；thinking block 绑定产生它的模型与会话；部分 computer use 工具版本返回错误；advisor 工具拒绝四种模型当 advisor。另有一项不报错但改变响应形态：工具调用之间的文字改从 thinking block 返回，流式转发这类文字给用户的应用在工具调用之间会静默，直到设置能返回文字的 `display` 取值，或改用 `between_tools` 关闭前置 thinking。

价格上，Claude Sonnet 5.5 与 Claude Sonnet 5 相同，只有 prompt cache 读取为每百万 token $0.10，是 Sonnet 5 费率的一半。

## 新模型

| 模型 | Claude API ID | 描述 |
| --- | --- | --- |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 速度与智能的最佳组合 |

[Adaptive thinking](https://platform.claude.com/docs/en/build-with-claude/thinking) 默认开启，[effort 参数](https://platform.claude.com/docs/en/build-with-claude/effort)控制思考深度，Claude API 上的默认值是 `high`。tokenizer 与 Claude Sonnet 5 相同，同一段文字产生相同的 token 计数。context window、输出上限、知识截止时间与价格见 [Claude Sonnet 5.5 模型页](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)；全部在售模型见 [models overview](https://platform.claude.com/docs/en/models/overview)。

## 先看一个能直接跑的请求

下面这个请求在 Claude Sonnet 5.5 上原样可用。它设置了一个 effort 档位，SDK 示例按 block type 读取回复。它没有携带五种会返回 400 的设置：thinking budget、采样参数、assistant prefill、强制工具选择、`thinking: {"type": "disabled"}`。

```
client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    messages=[
        {
            "role": "user",
            "content": "Analyze the trade-offs between microservices and monolithic architectures",
        }
    ],
    output_config={"effort": "medium"},
)

print(f"Stop reason: {response.stop_reason}")
for block in response.content:
    if block.type == "text":
        print(block.text)
```

## thinking 默认开启

Claude Sonnet 5.5 上，不带 `thinking` 字段的请求按 [adaptive thinking](https://platform.claude.com/docs/en/build-with-claude/thinking) 运行，发 `thinking: {"type": "adaptive"}` 等价。在 Claude Sonnet 4.6 及更早模型和 Claude Haiku 4.5 上，同样的请求原先不带思考运行。要继续保持无前置 thinking，见下一节的 `between_tools`。

| 模型 | 不带 `thinking` 字段时的思考 | 接受的 `thinking.type` 取值 | 默认 `display` |
| --- | --- | --- | --- |
| Claude Sonnet 5.5 | 开启 | `"adaptive"`、`"between_tools"` | `"omitted"` |
| Claude Sonnet 5 | 开启 | `"adaptive"`、`"disabled"` | `"omitted"` |
| Claude Sonnet 4.6 | 关闭 | `"adaptive"`、`"disabled"`、`"enabled"`（已弃用） | `"summarized"` |
| Claude Sonnet 4.5 与 Claude Haiku 4.5 | 关闭 | `"disabled"`、`"enabled"` | `"summarized"` |

### 响应里的 thinking 怎么处理

原先不带思考运行的代码需要补齐三件事；来自 Claude Sonnet 5 的代码大概率已具备前两件。

- 按 `type` 读 content block。响应可以从 `thinking` block 开始，读 `content[0].text` 的代码会坏。
- 工具使用循环里把 `thinking` block 原样传回，空 block 也要传。见 [Preserving thinking blocks](https://platform.claude.com/docs/en/build-with-claude/thinking#preserving-thinking-blocks)。
- 重看 `max_tokens`。它覆盖 thinking 加正文，thinking token 按输出 token 计费。见 [Cost control](https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost#cost-control)。

thinking 文字默认省略：`thinking` block 到达时 `thinking` 字段为空，带一个 `signature`。要拿到可读的摘要，设 `display: "summarized"`，这是 Claude Sonnet 4.6 及更早模型和 Claude Haiku 4.5 上的默认值。见 [Controlling thinking display](https://platform.claude.com/docs/en/build-with-claude/thinking#controlling-thinking-display)。

### 关闭前置 thinking：between_tools

在 Claude Sonnet 5.5 上关闭前置 thinking，发 `thinking: {"type": "between_tools"}`。它是这个模型上最低的 thinking 设置。工具调用之间它写的短 [progress update](https://platform.claude.com/docs/en/build-with-claude/thinking#progress-updates) 仍然以 `thinking` block 返回、附带摘要文字；把这些 block 随 assistant turn 其余内容原样传回。传回的 progress-update block 给模型的是它当时写下的完整笔记，摘要文字只出现在响应里。请求不带工具时，响应只含正文，与 Claude Sonnet 5 上的 `disabled` 一致。Claude Sonnet 5 用 `thinking: {"type": "disabled"}` 关闭思考；在 Claude Sonnet 5.5 上发 `disabled` 返回 400 `invalid_request_error`：

```
To turn thinking off on this model, send "thinking": {"type": "between_tools"} instead of {"type": "disabled"}. The model does not think before responding. The short updates it writes between tool calls come back as thinking blocks.
```

`between_tools` 在提供 Claude Sonnet 5.5 的全部平台可用，无需 beta header。它接受 `low`、`medium`、`high` 三档 effort；`xhigh` 或 `max` 下带它的请求返回 400，要在那两档运行就用 adaptive thinking（省略 `thinking` 字段或发 `"adaptive"`，两者等价）。`between_tools` 不接受其他任何字段：带 `display`、`budget_tokens` 或 `block_binding` 都返回 400；手动 thinking budget（`thinking: {"type": "enabled", "budget_tokens": N}`）同样返回 400。配了[服务端 fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#server-side-fallback) 时，`between_tools` 请求如果 fallback 到 Claude Sonnet 5，会在那边以 `thinking: {"type": "disabled"}` 运行。

`between_tools` 下 effort 不能在会话中途变更：[per-message](https://platform.claude.com/docs/en/build-with-claude/effort#change-effort-mid-conversation-beta) `output_config.effort` 与生效档位不同就返回 400。要逐轮调节 effort，用 adaptive thinking。提示词层面的引导见[提示模式译文](sonnet-prompting.md)的无前置 thinking 一节。

迁移前（Claude Sonnet 5）：

```
client.messages.create(
    model="claude-sonnet-5",
    max_tokens=16000,
    thinking={"type": "disabled"},
    output_config={"effort": "xhigh"},
    messages=[{"role": "user", "content": "..."}],
)
```

迁移后（Claude Sonnet 5.5）：

```
client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=16000,
    thinking={"type": "between_tools"},
    output_config={"effort": "high"},
    messages=[{"role": "user", "content": "..."}],
)
```

## 强制工具调用返回错误

Claude Sonnet 5.5 不支持强制工具调用。`tool_choice` 设为 `{"type": "any"}` 或 `{"type": "tool", "name": "..."}` 返回 400 `invalid_request_error`，[token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) 端点执行同一检查：

```
tool_choice: type "tool" and "any" are not supported for this model.
```

`tool_choice: {"type": "auto"}`（默认值）与 `{"type": "none"}` 可用。要保证工具输入符合 schema，保持 `auto` 并给工具标记 `strict: true`（[strict tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use)），或把 schema 移到 [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)。要让模型调用工具，在 prompt 里说明该工具何时适用。strict 工具支持 JSON Schema 的一个子集，要求每个对象带 `additionalProperties: false`；单个请求最多 20 个 strict 工具；MCP、computer use、browser use 的 toolset 条目不接受 `strict`，长工具清单里只给需要的工具标记。

迁移前（Claude Sonnet 5）：

```
client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    tools=tools,
    tool_choice={"type": "tool", "name": "get_weather"},
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
)
```

迁移后（Claude Sonnet 5.5）：

```
client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    # strict tool use: every call matches the tool's input_schema
    tools=[{**tool, "strict": True} for tool in tools],
    tool_choice={"type": "auto"},
    messages=[
        {
            "role": "user",
            "content": "What's the weather in Paris? Use the get_weather tool.",
        }
    ],
)
```

## thinking block 绑定模型与会话

每个 thinking block 记录产生它的模型。每个模型只读自己的 block 与部分其他模型的 block。Claude Sonnet 5.5 读取 Claude Sonnet 5、Claude Opus 4.8、Claude Haiku 4.5 及更早模型的 thinking block；在 Claude API 与 Claude Models on Google Cloud（Google managed）上还读 Claude Haiku 5.5 的；它不读 Claude Opus 5、Claude Opus 5.5 以及任何 Claude Fable 或 Claude Mythos 模型的 block。在 Claude API 与 Google managed 上，Claude Opus 5.5 读 Claude Sonnet 5.5 的 thinking block，其余模型都不读。

因此，从 Claude Sonnet 5 换到 Claude Sonnet 5.5 的会话保留推理；从 Claude Sonnet 5.5 升到 Claude Opus 5.5（限上述两个平台）同样保留；其余任何从 Claude Sonnet 5.5 迁走的换法，切换之后的轮次都在无推理状态下运行。请求携带目标模型读不了的 block 时，API 在模型看到之前把它丢弃：请求照常成功，被丢弃的 block 不计费。带 `thinking-binding-controls-2026-08-01` beta header 时，丢弃动作会记录在顶层的 `input_transformations` 数组里。见 [Switching models mid-conversation](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking#switching-models)。

API 还会检查 Claude Sonnet 5.5 的 thinking block 之前的内容在 block 产生之后有没有变动：system prompt、tools 或更早的消息。会话保持只增不改：改指令或工具用 [mid-conversation system message](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages)，不要编辑历史。2026 年 8 月 31 日 00:00 UTC 及之后创建的账号，重放经过这类改动的 block 且不设 `thinking.block_binding.prefix_mismatch_behavior` 时返回 400（Claude API、Amazon Bedrock、Google managed 一致）；更早创建的账号只有把该字段设为 `"error"` 时才报错。要改为丢弃受影响的 block，发 `thinking-binding-controls-2026-08-01` beta header 并把字段设为 `"drop_block"`。`block_binding` 只配 `thinking: {"type": "adaptive"}` 工作；其他 thinking 设置下发不了 `block_binding`，此时从报错点名的 block 起，删去它与其后全部 `thinking` 和 `redacted_thinking` block，重试一次。见 [Preserved thinking](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking)。

## 部分 computer use 工具版本返回错误

Claude Sonnet 5.5 通过 `computer_toolset_20260801` toolset 支持 [computer use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)。Amazon Bedrock 上还接受带 `computer-use-2025-11-24` beta header 的 `computer_20251124` 工具。其余版本一律返回 400，例如 Claude API 上的 `computer_20251124`；`computer_20250124` 在所有平台都不接受。错误信息会点名被拒的 type，并在 `Did you mean one of` 之后列出模型接受的工具类型，开头是：

```
'claude-sonnet-5-5' does not support tool types: computer_20251124.
```

已经在用 toolset 的集成无需改动。要把 `computer_20251124` 集成迁到 toolset，按 [Migrate from `computer_20251124`](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool#migrate-from-computer-20251124) 操作：去掉该版本的 beta header，把 `tools` 里的条目换成 `{"type": "computer_toolset_20260801"}`，再为成员 `tool_use` block、批量动作与结果上的 `toolset_name` 更新 agent 循环。如果原先发 `fine-grained-tool-streaming-2025-05-14` beta header，迁到 toolset 时一并去掉：它与 toolset 条目同发返回 400，需要该行为的工具改为逐个设置 `eager_input_streaming: true`。

## advisor 工具拒绝四种模型

配 [advisor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool)（beta）时，Claude Sonnet 5.5 的 executor 需要以下模型当 advisor：Claude Mythos 5.1、Claude Fable 5.1、Claude Mythos 5、Claude Fable 5、Claude Opus 5.5、Claude Opus 5，或 Claude Sonnet 5.5 自己。Claude Opus 4.8、Claude Opus 4.7、Claude Sonnet 5 与 Claude Haiku 5.5 给 Claude Sonnet 5 的 executor 当 advisor 可用，给 Claude Sonnet 5.5 的 executor 当 advisor 返回 400 `invalid_request_error`。Claude Sonnet 5.5 接受的每个 advisor 返回的 advice 都加密，以 `advisor_redacted_result` block 到达，客户端读不到 advice 文字。见 [Model compatibility](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#model-compatibility) 与 [Result variants](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#result-variants)。

## 工具调用之间的文字进 thinking block

Claude Sonnet 5.5 在工具调用之间写的超过一两句的笔记，以 [progress-update `thinking` block](https://platform.claude.com/docs/en/build-with-claude/thinking#progress-updates) 返回，默认 `display: "omitted"` 下文字为空；更短的话留在 `text` block。Claude Sonnet 5 及更早模型上这些文字全部以 `text` block 返回。请求不会失败，但转发这类文字给用户的界面在工具调用之间静默。

用 adaptive thinking 时，把 `display` 设为 `"updates"`（beta，`thinking-display-updates-2026-08-18` header）只取更新笔记，或设为 `"summarized"` 把它们与推理摘要混在一起；渲染时把每个非空 `thinking` block 画在它后面紧跟的 `tool_use` block 之前。用 `between_tools` 时文字直接返回，无需 `display` 字段。见提示模式译文的「给用户看的进度更新」一节。

## 特性支持

Claude Sonnet 5.5 支持 [per-message effort](https://platform.claude.com/docs/en/build-with-claude/effort#change-effort-mid-conversation-beta)（beta）、[mid-conversation system message](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages)、[mid-conversation tool change](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages#mid-conversation-tool-changes)（beta）、最小可缓存 prompt 为 512 token 的 [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)、[batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing)、[Files API](https://platform.claude.com/docs/en/build-with-claude/files)、[PDF 支持](https://platform.claude.com/docs/en/build-with-claude/pdf-support)、[vision](https://platform.claude.com/docs/en/build-with-claude/vision) 与服务端、客户端 [tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)。前三项在 Claude Sonnet 5 上没有；Sonnet 5 的最小可缓存 prompt 是 1,024 token。

### Compact on demand（beta）

带 `compact-2026-09-04` beta header 时，请求携带顶层 `compaction` 参数会返回一个带签名的 `compaction` block，它汇总整个会话；之后发请求时把这个 block 放在最前，替代被汇总的那些消息。压缩时机由你选择，保留下来的轮次里的 thinking block 在条件满足时于替换之后仍然有效，条件见 [Compaction and preserved thinking](https://platform.claude.com/docs/en/build-with-claude/compaction-thinking-blocks#conditions-for-kept-thinking-to-stay-valid)。这在 Claude Sonnet 5.5 上要紧，因为它的 thinking block 绑定会话。平台可用性与完整请求流程见 [Compaction on demand](https://platform.claude.com/docs/en/build-with-claude/compaction-on-demand)。

### 在消息里定义工具（beta）

带 `inline-tools-2026-09-15` beta header 时，mid-conversation system message 里的 `tool_addition` block 可以携带完整的工具定义，无需引用 `tools` 清单。会话中途可以新增工具、改它的 schema、把服务端工具升到新版本，既不动 `tools` 也不损失 prompt cache。见 [Define tools in a message](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages#define-tools-in-a-message-beta)。

### thinking block 跟随产生它的账号

Claude Sonnet 5.5 产生的 thinking block 只在产生它的账号或其关联账号里可用。其他账号发来这类 block 时，API 在模型收到之前丢弃，请求照常成功。在 Claude API 与 Google managed 上带 `thinking-binding-controls-2026-08-01` beta header 时，响应把每个被丢弃的 block 列进 `input_transformations`，`reason` 为 `"organization_binding_mismatch"`。更早模型产生的 block 不受影响。见 [thinking blocks from another account](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking#account-bound-thinking)。

## 安全分类与 fallback

Claude Sonnet 5.5 的拒绝类别比 Claude Sonnet 5 多。被拒的请求返回 `stop_reason: "refusal"`，`stop_details` 点名以下类别之一：

- `"cyber"`：请求可能助长网络伤害，如恶意软件或漏洞利用开发。
- `"bio"`：可能助长生物伤害，如危险的实验方法。
- `"frontier_llm"`：可能帮助开发竞品 AI model。
- `"reasoning_extraction"`：要求模型在响应正文里复现内部推理。
- `"general_harms"`：属于其他使用政策区域；良性工作也可能触发。

[服务端 fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#server-side-fallback)（`fallbacks: "default"`，beta，Claude API 与 [Anthropic managed 的 Google Cloud](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/anthropic-managed) 可用）把 `"cyber"` 与 `"frontier_llm"` 的拒绝重试到 Claude Sonnet 5，其余三类不重试。也可以用 [SDK middleware](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#client-side-fallback) 或自行重试。输出开始之前到达的拒绝是否计费取决于类别，但无论哪种都消耗速率配额。见 [How refusals are billed](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#how-refusals-are-billed)。

实时 cyber 防护对从 Claude Sonnet 4.6、4.5 与 Claude Haiku 4.5 迁来的代码是新增的。正当安全工作被挡时，可申请 [Cyber Verification Program](https://support.claude.com/en/articles/14604842-real-time-cyber-safeguards-on-claude-opus-and-sonnet)。

## 迁移清单（按出发模型分组）

顺着分组往下做，做到点名你模型的那组为止。从 Claude Haiku 4.5 迁移时，除「Claude Sonnet 4 或更早」一组外全部适用，最后以「仅 Claude Haiku 4.5」一组收尾。

全部出发模型都要做：

- model ID 改为 `claude-sonnet-5-5`。
- 按 `type` 读 content block，thinking block 原样传回。
- 要继续无前置 thinking 运行，发最低的 thinking 设置（`high` effort 及以下）。
- 强制工具调用换成 `auto` 加 strict 工具。
- 会话保持只增不改。
- computer use 换 toolset，去掉 `fine-grained-tool-streaming-2025-05-14` beta header；Amazon Bedrock 上 `computer_20251124` 仍可用。
- advisor 工具配受支持的 advisor，预期加密的 advice。
- 工具调用之间的文字从 thinking block 读。
- 处理 refusal，配置 fallback。
- 重跑 effort 扫描，重新核定成本基线。

Claude Sonnet 4.6 及更早：

- 预期不带 `thinking` 字段的请求带思考运行；重看 `max_tokens`。
- thinking budget 换成 effort 档位。
- 删掉 `temperature`、`top_p`、`top_k`。
- 展示 thinking 文字的界面设 `display: "summarized"`。
- 重新计数 token，重新预算图像 token。

Claude Sonnet 4.5 及更早：

- 换掉 assistant prefill。
- 用标准 JSON parser 解析工具调用 input。
- 显式设置 `output_config.effort`。
- 删掉 context window 相关 beta header。
- 删掉 `interleaved-thinking-2025-05-14`；`fine-grained-tool-streaming-2025-05-14` 换成 `eager_input_streaming`。
- `output_format` 移到 `output_config.format`。

Claude Sonnet 4 或更早：

- 工具版本升到 `text_editor_20250728` 与 `code_execution_20260521`。
- 处理 `refusal` 与 `model_context_window_exceeded` 两种 stop reason。
- 检查工具字符串参数的尾部换行。
- 删掉 `token-efficient-tools-2025-02-19` 与 `output-128k-2025-02-19`。
- 复查 prompt。

仅 Claude Haiku 4.5：

- 替换 `claude-haiku-4-5-20251001` 及别名 `claude-haiku-4-5`。
- 按更高的单 token 价格重新核定成本。
- 复查在 Claude Haiku 4.5 上短到无法缓存的 prompt。

## 从 Claude Sonnet 4.6 及更早 Sonnet 迁移

先完成前面全部节，替换 `claude-sonnet-4-6`，再做本节改动。从 Claude Sonnet 4.5 或更早迁移的，继续做后面的子节。

### 破坏性变更

不带 `thinking` 字段的请求现在带思考运行，处理方式见前文「thinking 默认开启」与「关闭前置 thinking」。

thinking budget 返回错误。Claude Sonnet 4.6 把 `thinking: {"type": "enabled", "budget_tokens": N}` 当弃用设置接受，Claude Sonnet 4.5 与 Claude Haiku 4.5 用它控制全部思考；Claude Sonnet 5.5 返回 400：

```
"thinking.type.enabled" is not supported for this model. Use "thinking.type.adaptive" and "output_config.effort" to control thinking behavior.
```

删掉 budget，设一个 [effort](https://platform.claude.com/docs/en/build-with-claude/effort) 档位。budget 到 effort 没有固定换算，在两到三个档位上跑你的 eval 再定。

迁移前（Claude Sonnet 4.6）：

```
client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=16000,
    thinking={"type": "enabled", "budget_tokens": 10000},
    messages=[{"role": "user", "content": "..."}],
)
```

迁移后（Claude Sonnet 5.5）：

```
client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=16000,
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},  # or "max", "xhigh", "medium", "low"
    messages=[{"role": "user", "content": "..."}],
)
```

采样参数返回错误：删掉 `temperature`、`top_p`、`top_k`。thinking 文字默认省略，处理方式见「响应里的 thinking 怎么处理」。

### 其他变化

- token 增加约 30%：Claude Sonnet 5.5 用 Claude Sonnet 5 的 tokenizer；对 Claude Sonnet 4.6、4.5 与 Claude Haiku 4.5，同一段文字多产生约 30% 的 token，随内容浮动。用 [token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) 重新计数，重看 `max_tokens` 与成本。
- effort：`xhigh` 是新档位，全部档位经过重校准，处理方式见「推荐动作」。
- 图像：Claude Sonnet 5.5 用高分辨率图像档位，长边最多 2,576 像素、单张图像最多 4,784 visual token；Claude Sonnet 4.6、4.5 与 Claude Haiku 4.5 上限是 1,568 像素与 1,568 token。一张 2000×1500 的图像在 Claude Sonnet 5.5 上约花 2.5 倍 token。见 [Resolution and token cost](https://platform.claude.com/docs/en/build-with-claude/vision#evaluate-image-size)。

### 从 Claude Sonnet 4.5 或更早迁移

在 Claude Sonnet 4.5、Claude Sonnet 4 或 Claude 3.7 Sonnet 上，先完成前面全部节，再做本节改动。

prefill 返回错误。Claude Sonnet 5.5 拒绝预填的最后一个 assistant turn（Claude Sonnet 4.6 与 5 也是如此；4.5、Haiku 4.5 及更早接受）：

```
This model does not support assistant message prefill. The conversation must end with a user message.
```

按 prefill 的用途逐个替换：

- 输出格式：用 [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)，或带 enum 字段的分类工具。
- 开场白：在 system prompt 里要求直接给答案。
- 多余的拒绝：user message 里写清楚指令通常就够。
- 续写：移进 user message，例如 "Your previous response was interrupted and ended with `[previous_response]`. Continue from where you left off."
- 上下文提醒：放进 user turn。

工具 input 的转义可能有出入：用标准 JSON parser 解析 `input`。computer use 不接受 `computer_20250124`，处理方式见前文。Claude Sonnet 4.5 没有 effort 参数，显式设置档位。context window 更大、无需 beta header、输出上限更高，见[模型页](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)；删掉原先的 context window beta header。beta header 清理：删掉 `interleaved-thinking-2025-05-14`（adaptive thinking 自动交错思考）；`fine-grained-tool-streaming-2025-05-14` 换成逐工具的 `eager_input_streaming: true`，该 header 与 computer use 或 browser use toolset 条目同发返回 400，见 [Fine-grained tool streaming](https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming)。`output_format` 参数已弃用，仍要用就加 `structured-outputs-2025-11-13` beta header，不加返回 400；改用 `output_config.format`。

### 从 Claude Sonnet 4 或更早迁移

Claude Sonnet 4 在 Claude API 上已退役，Google managed 与 Amazon Bedrock 仍提供；Claude 3.7 Sonnet 已退役。从这两个模型迁移，先完成前面全部节，再做本节改动：

- 工具版本：用 `text_editor_20250728`，工具名 `str_replace_based_edit_tool`，没有 `undo_edit` 命令；用 `code_execution_20260521`。见 [text editor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool) 与 [code execution tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool#upgrade-to-latest-tool-version)。
- stop reason：处理 `refusal`；Claude 4.5 及之后模型在 context window 上限处还会以 `model_context_window_exceeded` 停止。见 [Handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)。
- 尾部换行：Claude 4.5 及之后模型在工具调用字符串参数里保留它们。
- beta header：删掉 `token-efficient-tools-2025-02-19` 与 `output-128k-2025-02-19`。
- prompt：对照 [prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) 复查。

## 从 Claude Haiku 4.5 迁移

先完成前面全部节（跳过「从 Claude Sonnet 4 或更早迁移」子节），再做本节改动：

- model ID：把 `claude-haiku-4-5-20251001` 或别名 `claude-haiku-4-5` 换成 `claude-sonnet-5-5`。
- 成本：单 token 价格更高，同一段文字产生的 token 也更多；重新计数，重新核定成本基线。见 [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing)。
- prompt caching：最小可缓存 prompt 从 4,096 token 降到 512。
- 交错思考：adaptive thinking 自动在工具调用之间运行，无需 beta header。
- 路由方向：Claude Sonnet 5.5 读 Claude Haiku 4.5 的 thinking block，向上换模型的会话保留推理；换回 Claude Haiku 4.5 时，Claude Sonnet 5.5 的 block 被丢弃。

## 推荐动作

重跑 effort 扫描。Claude Sonnet 5.5 有五个 effort 档位：`low`、`medium`、`high`、`xhigh`、`max`，Claude API 默认 `high`。档位经过重校准，同一档位产生的思考量与 Claude Sonnet 5 不同，不能沿用旧设置。非 agentic 且非延迟敏感的负载从 `high` 起；agentic 编码与多步工具使用，范围明确的任务从 `medium` 起、更难更长的转 `high`；聊天等延迟敏感负载从 `medium` 或 `low` 起。档位设在 `output_config.effort`，见 [Recommended effort levels for Claude Sonnet 5.5](https://platform.claude.com/docs/en/build-with-claude/effort#recommended-effort-levels-for-claude-sonnet-5-5)。之后对照[提示模式](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5)复查针对旧模型的 prompt 指令。

## 可用平台

- Claude API：全部客户，`claude-sonnet-5-5`
- AWS：[Claude in Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)（`anthropic.claude-sonnet-5-5`）与 [Claude Platform on AWS](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws)（`claude-sonnet-5-5`）
- Google Cloud：[Anthropic managed](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/anthropic-managed) 与 [Google managed](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed)，均 `claude-sonnet-5-5`
- Microsoft Foundry：[Claude in Microsoft Foundry](https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry)，`claude-sonnet-5-5`

## 延伸阅读

- [构建 Claude Sonnet 5.5](claude-sonnet-building.md)：选型分界与构建侧的破坏性变更细节。
- [Claude Sonnet 5.5 提示模式](sonnet-prompting.md)：提示词视角的 effort 校准与行为引导。
