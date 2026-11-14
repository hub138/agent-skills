# 构建 Claude Sonnet 5.5（Building with Claude Sonnet 5.5）

- 原文：[Building with Claude Sonnet 5.5](https://claude.dev/blog/building-with-claude-sonnet-5-5/)
- 来源：Anthropic（claude.dev），Addy Osmani 署名
- 发布：2026-09-28
- 译文说明：全文翻译；术语保留英文原词；站内相对链接转为绝对 URL。

## 机制概览

Claude Sonnet 5.5 是 Claude 5.5 家族继 [Opus 5.5](https://claude.dev/blog/getting-the-most-out-of-opus-5-5/) 之后的第二款模型。它比 Sonnet 5 明确升级：更聪明、更高效、快 30%。每 token 单价不变，而 Sonnet 5.5 干同样的活通常用少得多的 token，所以多数工作最多省 30% 成本。

想直接上手，按原样跑这个请求：

```python
import anthropic

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

for block in response.content:
    if block.type == "text":
        print(block.text)
```

循环按 type 逐块读，因为 Sonnet 5.5 默认思考，响应可能以一个 `thinking` block 开头，直接读 `content[0].text` 的代码会坏。

## 选型：Sonnet 5.5 还是 Opus 5.5

Claude 5.5 家族里，Opus 5.5 为需要仔细判断的复杂工作而建。Sonnet 5.5 适合范围清晰的日常任务：修 bug、快速迭代功能。它也能产出精致的文档、幻灯片与表格，对设计有很强的眼光。它的速度让它适合快节奏迭代。Claude Haiku 5.5 将在数周内加入家族，面向大流量、低延迟工作流。

> 「Epic 的早期测试里，Claude Sonnet 5.5 达到了你对更高档模型才敢期待的质量线，扛住了系统设计审计与数据流审查。新模型管理了数万行游戏玩法系统架构代码，响应保持利索，处理了多小时任务，prompt 也不用写那么细。」（Daniel Vogel，Epic Games COO）

Sonnet 5.5 最适合任务有清晰规格、结果有办法检验的场景。如 [prompting guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5) 所说：「最难的长程工作，Opus model 是更好的选择。」

## 定价

Sonnet 5.5 的全部价格，包括 batch 处理与 prompt caching，与 Sonnet 5 一致，换 model ID 不改你的每 token 账单。仅美国推理（`inference_geo: "us"`）是标准价的 1.1 倍。

每 token 价格不变，但总账单会变：如前所述，Sonnet 5.5 干同样的活通常用更少 token。

注意各表面给 Sonnet 的默认 effort 可能不同，比如 Claude Platform 上是 high，[Claude Code](https://claude.com/product/claude-code) 里是 medium。

Sonnet 5.5 用高分辨率图片档，长边最多 2576 像素，一张 2000×1500 图片的 token 数约是 Sonnet 4.6、Sonnet 4.5 或 Haiku 4.5 上的 2.5 倍。不需要细节就在发送前缩小。

## 模型细节

Claude API 默认 `high`，让你从强结果起步。从那里开始，评估，再选你的工作负载需要的 effort 档位。想用 `xhigh` 或 `max` effort 的话记住：Sonnet 5.5 会思考更久、花得更多。有些任务上你会失去 Sonnet 的有用之处：质量、速度与成本的平衡。那种情况考虑 Opus 5.5。

## 从 Sonnet 5 迁移

思考默认开启。你之前跑 Sonnet 5 关着思考的话，用 `between_tools` 关掉 upfront thinking。步骤 1 展示做法。

把 model ID 改成 `claude-sonnet-5-5`，然后处理五项破坏性变更与一项响应形态变化。[Sonnet 5.5 迁移指南](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide) 逐项完整覆盖。

Claude Code 也能替你迁移。跑 `/claude-api migrate this project to claude-sonnet-5-5` 调用内置的 [Claude API skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill#migrating-to-a-newer-claude-model)，它会在整个代码库里应用 model ID 替换与破坏性参数变更。

### 1. 用 between_tools 关掉 upfront thinking

Sonnet 5.5 上，不带 `thinking` 字段的请求跑 adaptive thinking，`thinking: {"type": "disabled"}` 返回 400 错误。改发新的 `between_tools` 设置。`between_tools` 下思考只发生在工具调用之间，总响应时间持平或更快。

```python
# Before: Claude Sonnet 5
client.messages.create(
    model="claude-sonnet-5",
    max_tokens=16000,
    thinking={"type": "disabled"},
    output_config={"effort": "xhigh"},
    messages=[{"role": "user", "content": "..."}],
)

# After: Claude Sonnet 5.5
client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=16000,
    thinking={"type": "between_tools"},
    output_config={"effort": "high"},
    messages=[{"role": "user", "content": "..."}],
)
```

例子里 effort 从 `xhigh` 降到 `high`，因为 `between_tools` 有这些限制：

- `between_tools` 在 `low`、`medium` 与 `high` effort 下工作。`xhigh` 或 `max` 下返回 400 错误；要在那里跑，用 adaptive thinking。
- 它不带其他字段。随它发送 `display`、`budget_tokens` 或 `block_binding` 返回 400 错误。
- `between_tools` 下，effort 不能在对话中途变化。要逐轮变 effort，用 adaptive thinking。
- 模型在工具调用之间写的简短进度更新仍以 `thinking` block 形态返回，带摘要文字。按 type 读 content block，把这些 block 原样随 assistant 轮的其他内容传回。没有工具时，响应只含 text。
- 它在提供 Sonnet 5.5 的每个平台都能用，不需要 beta header。你的 SDK 版本没定义 `between_tools` 的话，升级它。

用 `between_tools` 关掉 upfront thinking 后，对没有工具但需要几步推演的请求改用 adaptive thinking。

### 2. 用 auto 加 strict tools 取代强制 tool_choice

`any` 或 `tool` 型 `tool_choice` 返回 400 错误，token counting 端点上也一样。改发 `auto`，给工具标 `strict: true` 让输入符合 schema，并在 prompt 里说明何时用它：

```python
weather_tool = {
    "name": "get_weather",
    "description": "Get the current weather in a given location",
    "input_schema": {
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
        "additionalProperties": False,
    },
    "strict": True,
}

client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=1024,
    tools=[weather_tool],
    tool_choice={"type": "auto"},  # was {"type": "tool", "name": "get_weather"}
    messages=[
        {"role": "user", "content": "What's the weather in Paris? Use the get_weather tool."}
    ],
)
```

strict tool use 要求每个 object 都带 `additionalProperties: false`。

### 3. 保持对话 append-only

Sonnet 5.5 的 thinking block 绑定 model 与对话。Sonnet 5.5 能读 Sonnet 5 的 thinking block，所以从 Sonnet 5 切到 Sonnet 5.5 的对话保留其推理链。没有其他 model 读得了 Sonnet 5.5 的 block。

### 4. 把 computer use 迁到 toolset

Claude API 与 Google Cloud 上，Sonnet 5.5 只经 `{"type": "computer_toolset_20260801"}` 支持 computer use；声明 `computer_20251124` 的请求返回 400 错误。把请求里的 `anthropic-beta: computer-use-2025-11-24` header 删掉，SDK 里去掉 `betas` 参数，用标准 client 调 Messages API，别用 beta namespace。替换 `tools` 条目，并为成员 `tool_use` block、批量动作与结果上的 `toolset_name` 更新你的 agent 循环。如果你发 `fine-grained-tool-streaming-2025-05-14` beta header，也删掉它，因为跟 toolset 条目一起发返回 400 错误；改为在每个需要它的工具上设 `eager_input_streaming: true`。Amazon Bedrock 仍接受 `computer_20251124`。

### 5. 检查你的 advisor 搭配

advisor tool 下，Sonnet 5.5 执行器拒绝 Opus 4.8、Opus 4.7 与 Sonnet 5 当 advisor。可接受的 advisor 包括 Opus 5.5、Opus 5 与 Sonnet 5.5 自己。来自每个被接受 advisor 的 advice 以加密形态返回，是一个 `advisor_redacted_result` block，所以你的代码读不到 advice 文本。

### 6. 从 thinking block 读工具调用之间的文字

这项变化不引发错误，但 UI 可能不再显示模型在工具调用之间的笔记。那些笔记超过一两句时，以 progress-update `thinking` block 形态返回，默认 `display` 下为空。

adaptive thinking 下，把 `thinking.display` 设为 `"updates"`（beta，带 `thinking-display-updates-2026-08-18` header）或 `"summarized"`，在每个非空 `thinking` block 之后、紧随其后的 `tool_use` block 之前渲染它。`between_tools` 下，文字不经 `display` 直接返回。

Sonnet 5.5 还加了 per-message effort（beta）、对话中途 system message 与对话中途工具变更（beta）。从 Sonnet 4.6 或更早、或从 Haiku 4.5 迁移的话，[迁移指南](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide) 为每个起始 model 准备了清单。

## 调优

### 重跑 effort 扫描

effort 档位重校准了，同一档位产生的思考量与 Sonnet 5 上不同，旧设置带不过来。除非工作负载是 agentic 或延迟敏感，从 `high` 起步。agentic 编码与多步工具使用，范围明确的任务从 `medium` 起，更难更长的转 `high`。聊天与其他延迟敏感工作从 `medium` 或 `low` 起。只在 eval 显示质量收益时才用 `xhigh` 或 `max`。

思考计入 `max_tokens`，要留余地。agentic 编码把 `max_tokens` 设为 128,000（model 上限）并流式读响应。想少思考就降 effort 档位，在 system prompt 里叫模型少想不可靠。

### 删掉 Sonnet 5 的绕路手段

既有 Sonnet 5 的 prompt 不改也该表现良好。如果你的 prompt 里带着绕路手段，比如 refusal steering、tool-call retry shim 或「不许偷懒」，删掉它们并在调其他任何东西之前重跑 eval。

### 低 effort 下要求真实检查

Sonnet 5.5 一般会在报告改动完成前检查自己的工作，但 `low` effort 下有时会跳过一个真正执行改动的检查。如果你看到改动被报告完成却没有测试或构建输出，prompting guide 推荐这段 system prompt：

```text
When you change code that can be run, built, or type-checked, run a real
check that exercises the change before reporting it done: the project's
tests, type-checker, or build, or the changed command itself. A syntax-only
check, or a check command that failed to start, does not count; if all
that's missing is the project's declared dependencies, install them with
its own package manager and lockfile (e.g. npm install, pip
install -r requirements.txt), never via sudo or the system package manager,
unless told not to. Only if no real check can run here, say which one you
did not run and why instead of reporting the change as done.
```

### 用 thinking.display 做进度

别让模型在响应里写出它的推理，因为那会招来 `reasoning_extraction` 拒绝。改读摘要化的思考：

```python
thinking={"type": "adaptive", "display": "summarized"}
```

要单独的用户可见进度笔记，用 `display: "updates"`（beta）。想要可预期的更新点，比如第一次工具调用前一行、结尾一段简短回顾，在 system prompt 里说明。

### 缓存更多 prompt

最小可缓存 prompt 降到 512 token，更短的 system prompt 与工具定义现在也够格。cache read 花费是输入价的十分之一。请求之间改顶层 effort 会[让缓存失效](https://claude.dev/blog/lessons-from-building-claude-code-prompt-caching-is-everything/)；要单跑一轮不同档位，用 per-message effort（beta），它保住缓存。

> 包内互引：prompt caching 的完整策略（断点、更新纪律、五原则）见 claude-harness-design-patterns.md 与 claude-message-threads.md。

## 拒绝与 fallback

我们的自动化行为审计里，Sonnet 5.5 在多数 alignment 与诚实指标上改进或持平于 Sonnet 5。它也是第一款带与我们最强 model 相当的网络安全防护的 Sonnet model。多数常规软件开发不受影响。

被拒绝的请求返回 HTTP 200 与 `stop_reason: "refusal"`，`stop_details` 点名五个类别之一：`cyber`、`bio`、`frontier_llm`、`reasoning_extraction` 或 `general_harms`。服务端 fallback（`fallbacks: "default"`，beta，Claude API）会把 `cyber` 与 `frontier_llm` 拒绝重试到 Sonnet 5 上。其余三类不重试。你也可以用 SDK middleware 或自己的重试。

合法安全工作上，Cyber Verification Program 即将扩展覆盖 Sonnet 5.5。

## 可用性

Claude Sonnet 5.5 今日起在下列平台可用。开发者平台上用这些 model ID：

- Claude API：`claude-sonnet-5-5`
- Amazon Bedrock：`anthropic.claude-sonnet-5-5`
- Claude Platform on AWS：`claude-sonnet-5-5`
- Google Cloud：`claude-sonnet-5-5`
- Microsoft Foundry：`claude-sonnet-5-5`，仅 Global Standard 部署

### Claude Code 里

从 Claude Code v2.1.284（Agent SDK for TypeScript v0.3.284 或更高）起，`sonnet` 别名在 Claude API 上解析为 Sonnet 5.5。它默认以 `medium` effort 运行，1M 上下文窗口原生。Claude Code 里你关不掉 Sonnet 5.5 的思考，effort 决定 model 想多少。Sonnet 5.5 没有 fast mode。`default` model 仍是 Opus 5.5，范围明确的任务用 `/model sonnet` 切过去。

希望大家试用 Sonnet 5.5 时有所收获，也一如既往欢迎反馈。
