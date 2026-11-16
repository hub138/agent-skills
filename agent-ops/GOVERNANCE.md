# 开发规范（GOVERNANCE）

> **这份文件回答一个问题：任何人或 AI 改这个 skill 时，怎么改才不算把别人的工作改坏。**
> 结构与影响面看 `ANATOMY.md`；踩过的坑看 `FIELD-NOTES.md`；对外承诺看 `SKILL.md`。
>
> 适用：本 skill 的全部目录，包括雷达子功能（`radar/`）与所有脚本、模板、测试。

---

## 1. 单一权威源（改之前先确认你改的是不是权威）

| 信息 | 唯一权威源 | 派生 / 镜像 | 禁止 |
|---|---|---|---|
| 触发词、给 AI 的操作手册 | `SKILL.md` | 4 个安装副本、公开版 | 在 README 另写一套用法 |
| 对外一句话介绍、能力表 | `README.md` | — | 与 SKILL.md 承诺的能力不一致 |
| 目录职责、数据流、影响面 | `ANATOMY.md` | — | 在别处复制目录树导致漂移 |
| 变更流程、门禁、留痕格式 | 本文件 | — | 口头约定代替门禁 |
| 模型可用清单与红线 | `scripts/model_policy.py` | `model-catalog.md`、`SKILL.md` | 在脚本里再写一份 `ALLOWED_MODELS` |
| 平台进程/二进制探测 | `scripts/platform_util.py` | — | 直接读 `/proc/<pid>` 或写死 `/usr/local/bin` |
| 实战坑 | `FIELD-NOTES.md` | — | 改旧条目（只增不改，编号连续） |
| 变更历史 | `CHANGELOG.md` | 雷达 `radar/LEDGER.md` | 只在 commit message 里写、不进台账 |
| 雷达候选与结论 | `radar/state/radar.db`（索引） | `radar/LEDGER.md`（渲染） | 手改 LEDGER |
| 雷达分析正文 | `radar/analyses/`、`radar/applied/` | — | 只入数据库、不落 md |
| 公开脱敏版 | `scripts/desensitize.py` 的产物 | `agent-skills/agent-ops/` | 手改公开版 |

**判断口诀**：同一事实出现两处，先问「哪一处被代码或门禁读取」。被读取的那处是权威，另一处必须改成指针或由脚本生成。

---

## 2. 变更分级（先定级，再决定要跑多少门禁）

| 级别 | 典型改动 | 必需动作 |
|---|---|---|
| **P0 文案** | 错别字、补一句解释、改示例 | `doccheck.py` |
| **P1 行为** | 改一个脚本分支、加一个参数、修一个 bug | 失败测试 → 修复 → `pytest` + `doccheck` + 真业务路径冒烟 |
| **P2 机制** | 新子命令、新模块、DB 加列、新模板 | P1 + 更新 `ANATOMY.md`/`SKILL.md` 导航 + `CHANGELOG.md` + 雷达留痕（若来自雷达） |
| **P3 接口** | 改 SKILL.md 触发词、CLI 破坏性变更、装法变更 | P2 + 兼容层（旧调用仍可用）+ 4 个安装副本同步 + 公开版重新生成 |

**判定「是不是 P3」的依据**：外部（cron、其他 skill、你的自动化）是否按名字调用了你改的东西。查法见 `ANATOMY.md` 第 7 节。

---

## 3. 变更流程（八步，缺一步就不算完成）

1. **认领**：`git status --short`。多会话同时改同一仓库时，按文件划分归属；夹带别人的改动必须在提交说明里写明。
2. **定位**：读 `ANATOMY.md` 的「影响矩阵」，找到你要改的文件属于哪一层、下游是谁。
3. **查重**：在 `FIELD-NOTES.md` 搜关键词。这个坑以前踩过吗？踩过就直接用当时的修法，不要重新发明。
4. **设计**：默认最小改动——优先改一个文件、不引入新依赖、不动调度/租约语义。需要动核心语义时，先写失败测试把现状钉死。
5. **实现**：精确字符串替换，不用 `[\s\S]*?` 跨函数贪婪匹配（第 33 条事故：正则吞掉 8 个函数，测试仍全绿）。改脚本后核对顶层函数集合。
6. **门禁**：第 4 节四条命令全过。**pytest 全绿不等于 CLI 可用**：`--help` 由 argparse 提前返回，不执行业务分支，必须跑真业务路径。
7. **留痕**：`CHANGELOG.md` 记「改了什么/为什么/门禁结果/回滚方式」；若改动来自雷达候选，再用 `radar_cli.py applied` 入账并链接分析报告。
8. **同步与提交**：安装副本（4 处）→ 公开脱敏版 → 提交。公开版生成后必须检查是否泄漏内部路径/模型代号/域名。

---

