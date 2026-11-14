# Claude API 数据保留：零数据保留与 HIPAA 就绪

- 原文：[API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)
- 来源：Anthropic 官方文档（md 直链抓取）
- 发布：官方文档页，随 API 持续更新
- 译文说明：原文为英文，本篇为按本包语言规则的合规改写整理，术语保留英文原词。资格表过宽，本篇按官方「分析类与设计类条目完整收编，纯查询类条目收编主要机制与例外」的既定口径压缩为分组摘要，完整逐条资格表以官方页为准。

本页覆盖 Claude API（api.anthropic.com）、Claude Platform on AWS、Claude in Microsoft Foundry、Claude Models on Google Cloud（Anthropic managed），这些场景里 Anthropic 是数据处理方。Google managed 与 Amazon Bedrock 场景里云厂商是数据处理方，等价控制看云厂商自己的文档。

Anthropic 为 Claude API 提供两种数据处理安排：零数据保留（zero data retention，ZDR）与 HIPAA 就绪（HIPAA readiness）。功能资格表列明每种安排覆盖哪些 API 功能。

## 数据保留的总体方针

不同 API 与功能有不同的存储需求。功能不需要存储客户 prompt 或响应时，可能符合 ZDR 资格。功能必须存储时，Anthropic 按以下承诺把保留量设计到最小：保留的数据未经明确许可永不用于模型训练；只保留功能运转在技术上必需的内容，对话内容默认不保留，例外是 Covered Models 要求 30 天保留；保留数据按最短可行 TTL（存活时间）清除，客户可控制保留时长。

ZDR 与 HIPAA 两种安排之外还有几套独立的保留模型：Compliance API 走自己的保留模型；Activity Feed 保留数据 6 年；claude.ai 的聊天、文件与项目内容按组织在 claude.ai 管理设置里配置的保留策略执行；本地会话记录（用户机器上的 Cowork 与 Claude Code 会话）默认存 6 年，组织设了有限期对话保留期限时按该期限；云端远端会话记录保留 6 年，用户提前删除会话除外。ZDR 生效中的本地会话，Compliance API 不采集；HIPAA 就绪组织，只采集 Cowork 与 Claude Code 的本地会话，记录存 30 天。

## 零数据保留（ZDR）

ZDR 安排下，API 响应返回之后，Anthropic 不在存储中保留客户 prompt 或响应。申请 ZDR 联系销售团队。ZDR 按组织逐一开通，同一账号下新组织要单独申请，开通不自动延伸到其他组织。

ZDR 组织不能从浏览器直接调用 Claude API：API 拒绝其跨源（CORS）请求。网页应用要从自己的后端发请求。

### ZDR 覆盖什么

- Claude Messages API 与 Token Counting API：资格表内功能适用。用 `/v1/messages` 但表中标记 No 的功能（如代码执行）不覆盖。
- 搭配 API key 的 Claude Code：Commercial 组织（商业服务条款下的组织，区别于消费者账号）的 API key 适用。Claude Code 开了指标记录时，用量统计类生产力数据豁免于 ZDR、可能被保留。
- Claude Platform on AWS 与 Claude Models on Google Cloud（Anthropic managed）：与第一方 Claude API 同策略，ZDR 按需申请开通。

### ZDR 不覆盖什么

- Claude Console：含 playground 的全部使用。
- Claude Managed Agents：有状态资源，会话记录持续存在直到你删除。
- 消费者产品：Free、Pro、Max、Ultra 套餐，含这些套餐客户使用 Claude 网页、桌面、移动应用或 Claude Code。
- Teams 与 Enterprise 产品界面：不满足 ZDR 资格。唯一例外是 Claude Enterprise 上的 Claude Code，它有独立于本页安排的 ZDR 规格，仅面向合格账号、由 Anthropic 单独开通。
- Claude for Excel：当前不满足资格。
- Claude Fable 5.1、Mythos 5.1、Fable 5、Mythos 5 四个模型：要求 30 天数据保留，未经 Anthropic 明确授权不提供 ZDR。
- 第三方集成：第三方网站、工具处理的数据不覆盖。
- 被标记内容与法律要求保留：见「与安排无关的保留」。

## HIPAA 就绪

