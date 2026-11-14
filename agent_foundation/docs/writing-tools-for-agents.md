# 为 AI agent 编写工具（Writing tools for AI agents）

- 原文：[Writing tools for AI agents](https://www.anthropic.com/research/writing-tools-for-agents)
- 来源：Anthropic Engineering，作者 Ken Aizawa
- 发布：2025-09-11
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图，地址为原文 CDN 直链。

[Model Context Protocol（MCP）](https://modelcontextprotocol.io/docs/getting-started/intro)能让 LLM agent 获得数以百计的工具来解决真实世界的任务。但怎样让这些工具发挥最大效力？

本文描述我们在多种 agentic AI 系统上验证过的、最有效的性能改进技术。

先讲怎么做这几件事：

- 为工具构建并测试原型
- 创建并运行对「agent 使用工具」的全面评估
- 与 Claude Code 这类 agent 协作，自动提升工具性能

最后给出我们一路总结出的高质量工具五原则：

- 选对要实现的工具（以及不要实现的工具）
- 用命名空间为工具划分清晰的功能边界
- 让工具把有意义的上下文返回给 agent
- 为 token 效率优化工具响应
- 对工具描述与规格做提示词工程

![题图](https://www-cdn.anthropic.com/images/4zrzovbb/website/cdc027ad2730e4732168bb198fc9363678544f99-1920x1080.png)

## 什么是工具

在计算领域，确定性系统对相同输入总产生相同输出；非确定性系统（比如 agent）即使起点相同，也可能生成各异的回答。

传统写软件时，我们建立的是确定性系统之间的约定。例如 `getWeather("NYC")` 这样的函数调用，每次都以完全相同的方式取回纽约的天气。

工具是一种新型软件，它反映的是确定性系统与非确定性 agent 之间的约定。用户问「今天要带伞吗」，agent 可能调用天气工具回答，可能凭常识回答，甚至可能先追问用户所在的城市。偶尔，agent 会产生幻觉，或者根本没能理解一个工具的用法。

这要求我们从根本上换一种思路写软件：工具与 [MCP server](https://modelcontextprotocol.io/) 不能再像给其他开发者或系统写函数、写 API 那样来写，必须为 agent 而设计。

我们的目标是扩大 agent 能有效解决问题的作用面：让 agent 用工具 pursue 多种可行的成功策略。幸运的是，经验表明对 agent 最「合手」的工具，人类理解起来也出奇地直观。

## 怎么写工具

本节描述如何与 agent 协作，编写并改进你交给它们的工具。先搭一个快速原型并本地测试，再跑全面评估来度量后续每一次改动。与 agent 并肩工作，反复评估、改进，直到 agent 在真实任务上表现出色。

### 构建原型

不动手试，很难预料哪些工具对 agent 合手、哪些不合手。先快速搭起原型。如果用 [Claude Code](https://www.anthropic.com/claude-code) 来写工具（甚至可以一次生成），建议把它依赖的软件库、API、SDK（包括 [MCP SDK](https://modelcontextprotocol.io/docs/sdk)）的文档一并给 Claude。对 LLM 友好的文档通常能在官方文档站的扁平 `llms.txt` 文件里找到（我们 API 的在[这里](https://docs.anthropic.com/llms.txt)）。

把工具包装成[本地 MCP server](https://modelcontextprotocol.io/docs/develop/connect-local-servers) 或 [Desktop extension](https://www.anthropic.com/engineering/desktop-extensions)（DXT），就能在 Claude Code 或 Claude Desktop 应用里连接并测试它们。

把本地 MCP server 接入 Claude Code：运行 `claude mcp add <name> <command> [args...]`。

把本地 MCP server 或 DXT 接入 Claude Desktop 应用：分别前往 `Settings > Developer` 或 `Settings > Extensions`。

工具也可以直接传入 [Anthropic API](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview) 调用做程序化测试。

自己上手测试工具，找出毛糙之处。收集用户反馈，建立对「你的工具预期支持哪些用法与提示词」的直觉。

### 运行评估

接下来度量 Claude 使用你工具的效果，方法是跑评估。先基于真实使用场景生成大量评估任务。建议与 agent 协作分析结果、决定工具怎么改。完整流程见我们的 [tool evaluation cookbook](https://platform.claude.com/cookbook/tool-evaluation-tool-evaluation)。

![评估流程图](https://www-cdn.anthropic.com/images/4zrzovbb/website/6e810aee67f3f3c955832fb7bf9033ffb0102000-1920x1080.png)

#### 生成评估任务

有了早期原型，Claude Code 能快速探索你的工具，生成几十对提示词与回答。提示词要来自真实使用场景，基于真实的数据源与服务（例如内部知识库与微服务）。避免过于简单肤浅的「沙箱」环境，它们无法用足够的复杂度压测你的工具。强评估任务可能需要多次工具调用，甚至几十次。

强任务的例子：

- 下周约 Jane 开个会，讨论我们最近的 Acme Corp 项目。附上上次项目规划会的记录，并预订一间会议室。
- 客户 9182 报告一次购买被扣了三次款。找出所有相关日志条目，并判断是否有其他客户受同一问题影响。
- 客户 Sarah Chen 刚提交了取消请求。准备一份挽留方案。确定：(1) 她为什么要走，(2) 什么挽留方案最有吸引力，(3) 发出方案前需要注意哪些风险因素。

弱任务的例子：

- 下周和 jane@acme.corp 约个会。
- 在支付日志里搜 `purchase_complete` 和 `customer_id=9182`。
- 找到客户 45892 的取消请求。

每个评估提示词都应配一个可核验的回答或结果。验证器可以简单到「标准答案与采样回答的精确字符串比较」，也可以高级到「请 Claude 来当裁判」。避免过于严苛的验证器，它们会因为格式、标点、有效换述等表面差异把正确回答判错。

对每对提示词与回答，还可以可选地标注你期望 agent 在解题时调用的工具，以此度量 agent 是否在评估中理解了每个工具的用途。不过正确解题可能有多条路径，避免把策略规定得过窄，避免过拟合。

#### 运行评估

建议用直接 LLM API 调用程序化地跑评估。用简单的 agent 循环（`while` 循环包裹 LLM API 调用与工具调用的交替）：每个评估任务一个循环。每个评估 agent 拿到单个任务提示词与你的工具。

在评估 agent 的系统提示词里，建议指示 agent 输出结构化回答块（供验证）之外，也输出推理与反馈块。指示 agent 在工具调用与回答块之前先输出这些，可能通过触发思维链（CoT）行为提升 LLM 的有效智力。

用 Claude 跑评估时，可以打开 [interleaved thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking#interleaved-thinking) 获得同类能力的现成支持。这能帮你探究 agent 为什么调用或不调用某些工具，并定位工具描述与规格里待改进的点。

除顶层准确率外，建议收集其他指标：单个工具调用与任务的总耗时、工具调用总次数、token 总消耗、工具错误。追踪工具调用能揭示 agent 常走的流程，也提示哪些工具可以合并。

![评估指标示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/3f1f47e80974750cd924bc51e42b6df1ad997fab-1920x1080.png)

#### 分析结果

agent 是你的得力伙伴，能从相互矛盾的工具描述、低效的工具实现、令人困惑的工具 schema 等各方面发现问题并给反馈。但记住：agent 在反馈与回答里遗漏的内容，往往比它包含的更重要。LLM 并不总是[言行一致](https://www.anthropic.com/research/tracing-thoughts-language-model)。

观察 agent 在哪里卡住或困惑。通读评估 agent 的推理与反馈（或 CoT），找毛糙之处。复核原始记录（包括工具调用与工具响应），捕捉 agent 的 CoT 没有显式描述的行为。要读出字里行间的信息；记住，评估 agent 自己未必知道正确答案与正确策略。

分析工具调用指标。大量冗余工具调用说明分页或 token 上限参数需要调整；大量参数无效导致的工具错误，说明工具描述需要更清晰或补示例。发布 Claude 的 [web search 工具](https://www.anthropic.com/news/web-search)时，我们发现 Claude 会画蛇添足地在 `query` 参数后面加 `2025`，使搜索结果失真、性能下降（我们通过改进工具描述把 Claude 引回了正轨）。

### 与 agent 协作

甚至可以让 agent 替你分析结果、改进工具。把评估 agent 的记录拼接后粘给 Claude Code 即可。Claude 擅长分析记录并一次性重构大量工具，例如确保工具实现与描述在改动之后保持自洽。

事实上，本文的多数建议就来自我们用 Claude Code 反复优化内部工具的过程。我们的评估建立在内部工作区之上，复刻内部流程的复杂度，包含真实的项目、文档与消息。

我们依赖留出测试集（held-out test set）确保没有过拟合到「训练」评估上。这些测试集显示，即便超出「专家级」工具实现（无论出自研究人员手写还是 Claude 生成）的成绩，还能再压榨出额外的性能提升。

下一节分享这个过程中的所得。

## 高效工具的原则

本节把所得提炼成几条编写高效工具的指导原则。

### 为 agent 选对工具

工具越多未必结果越好。常见错误是工具只把既有软件功能或 API 端点包一层，至于它适不适合 agent，没经过考量。原因在于 agent 与传统软件的「可供性」（affordance）不同，它们感知「工具能做什么」的方式不一样。

LLM agent 的「上下文」有限（一次能处理的信息量有上限），而计算机内存廉价充裕。以通讯录里找联系人这个任务为例：传统软件可以高效地逐条存取联系人列表，逐个检查再往下走。

但 LLM agent 如果用一个返回全部联系人的工具，就得逐个 token 读过去，把有限的上下文浪费在无关信息上（想象你翻通讯录时从头到尾每页都通读，也就是暴力搜索）。对 agent 和人类都更好、更自然的做法是先翻到相关的那一页（比如按字母序定位）。

建议构建少量精心设计的工具，瞄准高价值流程，与评估任务匹配，再从这里向外扩展。通讯录的例子里，应该实现 `search_contacts` 或 `message_contact`，放弃 `list_contacts`。

工具可以合并功能，在底层处理多个离散操作（或 API 调用）。例如，工具可以在响应里附带相关元数据，或者把高频串接的多步任务收进一次工具调用。

例子：

- 与其实现 `list_users`、`list_events`、`create_event` 三个工具，考虑实现一个 `schedule_event`，由它找出空闲时间并安排日程。
- 与其实现 `read_logs`，考虑实现 `search_logs`，只返回相关日志行及其上下文。
- 与其实现 `get_customer_by_id`、`list_transactions`、`list_notes`，实现一个 `get_customer_context`，一次汇总客户的近期相关信息。

确保每个工具用途清晰、彼此独立。工具应该让 agent 能像人类一样，面对同样的底层资源时把任务分解、解决，同时减少中间输出本会消耗的上下文。

工具太多或功能重叠会分散 agent 的注意力，让它离开高效策略。慎重、有选择地规划建哪些工具（与不建哪些工具），回报可观。

### 为工具建命名空间

你的 agent 可能接入几十个 MCP server、几百个工具，其中包括其他开发者写的。工具功能重叠或用途含糊时，agent 会困惑该用哪个。

命名空间（把相关工具归于共同前缀之下）能帮助划分大量工具之间的边界；MCP client 有时会默认做这件事。例如按服务命名空间（`asana_search`、`jira_search`），再按资源细分（`asana_projects_search`、`asana_users_search`），能帮 agent 在正确的时机选用正确的工具。

我们发现前缀式与后缀式命名空间的选择，对工具使用评估有不可忽视的影响。效果因 LLM 而异，建议按自己的评估结果选择命名方案。

agent 可能调错工具、调对工具但参数错误、工具调用太少、或错误处理工具响应。有选择地实现那些名字本身就反映任务自然分解的工具，能同时减少加载进 agent 上下文的工具数量与描述篇幅，并把 agent 的计算从上下文转移回工具调用本身。这降低 agent 犯错的总体风险。

### 从工具返回有意义的上下文

同理，工具实现要注意只把高信号信息返回给 agent。优先考虑上下文相关性而非灵活性，避开底层技术标识符（如 `uuid`、`256px_image_url`、`mime_type`）。`name`、`image_url`、`file_type` 这类字段更可能直接指导 agent 的下一步动作与回答。

agent 处理自然语言名称、术语、标识符的成功率，显著高于处理晦涩标识符。我们发现，仅把任意的字母数字 UUID 换成语义上可解读的语言（甚至 0 起始的编号方案），就能通过减少幻觉显著提升 Claude 在检索任务上的准确度。

某些场景里，agent 需要同时与自然语言和技术标识符打交道（哪怕只为触发后续工具调用，例如 `search_user(name='jane')` → `send_message(id=12345)`）。在工具里暴露一个简单的 `response_format` 枚举参数即可两全：让 agent 控制工具返回「简洁」还是「详细」（见下图）。

可以加更多格式获得更大灵活性，类似 GraphQL 里精确选择要接收哪些信息。控制工具响应详略的 ResponseFormat 枚举示例：

```
enum ResponseFormat {
   DETAILED = "detailed",
   CONCISE = "concise"
}
```

详细工具响应示例（206 token）：

![详细工具响应示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/5ed0d30526bf68624f335d075b8c1541be3bb595-1920x1006.png)

简洁工具响应示例（72 token）：

![简洁工具响应示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/d4f649a66482efb5a80cf14ea85e84974ede1c49-1920x725.png)

连工具响应结构（XML、JSON 或 Markdown）都会影响评估成绩：没有放之四海皆准的方案。LLM 靠下一 token 预测训练而来，在贴近训练数据的格式上表现更好。最优响应结构因任务与 agent 而异，建议按自己的评估选择。

### 为 token 效率优化工具响应

优化上下文的质量重要，优化工具响应返回给 agent 的上下文数量同样重要。

对可能消耗大量上下文的工具响应，建议实现分页、范围选择、过滤、截断中的若干组合，并给参数设合理的默认值。Claude Code 默认把工具响应限制在 25000 token。我们预期 agent 的有效上下文长度会随时间增长，但对上下文节省的工具的需求会一直存在。

选择截断响应时，务必用有用的指引引导 agent。可以直接鼓励 agent 追求更省 token 的策略，例如知识检索任务用多次小而精准的搜索，替代一次大而宽的搜索。同理，工具调用报错时（例如输入校验失败），错误响应也要做提示词工程：清楚说明具体、可执行的改进方向，避免只给出难懂的错误码或调用轨迹。

截断的工具响应示例：

![截断的工具响应示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/e440d6a69d0ca80e71f3bec5c2d00906ff03ce6d-1920x1162.png)

无用的错误响应示例：

![无用的错误响应示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/2445187904704fec8c50af0b950e310ba743fac2-1920x733.png)

有用的错误响应示例：

![有用的错误响应示例](https://www-cdn.anthropic.com/images/4zrzovbb/website/810661bd44a35fb273806ae95160040155978c3e-1920x850.png)

### 对工具描述做提示词工程

现在讲改进工具最有效的方法之一：对工具描述与规格做提示词工程。它们会被加载进 agent 的上下文，共同把 agent 引向高效的工具调用行为。

写工具描述与规格时，想象你在向团队新成员介绍这个工具。把你可能默认对方知道的背景（专门的查询格式、小众术语的定义、底层资源之间的关系）显式写出来。清晰描述期望的输入与输出（并用严格的数据模型约束），消除歧义。尤其是输入参数命名要无歧义：参数名别用 `user`，用 `user_id`。

有了评估，你就能更有把握地度量提示词工程的效果。工具描述的小幅精修也能带来戏剧性提升：我们对工具描述做了精确精修后，Claude Sonnet 3.5 在 [SWE-bench Verified](https://www.anthropic.com/engineering/swe-bench-sonnet) 评估上取得当时最佳成绩，错误率大幅下降，任务完成率上升。

工具定义的其他最佳实践见我们的 [Developer Guide](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use#best-practices-for-tool-definitions)。为 Claude 构建工具的话，还建议阅读工具如何动态加载进 Claude [系统提示词](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/implement-tool-use#tool-use-system-prompt)。为 MCP server 写工具时，[tool annotations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) 能帮助声明哪些工具需要开放世界访问或做破坏性修改。

## 展望

为 agent 构建高效工具，需要把软件开发实践从可预测的确定性模式，转向非确定性模式。

通过本文描述的迭代式、评估驱动的过程，我们总结出工具成功的稳定规律：高效的工具有意为之且定义清晰，审慎使用 agent 的上下文，能在多样流程中彼此组合，让 agent 直观地解决真实世界的任务。

未来，agent 与世界交互的具体机制会持续演进：MCP 协议会更新，底层 LLM 也会升级。用系统化、评估驱动的方法改进工具，我们就能确保随着 agent 能力增长，它们使用的工具同步进化。

## 作者与致谢

本文由 Ken Aizawa 撰写，并感谢来自 Research（Barry Zhang、Zachary Witten、Daniel Jiang、Sami Al-Sheikh、Matt Bell、Maggie Vo）、MCP（Theodora Chu、John Welsh、David Soria Parra、Adam Jones）、Product Engineering（Santiago Seira）、Marketing（Molly Vorwerck）、Design（Drew Roper）、Applied AI（Christian Ryan、Alexander Bricken）各团队同事的宝贵贡献。

1 指对底层 LLM 本身的训练之外。
