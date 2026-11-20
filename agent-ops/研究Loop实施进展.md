# 研究 Loop 实施进展（对照《通用研究迭代Loop实施方案.md》）

> 2026-11-20 静态专项复审：撤回此前“全部完成”的结论。当前是研究账本与部分实验函数，不是已验收的自动研究系统。第 5 节记录本轮证据与待修项。
> 当前范围仅为静态研究：测试集、diff/源码上下文、提示词、探索策略、评测与报告；动态复现、日志预测对比、编译缓存暂不纳入验收。
> 状态按实际能力与证据分别记录。模块存在、单元测试通过、CLI 显示命令名均不等于工作流接通。
> 原则：脚本只做确定性操作（存储/计分/渲染/派发），判断与候选改进由 AI 在任务模板约束内完成；机器门禁决定晋级，模型不能直接改 accepted。

## 0. 全局契约（所有模块共用，先于一切实现）

- 存储：`RESEARCH_LOOP_HOME/<project_id>/state/research.db`（SQLite，WAL），运行文件不入 agent-ops 仓库。
- 事件流：`events(id, ts, kind, data_json)` 只追加；状态可由事件重放（correction 事件修正，不删历史）。
- 摘要：文件/协议摘要统一 sha256；大文件先临时写、校验后原子替换。
- 状态四层分离（方案 9.1）：执行 / 证据 / 实验 / 候选，互不等同，映射规则固定。
- 幂等键：`experiment_id + stage + attempt_id`；outbox 先登记再派发，回执对账。
- 命令一律 argv 数组，不拼接 shell；密钥从环境读，不落库不落日志。
- 模块间禁止循环 import：`core_types` ← `store` ← 其余。

## 1. 任务分解与状态

| # | 任务 | 产出 | 依赖 | 状态 |
|---|---|---|---|---|
| A1 | core_types：摘要/时间/JSON 工具/常量（状态四层枚举） | scripts/research_loop/core_types.py | — | 实现存在，完整验收待复核 |
| A2 | store.py：schema（events/experiments/attempts/metrics/artifacts/decisions/ideas）、tx、事件追加/重放 | scripts/research_loop/store.py | A1 | 实现存在，完整验收待复核 |
| A3 | protocol.py：project.json 加载与校验（方案 3.1 九组契约）、适配器命令执行（argv）、隔离模式 | scripts/research_loop/protocol.py | A1 | 实现存在，完整验收待复核 |
| A4 | loopctl.py 骨架 + init/doctor/status | scripts/loopctl.py | A2,A3 | 实现存在，完整验收待复核 |
| A5 | tests：store 事务/事件重放、protocol 拒绝非法契约 | tests/test_research_*.py | A2,A3 | 实现存在，完整验收待复核 |
| B1 | metrics.py：结果导入、rate/mean 聚合、Wilson 下界（双侧/单侧）、净收益判定 | scripts/research_loop/metrics.py | A1 | 实现存在，完整验收待复核 |
| B2 | report.py：STATUS/CHANGELOG/REPORT(md) + 自包含 HTML（五区、可收起导航） | scripts/research_loop/report.py | A2,B1 | 实现存在，完整验收待复核 |
| B3 | tests：Wilson 数值、121/123>0.98 过线、空分母、重复风险点不重计、渲染可复算 | tests/ | B1,B2 | 实现存在，完整验收待复核 |
| C1 | experiment.py：状态机（baseline→propose→trial→verify→expand→lock-final→final→adopt/rollback）、双批复验、连续两轮无收益换向 | scripts/research_loop/experiment.py | A2,B1 | 实现存在，完整验收待复核 |
| C2 | adapters.py：taskctl 桥（outbox 幂等/对账）、领域适配器加载 | scripts/research_loop/adapters.py | C1 | 实现存在，完整验收待复核 |
| C3 | loopctl：baseline/propose/trial/verify/expand/final/adopt/rollback/tick/resume/pause | scripts/loopctl.py | C1,C2 | 实现存在，完整验收待复核 |
| C4 | tests：状态机规则（同批对照/双批才扩大/换向/done 不晋级/执行失败≠无收益） | tests/ | C1 | 实现存在，完整验收待复核 |
| D1 | evalset.py：manifest 导入、关联组切分、8:2 策略配置、holdout 封存/开封 | scripts/research_loop/evalset.py | A3 | 实现存在，完整验收待复核 |
| D2 | leak.py：禁止源路径扫描、canary 探测、反向读取测试、隔离分级 | scripts/research_loop/leak.py | A3 | 实现存在，完整验收待复核 |
| D3 | tests：关联组不跨 split、封存后开封留痕、隔离不支持→终测 blocked | tests/ | D1,D2 | 实现存在，完整验收待复核 |
| E1 | ideas.py：技术点台账（三类探索轴、tries/wins、状态流转）、来源指纹去重 | scripts/research_loop/ideas.py | A2 | 实现存在，完整验收待复核 |
| E2 | loopctl：idea/explore/child/budget | scripts/loopctl.py | E1,C3 | 实现存在，完整验收待复核 |
| F1 | toy demo：迷你课题端到端真实可跑 | examples/ + 运行记录 | C3,D3 | 实现存在，完整验收待复核 |
| F2 | 报告页面：浏览器截图 + 点击验收（宽/窄、收起、证据链接） | /tmp 截图 | B2 | 实现存在，完整验收待复核 |
| F3 | 文档集成：SKILL 触发入口、README、ANATOMY 注册、CHANGELOG、安装副本同步 | 四文档 | 全部 | 实现存在，完整验收待复核 |
| F4 | 全量门禁：pytest / doccheck / anatomy / agentctl status / pyflakes | — | 全部 | 实现存在，完整验收待复核 |

