# 改进 skill-creator：测试、量测与迭代 Agent Skills（Improving skill-creator: Test, measure, and refine Agent Skills）

- 原文：[Improving skill-creator: Test, measure, and refine Agent Skills](https://claude.com/resources/articles/improving-skill-creator-test-measure-and-refine-agent-skills)
- 来源：Anthropic，作者 Anthropic Agent Skills 团队
- 发布：2026-03-03
- 译文说明：全文翻译，术语保留英文原词；站内相对链接转为绝对 URL；图片为 assets.claude.com 绝对直链并配中文短描述；页面未署名个人作者，来源按 Anthropic 团队口径标注。

skill-creator 现在帮你写 evals、跑 benchmark、并让你的 skills 在模型演进中保持可用。这些更新现已上线 Claude.ai 与 Cowork，作为 [Claude Code 插件](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator)提供，也在[我们的仓库](https://github.com/anthropics/skills/tree/main/skills/skill-creator)里。

自去年十月[发布 Agent Skills](https://claude.com/resources/articles/skills) 以来，我们注意到多数作者是领域专家，并非工程师。他们熟悉自己的工作流，却没有工具去判断一个 skill 在新模型下是否仍然可用、该触发时是否触发、编辑之后是否真的有改进。

今天我们发布 skill-creator 的增强能力，帮助作者更有把握地构建。我们把软件开发的一些严谨做法（测试、benchmark、迭代改进）带进 skill 编写，全程不需要任何人写代码。

## 两类 skills

skills 大致分为两类：

**Capability uplift（能力补充）型** skills 帮 Claude 做基座模型做不到、或做不到稳定一致的事。我们的[文档创建 skills](https://github.com/anthropics/skills/tree/main/skills) 就是好例子。它们编码了比单靠 prompt 能产出更好结果的技巧与模式。

**Encoded preference（倾向编码）型** skills 记录这样的工作流：Claude 本来就能做其中每一件事，skill 只是按你团队的流程把它们排好顺序。例子：按固定标准走查 NDA 审查的 skill，或从多个 MCP 拉数据起草周报的 skill。

这个区分之所以重要，是因为两类 skills 需要测试的理由不同：

- Capability uplift 型 skills 可能随模型进步变得不再必要。evals 告诉你那一刻何时到来。

- Encoded preference 型 skills 更耐久，但价值取决于对实际工作流的忠实度。evals 验证这份忠实度。

无论哪类，测试都把一个看起来能用的 skill，变成一个你知道确实能用的 skill。

## 用 evals 测试与改进 skills

skill-creator 现在帮你写 evals，也就是检查 Claude 对给定 prompt 是否按你预期行事的测试。写过软件测试的人会感到熟悉：定义几组测试 prompt（需要时附文件），描述好的输出长什么样，skill-creator 告诉你这个 skill 是否站得住。

以我们的 PDF skill 为例，它以前处理不了非可填写的表单。Claude 必须在没有字段定义引导的情况下把文本放到精确坐标上。evals 把这个失败单独隔离出来，我们发布了把定位锚定到提取文本坐标上的修复。

![skill-creator 的 eval 界面示意：定义测试 prompt 与期望行为，运行后显示通过与否](https://assets.claude.com/34aab7c39810d51fd6471da0fe1ea777fea3e711.png)

evals 的帮助很多，两个重要用途是抓质量回归与理解模型进步。

第一，**抓质量回归**。模型与周边基础设施在演进，上个月好用的 skill 今天可能行为不同。对着新模型跑 evals，在影响团队工作之前给你一个早期信号。

第二，**知道通用模型能力何时长过了你的 skill**。这主要适用于 capability uplift 型。如果基座模型在不加载 skill 的情况下开始通过你的 evals，这信号说明该 skill 的技巧可能已经被吸收进模型的默认行为。skill 没有坏，只是不再必要。

我们还加入了 **benchmark 模式**，用你的 evals 跑一套标准化评估。模型更新后，或你迭代 skill 本身时，都可以跑它。它跟踪 eval 通过率、耗时与 token 用量。

![benchmark 模式界面示意：按 eval 通过率、耗时、token 用量三项指标汇总](https://assets.claude.com/a17fb435f399ab7b41480ee4372ab52cef0e8ea1.png)

你的 evals 与结果留在你手里。可以本地存储、接入 dashboard，或接进 CI 系统。

## 用多 agent 支持更快更稳定地评估

顺序跑 evals 可能很慢，累积的上下文还会在多轮测试之间互相渗透。skill-creator 现在用 **multi-agent 支持**并行跑 evals：每个 eval 由独立的 agent 执行，各自持干净的上下文与独立的 token、计时指标。结果更快，没有交叉污染。

我们还加入了 **comparator agents** 做 A/B 对比：两个 skill 版本，或带 skill 与不带 skill。它们在不知道哪个是哪个的情况下评判输出，让你分清一次改动是否真的有帮助。

![comparator agents 界面示意：两份输出来源隐去，评判方盲测打分](https://assets.claude.com/52413cc0ceb3eba619bc5ca3845fe5bb6422d57c.png)

## 让 skills 在正确的时机触发

evals 量测输出质量，但前提是 skill 该触发时触发。随着 skill 数量增长，description 的精确度变得关键：太宽会误触发，太窄则永远不触发。skill-creator 现在帮你调 description，让触发更可靠：它对照示例 prompt 分析你当前的 description，并给出同时压低误报与漏报的修改建议。

我们把它跑了一遍文档创建 skills，6 个公开 skill 中 5 个的触发得到改善。

![description 调优界面示意：对照示例 prompt 分析当前 description 并建议修改](https://assets.claude.com/f3531e57903415ea85fc883ab023d59d77fd7b21.png)

## 展望

随着模型进步，「skill」与「specification（规格说明）」的界限可能模糊。今天，一个 SKILL.md 文件本质上是一份实现计划，用详细指令告诉 Claude「怎么」做某事。随时间推移，一段描述该 skill「做什么」的自然语言说明可能就够了，剩下的由模型自己想明白。

我们今天发布的 eval 框架是朝这个方向的一步。evals 已经在描述「什么」。最终，那段描述本身可能就是 skill。

## 上手起步

skill-creator 的全部更新现已上线 Claude.ai 与 Cowork。让 Claude 使用 skill-creator 即可开始。

Claude Code 用户可以安装[插件](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator)或从[仓库](https://github.com/anthropics/skills/tree/main/skills/skill-creator)下载。
