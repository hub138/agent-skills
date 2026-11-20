# 独立复核任务（盲审裁决）

## 因果
候选在两批不重叠开发用例上通过后，需要独立身份复核：确认改动真实有效、告警裁决正确、无泄漏。你看不到候选作者的理由与得分影响。

## 输入（全部允许）
- 候选 diff（改动前后的文件内容）
- 待裁决的逐条告警与对应代码/证据坐标
- 冻结的裁决规则（rubric）

## 禁止读取
标签文件、历史评测得分、后继修复、其他 agent 会话、候选作者的结论。

## 输出契约（JSON）
```json
{"alerts": [{"alert_id": "...", "verdict": "valid|false_positive|disputed",
             "evidence": "path:line 或可定位坐标", "reason": "一句话"}],
 "leak_suspect": false,
 "notes": "边界不确定项"}
```

## 红线
- 逐条裁决，unknown 如实标 disputed（不算 TP）。
- 结论只依据代码与规则，不依据"这条会让分数怎么变"。
