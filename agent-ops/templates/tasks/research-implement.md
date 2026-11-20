# 候选实施任务（把机制假设变成代码/规则/提示词改动）

## 因果
提案已通过门禁，现在把单机制改动实现在候选工作区。改动范围是边界——超出 allowed_paths 的任何修改都是违规。

## 输入
- 候选工作区（父候选快照副本）
- 提案 JSON（mechanism/hypothesis/falsify_plan）
- 允许的领域材料与训练集 few-shot（如有）
- 计划改动路径（candidate.allowed_paths）

## 输出契约
- 改动文件清单 + 每处改动对应机制的说明（一处改动说不清对应关系就是超范围）
- `progress.md`：步骤与阻塞，随时落盘
- `result.json`：{exec_status, cases:[...], started_at, finished_at}——exec_status=succeeded 才进实验账本；非 JSON/空/超时/降级归档不算评测通过

## 红线
- 只改 allowed_paths；不碰评测器；不硬编码项目 SHA/答案。
- 完成判据：改动可运行、结果文件符合 schema、progress 无未解决阻塞。
