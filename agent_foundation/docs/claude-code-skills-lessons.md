# Claude Code 构建经验：我们如何使用 skills（Lessons from building Claude Code: How we use skills）

- 原文：[Lessons from building Claude Code: How we use skills](https://claude.dev/blog/lessons-from-building-claude-code-how-we-use-skills/)
- 来源：Anthropic（claude.dev Blog），作者 Thariq Shihipar
- 发布：2026-06-03
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 claude.dev /media/ 绝对直链并配中文短描述；九类技能清单与九条制作要领完整翻译。

在 Anthropic 内部构建与规模化运营几百个 skills 的过程中，我们学到了什么。

Skills 已经成为 [Claude Code](https://claude.com/product/claude-code) 使用最多的扩展点之一。它们灵活、易做、易分发。

但这种灵活也让「怎样做效果最好」变得难判断。什么类型的 skill 值得做？skill 怎么组织结构？什么时候分享给别人？

我们在 Anthropic 大量使用 skills，活跃的有几百个。以下是我们用 skills 加速开发的经验。

## 什么是 SKILLS

Skills 是指令、脚本与资源的文件夹，agent 可以发现并使用它们，把事情做得更准更快。本文假定你已了解 skills 基础；新上手的话，先看我们的 [Skilljar 上的 agent skills 入门课程](https://anthropic.skilljar.com/introduction-to-agent-skills)。

一个常见的误解是把 skills 说成「只是一些 markdown 文件」。它们实际是文件夹，可以包含脚本、资产、数据等，agent 能发现、探索并操作它们。

在 Claude Code 里，skills 还有[丰富的配置选项](https://code.claude.com/docs/en/skills#frontmatter-reference)，包括注册动态 hooks。

我们发现 Claude Code 里最有效的那些 skills，都把配置选项与文件夹结构用得很充分。

## SKILLS 的类型

把 Anthropic 内部全部 skills 编目之后，我们看到它们聚成九类。最好的 skill 干净地归入其中一类；试图做太多事的 skill 横跨几类，让 agent 困惑。这份清单并非定论，但用它检查自己 skill 库的缺口很有用。

![九宫格技能类目图，每格一类与示例 skill 名：库与 API 参考、产品验证、数据获取与分析、业务流程与团队自动化、代码脚手架与模板、代码质量与评审、CI/CD 与部署、事故 runbook、基础设施运维](https://claude.dev/media/8c0b43b7a1f0aefab9af8990f3d69eb961d4c5eef12c1e72584828787e57cb5f.png)

### 1. 库与 API 参考

解释怎么正确使用某个库、CLI 或 SDK 的 skills。既有内部库，也有 Claude Code 常处理不好的公共库。这类 skill 通常带一个参考代码片段的文件夹，加一份 Claude 写脚本时要避开的 gotchas 清单。

示例：

- `billing-lib`：你的内部计费库，边界情况、易错点等
- `internal-platform-cli`：内部 CLI 封装的每个子命令，附使用时机示例
- `sandbox-proxy`：配置公司的出口网关做开发：哪些主机可达、怎么排查 connection refused、怎么加白名单条目

### 2. 产品验证

描述怎么测试或验证代码正确性的 skills。常与 playwright、tmux 等外部验证工具搭配。

[验证类 skills](https://claude.com/resources/articles/building-verification-loops-in-claude-code-with-skills) 在内部对 Claude 输出质量的影响最可量测。让一位工程师花一周专门把验证 skills 做到优秀是值得的。

可以考虑让 Claude 录下它输出的视频，让你看到它到底测了什么；或在每一步对状态做程序化断言。这些通常靠在 skill 里放各种脚本实现。

示例：

- `signup-flow-driver`：无头浏览器里走完注册 → 邮箱验证 → 引导流程，每步带状态断言的钩子
- `checkout-verifier`：用 Stripe 测试卡驱动结账界面，验证发票真实到达预期状态
- `tmux-cli-driver`：被验证对象需要 TTY 的交互式 CLI 测试

### 3. 数据获取与分析

连接你的数据与监控系统的 skills。可能包含带凭证取数的库、具体 dashboard 的 ID 等，以及常用工作流与取数方式的说明。

示例：

- `funnel-query`：「注册 → 激活 → 付费该 join 哪些事件」，加上真正存 canonical user_id 的那张表
- `cohort-compare`：对比两个群组的留存或转化，标记统计显著的差异，链接群组定义
- `grafana`：数据源 UID、集群名、问题到 dashboard 的对应表
- `datadog`：字段参考（@request_id 与 trace_id 的区别）、服务清单、指标前缀约定

### 4. 业务流程与团队自动化

把重复工作流自动化成一条命令的 skills。指令通常很简单，但可能依赖其他 skills 或 MCP。这类 skill 把以往结果存进日志文件，能让模型保持一致，并回顾该工作流此前的执行。

示例：

- `standup-post`：聚合工单系统、GitHub 活动与既往 Slack → 格式化的站会汇报，只写增量
- `create-<ticket-system>-ticket`：强制 schema 合法（枚举值、必填字段）加上创建后的流程（提醒评审人、发 Slack 链接）
- `weekly-recap`：合并的 PR + 关闭的工单 + 部署 → 格式化的周报帖

### 5. 代码脚手架与模板

为代码库里特定功能生成框架样板代码的 skills。可以和可组合的脚本搭配。脚手架需要自然语言描述需求、纯代码覆盖不了的场景里特别有用。

示例：

- `new-<framework>-workflow`：用你的注解脚手架出一个新 service/workflow/handler
- `new-migration`：迁移文件模板加常见 gotchas
- `create-app`：新内部应用，预接好你的认证、日志与部署配置

### 6. 代码质量与评审

在组织内强制执行代码质量、辅助代码评审的 skills。可以包含确定性脚本或工具以获得最大健壮性。你可能想让这些 skills 作为 hooks 的一部分自动运行，或放进 GitHub Action。

- `adversarial-review`：派一个全新视角的 subagent 做批评，实现修复，迭代到发现只剩吹毛求疵
- `code-style`：强制代码风格，尤其是 Claude 默认做得不好的那些
- `testing-practices`：怎么写测试、该测什么

### 7. CI/CD 与部署

帮你在代码库里取数、推送与部署代码的 skills。可能引用其他 skills 收集数据。

示例：

- `babysit-pr`：盯一个 PR → 重试不稳定的 CI → 解决合并冲突 → 开启 auto-merge
- `deploy-<service>`：构建 → 冒烟测试 → 按错误率对比做渐进放量 → 回归时自动回退
- `cherry-pick-prod`：隔离 worktree → cherry-pick → 冲突解决 → 按模板建 PR

### 8. Runbooks

接收一个症状（Slack 讨论串、告警、错误签名），走完多工具的调查，产出结构化报告的 skills。

示例：

- `<service>-debugging`：为高流量服务建立症状 → 工具 → 查询模式的映射
- `oncall-runner`：取告警 → 检查常见嫌疑 → 格式化一条发现
- `log-correlator`：给定请求 ID，从每个可能接触过它的系统里拉取匹配日志

### 9. 基础设施运维

执行例行维护与运维操作的 skills，有些涉及危险动作、需要护栏。它们让工程师在关键操作里更容易遵守最佳实践。

示例：

- `<resource>-orphans`：找孤儿 pod/卷 → 发到 Slack → 观察期 → 用户确认 → 级联清理
- `dependency-management`：你的依赖审批工作流
- `cost-investigation`：「为什么这个月的存储/流量账单暴涨」，带具体的桶与查询模式

## 制作 SKILLS 的要领

决定要做的 skill 之后，怎么写？以下是 Claude Code 团队的一些最佳实践与技巧。

### 别写显而易见的内容

Claude 已经会写代码、能读你的代码库。复述 Claude 默认就会做的事，只加上下文不加价值。要发布一个以知识为主的 skill，就把笔墨放在能推着 Claude 跳出常规思路的信息上。

[frontend design skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) 是个好例子：它由 Anthropic 的一位工程师与客户迭代构建，用于改善 Claude 的设计品味，避开 Inter 字体与紫色渐变这类经典套路。

### 建一个 Gotchas 节

![同一个 Billing Lib skill 文件在第 1 天、第 2 周、第 3 个月的形态：Gotchas 节从一行（proration 向下取整）长到四行](https://claude.dev/media/16acf64a5f80810ad01275e7a7de64b689ff947b145ee1b188f328e614cdfe98.png)

任何 skill 里信号密度最高的内容是 Gotchas 节。这些内容应从 Claude 使用你的 skill 时实际撞到的失败点里逐步积累。理想形态是随时间更新 skill，把这些 gotchas 沉淀下来。

例如：

- 「`subscriptions` 表只追加数据。你要的那行是版本号最大的，按 `created_at` 最晚取是错的。」
- 「这个字段在 API 网关叫 `@request_id`，在计费服务叫 `trace_id`，两者是同一个值。」
- 「Staging 环境即使 Stripe webhook 实际没处理也返回 200。要看真实状态去查 `payment_events`。」

### 用好文件系统与渐进式披露

![一个 queue-debugging skill 文件夹：SKILL.md 是枢纽，stuck-jobs.md、dead-letters.md、retry-storms.md、consumer-lag.md 是辐条；SKILL.md 里有症状到文件的对应表，告诉 Claude 该读哪个文件](https://claude.dev/media/d70d147c4c600c297d350ebd7a76f110c879ca670f9e40adb83b05882f71dd8c.png)

如前所述，skill 是文件夹，不只是 markdown 文件。应当把整个文件系统当作一种[上下文工程与渐进式披露](https://claude.dev/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models/)来用。告诉 Claude 你的 skill 里有哪些文件，它会在合适的时机去读。

渐进式披露最简单的形态是指向其他 markdown 文件。例如把详细函数签名与使用示例放进 `references/api.md`。

另一个例子：如果最终产出是 markdown 文件，可以在 `assets/` 里放一个模板文件供复制使用。

你可以有 references、scripts、examples 等多个文件夹，帮 Claude 更有效地工作。

### 别把 Claude 锁进轨道

Claude 一般会尽量遵守你的指令，而 skill 又高度可复用，所以指令写得太具体要当心。给 Claude 需要的信息，同时给它随场景调整的自由。

例如：

![cherry-pick 指令的两个版本。写得过于具体：六步编号逐步列出每个 git 命令。更好：「把 commit cherry-pick 到干净分支上。冲突按原意解决。无法干净合入时，说明原因。」](https://claude.dev/media/f634d39724ba5a2785fa6a8aa5614a1e4654c1d278a2d73b0e3b7ce0a74d84c4.png)

### 把 setup 想清楚

![standup-post 的 SKILL.md：Your config 节跑 shell 命令读 config.json，缺失时输出 NOT_CONFIGURED；指令让 Claude 未配置时向用户询问 Slack 频道与一条样例站会，然后把答案保存下来](https://claude.dev/media/c24d1f6d68756396e649a2a1ee89dcde197dad5675e9b75cf17099064345486e.png)

有些 skills 需要从用户那里拿一些上下文才能开始。例如做发站会汇报到 Slack 的 skill，你可能想让 Claude 问清楚发到哪个频道。

一个好模式是把 setup 信息存在 skill 目录的 config.json 文件里。配置缺失时，agent 就向用户询问需要的信息。

想让 agent 提出结构化的选择题，可以指示 Claude 使用 AskUserQuestion 工具。

### 描述写给模型看，不是写给人看

Claude Code 开启会话时，会构建一份全部可用 skills 及其 description 的清单。Claude 扫描这份清单来决定「这个请求有没有对应的 skill」。所以 description 字段并非内容摘要，它是[何时触发这个 skill 的描述](https://claude.com/resources/articles/improving-skill-creator-test-measure-and-refine-agent-skills)。

![babysit-pr 的两条 SKILL.md 描述。左边：「一个跨开发生命周期监控 pull request 状态的综合工具。」右边：「盯一个 PR 直到合并。触发词：babysit、watch CI、make sure this lands。」](https://claude.dev/media/1debbf1fd04f39bcfeb62bcb458574268414bd0f519c4390d708bbac8f1b724e.png)

### 帮 Claude 记住

![一份 ~/.claude/standups.log 文件，连续三天的带日期条目；onboarding redesign 线程在三天里都被高亮](https://claude.dev/media/829d6345a17c88a8eb51d616918194402492d1afaba783b00e8b5fdf06b89edf.png)

有些 skills 可以自带一种记忆，把数据存在 skill 内部。存储载体可以简单到只追加的文本日志或 JSON 文件，也可以复杂到 SQLite 数据库。

例如 `standup-post` skill 可以维护一份 standups.log 记录它发过的每条汇报，下次运行时 Claude 读自己的历史，就能说出跟昨天比有什么变化。

可以用环境变量 `${CLAUDE_PLUGIN_DATA}` 获得一个稳定目录来存数据，skills 里持久化数据的更多说明见[插件参考文档](https://code.claude.com/docs/en/plugins-reference#persistent-data-directory)。

### 存脚本、生成代码

你能给 Claude 的最强大工具之一是代码。给 Claude 脚本与函数库，让它把回合花在组合上，决定下一步做什么，无需每次重建样板。

例如在 `data-science` skill 里放一个从事件源取数的函数库。为了让 Claude 做复杂分析，可以给它这样一组 helper 函数：

![lib/signups.py 有三个 helper 函数 fetch、by_referrer、by_landing_page，docstring 里记着数据 gotchas，如 user_id 在注册完成前是 null](https://claude.dev/media/9306b89148d50e676d639a58b675a7461b8df96079f41db272558651be023f5f.png)

Claude 随后可以即时生成脚本，组合这些功能做更高级的分析，回答「周二发生了什么？」这类问题。

![Claude 生成的 investigate.py，导入那些 helper 对比周一与周二按来源与着陆页的注册量，结论是周二主页上出了问题](https://claude.dev/media/58c7ef840b2a94594f712995ad204a05360a28f0a02c74931a5c238c11426fa5.png)

### 按需 hooks

Skills 可以包含只在 skill 被调用时激活、只在会话期间生效的 hooks。用来放那些你不想一直开着、但特定时刻极其有用的强约束 hooks。

例如：

- **`/careful`**：通过 Bash 上的 PreToolUse matcher 拦截 rm -rf、DROP TABLE、force-push、kubectl delete。只在明确要碰生产环境时开，一直开着会逼疯人
- **`/freeze`**：拦截指定目录之外的一切 Edit/Write。调试时有用：「我想加点日志，但老是顺手『修复』无关代码」

## 分发 SKILLS

Skills 的一大好处是可以分享给团队。

两种分享方式：

- 把 skills 提交进你的仓库（放在 `./.claude/skills`）
- 制作 **plugin**，建一个 Claude Code Plugin 市场，用户上传与安装插件（见[文档](https://code.claude.com/docs/en/plugin-marketplaces)）

对跨少量仓库工作的小团队，提交进仓库就够用。但每提交一个 skill 也给模型上下文加一点负担。规模上来后，内部 plugin 市场让你分发 skills、让团队自行决定装哪些，还能带上 setup 流程。

## 运营一个 SKILLS 市场

怎么决定哪些 skills 进市场？别人怎么提交？

Anthropic 没有中央团队做决定；我们让最有用的 skills 自然浮现。谁有想让别人试用的 skill，可以上传到 GitHub 的沙箱文件夹，在 Slack 等场合指给别人。

skill 有了吸引力之后（由 skill 主人判断），就可以提 PR 把它移进市场。

## 组合 SKILLS

你可能想要相互依赖的 skills。例如一个文件上传 skill 负责上传文件，一个 CSV 生成 skill 生成 CSV 并上传。这种依赖管理在市场与 skills 里都还没有原生支持，但直接按名字引用其他 skills 即可，装了的模型会自己调用。

## 量测 SKILLS

要了解一个 skill 的表现，我们用一个 PreToolUse hook 在公司内部记录 skill 使用情况（[示例代码](https://gist.github.com/ThariqS/24defad423d701746e23dc19aace4de5)）。由此能发现哪些 skills 受欢迎、哪些相比预期触发不足。

## 开始

Skills 的最佳实践仍在演进。我们最好的 skills 大多从几行与一个 gotcha 起步，随 Claude 撞到新的边界情况被人持续补充而变好。

理解 skills 最好的方式是动手做、做实验，看什么对你有效。

- 阅读[skills 文档](https://code.claude.com/docs/en/skills)
- [找示例 skills 来定制](https://github.com/anthropics/skills)

*本文作者 Thariq Shihipar，Anthropic 技术团队成员，Claude Code 方向。*