## 2. 静态接入的输入边界

- 领导的 130/123 数量只是参考案例，不是本系统固定输入，不再以缺少那批 YAML 作为平台未完成的理由。
- 通用课题需要自己的数据 manifest、输入/标签分离、关联组与切分规则、评测接口、指标口径和证据；格式与样本数量可配置。
- 现有 testset_labels.json 是引入归因资料，可用于适配试验，不自动等同静态缺陷检测的正式测试集或人工精标集。
- 平台自身的自动派发、预算、冻结、隔离、few-shot 和结果契约缺口必须由实现补齐，不能转嫁为“等用户给数据”。
- tbase 场景使用近五版留出、训练正负 8:2、未召回问题加权等策略时，需确认版本与关联缺陷组；这些应为适配参数，不写死在通用核心。
- 人工精标需要审阅代码及证据，但系统应先提供待裁决材料、分歧记录和版本更新流程，不能仅提供 precise 字段就算完成。

## 3. 实现期发现的方案偏差与处置

（实现中记录，供方案修订。每条：发现 → 处置。）

1. 发现：engine 事件流与状态表双写不同步会导致报告读不到轮次（截图实证"轮次区空"）。处置：baseline/expand 关键事件与表写入合并到同一 tx_ctx 事务（方案 9.3 原则落地）。
2. 发现：toy demo 评测适配器初版遍历全部用例而非传入 ID——分母泄漏（80 vs 20）。处置：eval_cmd 加 assert 分母==传入用例数；这类错误正是评测适配器最常见的坑，方案 5.1 的分母纪律必须由适配器自检。
3. 发现：store 的 sqlite3 默认 isolation_level 会在 INSERT 后隐式开事务，BEGIN IMMEDIATE 冲突。处置：isolation_level=None（显式事务模式）。
4. 发现：HTML 模板含 CSS 百分号字面量，`%` 格式化报 unsupported format character。处置：模板字面 % 转义（生成器处理）。
5. 发现：adopt 未绑定终测候选（任意 candidate 可借 passed 终测采纳）。处置：adopt 校验 candidate_id==freeze.candidate_id。

