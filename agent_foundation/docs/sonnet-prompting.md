# 给 Claude Sonnet 5.5 写提示词（Prompting Claude Sonnet 5.5）

- 原文：[Prompting Claude Sonnet 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5)
- 来源：Anthropic（Claude Platform 文档），机构署名
- 发布：文档页未标注发布日期
- 译文说明：全文翻译；术语保留英文原词；站内相对链接转为绝对 URL。

本指南覆盖 Claude Sonnet 5.5 特有的提示模式。model 的 API 变更见 [What's new in Claude Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5)。适用于全部现役 Claude model 的通用技巧见 [Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)。

既有的 Claude Sonnet 5 提示词不做改动通常也能工作良好，[Prompting Claude Sonnet 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5) 里的模式仍是合理的起点。最困难的长时程工作，选 Opus model 更合适。按你观察到的现象对号入座：

- 不确定该用哪个 effort 档位，或轮次比 Claude Sonnet 5 上更长或更短：见「校准 effort」
- model 在编码任务完成之前停下来确认，或做了超出要求的事：见「引导主动性与范围」
- 你的集成今天关着 thinking 跑：见「无前置 thinking 运行」
- 需要几步推演的任务拿到的 JSON 答案错误或解析不了：见「带 JSON 输出的推演任务」
- 长的 agentic 轮看起来静默无声：见「给用户看的进度更新」
- 该搜索的时候 model 用训练知识回答已变化的细节：见「聊天与知识工作中的工具使用」
- 用户任务中途发的消息被忽略或被当成注入文本：见「任务中途的用户消息」
- 代码改动报告完成却没有跑测试或构建：见「编码任务上的验证」
- model 以错误的字母大小写调用工具，或用稍有出入的名字传参数：见「宽容的工具调用处理」
- 关于密集图表或技术图纸的回答漏掉细节：见「复杂视觉输入的工具」
- 请求返回 `stop_reason: "refusal"`：见「安全拒绝」

## 校准 effort

[Effort](https://platform.claude.com/docs/en/build-with-claude/effort) 是控制 Claude Sonnet 5.5 思考多少的主旋钮，随之变化的是质量、延迟与成本。它的档位经过重校准：同一个档位产出的思考量与 Claude Sonnet 5 上的同档位不同。对着你自己的 eval 重新跑一遍扫描，别把 Claude Sonnet 5 上用的取值直接带过来。从 `high` 起步（Claude API 的默认值），除非你的负载是 agentic 或对延迟敏感。agentic 编码与多步工具使用，范围明确的任务从 `medium` 起，更难更长的转 `high`。聊天等延迟敏感的工作从 `medium` 或 `low` 起，因为更高的 effort 意味着回复开始前更长的等待。质量需要就升高 effort。

较低的 effort 也改变 model 完成 agentic 工作的方式。`low` 档下它保持思考简短、可能跳过对改动的验证，见「编码任务上的验证」。`low` 与 `medium` 档下，长的 agentic 任务里它更可能在完成工作之前停下来与用户确认，见「引导主动性与范围」。

三个调整有帮助：

- 设 `max_tokens` 时给 thinking 与预期回复留出余地。thinking 计入 `max_tokens`，即使 thinking 内容不返回给你。按没有 thinking 的请求尺寸设的限额会把回复截断。agentic 编码把 `max_tokens` 设到 128,000（model 的最大值），并[流式](https://platform.claude.com/docs/en/build-with-claude/streaming)返回响应。
- `xhigh` 与 `max` 留给实测到质量收益的工作，这两档的 thinking 与回复长得多；且这两档不接受 `between_tools`，前置思考关不掉。
- 想要更少思考，降低 effort 档位。在 system prompt 里叫 model 少想，并不能可靠减少它的思考。

请求之间改变顶层 `effort` 值会让 prompt cache 失效。要在一轮对话中途换档，改用 [per-message effort change](https://platform.claude.com/docs/en/build-with-claude/effort#change-effort-mid-conversation-beta)（beta），它保住缓存。一次变更对后续每一轮持续生效，直到下一次变更替换它。例如 `low` 的交互会话里，在用户的难题之前加一条升到 `high` 的变更，Claude 答完之后再转回 `low`。per-message effort 需要 adaptive thinking；`between_tools` 下它返回 400 错误，见「无前置 thinking 运行」。

## 引导主动性与范围

Claude Sonnet 5.5 自己走多远，取决于 effort 档位与请求本身。较低 effort 下它有时在编码任务完成之前停下来确认；较高 effort 或开放式请求下，它可能做超出你要求的事。用 effort 档位与 system prompt 里的指令引导。

**把工作连续做完。** `low` 与 `medium` effort 的 agentic 编码任务上，model 有时在工作完成前停下来：确认计划、问一个自己能回答的问题、或多段任务做完一段就问要不要继续。先试更高的 effort 档位。想在不改 effort 的前提下让 model 连续工作，把这段加进 system prompt：

```
Keep working until everything the user asked for is done, and only stop to ask when you can't go on without the user or before a risky step.

When the work the user asked for is done and checked, stop and report. Don't add features, tests, files, docs or refactors that weren't asked for. If you think one would help, mention it at the end instead of doing it.
```

加上这段 prompt，model 在 `low` 与 `medium` effort 下把更多工作连续做完，这两档的会话因此更长、成本更高。这段 prompt 不取代你自己关于风险或不可逆操作的规则，那些规则留在 system prompt 里。

**编码时未经要求的添加。** model 倾向按你仓库的惯例添加测试、文档与小支撑文件，即使你没有要求。每个 effort 档位都会这样做，高档位更多。被要求的改动本身贴近要求。多数团队欢迎这一点。想把改动限制在明确要求的范围内，就只把上面那段 prompt 的第二段（以 "When the work the user asked for is done." 开头）加进去。`xhigh` 与 `max` effort 下，那一段会减少这类添加，让改动整体更小。

**`xhigh` 与 `max` effort 下的彻底性。** 这两档的 model 特别彻底。完成任务之后，它可能自己开始一轮轮 review 与验证，harness 提供 subagent 时就用 subagent；还可能顺手修它注意到的相关问题。这花更多时间与 token，例行工作在 `high` 或更低档位跑，那里这种行为罕见。如果你确实想要这两档的额外彻底性、又想让它对准任务本身，把这段加进 system prompt：

```
When the work the user asked for is done and its checks pass, stop and report. Don't start extra rounds of review or hardening on your own, and don't launch reviewer sub-agents unless the user asked for a review. If you think a deeper review is worth doing, say so at the end.
```

编码任务 `max` effort 的测试里，这段停掉了 model 启动 reviewer subagent 的行为，会话成本降约三分之一，质量无可测变化。它让主 agent 自己发起的 review 轮更少见，但没有完全消除。

**开放式请求。** 请求开放时（例如「给我看看你拿它能做什么」），model 可能直接开始做演示、报告或视频，而你只想要想法。想要想法或计划先行，就在请求里说明，或把这段加进 system prompt：

```
When the user asks for ideas, options or a plan, give them that and stop. Don't start building or changing anything until they say to go ahead.
```

## 无前置 thinking 运行

要让 Claude Sonnet 5.5 不带前置 thinking 运行，发送 `thinking: {"type": "between_tools"}`。它是这个 model 上最低的 thinking 设置，`high` effort 及以下接受。你的集成今天关着 thinking 跑的话，切换到 `between_tools` 并核对这几点：

- **`high` effort 及以下发送 `between_tools`。** `xhigh` 或 `max` effort 下带 `between_tools` 的请求返回 400 错误。`between_tools` 下 effort 也不能对话中途变更：per-message `output_config.effort` 与生效档位不同就返回 400。要每轮变 effort，用 adaptive thinking。`between_tools` 下删掉任何叫 model 不要思考的指令，这类指令让 model 更可能把内部 XML 标签写进可见输出。
- **按 block type 读响应。** adaptive thinking 下，响应可能从 `thinking` block 开始，默认 `display: "omitted"` 下它的 `thinking` 字段为空。`between_tools` 下，响应可能从 progress-update `thinking` block 开始。不要假设第一个 content block 是 text。
- **`thinking` block 原样传回。** `between_tools` 下，model 在工具调用之间写的笔记超过一两句时仍以 `thinking` block 回来，每个 block 带该笔记的摘要。把它们与 assistant 轮的其余部分原样传回。你传回去的 block 给 model 的是它写下的完整笔记，而非摘要。
- **无工具的推演任务用 adaptive thinking。** 不带工具的请求里，`between_tools` 意味着 model 不先思考就回答。需要几步推演的任务改用 adaptive thinking，见「带 JSON 输出的推演任务」。

## 带 JSON 输出的推演任务

本节适用于：你向 Claude Sonnet 5.5 要一个 JSON 答案，而任务需要几步推演。例子包括合计文档里的数字、套用一条规则、给条目排序。这类任务上 model 常不先思考就作答，`low` 与 `medium` effort 下尤其如此。什么有帮助，取决于你怎么请求 JSON。有 [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) 的地方优先用它，响应文本就是符合你 schema 的 JSON，没有需要解析的东西。

structured outputs 下，响应文本里只有 JSON，model 只能在 thinking 里推演。它跳过思考时，这类任务的准确度会低一些。这些改动能把准确度保持在高处。

**叫 model 先想。** adaptive thinking 下，把这行加在 system prompt 末尾：

```
Think the problem through before you answer.
```

有了这行，model 更常在回答前思考。`high` effort 下，这行把准确度带到接近 `xhigh` 的水平，输出 token 适度增加。`low` 与 `medium` effort 下它提升准确度，但到不了 `high` 的水平，输出 token 的增幅也更大。

**或直接用 `xhigh` effort。** adaptive thinking 下，`xhigh` 在这类任务上给出最高准确度，即使不加那行。它比 `high` 用更多输出 token。

**用 adaptive thinking，别用 `between_tools`。** 不带工具的请求里，`between_tools` 下 model 不先思考就作答，那行在那里无效，这类任务的准确度也更低。这类请求用 adaptive thinking 配本节的步骤。测试里把请求分成两份（答案一份、JSON 一份）得到了高答案准确度与 JSON 合规，但成本与延迟极高。

structured outputs 在 `low` 与 `medium` effort 下，model 偶尔一直思考到 `max_tokens`。`high` effort 及以上几乎不发生。`stop_reason` 为 `"max_tokens"` 的响应一律当失败处理，即使文本里是有效 JSON，然后重试。`max_tokens` 按「校准 effort」一节说的给 thinking 与 JSON 留够，但不超过你愿意为一次尝试花的。

用不上 structured outputs 时，在 prompt 里要 JSON。model 于是常在响应文本里推演，最后写 JSON。JSON 通常带着正确答案，但期待整个响应都是 JSON 的解析器会失败。两件事有帮助：

- **解析响应里最后一个 JSON 值。** 只读 `text` block，`stop_reason` 为 `"max_tokens"` 的响应当失败。从每个 `{` 或 `[` 起尝试解析一个 JSON 值，解析成功后从该值末尾继续，嵌套在里面的值不单独计数。保留最后找到的值。不要从第一个 `{` 取到最后一个 `}`：model 偶尔在最终 JSON 前写草稿，那个范围会把两者都包进来。答案是几个 JSON 值连排时（例如每行一条记录），保留最后一段仅由空格、逗号或换行分隔的连续值。校验结果有没有你期望的字段，没有就重试一次。测试里这让几乎每个响应都可用，准确度没有变化。
- **也考虑 `xhigh` effort 加 adaptive thinking。** model 于是把推演放进 thinking，几乎总是单独返回 JSON。输出 token 总量与 `high` 相当，因为推演从响应文本挪进了 thinking。

## 给用户看的进度更新

工具调用之间，Claude Sonnet 5.5 会写给用户看的笔记：刚发现了什么、接下来做什么。超过一两句的笔记以 [progress-update `thinking` block](https://platform.claude.com/docs/en/build-with-claude/thinking#progress-updates) 回来，更短的话留在 `text`。默认 `thinking.display` 下，progress-update block 的文本为空，只渲染 `text` block 的客户端在长的 agentic 轮里看起来静默。这在聊天界面等用户实时跟进 model 工作的产品里最要紧。

要展示这些笔记，设 `display: "updates"`（beta，`thinking-display-updates-2026-08-18` header）。`between_tools` 下笔记带着摘要文本回来，不需要 `display` 字段；`between_tools` 不接受任何其他字段：`display`、`budget_tokens` 或 `block_binding` 跟着它发送都返回 400 错误。migration guide 的 [text between tool calls](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide#text-between-tool-calls) 一节展示了怎么渲染这些笔记。有时 model 需要在长轮中途给用户看确切文本，比如一段代码或一个需要用户回答的问题。给这种情况配一个让 model 给用户发消息的简单工具，并告诉 model 只有这类内容才用它。工具在会话的第一个请求里声明，`tools` 列表后续就不变。

接着删掉「hold all findings for the final response」这类旧指令。然后想要可预期的更新点（例如第一次工具调用前说一行将做什么、结尾做简短回顾），在 system prompt 里说明，model 会遵循这类指令。固定点的更新在有人盯的工作里帮助最大。

长的工具调用轮仍然静默得超出你的预期时，harness 可以促成一次更新。让它数连续多少个工具调用步没有给用户发 text 或 progress update，连续若干步（例如五步）后，在最新的 tool results 之后追加一条单轮提醒，以 [turn-scoped system message](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages#turn-scoped-system-messages)（beta）发送，文本例如：

```
The user hasn't heard from you in a while — say in a few words what you're doing, then continue.
```

这轮仍然静默，第二次或第三次之后就不再发送。工具结果后频繁出现 harness 文本，会让 model 把那类文本当成可能的 prompt injection，见「任务中途的用户消息」。每条提醒在后续请求里保留在 `messages` 中：提醒是追加的、没有插入后再删除，prompt cache 与 [preserved thinking](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking) 保持完好。`high` effort 下，配着一个给用户发消息的工具，这条提醒让 model 更常更新用户、最长的静默段缩短，任务质量无可测变化。

## 聊天与知识工作中的工具使用

聊天与知识工作类任务上，Claude Sonnet 5.5 有时用训练知识回答本该 web 搜索能抓到变化的问题，例如什么允许、什么要求、什么收费。

先检查 prompt 里有没有打击工具使用的语言（「only use tools when strictly necessary」「minimize tool calls」），删掉。然后，产品给 model 配了搜索工具的话，把这段加进 system prompt：

```
Use the search tool to check specifics that may have changed since your training, such as what is allowed, required or charged, even when you feel confident. For researched work such as a report or a comparison, gather current sources rather than writing from your training knowledge.
```

这在答案依赖当下细节的研究与客服产品里最要紧。

## 任务中途的用户消息

Claude Sonnet 5.5 被训练抵抗间接 prompt injection：经由 tool result 与任务中读到的其他内容到达的恶意指令。有时它把真实的用户消息也当成可能的注入。设想用户任务中途输入的消息以 [mid-conversation system message](https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages) 的形态紧跟在 tool result 之后到达，或塞进 `tool_result` block 里。model 于是可能告诉用户 tool result 里有冒充用户消息的文字，然后忽略该消息或要求用户确认。

harness 在每个 tool result 后加的 token 倒计时会造成这个。允许用户在 model 多步轮进行到一半时发消息、或 harness 每步都在 tool results 后加指令或上下文，同样会。每种情况里，文字都紧跟 tool results 到达；有倒计时或每步指令时，每次工具调用都会发生。偶尔一次的单轮提醒（例如「给用户看的进度更新」里那条）到达的频率低得多。看到 model 对你自己的提醒有这种反应，就降低提醒频率。要避免这种误读：

- 用户文字绝不放进 `tool_result` block，这种摆放被误读的次数最多。
- 任务中途的用户输入作为 user turn 送达：用户的文字作为 text block 附在携带 `tool_result` blocks 的 user message 里、放在最后一个 `tool_result` 之后。
- harness 的通知（提醒一类）放单独的 mid-conversation system message，跟着用户文字；通知与用户文字绝不进同一个 block。
- 用户能中途输入的交互会话里，不要在 tool results 后加自己的 token 或预算倒计时。[Task budgets](https://platform.claude.com/docs/en/build-with-claude/task-budgets)（beta）加的是类似倒计时，还没见过它引发这种误读；设着 task budget 仍见误读的话，试一次不带它的会话。

## 编码任务上的验证

agentic 编码任务上，Claude Sonnet 5.5 一般在报告改动完成之前自查。`low` effort 下它有时不跑真正执行改动的检查就报告完成，比如因为项目依赖没装而跳过测试。

看到改动报告完成而 transcript 里没有测试或构建输出，就把这段（或类似的文字）加进 system prompt。`low` effort 下它让跳过或敷衍的检查变得罕见，任务质量无可测变化，单任务成本略高：

```
When you change code that can be run, built, or type-checked, run a real check that exercises the change before reporting it done: the project's tests, type-checker, or build, or the changed command itself. A syntax-only check, or a check command that failed to start, does not count; if all that is missing is the project's declared dependencies, install them with its own package manager and lockfile (e.g. npm install, pip install -r requirements.txt), never via sudo or the system package manager, unless told not to. Only if no real check can run here, say which one you did not run and why instead of reporting the change as done.
```

（这段与[构建 Claude Sonnet 5.5](claude-sonnet-building.md)的真实检查文字同源，两篇共用同一段 system prompt。）

## 宽容的工具调用处理

Claude Sonnet 5.5 偶尔以仅字母大小写不同的名字调用已声明的工具（例如用 `bash` 调 `Bash`），或以稍有出入的名字传已知参数。与其把这类调用当致命错误，让 harness 用两种方式之一处理：

- 匹配无歧义时接受调用，即使大小写错。
- 返回带 `is_error: true` 的 `tool_result`，写明确切期望的名字。model 通常下一轮就改正。见 [Handling errors with `is_error`](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls#handling-errors-with-is-error)。

## 复杂视觉输入的工具

密集图表与技术图纸，给 Claude Sonnet 5.5 一个能裁剪、缩放或对图片跑代码的方式。有这样的工具，model 读这类输入的准确度显著提升。图表上每个 effort 档位都有帮助；技术图纸上只有 `high` effort 起有效，`xhigh` 与 `max` 最强。图表上配工具，比把 effort 档位升高的收益更大：测试里 `high` effort 带工具比 `max` effort 无工具读得更准，成本只是一部分。[crop tool recipe](https://platform.claude.com/cookbook/multimodal-crop-tool) 有可用的工具定义。

## 安全拒绝

Claude Sonnet 5.5 跑着安全分类器，可能拒绝请求。拒绝以正常响应的形态到达，`stop_reason: "refusal"`，`stop_details.category` 标明[拒绝类别](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#refusal-response)：

- `cyber`：请求可能助成网络伤害，例如恶意软件或漏洞利用开发。在源码里找漏洞允许；高风险双用网络安全工作不允许。
- `bio`：请求可能助成生物伤害，例如危险实验方法。日常健康与教育问题不受影响。
- `frontier_llm`：请求可能帮助开发竞品 AI model。
- `reasoning_extraction`：请求要求 model 在响应文本里复现内部推理。
- `general_harms`：请求属于其他使用政策区域，良性工作也可能触发这个类别。

`cyber` 分类器挡住你们组织的合法安全工作时，可以申请 [Cyber Verification Program](https://support.claude.com/en/articles/14604842)。`bio` 分类器挡住生命科学工作时，可以申请 [Life Sciences Verification Program](https://www.anthropic.com/news/life-sciences-verification-program)。

开启[服务端 fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#server-side-fallback)（beta）时，它把 `cyber` 与 `frontier_llm` 的拒绝重试到 Claude Sonnet 5；`bio`、`reasoning_extraction`、`general_harms` 不重试。见 [Refusals, fallback, and billing](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5#refusals-fallback-and-billing)。

prompt 里要求 model 把推理写进响应的，删掉那些指令，它们招 `reasoning_extraction` 拒绝。adaptive thinking 下改从 [summarized thinking](https://platform.claude.com/docs/en/build-with-claude/thinking#summarized-thinking) block 读推理（`display: "summarized"`）。仍然可以要求对答案的简短解释或动作摘要，见 [Keep reasoning in thinking blocks](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#keep-reasoning-in-thinking-blocks)。

---

延伸阅读：
- [构建 Claude Sonnet 5.5](claude-sonnet-building.md)：本篇的配套构建指南，API 变更、迁移与调优细节在那里展开。
- [Claude Code 最佳实践](claude-code-best-practices.md)：跨 model 通用的提示与工程技巧。
