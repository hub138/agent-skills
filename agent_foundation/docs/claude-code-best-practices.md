# Claude Code 最佳实践（Best practices for Claude Code）

- 原文：[Best practices for Claude Code](https://code.claude.com/docs/en/best-practices)
- 来源：Anthropic（Claude Code 官方文档）
- 发布：原文页面未标注发布日期
- 译文说明：全文翻译，术语保留英文原词；代码块与配置示例保留英文原样；原文无插图。

Claude Code 的设计是：多数情况下，新会话里你随手输入的第一条普通 prompt 就已经把事做对，无需你做任何设置。

例如：

- 为了让命令安全运行而无需你逐条批准，新的终端与 VS Code 会话默认以 [auto mode](https://code.claude.com/docs/en/permission-modes#eliminate-prompts-with-auto-mode) 启动，一个分类器在执行前审查任何有风险的动作。
- 为了让主对话保持专注、独立的工作并行推进，Claude 把任务委派给 subagent，只在必要时向你汇报。
- 为了让长会话持续运转而无需你管理，对话会在上下文窗口填满之前自动压缩（compaction）。

本页讲默认值不够用时的做法。这通常发生在你的项目里有 Claude 只凭代码看不到的知识、规则或约束：

- 一段只存在某个人脑中的部署流程
- 一个绝不能被读取的文件
- 一道任何东西被算作完成之前必须通过的检查
- 一条你必须守住的预算

没有任何默认值能知道你项目里的这些事，所以这时你这边少量的设置会换来回报。

会话没有按你预期的方式进行时，原因几乎总是下面四种之一：

- Claude 做出来的东西与你设想的不同，或者它每个会话开头都要重新发现同一个事实。它缺的是从读仓库里得不到的信息。见「把 Claude 看不到的东西告诉它」。
- Claude 说自己做完了，实际没有完全做完，通常因为它没有办法检查自己的工作。见「给 Claude 一个可以运行的检查」。
- Claude 做了这个仓库里绝不允许发生的事，或者跳过了必须发生的步骤。只靠 prompt 保证不了这两条中的任何一条。见「执行不容例外的规则」。
- Claude 做对了，但花掉的时间、token 或权限确认超过了任务本身的价值。见「更改一个默认值」。

「让 Claude 无人值守运行」把同样四点应用到没人看管的运行上；「可以不再做的事」列出了被当前模型淘汰的旧建议。面向整个团队的设置在单独一页：[Set up Claude Code for your organization](https://code.claude.com/docs/en/admin-setup)。

## 确定性与非确定性指令

你给 Claude Code 的每一条指令都属于下面两种之一：

1. 非确定性：你写下指令，由 Claude（模型）来读。可以是你的 prompt、CLAUDE.md 或一个 skill。模型随后自行决定如何处理这些信息。它通常会照你的话做，当前模型也擅长在没有多少上下文的情况下理解你的意图，但没有任何保证说它一定照办。它仍然可能决定不做某些事，或者去做别的事。
2. 确定性：你配置指令，Claude Code（harness）必须执行它。可以是一个 hook、一条 deny rule 或一项托管设置。无论模型决定什么，Claude Code 每次都会应用它。

Claude Code 里的大多数事情都有这两种形态：

|  | 非确定性（Claude 决定） | 确定性（Claude Code 强制执行） |
|---|---|---|
| 做什么 | 你的 prompt、CLAUDE.md、Claude 自己启用的 skills | hooks，以及只有你能启动的 skills |
| 能碰什么 | auto mode 的分类器 | deny rules、strict mode 的沙箱、托管设置 |
| 什么时候算完成 | 要求它出示证据、/goal、/code-review | 测试、typecheck、Stop hook、CI |
| 花多少 | effort 档位、Claude 自己的节奏 | -p 下的 --max-turns 或 --max-budget-usd、你设置的支出上限 |
| 最终由谁裁决 | Claude 对自己做了什么的总结 | 分支保护、批准合并的那个人 |

多数时候，你想要的是让 Claude 自己决定。几乎所有指南都有例外，当前模型擅长阅读面前的代码并判断一条指南是否适用于当下情形。代码摆在眼前时，Claude 通常比你预先写下的规则更有资格下这个判断。

确定性那一类，用于你想确保某些事总是发生（或从不发生）、无论模型怎么决定的时候。这未必是什么大事。auto mode 已经挡住了那些大事，比如生产部署或强行推送覆盖别人的工作。它通常只关乎你的项目，而且多冷门都可以：

- 绝不修改 `src/gen/` 里生成的客户端代码
- 创建文件之后总是运行 license-header 脚本

这两条你都可以写进 CLAUDE.md 或 prompt，Claude 几乎每次都会遵守。但无论措辞多强硬，某一轮里 Claude 是否遵守那行字，仍然是 Claude 自己的决定。

如果你不断给 CLAUDE.md 的某一行加强调语气而 Claude 还是漏掉它，这是这行字应该进 hook 的信号。反过来同样成立：如果 hooks 管的只是个人倾向类的事，删掉它们，让 Claude 自己决定。

## 把 Claude 看不到的东西告诉它

只写下 Claude 无法靠读仓库找到的东西，或者那些它每个会话都要花时间重新发现的东西。

Claude 每个任务都从读你的代码开始，当前模型非常擅长这件事。它们会找到你的文件布局、你的约定、你的测试框架、既有组件的构建方式，通常比你自己解释得还快。这意味着你想写给 Claude 的大部分内容，它其实已经知道了。

它找不到的是从未进过仓库的信息：

- 你的团队在会议里做的决定
- 一段只存在某一个人脑中的部署流程
- 你的集成测试需要的环境变量

还有一类信息在仓库里，但要花几分钟翻找才能找到，而 Claude 每个会话开头都要重做一遍翻找。

在给 Claude 写下任何东西之前，先过一遍这个测试：

1. 它能靠读代码找到吗？
2. 它真的会去找吗？

两问都是「是」，就别写。

### 写具体的 prompt

具体的 prompt 同样有帮助，因为它给了 Claude 还没有的信息。如果你指名文件、描述症状、预先说清「修好了」是什么样子，通常能省掉后面一轮纠正。

两种合理做法之间的取舍也一样：代码里读不出你想要哪一个，如果你在意它选哪个，预先说出来。

| 不要写 | 写这个 |
|---|---|
| "fix the login bug" | "users report login fails after the session times out. look at token refresh in src/auth/, write a failing test that reproduces it, then fix it" |
| "add a calendar widget" | "follow the pattern in HotDogWidget.php and build a calendar widget that lets you pick a month and page between years. no new libraries" |

如果 Claude 需要的东西已经在你手上，直接递过去，不要描述它：

- 一个文件：输入 `@` 和路径，把[文件内容](https://code.claude.com/docs/en/common-workflows#reference-files-and-directories)带进你的消息。
- 一张图片：把设计稿或报错的截图直接粘贴进 prompt。
- 命令输出：从 shell 管道进来，`cat error.log | claude -p "what's going on here"`。

`think step by step` 或 `be thorough` 这类短语属于普通的 prompt 文本，算不上关键词。控制 Claude 思考强度的主要手段是 effort 档位，见「更改模型与 effort」。这类措辞仍能在 effort 档位之内轻推 Claude，但推不高过它。

仍然有用的一个短语是 `be ambitious`。Claude 倾向于保守地理解请求，做出满足要求的最小东西，因为它看不到你期望多完整。当你想要更完整的版本、边界情况也处理、顺手的相关功能也做上时，就说出来：

```
build the settings page from the mockup. be ambitious: empty and error states, the save flow wired up, keyboard navigation, not just the layout
```

这是在告诉 Claude 范围，只有你知道的范围，与思考强度无关。

当你在探索而并非修复某个具体问题时，像 `what would you improve in this file?` 这样含糊的 prompt 完全没问题。你会在过程中多做几轮纠正，这是代价的交换。

### 先和 Claude 头脑风暴

当你还不完全知道自己要什么时，不必先全部想清楚再发 prompt。让 Claude 来采访你：

```
I want to add rate limiting to the public API but haven't thought it through yet. Interview me until you could write the spec, then write it to SPEC.md.
```

Claude 会带着选择题回来，问那些你还没定的部分：按用户还是按 key 限流、超出限额的请求怎么处理、哪些不算在内。它一直问到答案凑成一份 spec 为止。

SPEC.md 存在之后，开一个全新会话从它开始构建，这样构建从干净的上下文与一份写好的完成定义开始。它也是你之后在「给 Claude 一个可以运行的检查」里让审查者对照的文件。

### 保持 CLAUDE.md 短小

Claude Code 会把 CLAUDE.md 加载进每个会话，这意味着其中每一行都会在每个任务上分走 Claude 的一点注意力，无论相关与否。这就是为什么这个文件最好只放 Claude 无法从代码本身推断出的内容：

- 在这个仓库里怎么确认工作完成：确切的测试、typecheck 与 lint 命令，以及怎么运行单个测试文件
- 代码有误导性的地方：一种到处都是、但新代码绝不能照抄的旧写法，或一个看起来废弃实际还在用的目录
- 不在仓库里的决定：团队定下的错误处理辅助函数、部署怎么做、什么改动需要迁移审查
- 任何你已经纠正过两次的东西

一份通过这个测试的 CLAUDE.md 天然就短：

```markdown
# Commands
- Install: pnpm install
- Run one test file: pnpm vitest run path/to/file.test.ts
- Typecheck: pnpm tsc --noEmit

# Conventions
- Use the error helpers in src/lib/errors.ts, never throw raw strings
- src/legacy/ is still live but don't copy its patterns into new code

# Gotchas
- Integration tests need DATABASE_URL set, see .env.example
```

在会话里运行 `/context all`，确认 Claude 加载了这个文件。

注意 typecheck 那一行只写了命令。Claude 需要知道命令，才能边做边检查自己的工作。如果你想让 Claude Code 在 Claude 结束前强制执行 typecheck 通过，那是 Stop hook 的职责。在这个文件里写一行 `Always typecheck before you finish`，多数时候有用，并非每次有用。

这个文件不必从零写：`/init` 会从你的代码库生成起始版本，接下来你的工作主要是删行。[memory 指南](https://code.claude.com/docs/en/memory#write-effective-instructions)建议保持在 200 行以内。`/doctor` 会为那些 Claude 已经能从代码推断出的内容给出[删减建议](https://code.claude.com/docs/en/memory#my-claude-md-is-too-large)。`/doctor prompt-audit` 标出那些为旧模型写的指令、指向已不存在文件的指令，以及[互相矛盾](https://code.claude.com/docs/en/memory#audit-your-instruction-files)的指令。

你的个人设置放进 CLAUDE.local.md，并把它加进 .gitignore，让它留在仓库外。

如果 Claude 一直忽略 CLAUDE.md 里确实写了的某一行，加上 IMPORTANT 大概率修不好。要么是文件长到那行字被淹没了，要么那是一条不容例外的规则，这时它应该进 hook。

### 把规则限定到代码库的一部分

如果一条规则只在代码库的某个部分重要，把它放进 `.claude/rules/` 并加 `paths:` 过滤，使它只在 Claude 真在那里工作时才加载。例如这个 `.claude/rules/api.md` 只在 `src/api/` 下的 TypeScript 文件上加载：

```markdown
---
paths:
  - "src/api/**/*.ts"
---
- Validate request bodies with the zod schemas in src/api/schemas/, don't hand-roll checks
- Every new endpoint needs an entry in openapi.yaml, CI fails without it
```

### 把团队流程放进 skills

更强的模型懂更多通用技术知识，但它不知道你们团队怎么做一次发布、你们的应急手册写了什么、你们希望 API 文档怎么写。这类知识放进 skill：一段流程或一块团队知识，保存在 `.claude/skills/<name>/SKILL.md`。

对这类内容，skill 也比 CLAUDE.md 更省上下文。对一个 Claude 能自己启动的 skill，它在每个会话里只看到名字与描述，只有任务需要时才读全文。一份冗长的发布流程放在 skill 里，不会像放在 CLAUDE.md 里那样压着你无关的 bug 修复。

CLAUDE.md 的规则同样适用于 skills：只写 Claude 自己找不到的东西。

对有副作用的工作流，比如真的切一次发布，加上 `disable-model-invocation: true`。Claude 于是不能自己启动这个 skill，只有你亲手输入 `/release` 时它才运行。保存为 `.claude/skills/release/SKILL.md`，大概长这样：

```markdown
---
name: release
description: Cut a new release. Bumps the version, writes the changelog entry, tags it and pushes the tag so CI can publish.
disable-model-invocation: true
---
1. Make sure you're on main with a clean tree. If not, stop and ask.
2. Run `pnpm changeset version` and commit the result.
3. Summarize the PRs merged since the last tag into CHANGELOG.md, one line each, user-facing changes only.
4. Tag `v<new version>` and push the tag. CI publishes from there, never publish from your machine.
```

### 接上 Claude 需要的工具

Claude 看不到的东西里，有些整个住在另一个系统里，比如你的 issue 单系统或错误监控看板。如果那个系统有 CLI，那通常是最容易的入口。装好 `gh` 并登录之后，Claude 会直接开 pull request、读评审意见，无需你解释任何东西。对它没见过的 CLI，指给它 `--help` 就够了。

对没有 CLI 的系统，有 MCP。从 shell 里添加一个 server：

```
claude mcp add --transport http notion https://mcp.notion.com/mcp
```

之后这个 server 出现在会话里的 `/mcp` 下。已连接的 server 即使你没用它，也会把工具名与说明加进上下文，所以在那里关掉你不需要的那些是值得的。

如果你用的是带类型的语言，代码智能插件能让 Claude 直接跳到定义，省去翻许多文件去找它。

## 给 Claude 一个可以运行的检查

Claude 在工作「看起来」完成时停下。如果它没有任何东西可以运行、来告诉它工作是不是真的完成了，「看起来完成」就是它仅有的依据。实际效果是测试套件成了你自己，每个错误都留在那里等你碰巧发现。

给它一个返回通过或失败的东西，Claude 就能把闭环自己合上。它做改动、跑检查，如果弄坏了什么就读输出、修好，再跑一遍检查。

这个检查几乎可以是任何东西，只要 Claude 读得到结果：

- 一个测试文件
- 一次构建的退出码
- 一个 linter
- 一个把输出与 fixture 对照的脚本
- 贴着设计稿的一张[浏览器截图](https://code.claude.com/docs/en/chrome)

如果你的仓库已经有了其中之一，你的 CLAUDE.md 里最有用的那一行就是运行它的命令。

检查做多严由你决定。选项从 Claude 自己拿捏一直排到 Claude Code 强制执行：

- 写在 prompt 里：`run the auth tests after, and keep going until they pass`。Claude 自己决定什么时候满意。这适用于任何任务，今天就可用，零配置。
- 作为 goal：[`/goal all tests in tests/auth pass and lint is clean`](https://code.claude.com/docs/en/goal) 设一个条件，由另一个模型在每一轮之后对照会话检查它，Claude 一直做到满足为止。你自己在会话里很少需要这个。它对长时间后台运行有用：那种场景下 Claude 有时会在条目还开着时以进度总结收尾，goal 把它送回去继续。
- 作为 Stop hook：[Stop hook](https://code.claude.com/docs/en/hooks#stop) 在 Claude 每次试图结束这一轮时运行你的脚本，脚本以退出码 2 退出时把 Claude 送回去干活。这个由 Claude Code（harness）强制执行，所以 typecheck 通过或到达[阻断上限](https://code.claude.com/docs/en/hooks#stop-input)之前，这一轮不会结束。下面有一个例子。
- 由没写这段代码的人来做：在终端里，[`/code-review`](https://code.claude.com/docs/en/code-review-local) 用一个从未见过你们对话的全新 subagent 审查 diff。它不会被产出这段代码的推理带跑。

无论用哪个选项，都向 Claude 要证据：它跑的命令与输出，或截图。单独一句「全部测试通过」说明不了什么，读输出比你自己重跑检查快。对一个你没盯着的会话，这也是你仅有的证据。

Claude 说做完之后，你还可以在会话里跑 `/verify`，它让 Claude 构建、运行这个应用并亲自看结果。这能抓到测试与 typecheck 抓不到的那类问题。

### 对照你的 spec 审查

如果你想让审查对照你的计划核对工作，而非泛泛找 bug，把审查 prompt 自己写：

```
use a subagent to review the rate limiter diff against SPEC.md, check every requirement is implemented and the listed edge cases have tests, report gaps that affect correctness and skip style
```

别把这条 prompt 里的 `skip style` 丢掉。一个被要求找问题的审查者总能找到点什么。如果你把每条发现都修掉，最终得到的是多余的抽象层与为不可能发生的场景写的测试。

### 用 Stop hook 强制执行检查

typecheck 规则的 Stop hook 版本是 `.claude/settings.json` 里的几行。退出码 2 就是阻断停止的东西。命令打印到 stderr 的内容会作为「还不能结束」的理由送回给 Claude，这就是为什么编译器输出被重定向到那里：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "pnpm tsc --noEmit 1>&2 || exit 2" }
        ]
      }
    ]
  }
}
```

想看它生效，让 Claude 做一个会弄坏类型的改动：它收到的并非完成，而是编译器报错，然后继续干到 `tsc` 通过。如果这个 hook 连续阻断八次停止、期间没有任何工具调用，Claude Code 会越过下一次阻断并结束这一轮。想抬高上限，设置 `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`。

## 执行不容例外的规则

如果某件事必须每次发生，把它做成 hook、deny rule 或托管设置。CLAUDE.md 是给指南的，Claude 有权判断一条指南不适用。

拿你可能写在 CLAUDE.md 里的三条规则举例：`Never read .env`、`Always run the formatter after editing`、`Don't touch the migrations folder`。Claude 几乎每次都会遵守。对那几个「几乎」不够好的场景，把它们从 CLAUDE.md 挪进 Claude Code（harness）自己应用的配置里。从此结果不再取决于模型记得什么、决定什么。

### 用 hooks 执行步骤

hooks 在 Claude 循环的固定节点上运行你的东西：工具调用之前或之后、Claude 试图停止时、会话启动时，等等。那个东西可以是：

- 一条 shell 命令（最常见）
- 一次发往 HTTP 端点的 POST
- 一次对你的某个 MCP server 的工具调用
- 一个 [`prompt` 或 `agent` hook](https://code.claude.com/docs/en/hooks#hook-handler-fields)，它让一个模型来决定

`prompt` 或 `agent` hook 让另一个模型来决定，所以它也不是确定性的。要真正的强制，用 `command` 或 `http` hook，并在 hook 本身崩溃或超时时也该叫停动作的话，加上 `onFailure: "block"`。对一个扫描提交里是否藏密钥的 hook 来说，扫描器宕机时你宁可挡住这次提交，也别放它过去没扫成。

这是格式化规则写成 PostToolUse hook 的样子。它在每次 `Edit` 或 `Write` 之后运行，Claude 记不记得这条规则不再重要，因为运行它的并非 Claude：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "npx prettier --write --ignore-unknown \"$(jq -r '.tool_input.file_path')\"" }
        ]
      }
    ]
  }
}
```

要检验这个 hook，让 Claude 往一个 Prettier 格式化的文件里加一行缩进很糟的代码。保存下来的文件回来时缩进已经被修好。

migrations 那条规则变成一个 PreToolUse hook，对 `migrations/` 下的任何路径以退出码 2 退出。你不必亲手写它：`write a hook that blocks edits to the migrations folder` 这句话本身就是可用的 prompt，`/hooks` 会展示结果。不过别过度使用：hook 是给零例外的规则用的，`Prefer named exports` 有的是例外，那一条留在 CLAUDE.md 里。

### 用权限规则与沙箱限制访问

权限规则决定 Claude 被允许运行、读取、抓取什么。deny rules 在包括 auto 与 bypassPermissions 在内的所有权限模式下都成立，这正是 `.env` 那条规则该放进那里的原因：

```json
{
  "permissions": {
    "allow": ["Bash(pnpm tsc --noEmit)"],
    "ask": ["Bash(git push *)"],
    "deny": ["Read(./.env)", "Read(./.env.local)", "Read(./secrets/**)"]
  }
}
```

保存之后，问 Claude `.env` 里有什么会失败，走 Read 工具与走 `cat .env` 一样失败。

规则匹配的对象是工具调用，意图不参与匹配，所以值得知道边界在哪：

- Read 规则确实拦得住 `cat .env`，因为 Claude Code 认得[常见的文件读取命令](https://code.claude.com/docs/en/permissions#read-and-edit)。
- 它拦不住一个自己打开这个文件的脚本。
- 对某个域名的 WebFetch deny rule 管不到 `curl` 访问同一个域名，除非沙箱开着。

要对文件系统或网络访问做操作系统层面的限制，在会话里用 `/sandbox` 打开沙箱。它把 Claude 的 shell 命令限制在 macOS、Linux 与 WSL2 上，并且会连带应用你的 Read deny rules 与 `WebFetch(domain:...)` 规则，所以任何安全相关的事你两样都想要。默认情况下 Claude 仍可请求在沙箱外重试被拦的命令，那个请求走正常权限流程。strict sandbox mode，在 `/sandbox` 的 Overrides 页签里，把重试关掉。

auto mode 是一个分类器模型在逐个判断动作，并非硬规则。它擅长这个，但像任何判断一样可能出错。你也可以调整它把什么看作有风险，你的组织可以整个关掉它，所以你的「绝不」规则该放进 deny rules 或 hooks。

### 选择规则对谁生效

一条规则住在哪里，决定了它对谁生效：

- `.claude/settings.local.json` 与 `~/.claude/settings.json` 只属于你自己。当你为某条命令选择「Yes, and don't ask again」时，Claude Code 把那条规则存进本地文件。
- `.claude/settings.json` 与其中的 hooks 属于仓库。一旦提交，它们对在这个仓库里工作的每个人生效。它的 deny rules 立即生效；allow rules 要等每个人接受那个目录的[信任确认对话](https://code.claude.com/docs/en/permissions#what-runs-before-you-trust-a-folder)之后，[workspace trust](https://code.claude.com/docs/en/hooks#workspace-trust) 也决定它的 hooks 什么时候开始在那台机器上运行。
- [托管设置](https://code.claude.com/docs/en/managed-settings)属于组织。它们来自管理控制台、MDM 或一个 `managed-settings.json` 文件，任何个人设置文件都无法越过它们，这使它们成为安全团队策略的唯一去处。如果你就是设置它们的人，见 [Set up Claude Code for your organization](https://code.claude.com/docs/en/admin-setup)。

无论作用域是什么，把强制执行的集合保持小。每个 hook 与 deny rule 都会偶尔在不该触发的时候触发，而且每一个都需要有人维护。如果你发现自己攒了四十个，多数大概是 Claude 本可以自己掂量的个人倾向。

## 更改一个默认值

默认值好到可以放着不动，直到某个任务花掉的时间、token 或打断超过了它应有的水平。到了那时，在会话里跑 `/usage` 看时间去哪了。

一个新会话已经替你做了一批决定：

- 交互式终端与 VS Code 会话在 auto mode 下启动。
- 在多数套餐与提供商上，它以 [medium effort 运行 Claude Opus 5.5](https://code.claude.com/docs/en/model-config#default-model-setting)。
- 它看到理由时把工作委派给 subagents。
- 对话变长时它做压缩。

多数时候你从不想这些。当某个任务确实花得比应有的多，原因通常是这四条之一。

### 更改权限模式

权限范围的两端各有代价：

- 手动模式：每个编辑、每条非只读命令都由你亲自批准。安全，但到第十次确认之后你开始不看内容就点同意，而且你离开键盘时一切都停住。
- `bypassPermissions`：批准你的 deny 与 ask 规则没盖住的一切，这只在一次性容器里说得通。

auto mode 位于两者之间，交互式终端与 VS Code 会话从它[开始](https://code.claude.com/docs/en/permission-modes#eliminate-prompts-with-auto-mode)。Claude 不为日常批准停下来，一个独立的分类器模型在动作执行前按[固定顺序](https://code.claude.com/docs/en/permission-modes)检查它们。它专注在你希望有个人在场拦住的事情上：

- `curl | bash`
- 生产部署与迁移
- 强行推送覆盖别人的工作
- 敏感数据发往外部端点
- 看起来是 Claude 读到的内容在驱动、你本人并没有驱动的动作

auto mode 拦下动作时，你会收到通知，动作出现在 `/permissions` 的 Recently blocked 里，你可以在那里批准它让 Claude 重试。[连续三次被拦](https://code.claude.com/docs/en/permission-modes)（或总共二十次）之后，auto mode 暂停并回到向你询问。

这些都不替代你的确定性控制，因为它跑在它们之后。deny 与 ask 规则以及 PreToolUse hooks 在分类器看到任何东西之前先应用，所以 deny rule 在 auto mode 里的拦截与在任何地方一样。沙箱仍然限制[它包住的 shell 命令](https://code.claude.com/docs/en/sandboxing)。

你也可以在对话里说 `don't push until I've reviewed`，分类器把它当作阻断信号。它仍然是一个读对话记录的模型，这句话可能在对话压缩后丢掉，所以重要的东西要放进 deny rule。

反过来的问题是分类器反复拦下你的环境里很常规的事。与其每次手动批准，把它加进 `autoMode.allow`，或在 [auto mode 配置](https://code.claude.com/docs/en/permission-modes)里描述你信任的基础设施。那是平实的英文而并非模式串，`/auto-mode-setup` 能从你的项目与最近会话替你起草 environment 部分：

```json
{
  "autoMode": {
    "environment": [
      "$defaults",
      "Source control: github.com/example-org and every repo under it",
      "Trusted internal domains: *.internal.example.com"
    ],
    "allow": [
      "$defaults",
      "Deploying to the staging namespace is fine, it's isolated from production and resets nightly"
    ]
  }
}
```

你设置的每个列表里都要保留 `"$defaults"`，因为没有它，你的条目会替换那个列表的内置规则而并非往里追加。对 environment 与 allow 来说，丢掉的是内置上下文与例外；少了它的 soft_deny 列表会丢掉对强行推送与生产部署的内置拦截。

autoMode 块也必须住在 `~/.claude/settings.json` 而非项目里，因为分类器无视项目设置里的 autoMode。

如果你更愿意在每个编辑与命令发生前看到它们，会话里的 Shift+Tab 在权限模式之间循环，手动模式也在其中；或从 shell 用 `claude --permission-mode manual` 启动。如果手动模式问得太勤，`/fewer-permission-prompts` 扫描你最近的对话记录，找出常见的只读 Bash 与 MCP 调用，加进 `.claude/settings.json` 的白名单。

### 更改模型与 effort

effort 是控制 Claude 思考时长的主要手段，它取代了人们过去用 prompt 措辞做的大部分事。Claude Opus 5.5、Sonnet 5.5 与 Haiku 5.5 默认在 medium，对范围清晰的日常功能开发足够。该动它的时候，在会话里用 `/effort`：

- 做对取决于容易看漏的场景时，用 `/effort high` 或 `/effort xhigh` 提上去。想想一段你没写过的代码里的 bug、一个时灵时不灵的测试、或一次要求 Claude 找齐旧数据结构全部读方的 schema 改动。Claude 会检查更多边界情况、在回答前验证更多自己的工作，多出来的时间与 token 就花在这里。
- 你在快速来回、反正每个结果都要亲自过目时，用 `/effort low` 降下来：头脑风暴、第一版草稿、跨几个文件的一次改名。Claude 更快给你起点，而既然每步都是你在掌舵，多想一阵除了等待之外改变不了什么。
- max 留给你想让 Claude 独自啃下来的难题，比如找一处安全漏洞。在普通任务上它容易想得过多，你为一个答案多付钱，而那个答案未必比 high 给你的更好。
- 只有下一条消息需要时，比如常规工作中间的一个刁钻问题，把 [`ultrathink`](https://code.claude.com/docs/en/model-config#use-ultrathink-for-one-off-deep-reasoning) 放进那条 prompt，而不必改设置。

模型本身，默认的 Opus 5.5 处理大多数编码都好，Sonnet 在常规工作上更便宜。Claude Fable 5.1 在你用 `/model fable` 显式选择时可用，Haiku 适合干简单活的 subagents。[模型配置](https://code.claude.com/docs/en/model-config)页面有每个套餐与提供商的完整列表。

### 了解 subagents 的代价

Claude 自己就会把工作委派给 [subagents](https://code.claude.com/docs/en/sub-agents)：

- 大范围代码检索交给内置的 Explore agent。
- 支线任务在 [fork 模式](https://code.claude.com/docs/en/sub-agents#fork-the-current-conversation)开着时（默认开）被 fork 出去。
- 它启动的 subagents 默认在后台运行，主对话继续前进。

你几乎从不需要主动要求这些，但知道你换到了什么、付出了什么代价是有用的。

Subagents 在这些场景里划算：

- 多块独立工作同时跑，整个任务更早完成
- 把长输出（一整轮测试、一次大范围检索）挡在主对话之外，否则它们会跟着你跑完这个会话剩下的一切
- 得到一个没看过这段代码怎么写出来的审查者
- 给一个任务比主会话更少的工具，比如一个能读不能改的审查者

它们的代价主要是 token，因为每个 subagent 发自己的请求，与你主对话计入同一份额度。有时也是时间：一个全新的 subagent 得先收集你的对话里已有的上下文，结果可能比在你这里就地做更慢。

而且默认情况下是同一个模型（或更小的模型）做同一个任务。你从中得到并行或全新的视角，得不到更聪明的答案。

想在它们身上少花：

- 在 subagent 定义里写 [`model: haiku`](https://code.claude.com/docs/en/sub-agents#choose-a-model)，如果它的活简单，比如收集导入某个模块的文件、检查文档里的链接。这类活不需要更大的模型，而 Haiku 每次请求便宜得多。
- 要求它回短总结，免得二十条结果照样填满你的上下文。
- 看 `/usage` 里每类 subagent 占你用量的份额，判断哪些挣回了它们的成本。
- 给 `.claude/agents/` 里的自定义 subagent 只配 `tools: Read, Grep, Glob`。现在它是一个什么都改不了的审查者，而这个限制由 Claude Code 强制执行，并非写在 prompt 里的请求。

那个审查者是一个短文件，`.claude/agents/reviewer.md`：

```markdown
---
name: reviewer
description: Reviews changed files against the spec they were built from. Use after implementing a feature, before opening the PR.
tools: Read, Grep, Glob
---
You're reviewing code you didn't write. Compare the changed files against the spec you're given,
check that every requirement is implemented and the listed edge cases have tests,
and report only the gaps that affect correctness. Skip style.
```

让 Claude「请 reviewer 对照 SPEC.md 审查 rate limiter」，缺口就回到你的会话里，Claude 在那里修掉它们。

### 控制成本与上下文

多数当前模型有 1M token 的窗口、接近顶部时自动压缩，你很少会把上下文用完。但你仍然可能为不需要的上下文付费。每次请求都发送整个对话，一个攒了三个无关任务的会话，在第四个任务的每一轮都要把三个都重读一遍。缓存热着时有折扣，过期后全价。

`/usage` 是第一个该看的地方。在 Pro、Max、Ultra、Team 与 Enterprise 上，它把用量按 skill、subagent、plugin 与 MCP server 分开列。它还会在某个模式超过你用量 10% 之后标出长上下文、频繁缓存未命这类模式。从那里出发，常规修法：

- 无关任务之间用 `/clear`。它不花钱，意思是下一个任务不再为上一个任务的历史持续付费。`/clear oauth-migration` 给你正离开的会话起个名字，之后可以回来。
- 带焦点的 `/compact`，比如 `/compact keep the API changes and the test commands`。长会话上 `/compact` 本身就是一次大请求，因为它读整个对话来做总结，缓存过期后更是如此。
- 盯着后台工作：一个 `/loop`、goal 在每轮之后的检查、Claude 自己的 subagents，都在你不打字时持续发请求。

[prompt cache](https://code.claude.com/docs/en/costs) 在订阅上持续约一小时，在 API key、云提供商或按量额度上五分钟。Subagents 五分钟，除非你改它。在一小时缓存下，一个超过约 200K token 且闲着的会话会在缓存过期前被压缩，所以午饭后你从一份总结继续。如果完全不需要历史，新会话仍然更便宜。

## 引导会话

看住第一分钟，Claude 一走错方向就按 Esc，两次纠正失败后跑 `/clear` 写一个更好的 prompt，而并非做第三次纠正。

再多的配置也替代不了看住第一分钟、在 Claude 走向你没打算去的方向时介入。这方面的控制只有几个，值得背下来：

- `Esc` 在动作中间停住 Claude，保留到那一点为止的一切，你可以转向而不丢工作。
- `/rewind`，或在空 prompt 上按两次 Esc，打开[回退菜单](https://code.claude.com/docs/en/checkpointing#rewind-and-summarize)，把代码、对话或两者退回更早的一个 prompt。这让先试大胆方案、不行再退回变得低风险。同一个菜单也能在对话变得陈旧时总结其中一段。
- `/clear` 从头开始。同一件事你纠正过两次还是错，第三次纠正多半只是往一个已经装着两次失败尝试的对话里再加内容，让 Claude 继续反复读。`/clear` 加一条揉进你所学到的东西的新 prompt，几乎每次都更好。

检查点覆盖 Claude 在你主对话里用自带文件工具编辑过的文件，只被 Bash 命令碰过的文件[不会恢复](https://code.claude.com/docs/en/checkpointing)。它们与 git 并存而并非取代 git。

两个小的：`/btw` 回答一个小问题而不往历史里加任何东西。跨好几天的工作，在会话里 `/rename oauth-migration` 给它起名，之后 shell 里的 `claude --resume oauth-migration` 能捡回来，检查点也在内。`claude --continue` 恢复最近那个。

## 让 Claude 无人值守运行

在一个运行交给无人值守之前，确认它知道完成长什么样、能检查自己的工作、只碰它该碰的。给它轮数或支出的上限，最后让一个人批准结果。

这一页上的每件事，在你不在场抓错时都更重要一点。你在看的时候，Claude 缺一块上下文不是大事：一两句话之内你就发现并告诉它。在一个你睡前启动的运行里，没人告诉它，第二天早上你发现它整晚建立在一个错误假设上。

把一个任务留着自跑之前，带着那个具体任务过这五问：

1. 它知道完成长什么样吗？一个 goal 条件、一份 spec 文件、或一个必须变绿的失败测试。
2. 它能检查自己的工作吗？测试套件、Stop hook、某种评审步骤。
3. 它被允许碰什么？权限规则、dontAsk、沙箱、worktree、唯一可以推的分支。
4. 什么让它停下来？`--max-turns`、`--max-budget-usd`、支出上限。
5. 结果去哪里，谁签字？一个 PR、一条评论或一份总结，然后由一个人批准合并、部署、或任何你收不回来的事。

一旦跑起来，Claude 会自己把长任务扛完。留在你手上的部分是启动它、这一次「完成」意味着什么、以及最后批准合并。

### 从脚本运行 Claude

`claude -p "prompt"` 跑一次就退出，Claude Code 就这样进了 CI 任务、git hooks 与 shell 循环。

在脚本里你几乎总要多加几个标志：

- [`--bare`](https://code.claude.com/docs/en/headless#start-faster-with-bare-mode) 跳过 hooks、skills、plugins、MCP servers 与 CLAUDE.md 文件，仓库的与机器的都跳，所以这个运行在哪里跑都做同样的事。它也从不碰你的 claude.ai 登录：认证来自 `ANTHROPIC_API_KEY`、你用 `--settings` 传入的文件里的 apiKeyHelper、或你云提供商的凭据。
- `--append-system-prompt`、`--mcp-config` 与 `--settings` 显式传入这个运行确实需要的东西。
- `--allowedTools` 预批准它的工具，[`--permission-mode dontAsk`](https://code.claude.com/docs/en/permission-modes#allow-only-pre-approved-tools-with-dontask-mode) 拒绝任何本会弹确认的东西。
- `--output-format json` 给你一个可解析的单一结果对象，`stream-json` 配 `--verbose` 在事件发生时流式输出。

合在一起，长这样：

```bash
for file in $(cat files.txt); do
  claude --bare -p "Migrate $file to the new logger API and commit. Reply OK or FAIL." \
    --allowedTools "Read,Edit,Bash(git add *),Bash(git commit *)" \
    --permission-mode dontAsk \
    --max-turns 20
