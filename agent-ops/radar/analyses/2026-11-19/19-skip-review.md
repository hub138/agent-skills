# skip 复核记录（2026-11-19，全量 42 条）

## 复核方式
逐条读标题+core，对照 agent-ops 的问题清单（编排/租约/续跑/信封/审计/清理）。

## 升级 6 条（triage_override 事件留痕，深读见 09-17 报告）
- #35 deepseek-harness：dsh-lessons 对标项目
- #36 Managed Agents 稳定交付
- #52 Agent 全栈
- #72 Skill 自进化（与 #79 同文，深读一份）
- #82 OpenAI OpenClaw 安全加固
- #89 Bug0 QA Agent

## 维持 skip 36 条（分类理由）
模型/产品发布、存储基建、观点人事、领域专深（搜广推/召回/游戏）、
弱相关工程——均与编排运维层无可迁移机制；同类 CLI harness（deepseek-recipe/
qwen-code）机制已在 dsh-lessons 对标，形态不适用。
分诊词表无修改（无误杀教训），但新增一条经验：**上游 100 分条目也可能被
词表判 skip（#89），分诊分数与上游评分是两套口径，复核不能省**。
