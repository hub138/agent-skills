# stock-guardian 加强手册（给下一个来维护/加强的 AI）

本 skill 的定位：帮一位投资小白用户抹平与专业操盘手的差距。用户不懂 K 线，你是内行；用户情绪冲动（清仓后反弹即归咎 AI、连错后想 allin），你是纪律。你的出口不是"建议"，是指令。

## 一、绝对路径

| 用途 | 路径 |
|---|---|
| skill 根目录 | `/root/.agent/skills/stock-guardian` |
| 主文件（工作流+输出铁律） | `/root/.agent/skills/stock-guardian/SKILL.md` |
| 规则主体（27 节纪律体系） | `/root/.agent/skills/stock-guardian/references/rules.md` |
| 定时任务配方（12 任务模板） | `/root/.agent/skills/stock-guardian/references/cron-recipe.md` |
| 持仓档案模板（用户数据落这里，绝不进 skill） | `/root/.agent/skills/stock-guardian/references/portfolio.template.md` |
| 票性仪表盘（统计画像脚本） | `/root/.agent/skills/stock-guardian/scripts/stock-behavior.js` |
| 分钟级看门狗 | `/root/.agent/skills/stock-guardian/scripts/watch.sh` |
| 行情拉取 | `/root/.agent/skills/stock-guardian/scripts/monitor.sh` / `quote-public.sh` |
| 企微群推送 | `/root/.agent/skills/stock-guardian/scripts/notify-webhook.sh` |
| 当日档案落档 | `$HOME/.stock-guardian/day/YYYY-MM-DD.md`（经 `day-log.sh`；`/root/.stock-guardian/` 是 root 用户的 $HOME 实例，非 root 机器上以 $HOME 为准，可用 PORTFOLIO 环境变量覆盖档案位置） |
| 用户真实档案（私有，不在 skill 内） | `$HOME/.stock-guardian/portfolio.md`（同上，$HOME 口径 + PORTFOLIO 覆盖） |
| 发布脚本 | `/root/.agent/skills/skill-creator-for-knot/scripts/publish_skill.py` |

## 二、这个 skill 是怎么变成现在这样的（批评→规则映射）

演进方式：用户在实践中暴露真实痛点 → 批评或亏损 → 转化为结构性规则。以下映射表是骨架，改动前先对照，避免推翻已有共识：

| 用户的原话/痛点 | 落地的规则 |
|---|---|
| "我要 allin 你不拦，我要你有个屁用" | 立场与放行纪律：三档放行（计划内自主批/计划外改造/超限直接说不行），错拦成本记账 |
| "你不要拿 skill 说事，skill 规则也是你给的" | 判断基于"最高可能和最大事实"，不盲信单一指标；规则线只是画线日快照 |
| "规则是死的，应该大模型每次给" | 动态重估协议：八条触发条件，命中即从零重估，判据四件套（数字+口径+依据+保鲜期，量能类 2 交易日） |
| "成熟玩家优先做T而不是减仓" | T 优先原则 + 全跌日反T特权 + 四类例外（证伪/无条件线/财报周/系统性急跌） |
| "这票是抗跌的好票你让我卖？"（用户原话已泛化，真实票名属档案数据） | 票性画像体系：逆势强势/抗跌/顺周期β/补跌四类，强票全跌日持有是特权；画像数字必须出自 stock-behavior.js |
| "通知看不懂、技术和操作混在一起" | 通知三层结构（怎么做≤50字→为什么≤30字→凭什么证据收尾）+ 四分支预案 + 字数硬上限（300/150/50） |
| "我不知道大盘什么样" | 九维清单第零维：大盘全天走势+与上午结构对照，个股动作必答"为什么这不是顺势裸奔" |
| "半导体100次高开99次低走" | 仪表盘统计（高开低走率/周五表现/放量跟涨率），样本不足 8 禁引用 |
| "周五隔着周末呢" | 周五协议：注码减半管新仓不管存量、14:30 后只先卖后买、周一双分支预案 |
| "我说啥才加啥，窟窿补不完" | 反补丁模式：每次大改版前用外部框架自顶向下扫描（见下） |
| "你是内行自己专业起来" | 情绪周期四档、供给冲击四事件、竞价预读、赔率先行、证伪优先、规则冲突裁决表、月度归因、机会成本排序 |

## 三、自顶向下审计方法论（反补丁模式的核心）

不要等用户批评再补。每次大改版前，拿完整框架对照现状扫缺口：

1. 框架：四大模块——市场认知 / 交易策略 / 风控资金 / 执行复盘，逐模块问"这一块还有什么没建模"。
2. 首扫成果（2026-10-16）：组合总风险敞口上限、账户级熔断+连亏降档、牛/基/熊三情景预演+宏观日历 T-1 冻结、五种行为共性监控。
3. 每个候选新规则过三道门：与现有体系冲突吗（查规则冲突裁决表）→ 是否固化用户数据（脱敏铁律）→ 是否预设偏向话术（如"拿住别乱动"这种没分析先给动作的）。**三道门的判定结果落进 day file**（采纳/未采纳+理由），未采纳的候选进本手册第八节排除清单，防止后来者重复提出、重复吵。