done
```

一次运行结束时，Claude 回 OK 或 FAIL，撞到轮数上限的运行以报错退出。先在三个文件上试，看哪里不对，修 prompt，再跑剩下的。

传 `--permission-mode auto` 时 auto mode 也能配合 `-p`。在非交互运行里，分类器的一次拦阻只拒绝那一个动作、Claude 继续，反复拦阻也不会像终端里那样暂停运行。依赖它之前先读[阈值在那里怎么适用](https://code.claude.com/docs/en/permission-modes)。

### 按时间表或事件启动运行

一旦运行起来，Claude 能自己处理剩下的。它做不到的一件事是决定启动，所以得有什么来启动：你、一个定时器、或一个像 CI 挂了或新 PR 这样的事件。

在一个打开的会话里，那是 `/loop`，按间隔重复一条 prompt：

```
/loop 15m check CI on this branch, and if it's red pull the failing job's log, fix it and push
```

每一轮运行都是同一会话里的又一个回合，所以别让一个 `/loop` 长在一段长对话里。对任何该在你合上笔记本时发生的事，`/schedule` 建一个按定时器运行的[云端定时任务](https://code.claude.com/docs/en/routines)。它要 claude.ai 登录而非 API key。你可以让 Claude 加一个 GitHub 事件触发器，或在 claude.ai/code/routines 加 API 触发器。

让一个云端定时任务跑着之前，用一条任务绕不过的 GitHub 分支规则保护好 main。任何新东西的前几轮都要先看着跑，再信它无人值守。

### 并行运行多个会话

当你同时推进几块分开的工作，给每块一个自己的检出，改动才不会相撞。`claude -w feature-auth` 在一个新 worktree 里开会话，桌面应用并排放好几个，云端会话把它们跑在云里而非你的机器上。

worktree 是一份全新检出，这意味着像 `.env` 这样被 gitignore 的文件不在那里，依赖也没装。对前者，把你需要的 gitignore 文件列在仓库根的 `.worktreeinclude` 里（语法同 .gitignore），Claude Code 会把它们复制进它建的每个 worktree：

```
.env
.env.local
config/dev-credentials.json
```

只放小文件：它做的是复制，不做链接，把 node_modules 放进去意味着每个 worktree 一份完整拷贝。大目录有 `worktree.symlinkDirectories` 设置，或者把安装命令写在 CLAUDE.md 里，让 Claude 每次在新检出里启动时自己跑。

这些你几乎从不必自己清理：

- 退出一个未命名的 worktree 会话时，若里面没有东西，Claude Code [移除这个 worktree](https://code.claude.com/docs/en/worktrees#clean-up-worktrees)。对命名会话或有改动的会话，它问你怎么处理。
- subagent 的 worktree 在 subagent 结束且没有改动时消失。
- 留下来的 subagent 与后台会话 worktree，在超过 cleanupPeriodDays 且不含工作时被清扫。

一个 `claude -p --worktree` 的运行要你自己清理，它退出时不问。用 `git worktree remove <path>` 移除；git 因 worktree 被锁而拒绝时，先 `git worktree unlock <path>`。

对一次跨大量文件的机械大改，`/batch migrate every handler to the v2 response helpers` 把工作切成 5 到 30 个单元并给你看计划。你批准后，每个单元拿到自己的 worktree，开一个 PR 或报告发生了什么。从 shell 看，`claude agents`（仍是研究预览）给你一屏看完机器上所有后台运行的东西。

第二个会话也是你能得到的最容易的独立审查者。一个会话写 rate limiter，另一个没看过它怎么写出来的会话审查 `@src/middleware/rateLimiter.ts`，你把发现粘贴回第一个。与 `/code-review` 同一个思路，由你传递消息。

## 可以不再做的事

这里每一条在写成时都是好建议。多数是对模型还做不到某件事的时期的绕法，而模型已经赶上了。如果几条还留在你的习惯里，这里是能安全放弃它们的原因。

| 旧建议 | 为什么过时了 |
|---|---|
| 上下文窗口是主要约束，要激进管理它 | 多数当前模型有 1M token 窗口，压缩自动发生，用完很少见。任务之间 `/clear` 仍然值得做，因为专注的上下文给你更好的答案也更便宜。 |
| 给 Claude 总漏掉的那条指令加 IMPORTANT 或全大写 | 旧模型有时需要强调。当前模型遵从一行措辞平实的话，不断堆强调多半让 Claude 过度套用那条规则。如果是一条不容变通的规则，把它变成 hook 或 deny rule。如果那行字在长文件里被淹没，是文件该更短了。 |
| 用 subagents 保护你的上下文窗口 | 上下文用完很少再是问题。Subagents 仍然适合并行工作、把嘈杂输出挡在外面、独立评审，但每一项都额外花 token。 |
| 委派给 subagent 以得到更好的答案 | 把同一个任务交给 subagent 不会让答案更好。一个全新的审查者确实有用，因为它没看过你的推理，这与委派是两回事。 |
| prompt 里写 think hard、think harder、be thorough | 那是 effort 的职责。这些短语是普通 prompt 文本，在 effort 档位之内轻推 Claude，并非抬高它的关键词。ultrathink 仍然有效：它对那一轮要求更深推理，不动你的 effort 设置。 |
| 告诉 Claude 继续、循环直到完成、别偷懒 | 当前模型通常不被告知也会把约定任务扛完，这类话更可能造成过度工作，解决不了停顿。给 Claude 一个要通过的检查是另一回事，仍然值得做。运行确实提前停了就说 continue，没人看的运行用 /goal 或 Stop hook 强制。 |
| 在 CLAUDE.md 里描述架构与文件布局 | Claude 自己会读仓库。只写仓库里没有的东西。 |

如果本页任何其他建议开始让你觉得是无谓的忙碌，那多半是它也该进这张表的信号。

## 相关资源

- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)：循环、工具、启动时加载什么
- [Explore the context window](https://code.claude.com/docs/en/context-window)：会话里什么占空间、什么时候加载
- [Extend Claude Code](https://code.claude.com/docs/en/features-overview)：skills、hooks、MCP、subagents 与 plugins 之间的选择
- [Choose a permission mode](https://code.claude.com/docs/en/permission-modes) 与 [Configure permissions](https://code.claude.com/docs/en/permissions)
- [Manage costs effectively](https://code.claude.com/docs/en/costs)
- [Run Claude Code programmatically](https://code.claude.com/docs/en/headless) 与 [Automate work with cloud scheduled tasks](https://code.claude.com/docs/en/routines)
- 面向团队负责人与管理员：[Set up Claude Code for your organization](https://code.claude.com/docs/en/admin-setup)
