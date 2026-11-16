# 长任务续跑 → 断点快照四问进入任务提示词

- 分析报告：`radar/analyses/2026-11-16/05-long-task-resume.md`
- 改动文件：`templates/tasks/_done-contract.md`、`scripts/taskctl.py`、
  `tests/test_radar.py`
- 提交：`a7e9c50`（契约文本）+ 本记录所在提交（渲染时附加）

## 改了什么

1. `_done-contract.md` 新增「五、断点快照四问」：哪版目标 / 已完成什么 / 下一步 /
   未知副作用；并写死一条硬约束：**任何产生外部副作用的步骤，必须在执行之前
   落进 `progress.md`**。恢复时先做「世界对账」，按已提交 / 确认未发生 / 仍未知
   三路处理，未知即交人。
2. `taskctl.render_prompt()` 在渲染完任务模板后，自动把 `_done-contract.md`
   追加到提示词末尾。此前文档声称「派单时自动附在任务提示词末尾」，但代码没有做，
   实际只靠模板作者自觉——文档与实现不一致。
3. `tests/test_radar.py` 增加用例：`render_prompt` 的输出必须包含「断点快照四问」
   与「未知副作用」。

## 为什么这样改

- 本 skill 的 `resume` 语义是「读 progress 接着做」，但 progress 原来只被要求写进度，
  没有强制回答「哪版目标 / 有没有已发出但无回执的副作用」。这正是文章里
  「重跑变成新事故」的根因。
- 只改文档不够：不进入提示词，worker 不会照着做。所以把「附加契约」做成代码行为，
  并用测试钉住。
- 没有引入任何运行时状态或新依赖，默认行为对已完成任务无影响。

## 没抄什么

- **幂等键 / outbox / PREPARED→EXECUTED→CONFIRMED 三阶段**：本 skill 不直接调外部写
  接口，真正的外部副作用在子任务代码里，由子任务自己负责；在编排层再造一套是重复。
- **确定性重放**：依赖「编排代码 + 事件历史」模型，本 skill 的编排是 Python 脚本 +
  文件，`resume` 是「接着做」而不是「重放」。

## 门禁

```
pytest 全绿（项数以 doccheck 为准）
doccheck.py                     OK 文档数字与代码事实一致
agentctl.py status              OK
agentctl.py status --json       OK
pyflakes | grep "undefined name '"   0
```

## 回滚

```bash
git revert <本记录所在提交>      # 撤销渲染附加与测试
git checkout HEAD~1 -- templates/tasks/_done-contract.md   # 仅撤契约文本
```

回滚不影响雷达台账（`radar/state/` 未进 git）。
