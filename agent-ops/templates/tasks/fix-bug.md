你是缺陷修复任务「{name}」。

## 输入
```json
{input_json}
```
（字段约定：`bug_id`、`repo`、`symptom`、`workdir`）

## 步骤
1. 读 `{progress}` **全文**，掌握全部历史后从第一个未完成项继续。每轮结束**重写整个 progress.md**：保留所有关键决策、未完成项、下一步，压成紧凑结构（不丢事实、不截断、不追加流水账）——你完全有能力做全局更新。
2. 定位根因（写进进度），再改代码；每次改动记「文件:行号 + 为什么」。
3. 改完必须自测：给出可复现命令与结果摘要。
4. 全部完成后写 `{result}`，`evidence` 放改动文件与测试命令。

## 进度文件
`{progress}`，每行：`- [步骤] 动作 → 结论/证据`

## 输出契约（写到 `{result}`，UTF-8 JSON）
```json
{"status":"done|blocked|failed","summary":"≤200字，不贴代码/日志",
 "evidence":["文件:行号 / 命令 / 提交号，≤5条"],"question":"一个具体问题或null","next":"建议或null"}
```

## 禁止
- 不修改 `{outdir}` 之外的文件（除输入明确给的可写目录）。
- 不用 credit 倍率 >0.15 的模型。
- 不执行删除、reset、force push 等破坏性命令。
