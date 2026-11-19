# deepseek-ai/deepseek-harness（repo 深读，203.3MB）

来源：radar/state/cache/github.com/deepseek-ai/deepseek-harness @ HEAD

## 结构
packages/ 多层：shell / api / host / boot / lsp / connector / browser-use / mcp /
deliverables / interaction / plan / document——完整的 IDE 级 harness 全栈形态。

## 判定：skip
与 dsh-lessons.md 结论一致：DS Harness 是面向终端用户的完整产品，
agent-ops 是单人可维护的单机编排 skill，形态差两个数量级。
机制层面（租约/事件/交付物契约）均已等效实现。学架构不 vendor。
