# 构建有效的 agent 自动化（Building effective agent automations）

- 原文：[Building effective agent automations](https://claude.dev/blog/building-effective-agent-automations/)
- 来源：Anthropic（claude.dev Blog），作者 Lance Martin、CJ Avilla
- 发布：2026-10-08
- 译文说明：Managed Agents 的三原语（session、harness、sandbox）、vaults 凭据机制与构建模块演进见 managed-agents.md 与 managed-agents-evolution.md；sandbox 隔离与权限收窄的通用原则见 contain-claude.md。本文独有增量在无人值守定时自动化的运行纪律：书签续读替代固定时间窗、失败读取三规则（书签不动、其余来源照写、结尾点名）、送达确认三规则与 maybe posted 状态、每轮重读只读 preferences、ledger 台账与运行记录三态、environment 允许清单与只读权限、budget 上限与 budget_reached 暂停、六条上手规则；外加 daily-brief 八文件参考配置与 ant apply、onboard 命令的配置形态。

AI 加速了我们的工作，跟上它变得越来越难。Anthropic 内部经常用[简单的 agent 自动化](https://claude.com/resources/articles/how-an-anthropic-japan-business-development-representative-runs-his-day)来帮忙：它们[按计划运行](https://claude.com/resources/articles/whats-new-in-claude-managed-agents)，在后台收集上下文，主动把需要知道的事告诉我们。但把 agent 自动化做好很难：它们会在无人察觉的情况下失去对某个来源的访问，或者不遵循我们的 preferences。

用 [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview)（beta），我们构建了一个参考实现：按计划读取自定义来源（例如 Slack 和 GitHub 仓库），追踪上次运行以来的变化，把你需要知道的内容发出去（例如发到 Slack）。本文走查每一步，分享参考实现，并提供一条在 [Claude Code](https://claude.com/product/claude-code) 里运行的命令，替你完成 agent 配置。

## 获取代码

参考实现[在这里](https://github.com/anthropics/claude-quickstarts/tree/main/managed-agents/daily-brief)。想要交互式走查，在 Claude Code 里运行下面的命令。`claude-api` skill 可以按照本文的指引帮你搭建这个 agent：

```
/claude-api managed-agents-onboard https://claude.dev/blog/building-effective-agent-automations/
```

这个参考实现需要一个 Slack app（[从 manifest 创建](https://api.slack.com/apps?new_app=1&manifest_yaml=display_information%3A%0A%20%20name%3A%20Daily%20brief%0A%20%20description%3A%20Posts%20one%20short%20brief%20each%20weekday%20morning.%0Afeatures%3A%0A%20%20bot_user%3A%0A%20%20%20%20display_name%3A%20Daily%20brief%0A%20%20%20%20always_online%3A%20false%0A%20%20app_home%3A%0A%20%20%20%20home_tab_enabled%3A%20false%0A%20%20%20%20messages_tab_enabled%3A%20true%0A%20%20%20%20messages_tab_read_only_enabled%3A%20true%0Aoauth_config%3A%0A%20%20scopes%3A%0A%20%20%20%20bot%3A%0A%20%20%20%20%20%20-%20channels%3Ahistory%0A%20%20%20%20%20%20-%20chat%3Awrite%0Asettings%3A%0A%20%20org_deploy_enabled%3A%20false%0A%20%20socket_mode_enabled%3A%20false%0A%20%20token_rotation_enabled%3A%20false%0A)）和一个 [GitHub token](https://github.com/settings/personal-access-tokens/new)。下面列出的文件是 Claude API 资源的配置，覆盖 agent、它的 environment、memory stores、vault 和 deployment。

```
daily-brief/
├── agent.md                        model, tools, instructions
├── deployment.md                   schedule, time zone, budget, input message
├── environment.yaml                network allowlist
├── memory_store_preferences.yaml   user preferences
├── memory_store_state.yaml         the agent's 书签, ledger, notes, and run records
├── vault.yaml                      the vault that holds the credentials
├── claude-lock.json                resource IDs, written by ant apply
└── slack/manifest.yaml             one bot app
```

[`ant apply`](https://platform.claude.com/docs/en/cli-sdks-libraries/cli/apply) 是 ant CLI 里的一个命令，它读取这些文件，在你的 Claude API workspace（平台存储并运行这些资源的地方）里创建资源，并把资源 ID 记进 `claude-lock.json`。

下面的章节会用到这个命令。配置完成后，自动化就按计划运行在 Anthropic 的基础设施上，[你的机器上不需要常驻任何东西](https://claude.dev/blog/claude-code-in-the-cloud/)。

## 总览

我们要构建的 agent 有六个组件，按以下顺序讲解：

- Sources——一份具名的读取位置清单
- Destination——agent 唯一可以写入的地方
- Agent——model、tools 与 agent.md 里的 run steps
- Schedule——一份 cron 计划
- Memory——你的 preferences 与 agent 自己的记忆
- Guardrails——只读的地方一律只读，每轮设花费上限

![总览：计划唤醒 agent，agent 读取各来源并把简报发往唯一目的地送达读者；memory 保存 agent 的状态与读者的 preferences；guardrails 环绕 agent](https://claude.dev/media/fdbe45db5e3ce9afbb00bf62f87e64078a683800bc492d4ac6cf716a2d313a00.png)

## Sources

agent 读取两个默认来源：Slack 频道和 GitHub pull requests。频道与仓库列在你的 `preferences` 文件里。模板可以扩展出其他来源。

![Sources 高亮：来源只读，经 MCP 或 HTTPS 携 vault 凭据访问，汇入 agent](https://claude.dev/media/d8508de61bb90f3bfccf6184dd3d7cbe9c65e2e76bd00477efd1620e3910dae7.png)

### 给 agent 独立且限定的凭据

在 [Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) 里，凭据存放在 [vaults](https://platform.claude.com/docs/en/managed-agents/vaults) 中。agent 可以引用这些凭据，但真实值留在 vault 里、[在 sandbox 外](https://claude.com/resources/articles/giving-companies-more-control-over-their-ai-agents-with-nvidia)——Claude 的代码运行在 sandbox 内（另见[这里](https://www.anthropic.com/engineering/managed-agents)和[这里](https://x.com/katelyn_lesse/status/2099315903884415400)）：

- **MCP servers（GitHub）。** agent 经一个运行在 sandbox 外的 proxy 调用 MCP 工具。proxy 按 URL 找到匹配该 server 的 vault 凭据。
- **shell（Slack）。** agent 在 sandbox 内用 bash 工具以 curl 调用 Slack API。sandbox 里只有一个不透明占位符 `$SLACK_BOT_TOKEN`；请求离开 sandbox 时，平台只为你允许的 host 换入真实 token。

用 `ant` CLI 和仓库里的模板文件创建 vault：

```
ant apply vault.yaml
```

它会在你的 Claude API workspace 里创建 vault，并把 ID 记进 `claude-lock.json`。然后用 [TypeScript SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/typescript) 把每条凭据加进 vault。下面是加入 Slack 凭据的例子：

```
const vaultId = process.env.VAULT_ID!; // the vault's ID, from claude-lock.json

await client.beta.vaults.credentials.create(vaultId, {
  display_name: "SLACK_BOT_TOKEN",
  auth: {
    type: "environment_variable",
    secret_name: "SLACK_BOT_TOKEN",
    secret_value: process.env.SLACK_BOT_TOKEN!,
    networking: { type: "limited", allowed_hosts: ["slack.com"] },
    injection_location: { header: true },
  },
});
```

vault 建好、每条凭据加好后，把 vault 挂到 deployment 上：从 `claude-lock.json` 把 vault ID 抄进 deployment 文件 `deployment.md` 的 `vault_ids`。

### 从上次读到的地方继续

一个常见错误是让 agent 读一个固定窗口，比如「过去 24 小时」。晚跑的运行会留出空档，早跑的运行会重复条目。正确的做法是给每个来源一个书签。每轮结束时，agent 把它从每个来源读到的最新条目的时间戳写进书签文件，每个来源一条：`"slack": "2026-09-14T13:02:11Z"`。

下一轮从这些书签起步，窗口随之拉伸或收缩，正好覆盖自上次运行以来的全部内容。书签存放在名为 `state` 的 [memory store](https://platform.claude.com/docs/en/managed-agents/memory) 里：那是一个文本文件夹，平台把它挂载进每轮 sandbox 的 `/mnt/memory/` 下，并在各轮之间保留。agent 用普通文件工具读写它，`agent.md` 里的指令告诉它怎么用。

### 别把失败的读取当成安静的一天

如果某个 MCP server 宕机或它的 token 过期，运行照常启动，只是没有那个 server 的工具。[session 会记录一条错误](https://claude.com/resources/articles/agent-observability-on-the-claude-platform)，但 agent 从那个来源什么都看不到，于是报告「nothing new」。

`agent.md` 里的三条规则修复这个问题。某个来源失败时，agent 会：保持该来源的书签原地不动；用其余来源写简报；并在简报结尾用一行点名它读不了的东西（"pull requests unavailable this run"），让读者知情。

## Destination

我们的模板每次运行都向一个 Slack 频道发一条带日期的帖子。

![Destination 高亮：确认今日简报尚未发出后，agent 发往唯一目的地，简报送达读者](https://claude.dev/media/15481dc4dff01b4a613e8ff36039bc14036ab97781eddeaf749746533b97bd16.png)

agent 用 sandbox 里的 bash 工具发帖，用的是它读取时同一个 bot token。

发帖不需要任何批准。agent 用一条 bash 命令发送，而内置 bash 工具默认不请求批准；`slack.com` 也在 agent 的 [environment](https://platform.claude.com/docs/en/managed-agents/environments)（它运行所在的 sandbox）的允许清单上。发帖就是一条请求：

```
curl -s https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"channel": "C0123456789", "text": "Daily brief, Tue Sep 15 ..."}'
```

### 记录之前先确认帖子送达

帖子确认送达后，agent 才更新已报告条目的 ledger 和书签。这些记录一旦与实际发出的内容不符，会出两种事故：agent 记录了一条从未送达的帖子，书签前移，那些条目从此永远不会被报告；agent 因为不确定第一条帖子是否送达而重发，读者收到同一份简报两遍。

`agent.md` 里的三条规则防止这两种情况。第一，agent 先在频道的近期消息里找今天的标题，这一期已经存在就不再发。第二，只有 Slack 返回 `"ok": true` 和一个 message ts，帖子才算发送成功。第三，agent 在确认之后才更新 ledger 和书签。结果不明时，它把这一轮标记为 "maybe posted"，其余什么都不改，这样什么都不会丢。

agent 在它的 memory store 里保留一份运行记录（`runs/<date>.md`）。发帖前它把这一轮标为 "posting"，成功则标为 "posted" 并附上 message ID，否则标为 "maybe posted"。

## Agent

在 Claude Managed Agents 里，[agent](https://platform.claude.com/docs/en/managed-agents/agent-setup) 是一份带版本的配置：一个 model、一段 system prompt、一组 tools。每轮运行走完它的 run steps 就停止。

![Agent 高亮：model 加一段持有 run loop 与判断规则的 prompt](https://claude.dev/media/8b00d803c6eee8a1c6419c15961f688cba2f6fbff5031e1bd0539725cba1780b.png)

在我们的参考实现里，agent 配置是 `agent.md`：

```
---
name: Daily brief
model: claude-sonnet-5-5
mcp_servers:
  - type: url
    name: github
    url: https://api.githubcopilot.com/mcp/
tools:
  - type: agent_toolset_20260401
    configs:
      - name: web_search
        enabled: false
      - name: web_fetch
        enabled: false
  - type: mcp_toolset
    mcp_server_name: github
    default_config:
      permission_policy:
        type: always_allow
---

[Eight numbered run steps; the full text is in agent.md in the repo.]
```

frontmatter 提供 agent 名称、model、tools 和 MCP servers；正文提供 agent 指令。MCP 工具默认请求批准，而无人值守时没有人批准，所以 GitHub 工具集设为 `always_allow`，GitHub token 用 `read-only`。

### 保持简报简短

`agent.md` 引导 Claude 保持克制：

```
4. Decide. An item earns a line when the reader would act on it today, or it changes a decision they are about to make. When unsure, leave it out. Most days that is a few items, sometimes none. A count ("12 open reviews") is not an item; link the ones that are blocked. An item already in the ledger and still open is carried as one marked line ("still waiting, day 3"), not re-reported; a closed item is dropped without comment. Do not bring back a topic the preferences file has retired.
```

一条条目要配上简报里的一行，条件是读者今天会据此采取行动，或者它会改变读者即将做出的决定。拿不准就不写。大多数日子里就是几条，有时一条都没有。一个计数（"12 open reviews"）算不上条目；把受阻塞的那几条加上链接。已经在 ledger 里且仍然开放的条目，作为一行带标记的内容携带（"still waiting, day 3"），不重新报告；已关闭的条目不加说明直接丢弃。preferences 文件已经不再收录的话题，不要让它复活。

### 发帖前一刻复查仍然开放的一切

从 agent 读取来源到它发帖之间，条目会发生变化。发帖前一刻，`agent.md` 指示 agent 复查每条条目的实时状态：

```
5. Verify. The world moved while you read. For every item you will report, re-check its live source just before posting: resolved since you read it, drop it; still open but changed, fix the line; cannot confirm, drop it and list it in the run record's cuts. One stale "still waiting on you" costs more trust than ten missing items, so never hedge an item's status: assert it or drop it. Every link is copied from the source's own link field (a pull request's html_url, a Slack permalink), never assembled by hand.
```

你读的时候世界在动。对你要报告的每条条目，发帖前一刻复查它的实时来源：读过之后已经解决，丢弃；仍然开放但内容有变，修正那一行；无法确认，丢弃并列入运行记录的 cuts。一条过时的 "still waiting on you" 耗费的信任比十条缺失的条目更多，所以绝不给条目状态加含糊措辞：要么断言它，要么丢弃它。每个链接一律复制自来源自身的 link 字段（pull request 的 html_url、Slack permalink），绝不手工拼装。

## Schedule

在 [Claude Managed Agents](https://claude.com/platform/claude-managed-agents) 里，agent 只是一份配置文件；运行它的是 [deployment](https://platform.claude.com/docs/en/managed-agents/scheduled-deployments)。deployment 指名 agent、environment 和每轮的首条消息，还持有 schedule、vault、memory stores 和 budget。计划每次触发，平台就启动一个全新的 agent [session](https://platform.claude.com/docs/en/managed-agents/sessions)。

![Schedule 高亮：一份定时 deployment，每轮唤醒 agent](https://claude.dev/media/a206f78f34b18dcf7a51bc9bca1acaaf3b68df80ee4034ff521cfbf353af7bc5.png)

在我们的模板里，deployment 写在 `deployment.md`，首条消息就是它的正文：

```
---
name: Daily brief
agent: ./agent.md
environment_id: ./environment.yaml
schedule:
  type: cron
  expression: "32 7 * * 1-5"
  timezone: America/New_York
vault_ids: [vlt_...]   # the vault you create under Sources
resources:
  - path: ./memory_store_preferences.yaml
    access: read_only
    instructions: The reader's preferences. Re-read them every run. Never write here.
  - path: ./memory_store_state.yaml
    access: read_write
    instructions: Your state. 书签, ledger, notes, proposals, and run records.

---

Write today's brief.
The reader's time zone is America/New_York. Work out every date in that zone.

Follow your run steps in order. Today's edition is titled "Daily brief, <weekday> <month> <day>".
```

这条命令按文件里以路径指名的内容创建 deployment，带上 agent、environment 和 memory stores：

```
ant apply deployment.md
```

不想等计划触发，可以用 `ant beta:deployments run --deployment-id <id>` 手动启动一轮，ID 取自 `claude-lock.json`。

### 按你的时区计算日期

一个常见 bug 是 agent 把今天早上叫成「昨天」，因为它按服务器时区算日期。在 `deployment.md` 里，`timezone` 字段决定运行的触发时间，正文第二行告诉 agent 用哪个时区计算日期。

## Memory

每轮运行都在一个全新的 sandbox 里开始，对上一轮毫无记忆。没有记忆，反馈就无法生效。但陈旧的记忆也会迷惑 agent：它会把一条已经解决的条目报成 still waiting，或者因为一条条目「已经报告过」而把它丢掉，哪怕它仍然开放。

![Memory 高亮：state 由 agent 读写，preferences 由读者写、agent 只读](https://claude.dev/media/30e51eab0381bb583fe355fe412162b4e8868643b8d58b2c76c4aa2d0eafea57.png)

我们的模板保留两个 [memory stores](https://platform.claude.com/docs/en/managed-agents/memory)，即挂载在 /mnt/memory/ 下的文件夹（见 Sources）：

- **preferences**（你的，agent 只读）：读哪些频道和仓库、略去什么、长度上限、目的地、何时停止。
- **state**（agent 的，读写）：书签、已报告条目的 ledger、每轮一条的运行记录、它对你 preferences 的修改提议，以及每个来源行为方式的笔记（"returns only the newest 50 items"）。

`ant apply deployment.md` 创建 preferences store，但不创建里面的文件。首次运行之前，用仓库里的 `scripts/seed-preferences.sh` 把你的 preferences.md 写进去。

### 每轮开始时重新读取 preferences

一个常见问题是 preferences 的一份副本被写进 prompt 固定下来，于是你早已改掉的规则还在继续生效。让 agent 每轮重新读文件。如果它读不到文件，就应该停下来并说明，绝不按默认值继续运行。

### 保留已报告条目的台账，报告变化

agent 保留一份 ledger（台账）文件 `ledger.md`，记录它报告过的每个条目，这样简报不会自我重复。每行记录条目的报告时间、来源出处、一个不变的 ID（Slack 消息时间戳或 pull request 编号），以及它的最后已知状态：

```
2026-09-09 slack:C0123456789 1788963600.000100 refund thread: customer waiting on a decision
2026-09-11 github 481 review blocked, day 2 (still waiting)
2026-09-11 slack:C0234567891 1789117333.000300 enterprise escalation: owner named, in progress
```

## Guardrails

我们的自动化在「后台」按计划运行，所以要限制 agent 能做什么、能花多少。

![Guardrails 高亮：环绕 agent 的边界，带轮数、时间与花费上限，加一条有人看着的心跳](https://claude.dev/media/746533f20f4e2bf093d08a04f368a8c5eca739de6579c384e9742b86d5385f50.png)

### 限制它能做什么

agent 读的是别人写的消息和 issue，那些文本可能被解读成指令。要限制 agent 在听从它们之后能做什么。在我们的例子里，GitHub token 和 `preferences` store 是只读的，environment 只能到达允许清单上的 host。一条植入的指令仍然能改变简报的内容，包括借 agent 跨轮保留的笔记这条渠道；它写不了 GitHub，也改不了你的规则。

Slack 是个例外：发帖用的是同一个 token，所以只把 bot 邀请进它需要读或需要发的地方。

### 用真实运行数字设定花费上限

花费上限防止成本失控。从正常一轮成本的 3-5 倍起步，看到真实数字后再收紧。触顶的运行会暂停，不计为失败；所以上限设得过低时，你看到的只是一份安静下来的简报。这个上限就是 `deployment.md` 里的 [`budget`](https://platform.claude.com/docs/en/managed-agents/budgets)。每轮运行拿到全额；达到上限的运行以 `budget_reached` 这个停止原因暂停：

```
budget:
  type: limit
  max_list_cost:
    amount: "500" # a string, in cents: "500" is $5.00
    currency: USD
```

## 上手

我们的参考实现归结为六条规则：

- 每个来源从书签续读，不用固定时间窗口。
- 失败的读取报告为无法读取，绝不报告为安静的一天。
- 发帖前一刻复查每一条条目。
- 帖子只在 Slack 确认后才计为已发送，随后才更新书签和 ledger。
- 每轮重新读取 preferences，读的是 agent 改不了的存储库。
- 只读的地方一律给 agent 只读权限，并给每轮运行设花费上限。

Claude Code 可以带你走完本文的指引。先更新：

```
claude update
```

然后用 claude-api skill：

```
/claude-api managed-agents-onboard https://claude.dev/blog/building-effective-agent-automations/
```

claude-api skill 读这篇文章，提议一套配置，把文件写进你项目的 agents/ 目录，再用 ant apply 创建资源。把它当作起点，按你自己的 sources、destination 和 memory preferences 定制这个 agent。