## 4. 二轮审计（audit-exp-report 11 条 + 自查 2 条）处置记录

历史阶段曾宣称“全部修复”（提交至 6160aae/7e8d64b/85e0a38+）；下列为当时处置记录，不是当前验收结论。第 5 节的反向复现已推翻“门禁不可绕过”和“全部接线可靠”的说法：

1. 【严重】verify 不传 case_ids_b 直接 TypeError → LoopRuleError 显式要求 + demo 补传。
2. 【严重】expand 不校验双批复验（verify.concluded 无人消费）→ expand 前置 both_pass 检查，门禁不可绕过（demo 实证拦截）。
3. 【严重】fold_state 不消费 round.aborted → abort 死锁 → 加分支（不进 plateau，符合 9.1）。
4. 【高】report._planned_events 读不存在的 experiment_planned → 改读 round.started；start_round 事件补 hypothesis/parent_candidate。
5. 【高】事件契约双重不匹配（kind/payload）静默丢 FP/FN 明细 → 统一 metrics_imported+per_metric。
6. 【高】_net_gain minimize 方向整错 + 双实现漂移 → 委托 metrics.net_gain（唯一口径）；轮内对照剥离 threshold（threshold 是终验门槛，方案 6.2 vs 5.2 分工）。
7. 【中】dev/verify 尝试不落表 → 落 attempts/metrics；_current_best direction 感知+仅采纳；record 孤儿 attempt 修复；abort 改 exec_status。
8. 【中】阶段 C/D/E 16 子命令全部接线（此前 16/16 缺失）。
9. 【低】status-replay 实现重放核对。
10. 【自查】plateau 换向失效（fold_state 不更新）→ 修复+回归测试（同方向第三轮被拒实证）。
11. 【自查】verify 不重叠检查是字符级集合交集 → 事件保留 case_ids 原列表真交集（重叠 1 条即拒实证）。

历史曾列为通过：metrics Wilson/导入校验、store 事务、experiment 阶段顺序、报告口径、原子写、outbox 幂等键。基础函数通过不代表端到端可信；后续仍须按真实业务与故障窗口复验。

## 5. 静态专项复审：未完成，禁止再以单测全绿宣布交付

### 5.1 本轮主审复现（代码未修复）

审计基线为 `cb065ff`。所有复现使用内存数据库或独立临时目录，不操作正式课题、不发通知、不运行动态测试、不调用付费/真实模型。

| 级别 | 当前问题与定位 | 本轮观察到的证据 | 验收要求 |
|---|---|---|---|
| 严重 | loopctl.py `_trial_common` / `_metrics_arg`：parser 生成 candidate_metrics，handler 却读取 metrics_file；trial 还访问未定义 candidate_id | 实际按 --help 填齐 trial 参数，退出码 1，仍提示“需要 --candidate-metrics” | 真正通过 CLI 跑 baseline→trial→verify，不以 --help 或直接调用引擎代替 |
| 严重 | experiment.py `record_dev` / `verify` / `expand` 未绑定同一候选内容 | start_round 登记 candidate-A；record_dev 改成 candidate-B，expand 仍 adopted=True | 候选文件/配置摘要、父版本、数据/Judge摘要和批次必须绑定并校验；字符串 ID 不能替代内容摘要 |
| 严重 | loopctl.py `cmd_final` 无报告时自动填 pass；experiment.py `check_leak` 只看 verdict | 手填 {verdict: pass} 被接受 | 必须有在 reviewer 实际受限身份下生成的隔离/反向读取证据；缺失就 blocked，不接受手工声明为权限证明 |
| 严重 | protocol.py 放行空 final_gate；experiment.py `final_evaluated` 未核对留出组与冻结组 | 空门禁协议校验通过；冻结 holdout-1 后用 different-holdout、空指标和伪输出摘要，得到 passed=True/gates={} | 拒绝空计分规则；核对冻结清单、输入/输出摘要、覆盖率、评测身份和真实计分 |
| 高 | experiment.py `verify` 记录 gate_ok_a/b，但 both_pass 只看净收益 | 设置 dev_recall_min=0.9，两批召回均0.6，仍 both_pass=True，expand可通过 | 需同时满足开发门槛和净收益，并验证两批用例/关联组不重叠 |
| 高 | protocol.py 校验过浅，store.py 未启用外键 | project_id=../escape、primary_metric=None、max_rounds=-1均未被协议拒绝；PRAGMA foreign_keys=0 | 严格类型、有限数值、路径归属/ID与预算检查；迁移前检查旧数据，外键与父子引用一致 |

