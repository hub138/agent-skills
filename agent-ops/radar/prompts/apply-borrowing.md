# 任务书：把一条借鉴落到代码里（radar/apply-borrowing）

> 目标：用最小、可测、可回滚的改动，把分析报告里的机制接进 agent-ops。
> **落地不是复刻**：能少一行就少一行，能不引入依赖就不引入。

## 0. 前置检查（缺一项就先补）

1. 分析报告存在且已 `record` 入账（`radar_cli.py list` 能看到 verdict）。
2. 读过 `ANATOMY.md` 第 6 节影响矩阵，知道要改的文件的下游是谁。
3. 在 `FIELD-NOTES.md` 搜过关键词：同一个坑是否已经踩过、同一个机制是否评估过。
4. `git status --short` 干净，或你清楚哪些改动不是你的。

## 1. 写方案（先写再改，≤10 行）

在分析报告末尾补一节「落地方案」，回答：

- 改哪 1–3 个文件？为什么是这几个？
- 新增什么字段/子命令/校验？**默认行为是否改变？**（默认不变优先）
- 测试加在哪？要钉住的失败场景是什么？
- 若与现有机制（租约、状态机、manager 决策）冲突，冲突点在哪、怎么解？
- 回滚方式是什么？

方案里必须有一句「**不做什么**」：明确放弃上游的哪些部分（框架、依赖、部署形态）。

## 1.5 事前审（要不要做）

方案写完、动手之前，三问答不好就不做——**不做也是合格结论**：

1. 这件事解决的是本 skill 的**真实缺口**，还是「看起来很酷」？
2. 不做的代价是什么？（没人提需求 = 代价可能为零）
3. 一周后回头看，会后悔做吗？

三问结论写进 `applied --review` 的 `pre` 字段（如 `"做：补真实缺口"` /
`"推迟：触发条件未到"`）。答好后才进第 2 步。

## 2. 先写失败测试

在 `tests/` 增加用例，先让它在当前代码上**失败**，证明缺口真实存在。

- 纯函数：直接断言返回结构/边界。
- 子命令：用 `subprocess` 调 CLI，断言退出码与 JSON 字段（不要只测函数，防止 argparse 路径没接上）。
- 数据迁移：旧库 → 新库，断言只加列、旧数据可读。

## 3. 最小实现

硬约束：

- 不新增第三方依赖；只用标准库。
- 不改调度/租约的默认语义（除非分析报告明确论证且测试覆盖并发路径）。
- 新参数默认关闭，或对旧行为完全兼容。
- 错误信息带「下一步怎么办」，不要只抛 traceback。
- 不顺手重排目录、不重命名既有字段（用户明确要求：只改需要改的那一处）。

## 4. 门禁（GOVERNANCE 第 4 节，逐条跑）

```bash
python3 -m pytest tests/ -q
python3 scripts/doccheck.py
python3 scripts/anatomy_check.py
python3 scripts/agentctl.py status
python3 scripts/agentctl.py status --json | python3 -m json.tool >/dev/null
python3 -m pyflakes scripts/*.py | grep -c "undefined name '"   # 期望 0
```

改了雷达自身还要：

```bash
python3 scripts/radar_cli.py status --json | python3 -m json.tool >/dev/null
python3 scripts/radar_cli.py intake --file <本期简报> --dry-run   # 解析仍正常
```

门禁红了就修；修不动就**不提交**，在报告里写清卡点。

## 5. 留痕（两份，缺一不可）

### 5.1 `radar/applied/<日期>-<slug>.md`

按 `radar/README.md` 5.2 的模板写，重点：

- **改了什么**（行为变化，不是文件清单）
- **为什么这样改**（上游机制 → 本地抽象的映射）
- **没抄什么**（明确列出并给理由）
- **门禁**（真实输出摘要）
- **回滚**（命令）

### 5.2 台账

```bash
python3 scripts/radar_cli.py applied \
  --candidate <id> \
  --files scripts/taskctl.py tests/test_taskctl.py \
  --summary "新增 envelope 子命令校验 result.json 五字段" \
  --rationale "借鉴 SaResultEnvelope；只做校验不改写入路径" \
  --diffstat "+86 -0" \
  --tests '{"pytest":"73 passed","doccheck":"OK","smoke":"OK"}' \
  --commit <sha>
python3 scripts/radar_cli.py ledger
```

同时按 `GOVERNANCE.md` 5.1 在 `CHANGELOG.md` 记一段。

## 5.5 事后审（做的对不对）

门禁全绿 ≠ 做得对。提交前三问，答进 `--review` 的 `post` 字段：

1. 改动是最小吗？有没有夹带无关变更？
2. 回滚命令在临时副本上**真的执行过**吗？
3. 一周后这段代码还会被理解吗（命名/注释/文档）？

发现问题当场修，不带病提交。

## 6. 提交

- 一个借鉴一条提交（或一组可整体 revert 的提交）。
- Message：`feat(radar): 借鉴 <来源> 的 <机制>，<一句话效果>`。
- 提交前 `git diff --stat` 自查：有没有夹带无关文件、有没有把 `radar/state/` 带进去。

## 7. 红线（违反即回滚）

1. 执行了上游仓库的代码（`npm install` / `make` / 跑它的测试）。
2. 引入了第三方依赖或外部服务。
3. 改了调度/租约语义却没有并发或失败路径测试。
4. 落地报告只写「已实现」，不写改动理由与回滚方式。
5. 为了让测试过而放宽断言，或删掉既有测试。
6. 把「上游这么做」当成理由，而没说清本 skill 的哪个失败场景被解决。

## 8. 完成判据

- [ ] 失败测试先红后绿；
- [ ] 五条门禁真实通过（有输出，不是口头「应该没问题」）；
- [ ] `radar/applied/` 报告 + 台账 + `CHANGELOG.md` 三处一致；
- [ ] 提交只含本次改动，可 `git revert` 干净回滚；
- [ ] 如果最终决定不落地：回写分析报告，把 verdict 改成 `skip` 或保留 `adapt` 并写明「本期未落地及原因」。