Claude API 为处理受保护健康信息（PHI）的组织支持 HIPAA 就绪集成。签署 BAA（Business Associate Agreement，商业伙伴协议）并开通组织的 HIPAA 开关后，可用受支持的功能处理 PHI。合格组织可在 Claude Console 直接查看并签署 BAA。HIPAA 就绪施加比 ZDR 更宽的隐私与安全防护（加密、访问控制、审计日志，保护 PHI 全生命周期），允许带防护地保留数据而非要求立即删除。组织处理 PHI 时用 HIPAA 就绪即可，不需要再叠加 ZDR。

### HIPAA 就绪覆盖什么

Claude API 的资格表内功能；Claude in Microsoft Foundry（Anthropic 托管或 Azure 托管）在 BAA 加 Azure 订阅开通 HIPAA 配置的条件下合格。

### HIPAA 就绪不覆盖什么

消费者产品；Claude Console 界面本身（在 Console 设置里开通 HIPAA 就绪受支持，通过 Console 处理 PHI 不覆盖）；Amazon Bedrock 与 Google Cloud Agent Platform 等伙伴运营平台；Claude Platform on AWS（HIPAA 就绪不可用）；第三方集成；Claude Code；beta 功能（一般不覆盖，除非资格表明确列为合格）。

### PHI 处理准则

PHI 指一切可识别个人身份的健康信息。在 Claude API 的场景里，PHI 通常出现在消息内容（prompt 与 Claude 响应）、附件（图片、PDF）与文件名或元数据里。BAA 下不预期含 PHI 的字段：workspace 名、用户信息（姓名、邮箱、电话）、账单数据、工单。

用结构化输出或 `strict: true` 工具时，API 把 JSON schema 编译成语法、与消息内容分开缓存。这些缓存 schema 得不到 prompt 与响应那样的 PHI 防护。JSON schema 定义里禁止包含 PHI，这条限制覆盖 schema 属性名、`enum` 取值、`const` 取值与 `pattern` 正则。病人特定信息只应出现在消息内容里，那里受 HIPAA 防护。

### HIPAA 错误处理

签署的 BAA 是覆盖范围的权威来源，API 也会自动强制执行限制。HIPAA 组织的请求带上不合格功能时，API 返回 400 错误防止误用：

```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "The requested features are not available for HIPAA-regulated organizations without Zero Data Retention: code_execution."
  }
}
```

错误消息列出请求里检测到的不合格功能，删掉再重试。消息里 “without Zero Data Retention” 是 API 自己的措辞，不改变处理方式。资格表 Details 列写明不拦截的客户端工具，请求被接受但仍在 HIPAA 就绪之外。

### 开通路径

标准 BAA 在 Console 自助开通：数据保留设置页（platform.claude.com/settings/privacy）→ 有 HIPAA 管理权限的组织管理员看到 HIPAA 合规卡片 → 下载 BAA 与实施指南 → 授权法律代表接受协议 → 生效即时且配置永久、管理员无法关闭 → API 自动强制功能限制。需要谈判式 BAA 的组织走销售团队。

### 组织级强制

HIPAA 就绪按组织级强制。同时需要 HIPAA 就绪与通用 API 访问时，各用单独的组织。

## 模型特定的数据保留要求

Claude Fable 5.1、Mythos 5.1、Fable 5、Mythos 5 被指定为 Covered Models，要求 30 天数据保留，因此 ZDR 不可用（Anthropic 明确授权除外）。Claude API 上，数据保留配置不满足要求的组织请求这些模型时返回 400 invalid_request_error：

```json
{
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "In order to access this model, your organization or workspace must have data retention enabled."
  }
}
```

30 天要求在 Covered Models 提供的全部平台适用。Claude API 与 Claude Platform on AWS 上 Anthropic 处理保留数据；Amazon Bedrock 与 Google Cloud Agent Platform 上保留数据留在云厂商环境内。

### 为单个 workspace 开 30 天保留

ZDR 组织可以只给某个 workspace 开 30 天保留来使用这些模型：数据保留设置页选 workspace → 选标准数据保留（30 天）→ 接受条款后生效。Default Workspace 永远跟随组织设置，要用另一个 workspace。验证方式：该 workspace 请求 Covered Models 成功，未覆盖的 workspace 继续跟随组织默认。

