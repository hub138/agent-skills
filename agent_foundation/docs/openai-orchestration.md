# OpenAI 编排与交接：handoffs 与 agents-as-tools 的选型

- 原文：[Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration)
- 来源：OpenAI 官方 Agents SDK 文档（镜像站 developers.openai.ac.cn 抓取，官方站对命令行抓取返回 Forbidden）
- 发布：官方文档页，随 Agents SDK 持续更新
- 译文说明：原文为中文镜像，本篇为按本包语言规则的合规改写整理，术语保留英文原词。原文代码示例附 JavaScript 与 Python 两份，译文保留 Python 一份。

当专职智能体应当负责任务的不同部分时，多智能体工作流有用。第一个设计选择是决定：工作流的每个分支里，由谁负责最终面向用户的回答。

## 选择编排模式

| 模式 | 适用情形 | 发生什么 |
|---|---|---|
| 交接（handoffs） | 专职智能体应当接管该分支的对话 | 控制权转移给该专职智能体 |
| 智能体作为工具（agents as tools） | 管理智能体应当保持控制权，把专职智能体作为受限能力调用 | 管理智能体保留回复的所有权 |

## 用交接委派所有权

当专职智能体应当负责下一次回复，而不单纯是在幕后提供协助时，交接是最明确适用的选择。

```python
from agents import Agent, handoff

billing_agent = Agent(name="Billing agent")
refund_agent = Agent(name="Refund agent")

triage_agent = Agent(
    name="Triage agent",
    handoffs=[billing_agent, handoff(refund_agent)],
)
```

保持路由表面清晰易读：

- 给每个专职智能体分配单一的任务。
- 保持 `handoffDescription` 简短且具体。
- 仅当下一个分支确实需要不同的指令、工具或策略时才分设智能体。

进阶用法里，交接还能携带结构化元数据或过滤后的历史记录。这些 API 因语言而异，细节保留在 SDK 各语言文档中。

## 在管理模式工作流里把智能体作为工具

`agent.asTool()` 适用于主智能体应当继续对最终回答负责、把专职智能体当作协助者调用的情况。

```python
from agents import Agent

summarizer = Agent(
    name="Summarizer",
    instructions="Generate a concise summary of the supplied text.",
)

main_agent = Agent(
    name="Research assistant",
    tools=[
        summarizer.as_tool(
            tool_name="summarize_text",
            tool_description="Generate a concise summary of the supplied text.",
        )
    ],
)
```

这通常在以下情况更适用：

- 管理智能体需要综合并输出最终回答。
- 专职智能体执行的是一个有界任务，例如摘要或分类。
- 你希望保持一个稳定的外部工作流、嵌套调用专职智能体，不做所有权转移。

## 仅当接口定义改变时才添加专职智能体

尽可能先从单个智能体开始。只有当专职智能体能实质改善能力隔离、策略隔离、提示词清晰度或追踪（trace）可读性时，再添加它们。过早分设会产生更多的提示词、更多的追踪和更多的审批界面，却不一定让工作流变得更好。

## 后续步骤

所有权模式确定后，继续读覆盖运行时与状态问题的相邻指南：

- 智能体定义：完善每个专职智能体的指令、工具与输出定义。
- 运行智能体：了解交接与工具在运行中的表现方式。
- 结果和状态：了解 `lastAgent` 与可恢复状态如何影响下一轮。

> 包内互引：SDK 总纲与 Responses API 的分工见 openai-agents-sdk.md；业务方视角的 manager 与 decentralized 两模式见 openai-practical-guide.md；Anthropic 侧的 subagent 分解判据见 multi-agent-when.md 与 fold-subagents.md。
