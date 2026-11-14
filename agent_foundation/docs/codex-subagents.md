# Codex subagents：并行子智能体工作流（Subagents）

- 原文：https://developers.openai.com/codex/concepts/subagents
- 来源：OpenAI（Codex 官方文档）
- 发布：官方文档页，随 Codex 版本持续更新
- 译文说明：全文翻译，术语保留英文原词，代码块与命令保持英文原文。

Codex 可以通过并行衍生专用智能体来运行子智能体工作流，让它们同时进行探索、处理或分析工作。

本页介绍核心概念与权衡考量。有关设置、智能体配置及示例，见 [子智能体](https://developers.openai.com/codex/subagents)。

## 为什么子智能体工作流有帮助

即使拥有庞大的上下文窗口，模型也存在局限。如果你用嘈杂的中间输出（如探索笔记、测试日志、stack trace 和命令输出）填满主对话（即你定义需求、约束和决策的地方），会话的可靠性会随时间下降。

这通常被称为：

**上下文污染（Context pollution）**：有用的信息被淹没在嘈杂的中间输出之下。

**上下文腐化（Context rot）**：随着对话中充斥着不那么相关的细节，模型表现会退化。

背景阅读见 Chroma 的[上下文腐化](https://research.trychroma.com/context-rot)研究报告。

子智能体工作流通过把嘈杂的工作移出主线程来提供帮助：

保持**主智能体**专注于需求、决策和最终输出。

针对探索、测试或日志分析，并行运行专门的**子智能体**。

从子智能体返回**摘要**，避免返回原始的中间输出。

当工作可以独立并行运行时，它们还能节省时间；把较大的任务分成有边界的片段，也使其更易于管理。例如，Codex 可以把对数百万 token 文档的分析分成较小的问题，并把提炼出的结论返回给主线程。

作为起点，对于阅读密集型任务（如探索、测试、分类和总结），使用并行智能体。对于并行写入密集型工作流请务必谨慎，因为多个智能体同时修改代码可能导致冲突并增加协作成本。

## 核心术语

Codex 在子智能体工作流中使用了一些相关术语：

**子智能体工作流（Subagent workflow）**：Codex 运行并行智能体并汇总其结果的工作流。

**子智能体（Subagent）**：由 Codex 启动并受委托处理特定任务的智能体。

**智能体线程（Agent thread）**：智能体的 CLI 线程，你可以使用 `/agent` 对其进行检查并切换。

## 触发子智能体工作流

Codex 不会自动生成子智能体。它只应在被明确要求使用子智能体或并行智能体工作时才会使用它们。

在实践中，手动触发意味着使用直接指令，例如「生成两个智能体」「并行委托此任务」或「每个要点使用一个智能体」。子智能体工作流比类似规模的单智能体运行消耗更多的 token，因为每个子智能体都会进行自己的模型推理和工具调用。

一个好的子智能体提示词应该解释如何分配工作、Codex 是否应在继续前等待所有智能体完成，以及应返回何种摘要或输出。

```
Review this branch with parallel subagents. Spawn one subagent for security risks,
one for test gaps, and one for maintainability. Wait for all three, then summarize
the findings by category with file references.
```

## 选择模型与推理

不同的智能体需要不同的模型和推理设置。

如果你未指定模型或 `model_reasoning_effort`，Codex 会选择一种平衡任务智能水平、速度和成本的配置。它可能会选用 `gpt-5.4-mini` 进行快速扫描，或使用更高配置的 `gpt-5.5` 处理要求更高的推理。当你想要更细致的控制时，在提示词中引导该选择，或直接在智能体文件中设置 `model` 和 `model_reasoning_effort`。

对于 Codex 中的大多数任务，从 `gpt-5.5` 开始。当你想要更快速、更低成本的选项来处理较轻的子智能体任务时，使用 `gpt-5.4-mini`。如果你有 ChatGPT Pro 并希望进行近乎即时的纯文本迭代，`gpt-5.3-codex-spark` 仍可在研究预览版中使用。

### 模型选择

**`gpt-5.5`**：从这里开始处理高要求智能体。它最擅长处理需要规划、工具使用、验证，并在较大上下文范围内持续跟进的歧义性、多步骤任务。

**`gpt-5.4`**：当工作流固定使用 GPT-5.4 时使用。它结合强大的编码、推理、工具使用能力和更广泛的工作流支持。

**`gpt-5.4-mini`**：用于把速度和效率置于深度之前的智能体，例如探索、阅读密集型扫描、大文件评审或处理辅助文档。它非常适合作为向主智能体返回提炼结果的并行工作者。

**`gpt-5.3-codex-spark`**：如果你有 ChatGPT Pro，当延迟比更广泛的能力更重要时，使用此研究预览模型进行近乎即时的纯文本迭代。

### 推理努力度（model_reasoning_effort）

**`high`**：当智能体需要追踪复杂逻辑、检查假设或处理边缘情况（例如评审或安全类智能体）时使用。

**`medium`**：大多数智能体的平衡默认值。

**`low`**：当任务直截了当且速度最为重要时使用。

更高的推理努力度会增加响应时间和 token 使用量，但可以提高复杂工作的质量。有关详细信息，见[模型](https://developers.openai.com/codex/models)、[配置基础](https://developers.openai.com/codex/config-basic)和[配置参考](https://developers.openai.com/codex/config-reference)。