## 功能资格表

官方页给出四张资格表，每列三种取值：

- Yes：功能完全合格。ZDR 列的 Yes 还要求模型不需要 30 天保留。
- Yes（qualified，有保留条件）：prompt 与输出不存储，但功能运转需要短暂保留某个有边界的产物（Details 列指名）。受「数据保留总体方针」的承诺约束。
- No：不合格。HIPAA 就绪下 API 拦截含 No 功能的请求并返回 400（Details 列另写明的除外）；ZDR 下 API 不拦截，用它是把这部分数据走出 ZDR 安排的选择，功能自身的保留策略适用。标记 No 的功能通常是有状态的（存任务、文件或容器状态）。

四张表的分组摘要（完整逐条以官方页为准）：

- 平台功能表（26 项）：不合格项有 Agent Skills（标准策略保留）、Batch processing（29 天保留，异步存储必需）、Files API（保留到显式删除或到期）、MCP connector 与 MCP tunnels（标准策略保留）、programmatic tool calling（代码执行容器，最长 30 天）。有保留条件项两项：cache diagnostics（哈希指纹与 token 数估计短暂保留用于下个请求对比）、structured outputs（仅 JSON schema 缓存最长 24 小时，覆盖 `strict: true` 工具的同一条语法管道；schema 内禁放 PHI）。prompt caching 为 Yes（KV cache 表示与密码学哈希按缓存 TTL 存于内存、到期即删）。web search、web fetch、browser use 为 Yes，但三者的动态过滤不合格。computer use、thinking、citations、token counting、PDF 支持、数据驻留、effort、fast mode 等为 Yes。browser use、advisor tool、tool search、threshold compaction、web fetch 在 HIPAA 列为 No。
- Messages API 功能表（8 项）：bash tool、text editor tool、memory tool 为客户端侧工具，全部 Yes；code execution tool 为 No（容器数据最长 30 天）；context editing 为 Yes（实时应用编辑）；message threads 为 No（内容存内存、服务端管理的密钥加密、不写入持久存储、最迟最后使用后 1 小时删除，用它不影响其他 ZDR 合格功能的使用）。
- Managed Agents 功能表（1 项）：全部不合格。会话是有状态资源，记录持续存在直到删除，含 self-hosted sandboxes 子功能。
- 其他功能表（3 项）：1M token 上下文窗口 Yes；OpenTelemetry 导出 Yes（span 的 ZDR 资格跟随产生它的功能，HIPAA 组织可导出元数据）；user profiles No（按标准策略保留到删除，HIPAA 组织可用但不得含 PHI）。

## 与安排无关的保留

即使有 ZDR 或 HIPAA 安排，法律要求或被自动信任与安全系统标记的内容，Anthropic 可继续保留。聊天或会话被标记时，输入与输出最长保留 2 年。

## 常见问题选摘

- 怎么知道组织有没有 ZDR：查合同条款或问客户代表。
- ZDR 下用了标记 No 的功能会怎样：请求不被拦截。这些功能本质上是有状态的：Batch API 存任务、Files API 存文件、代码执行跑在持久容器里，数据按各功能自己的文档保留。用它就是选择让这部分数据走出 ZDR 安排。
- HIPAA 就绪与 ZDR 的差别：ZDR 防止响应返回后存储客户数据；HIPAA 就绪是全生命周期的防护体系（加密、访问控制、审计日志），允许带防护保留而非要求立即删除。两者覆盖的功能集合不同。
- 已有 HIPAA 就绪还要 ZDR 吗：不需要，HIPAA 就绪就是为处理 PHI 的组织准备的 ZDR 替代方案。
- Claude Code 的 ZDR 资格：两条独立规格。Commercial 组织的按量 API key，跟随该组织的 API ZDR 安排；Claude Enterprise 上的 Claude Code 走单独规格，由 Anthropic 为组织开通。

> 包内互引：message threads 的 ZDR 例外与 1 小时删除机制见 claude-message-threads.md；context editing 的 ZDR 合格声明见 claude-context-editing.md；memory tool 的客户端侧存储控制见 claude-memory-tool.md；batch 的 29 天保留对照 OpenAI 批处理 30 天自动删除见 openai-batch-api.md。
