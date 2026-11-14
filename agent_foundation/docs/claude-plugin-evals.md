# Claude Code plugin evals：给插件跑评测（Claude Code plugin evals）

- 原文：[Claude Code plugin evals](https://code.claude.com/docs/en/plugin-evals)
- 来源：Anthropic（Claude Code 官方文档）
- 发布：官方文档页，随 Claude Code 版本持续更新（要求 v2.1.269+）
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL，文档内部锚点转为原文 URL 加锚；代码块与目录树保持英文；三个 frontmatter 字段表、六类 grader 表、Command options 表、exit codes 表、target 表、JSON 字段表、mock files 表完整翻译。

`claude plugin eval` shell 命令把你的 [plugin](https://code.claude.com/docs/en/plugins/overview) 放到一组测试 case 前运行并给结果打分。每个 case 是一条贴近真实的 prompt 加一个或多个 grader。grader 是对 Claude 产出做的通过/不通过检查，比如对回复跑一个 regex、确认某个工具被调用过，或由第二个模型按 rubric 评判回复。

你不一定要手写测试套件。`claude plugin eval init` 会询问你的插件情况，提议 case 与 grader，试跑一遍，然后写出文件。你也可以在一个已经打开的会话里让 Claude 做同样的事。

用 evals 来做三件事：

- 衡量你的插件让 Claude 稳定产出正确结果的程度
- 在你改动插件或新模型发布时抓住回归
- 看插件相比没有插件贡献了多少

本页面向已有可运行插件、想测试其行为的 plugin 与 skill 作者，以及在 CI 里给插件改动设闸门的团队。如果只是在一个 Claude Code 会话里迭代单个 skill，[skill-creator plugin](https://code.claude.com/docs/en/skills#run-evals-with-skill-creator) 用自己的 `evals/evals.json` 格式跑类似的对比，两个工具互不读取对方的 case 文件。要创建插件看 [Create a plugin](https://code.claude.com/docs/en/plugins/create)；要检查插件文件的语法与 schema 错误（而非行为），用 [`claude plugin validate`](https://code.claude.com/docs/en/plugins/cli-reference#plugin-validate)。

## 前置要求

运行 plugin evals 需要：

- Claude Code v2.1.269 或更高。跑 `claude --version` 检查，`claude update` 升级。
- 若装了 git，需 2.31 或更高。跑 `git --version` 检查。git 过旧时 `claude plugin eval` 在运行任何 case 前就停住。没装 git 也能正常运行。
- 一个含 `plugin.json` 或 `.claude-plugin/plugin.json` manifest 的插件目录，或一个 [skills-directory plugin](https://code.claude.com/docs/en/plugins/loading#plugins-shared-through-a-repository)。
- 与你正常 Claude Code 会话相同的认证与模型提供方。eval run、judge 打分的 grader、`claude plugin eval init` 都用你的凭据调模型，计入你套餐的用量限制或 API 账单。命令报出的成本是这些调用的[牌价估算](https://code.claude.com/docs/en/costs)。如果你在 Amazon Bedrock、Google Cloud Agent Platform 或 Microsoft Foundry 上跑 Claude Code，从导出与正常会话相同提供方变量的 shell 里跑套件，因为每个 run 从该 shell 继承这些变量，见 [`env` 字段](https://code.claude.com/docs/en/plugin-evals#prompt-md-fields)。

## 一次 eval run 怎么运转

eval 套件放在插件内名为 `evals/` 的目录里，布局见后文「写并打磨 case」。每个 case 是独立子目录，含一条 [prompt](https://code.claude.com/docs/en/plugin-evals#set-run-limits-and-tools-in-prompt-md) 与一个或多个 [grader](https://code.claude.com/docs/en/plugin-evals#grade-the-result)。prompt 是使用你插件的人可能输入的内容，比如一条本应由其中某个 skill 处理的请求。

### 一个 run 里发生什么

每个 case 的每个 run，Claude Code 都启动一个全新的、[隔离](https://code.claude.com/docs/en/plugin-evals#how-runs-are-isolated)的[非交互会话](https://code.claude.com/docs/en/headless)，只加载你的插件，发送 prompt，让 Claude 工作直到完成或达到该 case 的轮次与时间上限。随后每个 grader 检查最终回复、transcript 或 Claude 创建的文件，给出通过或不通过。

### 一个 case 怎么打分

非确定性 agent 的单次 run 说明不了什么，所以每个 case 默认跑三次。一个 run 的分数是它通过的 grader 占比（设了 weight 就按权重加权），case 的分数是各 run 的均值。case 分数达到 [`--threshold`](https://code.claude.com/docs/en/plugin-evals#command-options)（默认 `1.0`）即通过。

模型调用方面，一个套件大约做 cases × runs 次带插件的 agent run，[no-plugin baseline](https://code.claude.com/docs/en/plugin-evals#the-no-plugin-baseline) 再来同样数量，外加每个 `llm` 或 `baseline` grader 每个 run 三次短 judge 调用。

### no-plugin baseline

单独一个高分不能说明插件帮了忙，因为 Claude 可能没有插件也做得一样好。为把两者分开，case 的 run 会在不加载插件的情况下重复一遍，你得到两个分数：`WITH` 与 `W/OUT`。它们的差值 `Δ` 就是插件贡献的部分。如果某个 case 带插件与不带插件都拿 1.0，让 它通过的不是插件。

两组 run 分别叫 with-arm 与 without-arm；哪些 case 只跑 with-arm、grader 在两臂间怎么打分，见 [Score against the no-plugin baseline](https://code.claude.com/docs/en/plugin-evals#compare-against-a-no-plugin-baseline)。

## 创建你的第一个 eval 套件

本节走一遍为你的插件写一个 case、运行、读结果的过程。开始前确认：

- Claude Code v2.1.269 或更高，以及其余[前置要求](https://code.claude.com/docs/en/plugin-evals#requirements)
- 一个开在插件根目录（含 `plugin.json` 或 `.claude-plugin/plugin.json` 的那层）的终端
- 插件里一个想测的 skill，以及一条应该触发它的用户式请求

1. **创建 case。**在插件根目录运行：

```
claude plugin eval init
```

如果 Claude Code 尚未信任这个目录，它先问 `Trust this plugin directory?`，回答 `y`。随后打开一个交互式 Claude Code 会话。Claude 读取你的插件，问你什么样的结果算好，提议应该与不应该触发插件的 prompt，为每条设计 grader，各试跑一次确认行为正常，然后在 `evals/` 下按 prompt 写出 case 目录，每个以 prompt 命名。

Claude 告诉你套件就绪后，用 `/exit` 或 Ctrl+D 退出该会话回到 shell。

如果你已在插件根目录开着一个 Claude Code 会话，也可以直接在里面让 Claude 跑 `claude plugin eval init`。Claude 执行命令后在同一对话里问你同样的问题。

想自己写一个 case 看文件里到底是什么，走 [Write a case manually](https://code.claude.com/docs/en/plugin-evals#write-a-case-manually)，然后回来运行。

2. **运行套件。**回到插件根目录的 shell，运行 `evals/` 下全部 case：

```
claude plugin eval .
```

第 1 步里你已经信任过这个目录，run 立即开始。如果你是手写的 case，run 先问 `Trust this plugin directory? [y/N]`，回答 `y`。[What a run can access](https://code.claude.com/docs/en/plugin-evals#security) 解释你同意的是什么。

每个 case 带插件跑三次、不带跑三次，一个 case 共六个 run。每个 run 结束时打印一行进度，带该 run 的分数与每个 grader 的判定。

3. **读摘要。**套件跑完先看到摘要表，再看到报告去向：

```
CASE        WITH  W/OUT Δ      RUNS COST    NOTES
first-case  1.00  0.33  +0.67  6    $0.41

1 case(s) · mean Δ +0.67 · 74s · $0.41
Report: /home/you/my-plugin/evals/results/2026-09-10T17-02-11-482Z/report.html
Published: https://claude.ai/... · keep local next time with --no-publish
```

`WITH` 是加载插件时的 case 分数，`W/OUT` 是不带插件的分数，`Δ` 为正说明插件抬高了分数。`COST` 是模型调用的牌价估算，`NOTES` 显示 with-arm 里权重最高的未通过 grader 的解释，或该 run 的错误。

4. **打开报告并迭代。**打开 `Published:` 的 URL（没有该行时打开 `Report:` 路径），看每个 run 里每个 grader 的判定与解释，`llm` grader 还能看到 judge 的投票与它评审的摘录。`Published:` 行只在你的账号能[发布报告](https://code.claude.com/docs/en/plugin-evals#html-report)时出现。

最常见的第一个发现是 `Δ` 接近零且该 case 的 `tool_used: Skill` grader 未通过，含义是 Claude 在自然表述下没有选你的 skill。调整 skill 的 [`description`](https://code.claude.com/docs/en/skills#frontmatter-reference)，再跑一次 `claude plugin eval .` 做对比。

要少跑几轮只迭代单个 case，可以单臂单次运行。单次 run 噪声大，相信任何改动前先用默认三次确认。单臂下表格显示 `SCORE` 与 `PASS%` 列，取代 `WITH`、`W/OUT` 与 `Δ`：

```
claude plugin eval . --case <case-name> --runs 1 --ablation none
```

把 `<case-name>` 换成 `evals/` 下的某个目录名。

## 写并打磨 case

`claude plugin eval init` 写出的 case 都是普通文件，可以打开、修改、增补。一个 case 是插件 eval 目录下的一个子目录，含 `prompt.md`、`case.yaml` 或两者。每个 case 至少给一个 grader，写成 `graders/<name>.md` 文件或 `case.yaml` 里的 `graders:` 条目，缺 grader 的 case 加载失败。要给 case 分组，把它们嵌套在一个自身不是 case 的目录下；case 目录里的任何东西（`graders/`、fixture 文件等）都属于该 case。

这是 `claude plugin eval init` 写出的布局，也是新套件该用的布局。[eval suite reference](https://code.claude.com/docs/en/plugin-evals#eval-suite-reference) 有含 mock 与结果目录的完整树：

```
my-plugin/
├── .claude-plugin/plugin.json
├── skills/...
└── evals/
    ├── first-case/
    │   ├── prompt.md          # frontmatter: case fields; body: the prompt
    │   ├── graders/
    │   │   ├── criteria.md    # frontmatter: type + options; body: rubric or pattern
    │   │   └── skill-fired.md
    │   └── case.yaml          # optional: only for context.* fields
    ├── ignores-unrelated-request/
    │   └── ...
    └── results/               # written by each run; add to .gitignore
```

### 手写一个 case

让 Claude 用 `claude plugin eval init` 写 case 是推荐路径。想自己写，从空白模板开始。下面的命令创建名为 `first-case` 的 case，带占位的 `prompt.md` 与一个占位 grader，不运行任何东西：

```
claude plugin eval init --bare first-case
```

```
evals/first-case/
├── prompt.md            # the prompt sent to Claude, plus run limits
└── graders/
    └── criteria.md      # one grader: how to score the result
```

`prompt.md` 里写每个 run 中 Claude 收到的消息，并在 frontmatter 里设 run 的上限与 case 可用的工具。打开 `evals/first-case/prompt.md`，把占位正文换成一条本应由你的 skill 处理的请求，措辞按用户会怎么输入来写，不要点名 skill。这个例子面向一个起草 commit message 的 skill，换成你自己的请求：

```
---
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

Write me a commit message for this change: I renamed getUser to fetchUser and updated the three call sites.
```

每个 run 都从空工作目录开始，所以任务需要什么就写进 prompt 本身，或先[搭好工作区](https://code.claude.com/docs/en/plugin-evals#add-setup-or-history-with-case-yaml)。

[frontmatter 字段全表](https://code.claude.com/docs/en/plugin-evals#prompt-md-fields)覆盖 model、timeout、tags 与环境变量。

`graders/` 下每个文件是 run 之后应用的一项检查。打开 `evals/first-case/graders/criteria.md`，把占位内容换成给 judge 模型的 rubric，写成具体的 PASS 与 FAIL 条件：

```
---
type: llm
---

PASS if <what a correct response contains>.
FAIL if <what a wrong or missing response looks like>.
```

再加第二个 grader，检查产出答案的是不是你的 skill。创建 `evals/first-case/graders/skill-fired.md`，把 `your-skill-name` 换成该 skill 在 `skills/` 下的目录名，也就是 Claude 调用它时用的名字：

```
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?your-skill-name"'
---
```

Claude 在 run 里至少调用过该 skill 一次即通过，带命名空间的 `plugin-name:skill-name` 形式也算。

[Grader types](https://code.claude.com/docs/en/plugin-evals#grader-types) 列出其余检查，比如匹配 regex 或确认文件被创建。

两个文件保存后，按[快速上手](https://code.claude.com/docs/en/plugin-evals#create-your-first-eval-suite)的方式，在插件根目录跑 `claude plugin eval .`。

### 在 prompt.md 里设 run 上限与工具

在 `prompt.md` frontmatter 里设 case 的 `max_turns`、`timeout_seconds`、`model`、`tags` 与可用的 `allowed_tools`；[prompt.md frontmatter](https://code.claude.com/docs/en/plugin-evals#prompt-md-fields) 参考列出每个字段与默认值。

Claude 收到的正文与你写的完全一致。正文里的 `@path` 提及不会展开成文件附件，所以 Claude 需要读文件时，在 `allowed_tools` 里授予相应工具。

### 选择 grader 并设权重

grader 的 frontmatter 设它的 `type`，可选设 `weight`（让它占 run 分数更大比重）与 [`arm`](https://code.claude.com/docs/en/plugin-evals#compare-against-a-no-plugin-baseline)（控制它相对 baseline 怎么打分）。六类里 `regex`、`tool_used`、`tool_order`、`file_exists` 由 transcript 与文件直接算出，零成本；`llm` 与 `baseline` 调 judge 模型，计入 run 成本。

没有自定义代码 grader。

[Grader types](https://code.claude.com/docs/en/plugin-evals#grader-types) 列出每类的选项与通过条件，[what a grader can look at](https://code.claude.com/docs/en/plugin-evals#what-a-grader-can-look-at) 列出 `target` 与 `focus` 接受的取值。

默认情况下，`llm` 与 `baseline` grader 的 judge 是 Claude Code 用于后台任务的模型。传 `--judge-model sonnet` 或完整模型 ID 自己指定 judge。

#### 选信号稳定的 grader

`llm` grader 请模型给裁定，答案会随 run 变化，要读的文本越长变化越大。这些习惯让套件分数稳到可以信任：

- 长输出（比如生成的文件）用 `regex` grader 对文件内容打分，每次同样的方式检查整个文件。`llm` grader 留给短输出，rubric 写成具体的 PASS 与 FAIL 条件。
- 每个 case 给一个盯结果的 grader（最终消息或产出的文件），再给一个盯过程（`tool_used` 或 `tool_order`）。合起来既告诉你答案对不对，也告诉你是你的插件产出的。
- case 的 `tool_used: Skill` grader 通过但 `Δ` 为负时，先怀疑 judge 再怀疑插件。小 judge 模型可能因为格式与 rubric 描述不同而把正确答案判错。用 `--judge-model sonnet` 重跑，收紧 rubric，让格式不左右裁定。
- 要检查 run 内的构建或测试是否通过，让 prompt 请 Claude 跑它并把结果写进文件，对该文件打分，再用 `tool_used` grader 的 `input_match` 点名命令，断言命令确实跑过。

#### 相对 no-plugin baseline 打分

插件受测时，case 正常跑两臂。with-arm 是加载插件的 run，without-arm 是同等数量、完全不加载插件的 run。摘要与报告展示两个分数与 `Δ`（with-arm 分数减 without-arm 分数）。

这些情况下 case 只跑 with-arm，没有 `W/OUT` 分数与 `Δ`：

- **传了 `--ablation none`**：每个 case 单臂运行，在不需要对比时（比如打磨 grader 期间）成本减半。
- **case 恢复一段 transcript 且 target 是路径**：target 是 `.` 这类路径而非已装插件名时，[`context.history_file`](https://code.claude.com/docs/en/plugin-evals#add-setup-or-history-with-case-yaml) 的 case 默认单臂，依据是录下的对话已经反映了插件。run 在 stderr 打印 `single-arm (no Δ)` 提示点名这些 case。要对比恢复的那一轮带不带插件，传 `--ablation with-without`。
- **case 没找到插件**：target 是路径时，Claude Code 定位不到插件的 case 也默认单臂。修复见 [the baseline arm shows no plugin](https://code.claude.com/docs/en/plugin-evals#the-baseline-arm-shows-no-plugin-or-delta-is-zero)。

双臂运行中，部分 grader 报告为 `scored: false`。「skill 被调用了」这类检查没有插件永远通不过，计入会把 without-arm 压向零、抬高 `Δ`。为让两臂可比，Claude Code 在两臂都把这类 grader 排除出分数，在 with-arm 里只作为通过/未通过指示报告。包括：

- 每个 `tool` 为 `Skill` 的 `tool_used` grader
- 每个 `target: mock_calls` 的 `regex` grader 与每个 `focus: mock_calls` 的 `llm` grader，前提是 case 里的每个被 [mock 的服务器](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers)都是你插件声明的
- 你标了 `arm: with-only` 的任何 grader

三个设置改变这个排除：

- **全部 grader 被排除**：如果 case 的每个 grader 都在排除集里，它们按正常方式打分，否则就没东西可打了。
- **`arm: both`**：给 grader 设 `arm: both` 强制两臂都打分，「不得调用该 skill」的检查配 `min: 0` 与 `max: 0` 正需要这个。
- **`--ablation none`**：`--ablation none` 下不排除任何东西，同一套件在两种模式下绝对分数可能不同。

### 换一个 eval 目录

`evals/` 已被别的工具占用时，把套件放在别的目录。可以把目录记进插件的 `plugin.json`，让每次 run 与每个协作者都用它；也可以单次运行时在命令行传：

- **`plugin.json` 里**：加 `"experimental": { "evals": "quality/evals" }`。
- **命令行**：给 `claude plugin eval` 与 `claude plugin eval init` 都传 `--eval-dir quality/evals`。

两个都设时用 flag 的目录。给纯目录名的相对路径，比如 `qa` 或 `quality/evals`。绝对路径或含 `..` 的路径不被接受：作为 flag 值是错误，不可用的 manifest 值会打印 `Warning:` 行并改用 `evals/`。case、结果与 `init` 输出全部移到那个目录。

## 搭 fixture 与 mock

一个 case 可能需要比 prompt 更多的东西：工作区里的文件或 git 仓库、要续接的早前对话、你插件连接的 MCP 服务器该给的回答。这些都放在 case 旁边配置，让 run 保持可重复。

### 用 case.yaml 播种工作区或对话

每个 run 从空工作区开始。case 需要 prompt 之外的东西时，在 `prompt.md` 旁边加一个带 `context` 块的 `case.yaml`：

- **fixture 文件或 git 仓库**：在 case 目录写一个 Bash 脚本，名字写进 `context.scaffold_script`。脚本以你的身份、在 agent 沙箱之外运行，且只在你传 `--scaffold` 时执行，所以只给你自己或你组织写的套件传这个 flag。
- **要续接的早前对话**：把 transcript 存成 `.jsonl` 文件，名字写进 `context.history_file`，case 的 prompt 成为下一轮用户输入。target 是路径时，这类 case 默认[不带 baseline 臂](https://code.claude.com/docs/en/plugin-evals#compare-against-a-no-plugin-baseline)。
- **run 中 Claude 可读的 fixture 目录**：列进 `context.add_dirs`。

`case.yaml` 还需要 `schema_version: "1.1"` 与 `name`；[case.yaml fields](https://code.claude.com/docs/en/plugin-evals#case-yaml-fields) 参考有全表。

这个 `case.yaml` 用脚本播种工作区，并让 Claude 从 `resources/` 目录读 fixture：

```
schema_version: "1.1"
name: changelog-from-diff
tags: [smoke]
context:
  scaffold_script: fixture.sh
  add_dirs: [resources]
```

scaffold 脚本从空工作区启动，带一个小的固定环境：你 shell 的 `PATH`、指向 run 临时 home 目录的 `HOME`、`TMPDIR`，以及 `TERM=dumb` 等少量常量。你 shell 里的其他东西进不去，case 的 `EVAL_*` 变量也进不去。脚本非零退出或超过 120 秒，该 run 记 0 分并带 `scaffold failed` 错误。脚本只用来给文件与 git 状态，它写的项目配置[不会被加载](https://code.claude.com/docs/en/plugin-evals#how-runs-are-isolated)。

### mock MCP 服务器

你可以在不启动真实服务的情况下，评测一个 skill 会调 MCP 工具的插件。在 `evals/mocks/<server>/<tool>.md` 为整套 suite 放每个工具一个 Markdown 文件，或放在 case 自己的 `mocks/` 目录里只给单个 case 用。`<server>` 是该服务器在你插件 [MCP 配置](https://code.claude.com/docs/en/plugins/components#mcp-servers)里的名字。

run 从不主动启动你插件的真实 MCP 服务器，除非你要求。Claude Code 在每个服务器的名字下注册一个替身服务器。有 mock 文件的工具从文件作答，且不需要 `--allow-tools` 授权；没有 mock 文件的工具对 Claude 不可用。完全没有 mock 的服务器，在 case 的 `mocked:` 进度行里显示为 `plugin_<plugin>_<server>[not started: no mock]`。

文件正文就是工具返回给 Claude 的内容。这个 mock 替代名为 `tracker` 的服务器上的 `create_issue` 工具，检查 Claude 发来的输入，并回显标题。存成 `evals/mocks/tracker/create_issue.md`：

```
---
expect:
  title: string
  priority: [low, medium, high]
---

Created issue #4821: {{input.title}}
```

mock 文件的正文与 frontmatter 接受这些选项：

- **替换占位**：用 `{{input.<field>}}` 插入调用的输入字段，用 `{{file:fixtures/{input.<field>}.json}}` 插入 mock 旁 fixture 文件的内容。
- **`expect:`**：`expect:` 块守卫输入。调用违反它时，run 以 0 分终止并记录原因，这样 case 可以断言你的插件让服务器做了什么。
- **`error: true`**：设 `error: true` 把正文作为工具错误返回。
- **`type: agent`**：设 `type: agent` 让 judge 模型按正文指示扮演服务器应答。agent mock 的调用共享每个 run 一次的[预算](https://code.claude.com/docs/en/plugin-evals#mock-call-budget-exceeded)，为 case `max_turns` 的四倍，超出的调用让 run 以 0 分终止。

[mock file reference](https://code.claude.com/docs/en/plugin-evals#mock-files) 列出全部键与 `_server.md`、`_tools.json` 文件。

要对调用本身打分，把 grader 指向 `target: mock_calls`。

要改为对插件的 真实 MCP 服务器跑，传下面任一 flag。两种情况下这些进程都以你的身份、在 run 沙箱之外运行，其工具需要 [`--allow-tools` 授权](https://code.claude.com/docs/en/plugin-evals#grant-tools)：

- **`--allow-real-servers`**：为你没 mock 的每个服务器启动真实进程，被 mock 的工具继续从文件应答
- **`--mocks off`**：完全忽略 `mocks/`，启动插件声明的每个服务器

#### 回放 agent mock 的回答

`type: agent` 的 mock 用 [`--judge-model`](https://code.claude.com/docs/en/plugin-evals#command-options) 应答，所以它的输出随 run 变化，换 judge 也变。run 无错误、无终止地完成后，Claude Code 把每个 agent mock 的回答存到结果目录下的 `mock-recordings/`。

打开那里的 `ADOPT.txt` 查看每段录音，与要拷贝进的 `.replay/<server>/` 目录（在产出它的 mock 旁边）。把录音拷进去后，后续 run 对同一调用直接从录音应答，不再调模型。把 `mocks/.replay/` 随 `mocks/` 其余部分一起提交，CI run 才可重复。

## 运行 evals

套件就位后，用 `claude plugin eval` 运行。target 参数选哪个插件与哪些 case 运行，`--allow-tools` 授予只读集之外 case 需要的工具，其余选项控制运行次数、模型、成本与输出。

### 选测什么

多数时候在插件根目录跑 `claude plugin eval .`，加载你所在的插件，运行套件里全部 case。要跑单个 case 文件，或评测一个已安装（而非正在开发）的插件，传不同的 target：

| Target | 运行什么 |
| --- | --- |
| 插件根目录，如 `.` | eval 目录下全部 case，加载该插件 |
| 单个 `prompt.md` 或 `case.yaml` 文件 | 该 case，加载其所属插件 |
| 已装插件名，`name` 或 `name@marketplace` | 该插件与其 eval 目录里的 case，[就地读取或从安装副本读取](https://code.claude.com/docs/en/plugins/loading#in-place-and-copied-plugins)。结果写进当前目录的 `./evals/results/`，或 `--eval-dir` 时的 `./<dir>/results/` |
| `name@skills-dir` | 同上，适用于 [skills-directory plugin](https://code.claude.com/docs/en/plugins/loading#plugins-shared-through-a-repository) |
| 省略 | 当前目录作为路径处理 |

加 `--case <glob>` 按 case 名过滤，加 `--tag <tag>` 只保留带任一给定 tag 的 case。

target 放在 `--tag`、`--allow-tools` 与 `--json` 之前。前两个吃列表，`--json` 吃可选路径，各自会把跟在后面的 target 当成自己的值。

### 授予工具

run 从不为权限停下来询问。需要授权而你没给的内置工具（如 `Bash`、`Write`、`Edit`、`WebFetch`、`WebSearch`）会从会话中移除，Claude 完全调不到它们。

run 只允许 case 在 `allowed_tools` 里列出的只读工具——`Read`、`Glob`、`Grep`、`NotebookRead`、`Skill`、`AskUserQuestion`、`Agent`、`TodoWrite` 与任务工具 `TaskCreate`、`TaskGet`、`TaskList`、`TaskUpdate`、`TaskStop`——加上你用 `--allow-tools` 授予的。该授权对该次运行的每个 case 生效。要让 case 用 `Bash`、`Write`、`Edit`、`WebFetch` 或 `WebSearch`，你自己授权：

```
claude plugin eval . --allow-tools Write Edit "Bash(npm test *)"
```

case 请求了没授权的工具时，进度输出把它列为 `not granted`。被 [mock](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers) 的 MCP 服务器上的工具不需要授权。真实插件 MCP 服务器上的工具需要两样：服务器启动（`--allow-real-servers` 或 `--mocks off`）与按名授权，如 `--allow-tools "mcp__plugin_my-plugin_github__*"`；插件的 MCP 工具命名为 `mcp__plugin_<plugin>_<server>__<tool>`。

你以任何形式授予 `Bash` 时，每条命令都跑在 Claude Code 的 [OS 级沙箱](https://code.claude.com/docs/en/sandboxing)里。写入限制在 run 的工作区内，你的 home 目录与 Claude Code 配置不可读，网络访问限制在你用 `--allow-tools "WebFetch(domain:example.com)"` 授权的域名。在没有沙箱后端的机器上授予 Bash 或 PowerShell 时，Claude Code 拒绝每个 run 而非无约束地跑，case 显示 run 错误且通常 0 分。原生 Windows 没有后端，授予 shell 的套件要在 WSL2 下跑；Linux 上先装 `bubblewrap` 与 `socat`。见[沙箱前置要求](https://code.claude.com/docs/en/sandboxing)。

### 命令选项

本表覆盖运行次数、模型、打分、成本、工具授权、mock 与输出的选项。跑 `claude plugin eval --help` 看完整清单，还包括 `--case`、`--tag`、`--eval-dir`、`--no-scaffold`、`--report`、`--verbose`。

| 选项 | 默认 | 效果 |
| --- | --- | --- |
| `--runs <n>` | 各 case 的 `runs`，否则 3 | 每臂每 case 的运行次数 |
| `-j`、`--concurrency <n>` | `1` | 同时跑的 agent run 上限，1 到 8。它们共享你账号的速率限制，所以压缩的是墙上时钟时间，吞吐不会越过该限制。结果保持 case 顺序 |
| `--model <model>` | 各 case 的 `model`，否则设了 `ANTHROPIC_MODEL` 时用它，否则 Claude Code 默认 | 受测 agent 的模型。CI 里固定它，免得模型轮换被误判为插件回归 |
| `--judge-model <model>` | [后台任务](https://code.claude.com/docs/en/plugin-evals#grade-the-result)所用模型 | `llm` 与 `baseline` grader 的模型 |
| `--ablation <mode>` | 按 case 决定；见 [Score against the no-plugin baseline](https://code.claude.com/docs/en/plugin-evals#compare-against-a-no-plugin-baseline) | 是否每个 case 再跑一遍不带插件的 run 来衡量增量。`none` 单臂；`with-without` 加 no-plugin baseline |
| `--threshold <0..1>` | `1.0` | case 的 with-arm 分数至少达到此值算通过。任何 case 低于它，命令 exit 1 |
| `--max-cost-usd <usd>` | 无上限 | 该 run 牌价成本估算的上限，不是套餐用量的上限。每个 run 开始前检查。花到后不再启动新 run；已启动的会跑完，所以开销可越过该上限。若有 run 未启动，命令 exit 2 并带部分结果 |
| `--allow-tools <tools...>` | 无 | 授予只读集之外的工具。见 [Grant tools](https://code.claude.com/docs/en/plugin-evals#grant-tools) |
| `--scaffold` | 关 | 运行各 case 的 [`scaffold_script`](https://code.claude.com/docs/en/plugin-evals#add-setup-or-history-with-case-yaml) |
| `--trust-plugin` | 关 | 跳过首跑信任提示，用于你自己就会运行的插件代码与套件。CI 里传它，任务不会被提示拒绝或挂等。见 [What a run can access](https://code.claude.com/docs/en/plugin-evals#security) |
| `--mocks <mode>` | `record` | `record` 从 [mock](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers) 应答 MCP 工具调用，不启动插件的真实服务器，并保存 agent mock 的回答供回放。`off` 忽略 mock 并启动插件声明的真实 MCP 服务器 |
| `--allow-real-servers` | 关 | 在 `--mocks record` 下，为没有 mock 的服务器也启动插件的真实 MCP 服务器 |
| `--json [path]` | 关 | 把[结果文档](https://code.claude.com/docs/en/plugin-evals#json-result)打到 stdout，或写进以 `.json` 结尾的路径。运行安静：无进度行与摘要表 |
| `--output-dir <dir>` | `<eval dir>/results/<timestamp>/` | `aggregate-result.json` 与 `report.html` 的去处 |
| `--no-publish` |  | 报告留在本地。见 [HTML report](https://code.claude.com/docs/en/plugin-evals#html-report) |
| `--publish-report` |  | 在默认留本地的场景（如 Claude Code 会话里发起的 run）也发布报告 |
| `--keep-temp` | 关 | 保留每个 run 的沙箱目录并打印路径，用于调试 Claude 产出了什么 |

### 在 CI 里跑 evals

CI 任务里带 `--json` 跑套件写结果供归档，按 exit code 判定构建成败。传 `--trust-plugin` 让任务不卡在[首跑信任提示](https://code.claude.com/docs/en/plugin-evals#security)，两个模型都固定让分数跨时间可比，报告留本地，再设成本上限兜底：

```
claude plugin eval . \
  --trust-plugin \
  --json results.json \
  --threshold 0.8 \
  --model claude-sonnet-5 \
  --judge-model claude-haiku-4-5 \
  --no-publish \
  --max-cost-usd 20
```

任务的 exit code 告诉你发生了什么：

| Exit code | 含义 |
| --- | --- |
| 0 | 套件通过：每个 case 分数达到或超过 `--threshold`，且没有其他东西让 run 失败 |
| 1 | 有 case 低于 threshold、case 文件加载失败、没找到 case、run 无法启动，或 run [以 API 错误收场](https://code.claude.com/docs/en/plugin-evals#runs-ended-on-an-api-error)。插件目录不受信且没传 `--trust-plugin`、选项非法、`--json` 结果写不进时也返回 1 |
| 2 | 部分运行：`--max-cost-usd` 上限触顶，或你的凭据在首次 run 前或首 run 时被拒。`results.json` 仍会写出，带 `partial: true` 与原因 |
| 130 | 被中断。写出部分结果 |

with 减 without 的 delta 只报告，从不改变 exit code；HTML 报告写入或发布的失败同样不影响。

要看某个 case 为什么分数低，本地不带 `--json` 跑，每个 run 的进度与 grader 行会打出来。

CI runner 还需要这些就位：

- **安装与凭据**：CI runner 需要 Claude Code 安装与[环境里的凭据](https://code.claude.com/docs/en/authentication)，如 `ANTHROPIC_API_KEY` 或你云提供方的变量。
- **信任**：没传 `--trust-plugin` 时，Claude Code 尚不信任的 checkout 目录需要[首跑信任提示](https://code.claude.com/docs/en/plugin-evals#trust-the-plugin-directory)，无法询问的 run 被拒并 exit 1。
- **CI 里的 `init`**：`claude plugin eval init` 需要终端来问问题；CI 里跑 `claude plugin eval init --bare <name>` 拿空白模板。

要让成本可预期：每次改动都跑的快速套件只给不调 judge 的 grader，不需要 `Δ` 的地方用 `--ablation none`，`partial: true` 的文档与带 `skippedPaidGraders` 的 run 不进任何趋势图。

## 读结果

只要有 case 的每个 run 都在 eval 目录里写一个 `results/<timestamp>/` 目录，含 `aggregate-result.json` 与 `report.html`。路径 target 时在插件内；点名插件时在你当前目录下，见 [target 表](https://code.claude.com/docs/en/plugin-evals#choose-what-to-evaluate)。摘要表、JSON 与报告渲染的是同一份结果数据。

### HTML 报告

`report.html` 是单个自包含文件，不发起任何外部请求，可以附到 CI 任务或从磁盘打开。这个例子是一个三 case 套件以 `--threshold 0.8` 运行的报告顶部；显示的成本是牌价估算，随模型与 case 数量变化：

从上往下读：

- **判定行与指标块**回答整个套件层面插件有没有帮忙。Suite score 是各 case 带插件分数的均值，Ablation Δ 是它相对 baseline 分数高出或低出的量，Cases 计数多少 case 达到 threshold。Perfect runs 是每个 grader 都通过的带插件 run 占比。
- **每个 case 卡片**显示该 case 自己的 `Δ` 与带插件分数，进度条上有 threshold 刻度。`Δ` 为负的 case 左边是红边，滚动时回归一眼可见。
- **case 内部**，带插件的 run 在前，baseline 的 run 在后。每个 run 列出各 grader 的通过与未通过标记。未通过的 grader 已展开显示解释，`llm` grader 还显示 judge 的投票与它看到的证据，run 分数低的原因在这里找。不计分的 grader（如 `tool_used: Skill`）带 `plugin-fired indicator` 徽章。
- **Prompt 与 Graders** 在 run 之下，展示该 case 的 prompt 与每个 grader 的 rubric 或 pattern，不看套件只看报告的人也能知道问了什么、什么算好。

你用 claude.ai 订阅登录且账号可用 [artifacts](https://code.claude.com/docs/en/artifacts) 时，Claude Code 还会把报告发布为私有 artifact 并打印 `Published: <url>`。传 `--no-publish` 留本地。没出现 `Published:` 行时（如 API key 认证），本地文件就是报告。

由 Claude Code 会话发起的 run（比如你让 Claude 替你跑套件）也留在本地，其 `Report:` 行写着 `kept local`。给那条命令加 `--publish-report` 才发布。

### JSON 结果

`aggregate-result.json` 与 `--json` 输出是带 `schemaVersion: 1` 的版本化文档，供 CI 脚本解析。字段名是 camelCase，新字段只增不改名，脚本按忽略不认识的字段来写。

这是闸门脚本通常读的字段。文档还带套件配置、每个 grader 定义与逐 run 的 grader 结果（含解释与证据）：

| 字段 | 含义 |
| --- | --- |
| `partial`、`partialReason` | 套件没跑完时为 `true`，配 `cost_ceiling`、`interrupted` 或 `auth_failed`。趋势图不要算部分结果 |
| `aggregates.overallScore` | 全套件 case 分数均值 |
| `aggregates.casesPassed`、`aggregates.casesTotal` | 达到或超过 `--threshold` 的 case 数与总数 |
| `aggregates.meanDelta` | 各 case `Δ` 的均值，双臂模式下 |
| `cases[].name` | case 名 |
| `cases[].aggregates.score` | 该 case 带插件 run 分数的均值 |
| `cases[].aggregates.delta` | with-arm 分数减 without-arm 分数。case 单臂或两臂不可比时省略 |
| `cases[].arms.with[].error` | `null`，或 run 异常收场的原因，如 `timed out after 300s`。其中部分 run 仍按已产出的内容打分，所以非 null 的 error 不必然是 0 分。[以 API 错误收场](https://code.claude.com/docs/en/plugin-evals#runs-ended-on-an-api-error)的 run 不打分记 0 分 |
| `cases[].arms.with[].aborted` | [mock](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers) 通过 `expect:`、`abort_when` 或 [agent-mock 调用预算](https://code.claude.com/docs/en/plugin-evals#mock-call-budget-exceeded)让 run 终止时出现，带 `server`、`tool` 与 `reason`。run 记 0 分且 `error` 保持 `null` |
| `cases[].arms.with[].skippedPaidGraders` | 成本上限跳过该 run 的 judge grader 时为 `true`，其分数不可比 |
| `costUsd`、`durationSeconds`、`claudeVersion` | 含 judge 调用的牌价估算成本、墙上时钟秒数、跑套件的 Claude Code 版本 |

## run 能访问什么

`claude plugin eval` 加载目标插件的 skills、hooks 与 agents，在你的机器上以你的身份运行它的 eval 套件。把它指向一个插件，与 `claude --plugin-dir` 是同等的信任决定，所以只评测你信任的插件。

本节的隔离限制的是受测 agent 能触到什么；它对插件自身代码不构成边界，套件通过也说明不了插件是否安全。

### 信任插件目录

第一次对某个目录跑 `claude plugin eval` 时，Claude Code 在加载其中任何东西之前问 `Trust this plugin directory?`，除非你在交互式 `claude` 会话里已接受过该提示。在 git 仓库内回答 yes，整个仓库受信，交互会话同样。stdin 或 stdout 不是终端、或传了 `--json` 时，run 无法询问并以 exit 1 拒绝；传 `--trust-plugin` 自己声明信任，只用于你愿意在自己机器上运行的插件。点名（而非路径）的 target，即已装插件或 skills-directory plugin，跳过该提示。

插件与套件的一些部分只在你传对应 flag 时才在本次 run 运行：

- case 的 [`scaffold_script`](https://code.claude.com/docs/en/plugin-evals#add-setup-or-history-with-case-yaml)，需 `--scaffold`
- [只读集之外的工具](https://code.claude.com/docs/en/plugin-evals#grant-tools)，需 `--allow-tools`
- 插件的[真实 MCP 服务器](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers)，需 `--allow-real-servers` 或 `--mocks off`

case 的 `allowed_tools` 与 skill 自身的 `allowed-tools` frontmatter 都不能放宽其中任何一项。

插件带了你没写过的 hooks，或你启动了它的真实 MCP 服务器时，把分数当参考，除非你在容器或 CI runner 这类隔离环境里跑过——hooks 与服务器跑在 agent 沙箱之外，可能改动 grader 读的文件。

### run 怎么被隔离

每个 run 得到临时 home 目录、工作目录与 Claude Code 配置，受测 agent 以 `claude -p` 子进程在其中运行，只加载你的插件。写 case 时记住这些后果：

- **个人与项目级的东西一概不加载。**你的用户设置、hooks、`CLAUDE.md` 文件、MCP 服务器、其他已装插件、memory、skills 全部缺席。项目级配置也不在任何位置被读取：工作区之上或之内的 `.claude/` 目录、`CLAUDE.md`、`.mcp.json` 都不加载，`scaffold_script` 写的也不加载，`add_dirs` 目录只授予读权限。你 shell 环境的大部分同样被扣住；只有[白名单](https://code.claude.com/docs/en/plugin-evals#prompt-md-fields)与 `EVAL_*` 变量进入 run。case 依赖的 skills、agents、hooks、MCP 服务器都要随受测插件一起提供，[`scaffold_script`](https://code.claude.com/docs/en/plugin-evals#add-setup-or-history-with-case-yaml) 只能供给文件与 git 状态。
- **托管策略仍可限制 run。**管理员部署到机器的 [managed settings](https://code.claude.com/docs/en/managed-settings) 里的限制在 run 内生效，受管机器上的结果可能因此与不受管的不同。
- **Artifact 工具关闭。**发布 [artifact](https://code.claude.com/docs/en/artifacts) 的 skill 只能按它在这步之前的产出来打分。
- **case 定义对 agent 隐藏。**run 读不到 eval 目录，Claude 看不到 case 的 prompt、grader 或兄弟 case。
- **shell 命令之外没有网络沙箱。**你授权的 shell 命令跑在沙箱的网络规则下。`WebFetch(domain:…)` 授权直达该域名，插件自身的 hooks 与你启动的真实 MCP 服务器可以触达任何主机。

## eval 套件参考

eval 套件能容纳的一切都在插件的 eval 目录下，未另行配置时是 `evals/`。一个目录持有 `prompt.md` 或 `case.yaml` 即为 case，无 grader 的 case 以 `invalid case.yaml` 错误加载失败并点名 `graders`。这棵树展示 `claude plugin eval` 在 eval 目录读写的全部文件：

```
evals/
├── <case>/                        # one directory per case; nest under a non-case directory to group
│   ├── prompt.md                  # frontmatter: case and run fields; body: the prompt
│   ├── case.yaml                  # optional: context.* fields, or the whole case in one file
│   ├── graders/
│   │   └── <name>.md              # one grader per file; frontmatter: type and options; body: rubric
│   ├── mocks/                     # optional: mocks for this case only, same layout as below
│   └── <fixtures, scripts, transcripts referenced by case.yaml>
├── mocks/                         # optional: suite-wide MCP mocks
│   ├── <server>/
│   │   ├── <tool>.md              # one mocked tool; body: the tool result
│   │   ├── _server.md             # optional: one agent that answers several tools
│   │   ├── _tools.json            # optional: saved tools/list response for real descriptions and schemas
│   │   └── fixtures/              # files inserted with {{file:fixtures/...}}
│   └── .replay/<server>/          # adopted agent-mock recordings, answered without a model call
└── results/<timestamp>/           # written by each run; add results/ to .gitignore
    ├── aggregate-result.json
    ├── report.html
    └── mock-recordings/           # agent-mock answers from clean runs, with ADOPT.txt
```

### prompt.md frontmatter

`prompt.md` frontmatter 接受这些字段。未知键报错：

| 字段 | 默认 | 用途 |
| --- | --- | --- |
| `schema_version` | `"1.1"`，自动设置 | case 格式版本。写成 `prompt.md` 的 case 自动获得，很少需要手设 |
| `name` | 目录名 | case 名。`--case` 的 glob 匹配它，报告按它做键 |
| `description` |  | 给人看的。运行时不用 |
| `tags` | `[]` | `--tag` 过滤用的标签。任一 tag 命中即运行 |
| `plugins` | 最近的所属插件 | 相对 case 目录的受测插件目录。自动探测找不到你的插件时设 `plugins: ["../.."]`；见 [the plugin didn't load](https://code.claude.com/docs/en/plugin-evals#the-baseline-arm-shows-no-plugin-or-delta-is-zero) |
| `runs` | `3` | 每臂运行次数，1 到 50。`--runs` 覆盖它 |
| `expected_outcome` |  | 给人看的。运行时不用 |
| `model` | 子会话默认 | 受测 agent 的模型。`--model` 覆盖它 |
| `max_turns` | `10` | 轮次上限，最高 200。触顶记为 run 错误且通常拉低分数，宽裕地设 |
| `timeout_seconds` | `300` | 每 run 墙上时钟上限，最高 3600 |
| `allowed_tools` | `[]` | case 想用的工具，如 `[Read, Glob, Grep, Skill]`。只读工具列在这里即授予；其余见 [Grant tools](https://code.claude.com/docs/en/plugin-evals#grant-tools) |
| `append_system_prompt` |  | 追加到子会话 system prompt 的文本 |
| `env` | `{}` | 子会话的额外环境变量。键必须匹配 `EVAL_[A-Z0-9_]*`；其他键让 run 失败。run 只从你的 shell 继承白名单：`PATH` 与 locale 等基础项、代理与证书设置、选择与认证模型提供方的变量、多数 `ANTHROPIC_*` 与 `CLAUDE_CODE_*` 配置、`EVAL_*`。要给插件传别的（如工具链设置），导出成 `EVAL_*` 变量 |

### case.yaml 字段

`case.yaml` 是 `prompt.md` 的替代或搭档：用 YAML 描述 case，并加上指向其他文件的字段。要求 `schema_version: "1.1"` 与 `name`。`prompt.md` 的 `description`、`tags`、`plugins`、`runs`、`expected_outcome` 字段放顶层；`model`、`max_turns`、`timeout_seconds`、`allowed_tools`、`append_system_prompt`、`env` 放 `execution:` 下。两个文件并存时，`prompt.md` frontmatter 覆盖 `case.yaml` 的同名字段，`prompt.md` 正文是 prompt，`case.yaml` 列出的 grader 之后再追加 `graders/*.md`。

这些字段只存在于 `case.yaml`：

| 字段 | 用途 |
| --- | --- |
| `context.scaffold_script` | case 目录里的 Bash 脚本，在 Claude 启动前于空工作区运行，创建 fixture 文件或 git 仓库。仅在你传 [`--scaffold`](https://code.claude.com/docs/en/plugin-evals#add-setup-or-history-with-case-yaml) 时运行，环境最小、限 120 秒，非零退出让 run 失败 |
| `context.history_file` | case 目录里要恢复的 `.jsonl` transcript。case 的 prompt 成为下一轮用户输入 |
| `context.add_dirs` | case 目录内的目录，run 中 Claude 可读，只读授权 |
| `execution.prompt` | prompt 本身，用于整个 case 放在 `case.yaml`、省略 `prompt.md` 的写法 |
| `graders` | grader 列表，每个含 `name` 加 `graders/*.md` 文件 frontmatter 同款键。`llm` grader 的 rubric 放 `criteria` |

### grader frontmatter

`graders/` 下每个 grader 文件的 frontmatter 除自己类型的选项外都接受这些键。grader 的名字是去掉 `.md` 的文件名：

| 键 | 默认 | 用途 |
| --- | --- | --- |
| `type` | 必填 | [grader types](https://code.claude.com/docs/en/plugin-evals#grader-types) 之一 |
| `weight` | `1` | 在 run 分数里的相对权重。任意正数 |
| `arm` | 未设 | `with-only` 把 grader 从[双臂 run](https://code.claude.com/docs/en/plugin-evals#compare-against-a-no-plugin-baseline) 的打分中排除；`both` 强制 Claude Code 本会排除的 grader 在两臂都打分 |

#### grader 能看什么

`regex` grader 接受 `target`，`llm` grader 接受 `focus`。两者接受同样的取值：

| 取值 | grader 看到什么 |
| --- | --- |
| `last_message` | Claude 的最终回复文本。这是默认值 |
| `trace` | 会话的 JSON 形态，每行一条 message。`regex` grader 看到全部 message；`llm` judge 只看前 12 条与后 12 条。其内的引号与换行是 JSON 转义的，regex 匹配 `\"` 而非 `"` |
| `files` | Claude 在 run 中创建的路径清单，每行一条。不是文件内容，也不含 scaffold 创建的或 Claude 只修改过的文件 |
| `{ source: file, path: <path> }` | run 后工作区里某个文件的内容。用它给插件产出打分。PNG、JPEG、GIF、WebP 文件会作为图像展示给 `llm` judge。`llm` judge 拒收其他二进制文件（如 `.pptx` 或 PDF）；渲染成图像或写为文本再打分 |
| `mock_calls` | Claude 对[被 mock 的 MCP 工具](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers)的每次调用，含输入与 mock 的回答 |

#### grader 类型

每类 grader 的选项与通过条件如下：

| 类型 | 选项 | 何时通过 |
| --- | --- | --- |
| `regex` | `pattern`、`flags`、`match`、`target` | 在 target 中找到 JavaScript regex `pattern`。设 `match: not_contains` 要求不存在，`match: "count:N"` 要求恰好 N 次匹配。大小写不敏感写进 `flags: i`；内联 `(?i)` 不支持 |
| `tool_used` | `tool`、`input_match`、`min`、`max` | 对 `tool` 的调用次数中，JSON 编码输入匹配可选 `input_match` regex 的次数在 `min`（默认 1）与 `max`（默认无限）之间。断言工具从未被调用时设 `min: 0` 与 `max: 0` |
| `tool_order` | `before`、`after` | 两个工具都被调用过，且第一个匹配 `before` 的调用先于第一个匹配 `after` 的调用。各自是工具名或 `{ tool, input_match }` |
| `file_exists` | `path`、`exists` | Claude 创建的文件有匹配 `path` glob 的，或 `exists: false` 时一个都没有。只数 run 中创建的文件 |
| `llm` | `criteria`、`focus` | judge 模型对 rubric 投票，三票至少两票 PASS。`.md` 布局下文件正文就是 criteria |
| `baseline` | `baseline_file`、`criteria` | judge 认定 run 满足 criteria 的程度至少不输于 `baseline_file` 处的参考 transcript，那是 case 目录里的一个 `.jsonl` |

### mock 文件

`mocks/<server>/` 下的 `<tool>.md` 文件应答一个工具。正文是工具结果，支持 `{{input.<field>}}` 与 `{{file:fixtures/<name>}}` 替换。frontmatter 接受这些键：

| 键 | 默认 | 用途 |
| --- | --- | --- |
| `type` | `fixed` | `fixed` 按原文返回正文。`agent` 把正文当作给 [judge 模型](https://code.claude.com/docs/en/plugin-evals#command-options)的指示，它在 run 中扮演服务器，把早前调用当作历史 |
| `expect` | 未设 | 从点分输入路径到类型名（`string`、`number`、`boolean`、`array`、`object`）、[`/regex/`](https://code.claude.com/docs/en/plugin-evals#expect-patterns)、字面量或允许字面量清单的映射。调用违反它时 run 以 0 分终止，报告为 `aborted` 并带服务器、工具与原因 |
| `error` | `false` | 仅 `fixed`。把正文作为工具错误返回 |
| `abort_when` | 未设 | 仅 `agent`。一段文字，列出 agent 可以让 run 终止的唯一条件 |

服务器目录里工具文件旁边还有两个可选文件：

- **`_server.md`**：一个应答多个工具的 `type: agent` mock，工具列在其 `tools:` frontmatter 键里。同工具的 `<tool>.md` 优先。这里的 `expect:` 守卫除非 `tools:` 只列一个工具，否则是加载错误；守卫放到单个 `<tool>.md` 上 |
- **`_tools.json`**：从真实服务器保存的 `tools/list` 响应，让被 mock 的工具带真实的描述与输入 schema，而非宽松的占位

case 自己的 `mocks/` 目录用同样布局，逐文件覆盖套件级 mock。

#### expect 里的 regex 模式

`expect:` 里的 `/regex/` 值用一个小方言，Claude Code 在加载套件时检查：

- 字面字符、`.`、`\d` 这类转义、`[a-z]` 这类字符类
- 量词 `*`、`+`、`?` 与 `{m,n}` 形式，各自只作用于单个字符、转义或类
- 开头可选 `^`，结尾可选 `$`
- 仅有 flag `i` 与 `s`

方言之外的模式（含分组、交替、反向引用、环视或其他 flag）让 case 无法加载：case 记 0 分，error 点名该模式。要允许多个精确取值，写字面量清单，不写交替。

每个模式只检查到最大长度的值，更长的值算违规。量词会降低该长度，开头 `^` 会抬高它，所以用 `^` 锚定模式、少用量词。

## 排障

这些是作者们最常遇到的问题，按你看到的现象索引。

### "plugin eval is currently in early access"

你的构建早于该命令的正式发布。跑 `claude update`，然后在新会话里重跑命令。

### "plugin eval is currently unavailable"

Anthropic 在服务端关掉了该命令。你机器上没有任何东西能打开它；跑 `claude update`，稍后在新会话里重试。

### "is not a trusted plugin directory, and this run cannot stop to ask you about it"

这是对 Claude Code 尚不信任的目录的首次 run，且因为 stdin 或 stdout 不是终端、或你传了 `--json` 而无法询问。在终端里对该目录跑一次 `claude plugin eval <dir>` 并回答提示，或信任插件代码与套件时传 `--trust-plugin`。见 [What a run can access](https://code.claude.com/docs/en/plugin-evals#security)。

### "is too old for claude plugin eval"

你 `PATH` 上的 `git` 低于 2.31，`claude plugin eval` 在运行任何 case 前停住，exit 1 并报出你的版本：

```
git 2.30 is too old for claude plugin eval: it ignores the environment configuration (GIT_CONFIG_COUNT, added in git 2.31) that switches off the repository's git hooks and helper programs for the run. Install git 2.31 or newer.
```

每个 run 里，Claude Code 都会关掉 git hooks、凭据助手，以及仓库 git 配置可能启动的其他程序。它通过 git 从 2.31 版才开始读取的环境配置做到这点。更旧的 git 忽略那份配置，套件因此停住，而非在那些程序可能执行的情况下打分。装 git 2.31 或更高，重跑套件。

v2.1.283 之前，`claude plugin eval` 不检查 git 版本，旧 git 上套件会带着那些程序照跑。

### "cannot be evaluated where sessions load it"

你在 shell 里跑 `claude plugin eval`，点名了一个来自[本地路径添加的 marketplace](https://code.claude.com/docs/en/plugins/loading#in-place-and-copied-plugins) 的已装插件。现在没有会话能从那个 marketplace 加载它，命令以此消息拒绝并 exit 1。

```
Error: formatter@my-marketplace cannot be evaluated where sessions load it: no session could load it now. Its marketplace is a folder whose catalog could not be read, or lists it no more. Check the marketplace with `claude plugin marketplace list`, or pass ./<dir> to evaluate a directory.
```

`no session could load it now.` 之后的句子点名坏在哪里。

在 shell 里跑 `claude plugin marketplace list`，修好消息点名的问题。比如恢复 marketplace 目录，或把插件条目放回其 catalog。要不经 marketplace 评测插件源码，传它的目录作 target，如 `claude plugin eval ./plugins/formatter`。

### "No eval cases found"

生效的 eval 目录下不存在任何 `<case>/prompt.md` 或 `<case>/case.yaml`，或你的 `--case` 与 `--tag` 过滤没命中任何 case。从插件根目录跑，或跑 `claude plugin eval init` 创建套件。

### baseline 臂显示没有插件，或 delta 为零

摘要里没有 `W/OUT` 列，或 case 以 "ablation requested but no plugin resolved" 失败时，常见原因是没为该 case 找到插件。如果每个 case 都通过 `context.history_file` 恢复 transcript，缺列是预期行为，因为那些 case [默认单臂](https://code.claude.com/docs/en/plugin-evals#compare-against-a-no-plugin-baseline)。否则给 case 加 `plugins: ["../.."]`，给出从 case 目录到插件目录的路径。

插件确实加载了、`Δ` 仍接近零、`tool_used: Skill` grader 还失败，这通常是一个真实发现：skill 的 `description` 在这条 prompt 的措辞下不触发。调整 description，重跑同一套件。

### "Agent type '…' not found"，针对你插件的某个 agent

默认每个 case 带插件与不带各跑一遍，不带的 run 是 [no-plugin baseline](https://code.claude.com/docs/en/plugin-evals#the-no-plugin-baseline)。baseline run 里 Claude 派发你插件的 agent 时，Agent 工具调用失败，报 `Agent type '<plugin>:<agent-name>' not found. Available agents: ...`，清单只列没有插件时存在的 agent，比如[内置 subagents](https://code.claude.com/docs/en/sub-agents#built-in-subagents)。

这个报错是预期的，`Δ` 比较的就是你的插件 run 与 baseline。JSON 结果里 baseline run 在 `cases[].arms.without` 下。

带插件的 run 里，`allowed_tools` 列了 `Agent` 的 case 可以按命名空间名字派发你插件的 agent，如 `my-plugin:code-reviewer` 指名为 `my-plugin` 的插件里的 `code-reviewer` agent。要跳过 baseline run，传 `--ablation none`。

### 一切都记 0 分，但正确的文件确实生成了

你的 grader 把 `target` 指向了 `files`（创建路径的清单），实际想看的是文件内容。改用 `{ source: file, path: <path> }` 作 `target` 或 `focus`。

另一处，`file_exists` 只数 run 中创建的文件，scaffold 创建的或 Claude 只编辑过的文件对它不可见；给内容打分，或对 `Edit` 用 `tool_used`。

### 对 trace 的 regex 匹配不到我能看到的文本

- **target 错了**：默认 `target` 是 `last_message`，不是 trace。
- **JSON 转义**：target `trace` 时是每行一条的 JSON，引号呈现为 `\"`。
- **regex 语法**：regex 用 JavaScript 语法，大小写不敏感写 `flags: i`，别写 `(?i)`。

### 工具被拒、MCP 工具缺失、或 Bash 跑不了

只读集之外的一切都需要你的授权，如 `--allow-tools Bash Write`。你的个人 MCP 服务器在 run 里从不加载。插件自己的服务器除非你[主动启用](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers)否则不启动，其工具还需 `--allow-tools "mcp__plugin_<plugin>_<server>__*"` 授权；被 mock 的工具两者都不需要。

### run exit 1，但结果看着没问题

每个 case 都达到或超过 `--threshold` 而命令仍 exit 1 时，stderr 上有一行点名原因，`--json` 下也有。比如某个 case 文件加载失败，或某 run [以 API 错误收场](https://code.claude.com/docs/en/plugin-evals#runs-ended-on-an-api-error)。其余原因见 [exit codes](https://code.claude.com/docs/en/plugin-evals#run-evals-in-ci)。

默认 `--threshold` 是 1.0，任何 case 低于满分就 exit 1。把它设成你实际要求的分数。

### `--json output path must end in .json`

你把 target 放到了 `--json` 后面，被当成了输出路径。target 放前面，如 `claude plugin eval . --json`，或给 `--json` 一个明确的 `.json` 路径。

### run 得了 1.0 分，某个 grader 却显示 passed: false

双臂 run 里那个 grader 按设计被排除在分数外，其 `scored` 字段是 `false`。见 [Score against the no-plugin baseline](https://code.claude.com/docs/en/plugin-evals#compare-against-a-no-plugin-baseline)。

### "ended on an API error and scored 0 without grading"

这条 stderr 警告的含义是：至少一个 run 的最后一次请求被 API 以 HTTP 错误回应，如速率限制或套餐用量限制。这样的 run 不经打分记 0 分，无论分数与 `--threshold` 如何，命令都以非零退出。

修复办法：找到每个受影响 run 的错误，解决它报出的原因，重跑套件：

- **不带 `--json`**：错误在该 run 进度行的末尾，`error:` 之后
- **`--json` 下**：错误在 [JSON 结果](https://code.claude.com/docs/en/plugin-evals#json-result)的 `cases[].arms.with[].error` 或 `cases[].arms.without[].error`

计数包含 [baseline](https://code.claude.com/docs/en/plugin-evals#the-no-plugin-baseline) run。它们的分数从不决定 case 是否通过，所以可能每个 case 都通过、命令仍然失败。双臂 run 里，受影响 case 的 `W/OUT` 与 `Δ` 打印为 `—`。用量或速率限制类，见 [Runs fail with a usage-limit or rate-limit error](https://code.claude.com/docs/en/plugin-evals#runs-fail-with-a-usage-limit-or-rate-limit-error-partway-through)。

v2.1.299 之前，这样的 run 按它已产出的内容打分。

### 中途以 usage-limit 或 rate-limit 错误失败

以用量或速率限制错误收场的 run [不经打分记 0 分](https://code.claude.com/docs/en/plugin-evals#runs-ended-on-an-api-error)，命令非零退出。套件仍会跑完，不标 `partial`。限制重置后重跑，需要省着用时加 `--runs 1` 或 `--case` 过滤。

### "mock call budget exceeded"

run 里每个 `type: agent` 的 [mock](https://code.claude.com/docs/en/plugin-evals#mock-mcp-servers) 共享一份每 run 的调用预算，为 case `max_turns` 的四倍，默认 10 轮即 40 次调用。从 `.replay/` 录音应答的调用也算，case 的 `mock budget` 进度行打印预算。超出的调用让 run 以 0 分终止并报此原因，skill 大量调用 agent mock 时在 case 里调高 `max_turns`。

### run 超时或触到轮次上限

默认 10 轮、300 秒。需要更多的任务在 case 里调高 `max_turns` 与 `timeout_seconds`，成本上限交给 `--max-cost-usd` 兜底，而非把每 run 限制收紧。

## 延伸阅读

- [Create a plugin](https://code.claude.com/docs/en/plugins/create)：构建你要测的插件，开发期用 `--plugin-dir` 加载
- [Plugin commands reference](https://code.claude.com/docs/en/plugins/cli-reference#plugin-eval)：`plugin eval` 与 `plugin eval init` 的命令条目。manifest 的 [`experimental.evals`](https://code.claude.com/docs/en/plugins/manifest-reference#fields) 键在 manifest reference 上
- [Skills](https://code.claude.com/docs/en/skills)：skill 的 description 如何决定 Claude 何时调用它，检查 skill 是否触发的 case 量的正是这个
- [Sandboxing](https://code.claude.com/docs/en/sandboxing)：授予 Bash 后 run 适用的 OS 级沙箱
- [Publish a plugin](https://code.claude.com/docs/en/plugins/publish)：套件通过后发布插件
- [Measure plugin cost and usage](https://code.claude.com/docs/en/plugins/measure)：插件给每个会话的上下文加了什么、人们是否还在用它
