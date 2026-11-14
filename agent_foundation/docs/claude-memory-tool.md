# Claude 记忆工具：跨会话的文件式记忆

- 原文：[Memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- 来源：Anthropic 官方文档（md 直链抓取，文档状态 stable）
- 发布：官方文档页，状态 stable，支持 Claude 4 及以后全部模型
- 译文说明：原文为英文，本篇为按本包语言规则的合规改写整理，术语保留英文原词。原文代码示例附九种语言，译文保留 Python 与 JSON 形态。

记忆工具让 Claude 跨对话存取信息，载体是一个记忆文件目录。Claude 可以创建、读取、更新、删除在会话之间持续存在的文件，随时间积累知识，而无需把全部内容保留在上下文窗口里。

记忆支撑 just-in-time 上下文检索：agent 把学到的内容写进记忆文件，需要时按需读回，活动上下文保持聚焦当前任务。这对长时运行会话尤其重要。更广的模式见 Effective context engineering。

记忆工具在客户端运作：Claude 只发起文件操作请求，你的应用执行它们。数据存在哪里、怎么存，由你自己的基础设施决定。

## 用例

- 跨多个 agent 会话维持项目上下文。
- 把过去交互、决策与反馈里的经验用到新任务上。
- 随时间建立知识库。

## 运作方式

启用记忆工具后，Claude 开始任务前自动检查记忆目录。工作过程中，Claude 把学到的东西存在 `/memories` 下的文件里，之后的对话再读回来延续先前工作。

`/memories` 路径是一个前缀，由你的处理器映射到真实存储，例如每用户一个目录或数据库里的键。记忆完全存在于你的应用里。后续对话发送相同的 `tools` 条目、处理器服务同一个存储时，就从同一份记忆继续。出于安全，全部记忆操作必须限制在 `/memories` 目录内。

一次典型交互：

1. 用户请求：「帮我回复这条客服工单。」
2. Claude 检查记忆目录：「我来帮你回复这条工单。先查看我的记忆里有没有先前的上下文。」Claude 调用 `view /memories`。
3. 你的应用返回目录清单（文件与大小列表）。
4. Claude 读取相关文件：`view /memories/customer_service_guidelines.xml`。
5. 你的应用返回文件内容（带行号）。
6. Claude 基于记忆内容继续工作。

## 接入步骤

1. 请求里加 `tools` 条目 `{"type": "memory_20250818", "name": "memory"}`，这是全部配置：`name` 必须是 `memory`，Anthropic 提供的工具无需定义输入 schema。
2. 为每个记忆命令实现客户端处理器。处理器必须拒绝 `/memories` 之外的路径。

```python
client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=2048,
    messages=[
        {"role": "user", "content": "Help me respond to this customer service ticket."}
    ],
    tools=[{"type": "memory_20250818", "name": "memory"}],
)
```

## 实现记忆处理器

Claude 的回复以 `tool_use` 块结束，请求一次记忆操作（如 `view /memories`）。你的应用执行操作、在 `tool_result` 块里返回结果、把对话发回去让 Claude 继续：标准工具使用循环。

四个 SDK 提供记忆工具助手：Python 与 C# 子类化 `BetaAbstractMemoryTool`，TypeScript 用 `betaMemoryTool`，Java 实现 `BetaMemoryToolHandler`，把记忆接到你自己的存储上（磁盘文件、数据库、云存储、加密文件都可以）。Python 与 TypeScript 还附带现成的本地文件系统实现 `BetaLocalFilesystemMemoryTool`。助手与 tool-runner 界面在 SDK 的 beta 命名空间里，虽然记忆工具本身不需要 beta header。Go、Ruby、PHP 无现成助手，示例自己跑工具循环。

```python
import anthropic
from anthropic.tools import BetaLocalFilesystemMemoryTool

client = anthropic.Anthropic()
memory = BetaLocalFilesystemMemoryTool(base_path="./memory")

runner = client.beta.messages.tool_runner(
    model="claude-opus-5-5",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Remember that customer Acme Corp prefers email follow-ups."}
    ],
    tools=[memory],
)

final_message = runner.until_done()
print(final_message.content)
```

## 工具命令

客户端实现必须处理以下命令。这些规格描述推荐行为与返回字符串：Claude 读取工具结果里的任何文本，你可以按应用需要返回不同的字符串。

### view

显示目录内容或文件内容，可带行区间：

```json
{
  "command": "view",
  "path": "/memories/notes.txt",
  "view_range": [1, 10]
}
```

`view_range` 可选，适用于文本文件：`[start_line, end_line]` 返回这些行，`[start_line, -1]` 从起始行返回到文件结尾。

目录返回值：列出两层深度内的文件与目录、带人类可读大小（如 `5.5K`、`1.2M`）、排除隐藏项与 `node_modules`、大小与路径之间用制表符。空存储上首次 `view /memories` 不算错误：SDK 的本地文件系统实现会先创建记忆根目录，返回列表头加空目录自身的一行。

文件返回值：带头部与行号的内容。行号格式：宽度 6 字符、靠右排列空格补齐、1 起始索引、制表符分隔内容。超过 999,999 行的文件返回错误 `"File {path} exceeds maximum line limit of 999,999 lines."`。示例：

```text
Here's the content of /memories/notes.txt with line numbers:
     1	Hello World
     2	This is line two
```

Claude 的工具描述还说明 `view` 能显示图片文件（`.jpg`、`.jpeg`、`.png`），文本视图超过 16,000 字符会截断。预期会收到图片路径的 `view` 调用与长文件的后续区间视图。

错误处理：文件或目录不存在时返回 `"The path {path} does not exist. Please provide a valid path."`。

### create

创建新文件：

```json
{
  "command": "create",
  "path": "/memories/notes.txt",
  "file_text": "Meeting notes:\n- Discussed project timeline\n- Next steps defined\n"
}
```

成功返回 `"File created successfully at: {path}"`。文件已存在时返回 `"Error: File {path} already exists"`。Claude 的工具描述说 `create` 是「创建或覆盖」，所以已存在路径上也会收到 `create` 调用：返回错误是参考行为，改为覆盖是合法的实现选择。

### str_replace

替换文件里的文本。`new_str` 可选：省略时删除 `old_str` 不补新文本。

```json
{
  "command": "str_replace",
  "path": "/memories/preferences.txt",
  "old_str": "Favorite color: blue",
  "new_str": "Favorite color: green"
}
```

成功返回 `"The memory file has been edited."` 加编辑后文件的带行号片段。错误处理：文件不存在返回不存在错误；文本未找到返回 ``"No replacement was performed, old_str `{old_str}` did not appear verbatim in {path}."``；`old_str` 出现多次时返回 ``"No replacement was performed. Multiple occurrences of old_str `{old_str}` in lines: {line_numbers}. Please ensure it is unique"``。路径是目录时返回「文件不存在」错误。

### insert

在指定行插入文本：`insert_text` 插入到 `insert_line` 行之后，`0` 插到文件开头。

```json
{
  "command": "insert",
  "path": "/memories/todo.txt",
  "insert_line": 2,
  "insert_text": "- Review memory tool documentation\n"
}
```

成功返回 `"The file {path} has been edited."`。错误处理：文件不存在返回不存在错误；行号越界返回 ``"Error: Invalid `insert_line` parameter: {insert_line}. It should be within the range of lines of the file: [0, {n_lines}]"``。路径是目录时返回「文件不存在」错误。

### delete

删除文件或目录。成功返回 `"Successfully deleted {path}"`；不存在返回不存在错误。目录删除递归进行。工具描述告诉 Claude 不能删除 `/memories` 目录本身，所以拒绝以记忆根为目标的 `delete`。

### rename

重命名或移动文件、目录。成功返回 `"Successfully renamed {old_path} to {new_path}"`。错误处理：源不存在返回不存在错误；目标已存在时返回错误、不覆盖：`"Error: The destination {new_path} already exists"`。拒绝以记忆根为 `old_path` 的 `rename`。

## 提示词指引

请求的 `tools` 里存在记忆工具时，API 自动把下面这段指令加进 system prompt，无需自己发送：

```text
IMPORTANT: ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE.
MEMORY PROTOCOL:
1. Use the `view` command of your `memory` tool to check for earlier progress.
2. ... (work on the task) ...
   - As you make progress, record status / progress / thoughts etc in your memory.
ASSUME INTERRUPTION: Your context window might be reset at any moment, so you risk losing any progress that is not recorded in your memory directory.
```

Claude 的工具描述已经告诉它保持记忆目录整洁，无需重复。若 Claude 仍写出杂乱的记忆文件，可以在 prompt 里强化：

```text
Note: when editing your memory folder, always try to keep its content up-to-date, coherent and organized. You can rename or delete files that are no longer relevant. Do not create new files unless necessary.
```

也可以引导 Claude 往记忆里写什么，例如「只把与某个主题相关的信息写进记忆系统」。

## 安全考量

Claude 请求的每个文件操作都由你的应用执行，这些防护是你的责任：

- 敏感信息：Claude 通常会拒绝把敏感信息写进记忆文件。要更强的保证，在处理器写文件前加一道剥离敏感数据的校验。
- 文件大小：跟踪记忆文件大小、限制单文件上限。考虑限制 `view` 返回的字符数，让 Claude 用 `view_range` 翻页读完。
- 记忆过期：定期删除长期未访问的记忆文件。
- 路径遍历防护：恶意路径如 `/memories/../../secrets.env` 能触达 `/memories` 目录之外的文件，实现必须校验每个命令的每个路径。手段：校验全部路径以 `/memories` 开头；解析路径到规范形态后验证仍在记忆目录内；拒绝包含 `../`、`..\` 等遍历序列的路径；注意 URL 编码的遍历序列（`%2e%2e%2f`）；用语言自带的路径安全工具（如 Python 的 `pathlib.Path.resolve()` 与 `relative_to()`）。

## 错误处理

记忆工具的错误处理模式与文本编辑器工具相同。要把错误返回给 Claude，在工具结果上设 `is_error: true`、把消息放进 `content`：

```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01C4D5E6F7G8H9I0J1K2L3M4",
  "content": "Error: The path /memories/notes.txt does not exist",
  "is_error": true
}
```

## 与上下文编辑、compaction 的配合

记忆工具与上下文编辑配对管理长对话：上下文编辑在客户端清除特定工具结果。记忆工具也可以与 compaction 配对：compaction 在服务端把整个对话摘要化。长时运行 agent 可以两者都用，compaction 让活动上下文保持小而无需客户端记账，记忆保全必须活过摘要化的信息。详见上下文编辑文档的配合章节。

## 跨会话软件开发模式

跨越多个 agent 会话的软件项目里，刻意布设记忆文件，随工作进展临时写就的方式不要。这个模式把记忆变成恢复机制：每个新会话从上一个会话记录的状态接续。

1. 初始化会话：第一个会话在任何实质性工作开始前布设记忆文件，包括进度日志（已完成与待办）、功能清单（界定工作范围）、项目需要的启动或初始化脚本引用。
2. 后续会话：每个新会话开场先读记忆文件，恢复项目状态，不再重新探索代码库、重走先前决策。
3. 会话收尾更新：会话结束前更新进度日志，写明完成与剩余，保证下一个会话有准确起点。

关键原则：一次只做一个功能。功能只有在端到端验证确认可用后才标记完成，代码写完不算。这让进度日志在会话之间保持准确。实践案例（含初始化脚本、进度文件结构与基于 Git 的恢复）见 Effective harnesses for long-running agents。

> 包内互引：同日发布的配对能力见 claude-context-editing.md（客户端清除工具结果）；compaction 与 just-in-time 原则见 context-engineering.md；SDK 侧消息线程见 claude-message-threads.md；OpenAI 侧总纲见 openai-agents-sdk.md。
