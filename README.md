# agent-skills

**让 AI 智能体真正干活的技能包。**

一组遵循 `SKILL.md` 规范的 Agent 技能，适用于 Claude Code、Codex、CodeBuddy、Cursor 等命令行智能体。它们连起来是一条完整的能力链：**编排**（一个智能体调度一群子智能体干长任务）→ **工程**（一套从真实故障里长出来的 Agent 基建指南与原语库）→ **表达**（写作、配图、界面设计、技能维护的工艺纪律）→ **领域**（把纪律落到真金白银上的个人投资中枢）。

## 为什么有这个仓库

技能包最不缺的就是提示词。缺的是两样东西：**跑过真实任务的证据**，和**边界写清楚的判据**。

这里的每条规则都付过学费。源头是五个真实 agent 工程——批量任务流水线、迭代调优内核、经验中台、上游修复流水线、多智能体验证集群——在同一批问题上反复踩坑后收敛出来的做法：模型会超时、进程会卡死、磁盘会写满、输出会变形、人要在一半时改配置。

三条原则贯穿全部技能：

- **小而准**——一个技能解决一类失败模式，判据可查、边界写明，不写正确的废话。
- **可组合**——职责分明：谁管调度、谁管文字、谁管配图、谁管纪律，靠触发词自动路由，互不越权。
- **有证据**——关键机制带回归测试、故障注入或生产运行记录；没验证过的事，这里不吹。

## 技能总览

| 层 | 技能 | 一句话 |
|---|---|---|
| 编排 | [agent-ops](agent-ops/SKILL.md) | 单机 multi-agent harness：一句话派活，AI 管理者替你盯、纠正、推进 |
| 工程 | [agent_foundation](agent_foundation/README.md) | 72 篇公开资料 + 22 章工程指南 + 37 个零依赖原语模块 |
| 表达 | [human-voice](human-voice/SKILL.md) | 中文文本的人味增强与 AI 痕迹清理 |
| 表达 | [article-illustration](article-illustration/SKILL.md) | 文章配图：判定插图位、先找现成图再自绘、密度评估 |
| 界面 | [design-craft](design-craft/SKILL.md) | 界面设计规矩：层级、排版、间距、语义色、交互五态、评审门禁 |
| 元技能 | [skill-craft](skill-craft/SKILL.md) | 技能本身的工程：规则归并、抽象判据、独立评审、篇幅预算 |
| 领域 | [stock-guardian](stock-guardian/SKILL.md) | 个人持仓监控与纪律执行：档案化、双层警报、定时简报、做 T 功课制 |

---

## agent-ops · 多智能体编排与运维

> 你说一句目标，一群 CLI 子智能体去干活；一个 AI 管理者替你盯着、纠正、推进，甚至在发现新方向时调整任务目标。断了自动续，卡了自动管，全程可追溯——你只在真正需要拍板时出现。

它不是框架，不装服务，不用 Docker——**纯 Python 标准库 + 一份 SQLite 文件**，拷进技能目录就能用。

