# Codex 的 AGENTS.md 指令链与自定义层级

- 原文：[Custom instructions with AGENTS.md](https://developers.openai.com/codex/agent-configuration/agents-md)、[Customization](https://developers.openai.com/codex/concepts/customization)
- 来源：OpenAI 官方文档（镜像站 html 抓取，正文抽取后按本包语言规则改写）
- 发布：官方文档页，随平台持续更新
- 译文说明：原文为英文（镜像站自带中文翻译，对照官方原始 URL 收编），两页合并成一篇：agents-md 指南页给全量操作细节与走查，customization 概念页给五层自定义总览与反馈闭环。customization 页里 Skills、MCP、Subagents 三层的展开内容与既有译文重复（SKILL.md 结构、渐进式披露、主机-客户端-服务器三角色），本篇只收总览表与互引，不重复展开。

Codex 在执行任何工作之前读取 AGENTS.md 文件。通过全局指导加项目级覆盖（override）的组合，无论打开哪个存储库，每次任务开始时都保持一致的预期。这是 Codex 侧上下文工程的第一层：把持久指令放在仓库里随版本控制移动，把任务专属内容留给对话。

## 指令链的发现规则

### 发现时机与顺序

Codex 在启动时构建指令链（每次运行一次；在 TUI 里通常意味着每个启动的会话一次）。发现过程遵循优先级顺序：

- 全局范围：在 Codex 主目录（默认 ~/.codex，设置了 CODEX_HOME 时用该目录）里，先检查 AGENTS.override.md，存在就读它；否则读 AGENTS.md。此层级只用第一个非空文件。
- 项目范围：从项目根目录（通常是 Git 根目录）向下遍历到当前工作目录。找不到项目根时只检查当前目录。路径上每个目录依次检查 AGENTS.override.md、AGENTS.md、project_doc_fallback_filenames 里的备用名称，每目录最多收一个文件。
- 合并顺序：从根目录向下串联文件，用空行连接。离当前目录越近的文件覆盖之前的指导，因为它们出现在组合提示词的末尾。

### 32 KiB 截断与备用文件名

Codex 跳过空文件，组合大小达到 project_doc_max_bytes（默认 32 KiB）后停止添加文件。达到上限时的两条路：调高限制，或把指令分流到嵌套目录。指令文件体积失控的代价是尾部被静默截断，写在文件末尾的规则等于没写。有关这些配置项的详细信息，见[项目指令发现](https://developers.openai.com/codex/config-file/config-advanced#project-instructions-discovery)。

存储库已有别的文件名（例如 TEAM_GUIDE.md）时，把它加进备用列表，Codex 把它当作指令文件：

```toml
# ~/.codex/config.toml
project_doc_fallback_filenames = ["TEAM_GUIDE.md", ".agents.md"]
project_doc_max_bytes = 65536
```

设置后每个目录的检查顺序变成：AGENTS.override.md、AGENTS.md、TEAM_GUIDE.md、.agents.md。不在列表里的文件名被忽略。更大的字节上限允许在截断之前收进更多的组合指导。

### 创建全局指导

在 Codex 主目录创建持久默认值，让每个存储库继承工作协议。确保目录存在：

```bash
mkdir -p ~/.codex
```

创建包含可复用首选项的 ~/.codex/AGENTS.md：

```markdown
# ~/.codex/AGENTS.md

## Working agreements

- Always run `npm test` after modifying JavaScript files.
- Prefer `pnpm` when installing dependencies.
- Ask for confirmation before adding new production dependencies.
```

在任何地方运行 Codex 确认它加载了该文件：

```bash
codex --ask-for-approval never "Summarize the current instructions."
```

预期：Codex 在提出工作建议之前，会引用 ~/.codex/AGENTS.md 里的条目。

需要临时全局覆盖又不想删除基础文件时，使用 ~/.codex/AGENTS.override.md。移除覆盖文件即可恢复共享指导。

### 分层项目指令

存储库级文件让 Codex 了解项目规范，同时继承全局默认值。在仓库根目录添加 AGENTS.md 覆盖基础设置：

```markdown
# AGENTS.md

## Repository expectations

- Run `npm run lint` before opening a pull request.
- Document public utilities in `docs/` when you change behavior.
```

特定团队需要不同规则时，在嵌套目录添加覆盖文件。例如在 services/payments/ 内创建 AGENTS.override.md：

```markdown
# services/payments/AGENTS.override.md

## Payments service rules

- Use `make test-payments` instead of `npm test`.
- Never rotate API keys without notifying the security channel.
```

从 payments 目录启动 Codex：

```bash
codex --cd services/payments --ask-for-approval never "List the instruction sources you loaded."
```

预期：Codex 先报告全局文件，其次是仓库根目录的 AGENTS.md，最后是 payments 覆盖文件。

到达当前目录后 Codex 停止搜索，把覆盖文件放在尽可能靠近专项工作的地方。以下是添加了全局文件和 payments 特定覆盖后的示例仓库：

```
AGENTS.md               # 仓库期望
services/
  payments/
    AGENTS.md           # 已忽略，因为存在覆盖文件
    AGENTS.override.md  # 支付服务规则
  search/
    AGENTS.md           # 路径上此目录的规则
README.md
```

### 添加代码审查规则

对于 [GitHub 里的 Codex 代码审查](https://developers.openai.com/codex/third-party/github#customize-what-codex-reviews)，在离规则所管理代码最近的 AGENTS.md 中添加 ## Code Review Rules 部分。全仓库范围的检查放在根目录，特定于服务的检查放在嵌套文件中。

```markdown
## Code Review Rules

### Experiment cohorts

- Do not filter treatment comparisons on post-exposure behavior, including conversion or retention.
  Safe path: build cohorts from assignment or exposure; report conversion as an outcome.
```

保持规则简明，解释需要标记的行为以及任何安全路径或例外，把格式化和静态检查留给 CI。有关设置和规则编写指导，见[自定义 Codex 审查内容](https://developers.openai.com/codex/third-party/github#customize-what-codex-reviews)。

### 自定义 Codex 主目录

需要不同的配置文件（例如项目特定的自动化用户）时，设置 CODEX_HOME 环境变量：

```bash
CODEX_HOME=$(pwd)/.codex codex exec "List active instruction sources"
```

预期：输出列出相对于自定义 .codex 目录的文件。

## 验证与排障

验证设置的三个入口：

- 从存储库根目录运行 codex --ask-for-approval never "Summarize the current instructions."，Codex 应按优先级顺序回显来自全局与项目文件的指导。
- 用 codex --cd subdir --ask-for-approval never "Show which instruction files are active." 确认嵌套覆盖文件替代了更广泛的规则。
- 审计 Codex 加载了哪些指令文件：通过 codex -c log_dir=./.codex-log 开启纯文本 TUI 日志并检查 ./.codex-log/codex-tui.log，或启用会话日志记录后检查最近的 session-*.jsonl 文件。

指令看起来过时时，在目标目录中重启 Codex。每次运行（以及每个 TUI 会话开始时）都重建指令链，无需手动清理缓存。

排障五问：

- 什么都没有加载：确认在目标仓库中，并且 codex status 报告了期望的工作区根目录。确保指令文件包含内容；Codex 忽略空文件。
- 显示了错误的指导：检查目录树更高处或 Codex 主目录下是否存在 AGENTS.override.md。重命名或移除该覆盖文件，回退到常规文件。
- Codex 忽略了备用名称：确认 project_doc_fallback_filenames 中列出的名称没有拼写错误，然后重启 Codex 让更新后的配置生效。
- 指令被截断：提高 project_doc_max_bytes，或把大文件分散到嵌套目录，保持关键指导完整。
- 配置文件混淆：启动 Codex 之前运行 echo $CODEX_HOME。非默认值会把 Codex 指向与所编辑主目录不同的主目录。

## 五层自定义总览

customization 概念页把 Codex 的自定义分为五个协同的层级：项目指导（AGENTS.md）管持久指令、记忆（Memories）管从先前工作获取的上下文、技能（Skills）管可重用的工作流与领域专业知识、MCP 管访问外部工具与共享系统、子代理（Subagents）管把工作委派给专业的子代理。五层互补：AGENTS.md 塑造行为，记忆承载本地上下文，技能封装可重复的流程，MCP 连接本地工作区之外的系统。

层级与位置的对照表：

| 层级 | 全局（个人） | 存储库（团队） |
| --- | --- | --- |
| AGENTS | ~/.codex/AGENTS.md | 仓库根目录或嵌套目录的 AGENTS.md |
| 技能 | $HOME/.agents/skills | 仓库中的 .agents/skills |

## AGENTS.md 的内容与更新时机

### 写什么

用于希望 Codex 在该存储库每次都遵循的规则：构建与测试命令、审查期望、存储库特定的约定、特定目录的指令。保持精简。全局文件塑造 Codex 的交流方式（审查风格、详细程度、默认设置），仓库文件重点放团队与代码库规则。

当代理对代码库做出错误假设时，在 AGENTS.md 里更正，并要求代理自己更新 AGENTS.md，让修复持久存在。这是一个反馈闭环。

### 何时更新

官方给出五个信号：

- 反复出现的错误：代理反复犯同样的错误，加一条规则。
- 阅读过多：找到了正确的文件但读了过多的文档，加路由指导（优先处理哪些目录、哪些文件）。
- 反复出现的 PR 反馈：不止一次给出相同的反馈，把反馈编成规则。
- GitHub 里：在 pull request 评论里标记 @codex 发出请求（例如 @codex add this to AGENTS.md），把更新委托给云端任务。
- 自动化差异检查：用 automations 跑周期性检查（例如每日），寻找指导缺口，建议添加到 AGENTS.md 的内容。

配合基础设施强制执行：预提交钩子、代码校验工具、类型检查器在问题被人看到之前捕获它们。

## 与包内既有篇目的关系

AGENTS.md 的写作方法与 /init 脚手架、以及 OpenAI 自家仓库把它当目录而非百科全书的用法裁定（约 100 行、知识库进结构化 docs/ 目录、CI 与文档整理 agent 机械校验时效）见 [Codex 最佳实践](codex-best-practices.md) 与 [OpenAI harness 工程](openai-harness-engineering.md)。本篇补的是指令链的实现细节：三级发现链、override 机制、32 KiB 截断、备用文件名、验证与排障命令。

compaction 的机制细节见 [上下文编辑：清除、保留与压缩](claude-context-editing.md)（Anthropic 侧 server 端策略）；Codex 侧 Subagents 的委派机制见 [Codex 子代理](codex-subagents.md)。Codex 指令链「每轮重读、永不进压缩边界」的架构含义：会话中途给的单句约束在 150 轮后被压缩掉的风险真实存在，长期约束放 AGENTS.md 是结构性防线。

## 后续步骤

访问官方 [AGENTS.md](https://agents.md) 网站获取更多信息。查看[提示 Codex](https://developers.openai.com/codex/prompting)了解与持久化指导配合的对话模式。
