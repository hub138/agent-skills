# Bug0 QA Agent：Playwright 回放缓存

来源：20261115-42d9c1049d7fc1b0.md（infoq.cn/article/eO0w7sdaGClvppFqwt5j）

## 机制
自然语言声明式测试步骤 → 首跑 Agent 探索 UI 编译为浏览器操作 → 成功步骤缓存到
Redis → 后续回归直接确定性重放（避免 LLM 延迟与 token）；断言走视觉模型多 LLM 共识。

## 对照 agent-ops
「探索一次 → 缓存为确定性命令 → 重放」与 taskctl 断点续跑同构（探索=首跑，
确定性重放=从断点继续），但领域不同：Bug0 是 UI 回归测试，agent-ops 不做 UI 测试。

## 判定：skip
领域不匹配（QA/UI 测试）。可借鉴的思想已在收工契约里：确定性重放优先于重新推理
——这正是断点快照四问的意图。无新增落地项。