| 能力 | 说明 | 实测 |
|---|---|---|
| SQLite 任务队列 | 任务 = 数据库行，不是进程；原子抢占（`BEGIN IMMEDIATE`）、租约、惰性目录 | 10 万行插入 0.7s；取任务 **0.09ms** |
| 一句话派活 | `add --goal` / `plan --goal` 自动拆任务，提示词模板渲染 | 一句话拆出 3 个带交付物的任务 |
| 管理者 | AI 读全部进度，纠正/推进/**微调目标**，每条决策写 `decisions.jsonl` | 真实识别「重复报错死循环」并给出换策略指令 |
| 断点恢复 | 进度落盘 + 压缩留痕 + 失败原因回灌，重试带上下文 | 跑一半杀掉 → 新会话从断点继续 |
| 假死感知 | 输出文件长时间无增长 ≠ 立刻杀——标记后由管理者模型判断 | 误杀率 0（推理阶段不误判） |
| 死士巡检 | 健康检查的健康检查：进程/数据库/产出/队列/日志/通知链路 | 生产 cron 长期运行，误报实战修复 |
| 主动挂起 | `suspend` 腾出资源，`resume` 从断点回来，不耗重试次数 | 挂起期间不参与调度 |
| 限流自适应 | 区分带恢复时间的 429 与不限时的 429；后者走 AIMD 降并发 + 指数静默 | 假绿灯（exit 0 但输出是错误串）故障注入被拦截 |

架构与 [google/ax](https://github.com/google/ax)（Google 的 agent 编排运行时）同构：状态进数据库、轮询调度、任务不可变、原文留盘。它是集群级，本技能是单人可维护的单机形态，外加一个会写决策日志的管理者。9 个开源 harness 的横向对照研究见 [harness-lessons.md](agent-ops/harness-lessons.md)。

**5 分钟上手**

```bash
T=agent-ops/scripts/taskctl.py

python3 $T plan --goal "审查这个代码库：构建、测试覆盖、安全" --repo /data/project
python3 $T daemon --concurrency 2 --interval 30 &              # 无人值守调度
python3 agent-ops/scripts/manager.py daemon --interval 300 &   # 管理者上线
python3 agent-ops/scripts/deadman.py --config <配置>            # 死士巡检

python3 $T stats                 # 全部任务，每行一个
python3 $T brief <任务名>         # 结果摘要（5 个字段）
python3 $T history <任务名>       # 全史：做了什么、为什么、管理者怎么判断的
```

队列、监督、留痕本身零依赖；真正执行子任务的 CLI 智能体与模型通道可配置。回归测试：`python3 -m pytest agent-ops/tests/ -q`。

---

## agent_foundation · Agent 工程的地基

> 一本书、一套代码、一道红线。

四件东西打包在一起：

- **知识库**：`docs/` 里 72 篇公开工程文档的结构化整理——Anthropic、OpenAI、Google、DeepSeek 关于 agent 设计、上下文工程、工具调用、评测、沙箱、记忆的一手材料，按主题归位，不是链接堆。
- **工程指南**：`GUIDE.md` 共 22 章，按 agent 的一次完整生命周期排列——跑起来、听懂输出、断线续跑、判断失败、管住资源、组织并发、对外通信、形成记忆、设计工具、管好上下文、留下证据、干净收尾、放行发布、知道自己做得好不好。每条机制背后至少有一次真实故障；第 18 章是速查表，第 19 章是反模式清单，照症状反查。
- **原语库**：`src/agent_foundation/` 37 个模块，零运行时依赖，每个可独立取用——会话与断点（`snapshot`、`recovery`）、幂等与账本（`idempotency`、`campaign`、`convoy`）、预算与磁盘护栏（`budget`、`disk_budget`）、风控闸门（`risk_gate`、`admission`）、谱系与证据（`lineage`、`evidence`、`execution_receipt`）、记忆与经验（`memory`、`experience`）、对外通信（`webhook`、`notify_cadence`）。
- **开源隐私闸门**：`tests/test_privacy.py` 对包内任何文件零容忍内部路径、内网域名、内部模型代号和密钥。这道纪律本身也是从真实学费里抽象出来的通用能力。

```bash
cd agent_foundation && pip install -e . && python3 -m pytest tests/ -q
```

总纲一句话：**agent 的可靠性来自「假设一切会断」的设计立场。** 详见 [GUIDE.md](agent_foundation/GUIDE.md)。

---

## human-voice · 中文文本的人味

去 AI 味不是一个目标，是一层手法。这个技能做两件事：给出「模型组织答案时留下的结构痕迹」的识别清单与修法（路标词、三段式排比、模糊归因、翻译腔、讲义腔），并规定这些手法在各文体里的适用范围，防止手法反过来覆盖任务目的。

裁决顺序写死在技能里：事实与归属 > 任务目的 > 原意保真 > 人味。冲突时放弃手法。附 `scripts/scan_ai_flavor.py` 做批量体检。

## article-illustration · 文章配图

图为理解服务，回答不了问题的图一律不加。流程三步：定位插图位（抽象结构、并发时序、状态变迁、数据流向、多维权衡五类）、先找现成图、找不到再自绘。包含配图密度评估、图源许可核验、批量选文台账与并发锁，避免多会话同时改同一篇。

## design-craft · 界面设计规矩

先定位核心资产、再排改动顺序。覆盖视觉层级、排版尺度、间距栅格、语义色 token、交互五态、信息密度、文案语气、中文素材检索与许可核验，以及可执行的评审门禁脚本（`quality_gate.py`、`skill_check.py`）。

## skill-craft · 技能工程的元技能

整个包共用的方法层：一条经验该不该写进技能、怎么抽象才不是把个案当规律、怎么证明改动没膨胀也没丢能力、怎么做独立评审与多模型对抗。写技能之前先读它。

## stock-guardian · 个人投资纪律中枢

适配任意用户的持仓监控与纪律执行技能。行情双源：优先结构化行情工具，缺失时自动降级公开源（零密钥零账号），A 股/港股/美股开箱即用。

- **档案化**：持仓、成本、规则线（跌破哪卖/涨到哪减/哪天必须动）、监控宇宙、沟通偏好，全部落盘在 `$HOME/.stock-guardian/`，仓库内零用户数据。
- **监控宇宙推理**：按持仓自动推理该盯哪些海外标的（产业链/同行/汇率/ETF 成分），每条写明「为什么盯它」。
- **定时简报矩阵**：早报、午间、尾盘、美股三段、亚太早巡；无触发一句话报平安。
- **双层警报**：静态规则线（配置自检防漂移）+ 当日动态箱体（突破/跌破自动生成「该怎么办」并原样推送）。
- **做 T 功课制**：盘前三问定档 → 箱体确认出四件套（参考价/份数/时间窗/作废线）→ 尾盘落账 → 周五复盘；急跌日有盘中企稳判据解除停令；仓位爬坡管理（连赢升级、连亏降档）。
- **跨场景档案**：每个定时任务都是独立会话，day file 让 10 点画的箱体 11:45 还在、尾盘接得住早盘方案。
- **通知四渠道**：企微/钉钉/飞书群机器人、Bark 推送，按 URL 特征自动选消息格式。

初始化三步：依赖预检 `bash scripts/check-deps.sh` → 拷模板建档案 → 和 AI 说「我要用股票管家」。详见 [stock-guardian/README.md](stock-guardian/README.md)。

---

## 安装

```bash
git clone https://github.com/hub138/agent-skills.git
```

<details>
<summary><strong>Claude Code</strong></summary>

```bash
cp -r agent-skills/agent-ops agent-skills/agent_foundation agent-skills/human-voice \
      agent-skills/article-illustration agent-skills/design-craft agent-skills/skill-craft \
      agent-skills/stock-guardian ~/.claude/skills/
```

</details>

<details>
<summary><strong>CodeBuddy</strong></summary>

```bash
cp -r agent-skills/<skill-name> ~/.codebuddy/skills/
```

</details>

<details>
<summary><strong>Codex / Cursor / 其他智能体</strong></summary>

放到各家的 skills 目录（`~/.codex/skills`、`~/.cursor/skills` 或项目内 `.claude/skills`）。只装需要的技能即可——它们彼此独立，不存在隐式依赖。

</details>

依赖：核心脚本 Python 3.10+，`agent-ops` 与 `agent_foundation` 零第三方依赖；`stock-guardian` 的行情工具可选 Node.js ≥ 18，缺失时自动降级纯 bash 方案。装好后直接用触发词调用，不需要写配置。

## 目录约定

```
<skill>/
  SKILL.md        # 入口指令：触发条件、工作流、红线
  references/     # 方法手册：判据、模式表、清单
  scripts/        # 质量门与工具脚本
  tests/          # 回归测试（pytest / node --test，全部 mock 不烧额度）
```

## 质量与边界

- **agent-ops**：队列、管理者、死士三套回归测试；原子抢占、租约、幂等、退避、保序、断点恢复、假死判定、压缩留痕全部有单测或故障注入证据；健康巡检在生产 cron 长期运行。
- **agent_foundation**：14 个测试文件覆盖原语库；`test_privacy.py` 是开源资格闸门，内部痕迹零容忍。
- **stock-guardian**：12 个 node 测试覆盖状态机、出场闸门、警报同步；用户数据与代码彻底隔离。
- **诚实标注边界**：十万任务的月级长跑、多机共享（需换 PostgreSQL）未验证——这里只声明测过的。
- 模型与限流相关说明只描述**机制与实测方法**，不绑定任何平台的具体配额。

## 设计参考

agent-ops 与 agent_foundation 的设计经过 9 个开源 harness 的横向对照研究（全部 clone 研读，结论见 [harness-lessons.md](agent-ops/harness-lessons.md) 与 [dsh-lessons.md](agent-ops/dsh-lessons.md)）：

- [google/ax](https://github.com/google/ax) —— PostgreSQL 资源存储 + 分布式锁 + 轮询调度（与本仓库 SQLite + lease 同构）；任务级挂起/恢复检查点
- [agent-substrate/substrate](https://github.com/agent-substrate/substrate) —— actor→worker 映射、快照恢复（K8s 基建模式，单机不采纳）
- [bytedance/deer-flow](https://github.com/bytedance/deer-flow) —— 「压缩是破坏性设计」，压缩事件必须留痕
- [chaitanyagiri/munder-difflin](https://github.com/chaitanyagiri/munder-difflin) —— markdown-first 记忆：无损原文留盘，只压缩副本
- [PrimeIntellect-ai/prime-agent](https://github.com/PrimeIntellect-ai/prime-agent) —— 压缩阈值参数化与校验
- [truefoundry/trueforge](https://github.com/truefoundry/trueforge) —— agent 运行时层抽象、git 驱动技能包
- [AMD-AGI/PrimusClaw](https://github.com/AMD-AGI/PrimusClaw) —— per-session 沙箱 + 消息队列（单机不采纳）
- [HKUDS/OpenHarness](https://github.com/HKUDS/OpenHarness) —— session 存储与运行时解耦
- [AMAP-ML/LongHorizon-Harness](https://github.com/AMAP-ML/LongHorizon-Harness) —— 每轮独立验证再推进

## 新增技能

1. 技能目录（`SKILL.md` + `references/` + `scripts/` + `tests/`）拷到仓库根目录；
2. 在「技能总览」表里加一行：链接到 `SKILL.md`，一句话写清解决哪类失败模式；
3. 自查无内部路径、密钥、临时产物（`__pycache__`、`.work/` 等），跑一遍该技能自带的测试；
4. `git add <skill-name>/ README.md && git commit -m "Add <skill-name> skill" && git push`。

编写与评审规范见 [skill-craft](skill-craft/SKILL.md)。

## License

[MIT](LICENSE)
