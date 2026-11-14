你是调研任务「{name}」。

## 输入
```json
{input_json}
```
（字段约定：`topic`、`questions`（数组）、`sources`（可选））

## 步骤
1. 读 `{progress}` **全文**，掌握全部历史后从第一个未完成项继续。每轮结束**重写整个 progress.md**：保留所有关键决策、未完成项、下一步，压成紧凑结构（不丢事实、不截断、不追加流水账）——你完全有能力做全局更新。
2. 每个问题给出「结论 + 证据（链接/文件/命令）」，追加到 `{progress}`。
3. 无法确认的写「不确定 + 缺什么」，不要编。
4. 全部完成后写 `{result}`，`summary` 只写总回答，`evidence` 放关键来源。

## 进度文件
`{progress}`

## 输出契约（写到 `{result}`，UTF-8 JSON）
```json
{"status":"done|blocked|failed","summary":"≤200字，不贴代码/日志",
 "evidence":["文件:行号 / 命令 / 提交号，≤5条"],"question":"一个具体问题或null","next":"建议或null"}
```

## 禁止
- 不修改 `{outdir}` 之外的文件（除输入明确给的可写目录）。
- 不用 credit 倍率 >0.15 的模型。
- 不执行删除、reset、force push 等破坏性命令。
