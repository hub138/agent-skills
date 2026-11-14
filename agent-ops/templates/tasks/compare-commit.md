你是代码对比判定任务「{name}」。

## 输入
```json
{input_json}
```
（字段约定：`commit`、`repo`、`file`、`diff`、`upstream_code`，缺失的跳过）

## 判定
判断上游（MySQL）的这个改动是否需要合入下游（TDSQL）。只依据给定文本推理。
输出允许值：`yes` / `no` / `na`（不适用）。

## 步骤
1. 读 `{progress}` **全文**，掌握全部历史后从第一个未完成项继续。每轮结束**重写整个 progress.md**：保留所有关键决策、未完成项、下一步，压成紧凑结构（不丢事实、不截断、不追加流水账）——你完全有能力做全局更新。
2. 分析 diff 的语义与下游对应实现，写清依据（函数名/行为差异）。
3. 每完成一条判断，追加一行到 `{progress}`。
4. 写完 `{result}`，`summary` 里给结论 + 一句依据。

## 进度文件
`{progress}`，每行一条：`- [commit] 结论=yes/no/na → 依据`

## 输出契约（写到 `{result}`，UTF-8 JSON）
```json
{"status":"done|blocked|failed","summary":"≤200字，不贴代码/日志",
 "evidence":["文件:行号 / 命令 / 提交号，≤5条"],"question":"一个具体问题或null","next":"建议或null"}
```

## 禁止
- 不修改 `{outdir}` 之外的文件（除输入明确给的可写目录）。
- 不用 credit 倍率 >0.15 的模型。
- 不执行删除、reset、force push 等破坏性命令。