这些反向复现说明现有测试遗漏实际 CLI 与信任边界。测试通过与上述问题同时成立，不能互相抵消。

### 5.2 静态需求覆盖现状

- 已有基础：比例统计/Wilson函数、关联组与加权采样工具、来源idea表、事件表、部分状态机和Markdown/HTML报告生成。
- 自动研究未接通：tick目前只有reconcile；baseline/trial导入人工给定指标，不自动派发静态审查、判卷、选下一方向和采纳/恢复产物。
- 子Loop与预算未形成执行约束：child写关联事件，budget显示计数；尚不能证明共享预算、递归限制、策略试验、自动停止。
- 数据质量未形成完整工作流：有等级/切分字段，不等于缺陷引入→静态用例→rubric→独立裁决→版本更新→历史回归已经实现。
- 提示词需要复验：模板存在不代表提供了few-shot、对照脚本与静态源码证据，也不代表模板真正注入执行任务。
- changelog需要逐环校验：必须记录全部尝试（含无收益/失败）、真实FN/FP与漏因分桶、候选与数据版本、耗时/成本及证据；生成一个MD不等于这些数据已接通。
- toy-demo只能证明人工指定关键词候选的部分函数/计分路径；它手填隔离pass与封存示例，不能证明标签隔离、模型自主研究或真实源码审查。
- 本轮不要求动态日志对比、运行复现或编译缓存。静态的源码/祖先上下文导出、工具接入、泄漏防护仍属于需要验证的范围。

### 5.3 测试记录与后续修复次序

本轮在原代码上运行 `python3 -m pytest tests/ -q`：172 passed、2个已显示的采样警告；doccheck与anatomy_check通过。新增反向复现未进入该测试集，故“172绿”不证明本轮发现已修好。没有重跑toy-demo冒充新证据，也没有使用正式留出集调参。

优先级：
1. 先封堵假通过：缺隔离/空门禁/错候选/错留出组全部拒绝；不要为让演示过关降低判据。
2. 修实际CLI参数和统一结果契约，在独立目录用CLI跑完整的正路与违规反路。
3. 接通静态输入准备、few-shot、模型/工具审查、固定Judge、源码证据和逐点计分；失败原始输出保留，不降级计成功。
4. 接通outbox真实对账、pause/resume、预算/子Loop、换向策略，加入崩溃和重复回执测试。
5. 接通用例/rubric生成、精粗标独立裁决、数据版本演进、回归与报告明细，再做真实静态课题验收。

### 5.4 两路独立审计最终结果

两位只读审计员各返回 6 项，分别核验静态门禁与需求覆盖；以下是新增/补强结论。双方未改文件、未调用模型。gate审计员另运行了纯内存SQLite反例，不等于领域评测。