## 四、外部搜索方法

验证想法或找新维度时的搜索姿势：

1. 中文：`专业交易员 交易系统 框架 仓位管理 风控体系`、`做T 底仓滚动 T+0技巧`、`周五效应 A股 周末风险`、`情绪周期 连板梯队 冰点 退潮`。
2. 英文：`retail trader complete trading system components market regime risk management`、`position sizing consecutive losses circuit breaker`。
3. 筛选原则：先找多来源共识（熔断、注码梯度、日志复盘是共识度最高的三项），再逐条对照自己体系——**冲突的外部方法不盲加**。已毙案例：周五持币过节共识（与 T 优先+票性特权冲突）、网格/金字塔加仓（与 T 体系重复且冲突）、凯利公式（用户样本不足）、北向/两融（噪音大于信号）。
4. 搜索结论必须带出处落进 day file，"盘感推断"不许包装成事实。

## 五、加强时的操作规程（改→验→发→同步）

1. 改前通读 `rules.md` 相关节 + 规则冲突裁决表，新节插入注意锚点（用 grep 定位章节标题）。
2. 逻辑层铁律：**零用户数据**——真实票名、价位、金额、份数、券商名、用户原话里的持仓信息一律不进 skill 目录；数字只进 `/root/.stock-guardian/portfolio.md`。改完必须按**档案实时内容**构建关键词表跑脱敏扫描（扫描前先读一遍 portfolio.md，把其中每个票名、代码、券商名、全部价位数字、金额、份数收进词表），可复跑命令模板：`grep -rnE "<票名1>|<票名2>|<代码>|<券商名>|<价位>|<金额>|<份数>" /root/.agent/skills/stock-guardian/`——**词表取自档案而非固定清单**，档案换了票这条自动跟着变；零命中才算过，命中即改写为泛化表述（某强势票/某加仓带/某亏损题材股），教训结构保留。历史教训：固定词表两次漏扫（第一次漏票名、第二次漏价位带），根因都是没从档案现提词表。
3. 验证：`bash -n scripts/*.sh`、`node --check scripts/stock-behavior.js`、`check-sync.sh`（核对 watch.conf 每条警报线价格是否与 portfolio.md 同源，输出 OK/DRIFT）。
4. 发布 Knot 市场：`python3 /root/.agent/skills/skill-creator-for-knot/scripts/publish_skill.py --skill-id 78595 --change-message "<一句话>" /root/.agent/skills/stock-guardian`（凭据走 KNOT_JWT_TOKEN/KNOT_USERNAME 环境变量，勿手写 curl）。
5. GitHub 同步：先改本机版验证通过，再把 skill 全量拷贝到 `/data/code/agent-skills/stock-guardian/`（hub138/agent-skills 仓库，main 分支）commit + push。**同步前脱敏**：本手册与本目录内出现的内部平台路径（skill-creator-for-knot）、环境变量名（KNOT_JWT_TOKEN）、市场 ID（78595）不进公开版，公开版读者没有这些内部环境。
6. 线上同步：改了 `cron-recipe.md` 模板后，必须把对应线上 cron 任务的 jobMessage 同步更新，否则下次按配方重建会静默丢单条。
7. 落档：day file 记录改了什么+为什么；重大方法论变化写入长期记忆。

## 六、历史 badcase（别再犯）

- 用户喊 allin 时用"风险自负"话术放行（某亏损题材股高位追入被套的真凶就是没拦，票名与金额属档案数据，此处只留教训）。
- 拿四天前的"2 亿量能"口径卡当日突破（判据过保鲜期）。
- 周四全跌日让用户卖逆势强势票（卖飞某强势票，票名属档案数据）。
- 定案只盯个股没看大盘已在日内新低（九维第零维的由来）。
- 建议当成交记录（AI 建议减仓被记成用户已卖），建议与成交必须分开记。
- 通知里"详见 rules.md"指路话术——用户在手机上看不到你的文件，通知必须自含全部可执行信息。

## 七、已审未采纳排除清单（三道门拦下的，别重复提出）

本节与第四节已毙案例（外部搜索类）互补：那里毙的是外部方法，这里毙的是内部审计候选。每条写结论与理由，后来者提出同类候选前先查本节：

- **多账户资金调度**（2026-10-16 审计）：用户单账户形态，为不存在的场景建模是过度设计；出现多账户需求时再建。
- **信息源分级**（2026-10-16 审计）：行情数据已由 westock-data 优先 + qt.gtimg.cn 降级兜底覆盖，再建分级层重复且无新信息。
- **全票两两相关性矩阵**（2026-10-16 审计）：监控宇宙内票数多时矩阵计算重、维护成本高；已有"同向天数占比>80% 或 同行业/同映射链"双重判据覆盖组合风险识别，矩阵属杀鸡用牛刀，不建。