## 4. 门禁（提交前四条，缺一不可）

```bash
cd <skill 根>
python3 -m pytest tests/ -q                     # 全绿，且新增行为有新增用例
python3 scripts/doccheck.py                      # 输出 OK：文档数字与代码事实一致
python3 scripts/agentctl.py status               # 真业务路径：打印任务表，不是 traceback
python3 scripts/agentctl.py status --json | python3 -m json.tool >/dev/null  # JSON 契约
python3 -m pyflakes scripts/*.py | grep -c "undefined name '"   # 必须为 0
```

> 用 `undefined name '`（带单引号）而不是 `undefined name`：后者会误命中
> `supervisor.py` 的 `from manager import *`（pyflakes 报 "unable to detect undefined names"），
> 那条是兼容 shim 的已知误报，不是缺陷。

补充规则：

- **改过函数体**：对比改动前后 `^def (\w+)` 集合，或用 `tests/test_cli_smoke.py::test_agentctl_has_all_core_functions` 兜底。
- **改过雷达**：`python3 scripts/radar_cli.py status --json` 必须可解析；`intake --dry-run` 对一期真实简报能解析出条目。
- **改过公开版相关**：`python3 scripts/desensitize.py` 后，在产物里 grep 内部域名、内部路径、内部模型代号，必须 0 命中。
- **失败就停**：门禁失败不许「先提交再说」。修不动就在 `CHANGELOG.md` 记为未完成并说明卡点。

---

## 5. 留痕格式

### 5.1 `CHANGELOG.md`（每次提交一段，倒序）

```markdown
## 2026-11-16 · 雷达子功能 + 治理层
- 改了什么：新增 radar/ 与 scripts/radar_*.py；新增 GOVERNANCE/ANATOMY
- 为什么：把技术雷达的「分析→借鉴→清理」变成可追溯闭环
- 来源（可选）：radar 候选 #3（LoopForge）
- 门禁：pytest 68 passed；doccheck OK；agentctl status OK；pyflakes undefined=0
- 回滚：git revert <sha>
```

### 5.2 雷达分析报告（`radar/analyses/<日期>/<slug>.md`）

必含：来源条目、机制清单、证据坐标（`path:line` 或 URL）、与现有实现的对照、
`adopt/adapt/skip` 判定及理由、落地成本与风险、最小验证方案。
模板见 `radar/README.md`。

### 5.3 雷达落地记录（`radar/applied/<日期>-<slug>.md`）

必含：改动的文件与行为、为什么这样改、**哪些没抄及原因**、门禁输出、回滚方式。
「没抄什么」和「抄了什么」同等重要——它防止下一个人重复评估同一个机制。

### 5.4 `FIELD-NOTES.md`（每条：现象 → 根因 → 修法 → 验证）

只追加，不改旧条目；编号连续；写清「怎么证明修好了」，不写「应该好了」。

---

## 6. 禁止项（八条红线）

1. **不执行上游仓库的代码**。雷达只读分析：不 `npm install`、不 `make`、不跑测试脚本、不 `source` 其中的 shell。clone 只用于读。
2. **不把运行时数据提交进 git**：`radar/state/`（sqlite、audit.jsonl、cache）已在 `.gitignore`；clone 缓存可能上百 MB。
3. **不写死会漂移的数字**：测试数、坑条数、文件数交给 `doccheck.py` 对账。
4. **不用贪婪正则跨函数改代码**；不用 `--help` 代替业务冒烟。
5. **不在没有失败测试的情况下改调度、租约、状态机语义**。
6. **不手改公开脱敏版**，也不把含内部词表的 `desensitize.py` 发布出去。
7. **不删除台账、分析报告、`FIELD-NOTES.md` 旧条目**。判断错了就追加一条修正，不抹历史。
8. **不在门禁未过时 push**；不 force-push 主分支。

---

## 7. 提交规范

- 一条提交只做一件事；跨模块改动拆开。
- Message 三行内说清「改了什么 / 为什么 / 验证」，不堆形容词。
- 引用外部来源时给可复核坐标（仓库 + 文件 + 行，或文章 URL + 小节）。
- 提交前确认 `git status` 里没有 `radar/state/`、`*.log`、`__pycache__`。
- 回滚优先 `git revert`，不 `reset --hard` 覆盖别人的改动。

---

## 8. 事故复盘模板

```markdown
## <编号>. <一句话现象>
现象：可观测到的错误（报错原文/错误数据/用户看到的结果）
根因：机制层面的原因，不是「手滑」
修法：改了哪个文件哪一行，为什么这样修
验证：用什么命令/数据证明修好了
边界：还有哪些同类实例没修，怎么枚举
```

写入 `FIELD-NOTES.md`；同类问题超过两处时，先写审计脚本枚举全部实例，再一次性修（第 30 条）。