| 问题 | 当前代码证据 | 修复验收必须补什么 |
|---|---|---|
| 真taskctl桥接口不兼容 | adapters.py 110-113传add --experiment-id/--stage/--attempt-id/--prompt-file；taskctl.py 1131-1145不支持；reconcile用list --json，真实list也不支持。假taskctl测试忽略参数一律回task-123 | 用真实taskctl解析/调用路径测桥接，再做已受理但回执丢失的对账；禁止回查失败就盲重派 |
| report仍丢导入明细 | loopctl.py 135-139写per_metric[mid]为list；report.py 246-255仅收dict，有列表就跳过且不走表兜底；tests/test_research_report.py只造dict | 实际CLI record→report，核对每条的TP/FP/FN/unknown、分子分母及分桶，不为迎合测试改掉原输入 |
| B批和同批对照缺席报告 | verify写attempt+事件但未存metrics；record_dev仅存候选汇总；当前最佳取beneficial/untested尝试极值，而不是真实incumbent | 从真实baseline/A/B/expand路径渲染，展示每阶段baseline-vs-candidate、净增和证据；最佳必须与引擎状态一致 |
| 不重叠不等于独立 | 引擎不查manifest、关联组、split、用例有效性和批大小；sample_dev_batch仅exclude case_id；B批清单未落verify事件 | 两条同group不能分A/B；未知ID、重复ID、invalid、过小批次必须拒绝；清单及摘要落盘 |
| 正规limited报告也被终测接受 | leak.accepts_final只收full，但engine只看verdict；真实scan/probe产生limited/pass（禁止文件仍可读）也能推进final | 在真实reviewer身份下生成receipt，full模式才可终验；limited结果不能变成通过 |
| 冻结生命周期与预算失效 | seal可覆盖；终测不核对seal/open事件；重新加载改过data/Judge/final_gate的project仍可终测；max_rounds无执行检查 | 冻结内容摘要及开封状态，重载变更必须阻断；达到预算必须停；原seal不可覆写 |
| rollback后仍无法恢复探索 | fold_state不处理candidate.rolled_back/adopted，而start_round见freeze就拒绝；按提示rollback后新一轮仍被卡住 | 真实final失败→rollback→重建进程→新留出/新轮的恢复测试；保留旧组暴露记录，不得重伪装盲测 |
| few-shot/生成与三轴仍只是入口 | research-implement模板写few-shot“如有”；没有训练侧示例装配/泄漏检查；ideas只登记人工idea，没有静态用例/rubric生成及独立标注链 | 按用户要求few-shot必需，训练侧可证来源；三轴各有真实artifact和验证；从引入diff生成用例与rubric再独立审阅 |
| changelog成本与子Loop证据缺失 | 报告未消费完整diff/候选摘要、真实成本和子Loop结果；child只写关联事件，预算只显示计数 | 真实父子执行与回执、继承预算、复现argv、来源和耗时可关联；未知费用明确unknown |

### 5.5 最终补充：full隔离假阳性与未知派单状态

- 严重，目录隔离假阳性：leak.py的反向读取使用open(禁止目录)，触发IsADirectoryError便记为不可读；这不是PermissionError，更不是其子文件不可读。主审只读复核：workspace=scripts/research_loop、deny=tests，真实scan+probe返回full/pass且accepts_final=True，禁止目录下test_research_experiment.py仍可读。必须探测目录可遍历性/代表性文件、区分错误类型，并在真正reviewer身份中测试；当前连full标记也不可信。
- 高，未知派单状态错误解锁：adapters.py reconcile回查异常把dispatching改pending，没有确认任务不存在；下一次恢复可能重复派同一attempt。应保留needs_reconcile，只有确证未受理才允许重派，用真实队列接口和故障注入验收，不能用无视参数的假taskctl证明幂等。
- few-shot、静态用例/rubric生成、A/B批与同批基线明细、来源/diff/失败证据及FN分桶的缺口已由第二路最终收敛报告再次确认；这是实际执行/数据消费链未完成，不是补几句提示词即可修复。

复审结论：目前是“研究状态机/计分台账/报告原型 + 待接的执行适配器”，不是用户要求的静态研究自动循环。上述为本轮可确认的问题，不是“全部缺陷已枚举”，也不是已修复清单。

状态：本轮审计与文档更正已完成，代码问题尚未修复。不要再写“所有问题清零”“只缺用户的130条YAML”或“平台全部交付”。
