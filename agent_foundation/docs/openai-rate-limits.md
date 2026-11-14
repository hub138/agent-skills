# OpenAI 速率限制：指标体系、使用层级与缓解策略

- 原文：[Rate limits](https://developers.openai.com/api/docs/guides/rate-limits)
- 来源：OpenAI 官方文档（镜像站 html 抓取，站方页面自带中文翻译）
- 发布：官方文档页，随 API 持续更新
- 译文说明：本篇为按本包语言规则的合规改写整理，术语保留英文原词。

速率限制是 API 施加的限制，规定用户或客户端在指定时间段内可以访问服务的次数。

## 为什么会有速率限制

三个原因：防止滥用或误用（恶意攻击者可能发送大量请求企图使 API 过载或中断服务）；确保公平访问（个人或组织请求过多会拖慢其他人的访问，限制单人请求数让多数人都有机会使用）；管理基础设施总负载（请求剧增会给服务器重压并引发性能问题）。

## 限制指标如何工作

速率限制使用 RPM（每分钟请求数）、RPD（每天请求数）、TPM（每分钟 token 数）、TPD（每天 token 数）、IPM（每分钟图像数），以及某些流式音频模型按每分钟音频分钟数计。任一指标先到顶都触发限制。例如 RPM 是 20 时，发 20 个只含 100 token 的请求就触顶，即使 TPM 上限是 150k、实际只发了 2000 token。

Batch API 队列限制按给定模型排队的输入 token 总数计算。待处理批处理作业的 token 计入队列限制，作业完成后不再计入。

## 其他重要事项

- 速率限制按组织级与项目级定义，不按用户级。
- 速率限制因模型而异。
- 长上下文模型（如 GPT-5.5）的长上下文请求有单独的速率限制，可在开发者控制台查看。
- OpenAI 为每个组织设核准的每月使用额度，这与组织或项目可配置的消费限制是分开的。
- 某些模型系列共享速率限制：组织限制页面「共享限制」列表里的模型共用一份（例如共享 TPM 3.5M，对该列表内任何模型的全部调用都计入这 3.5M）。
- 向量存储摄取按每个向量存储 ID 速率限制：每个向量存储的 files 与 file_batches 接口共享每分钟 300 次请求，较大规模摄取优先用 file_batches。

## 使用层级

在账户设置的 limits 区域查看组织的速率与使用限制。随 API 消费增长自动晋升层级，多数模型的限制随之提高：

| 层级 | 资质要求 | 使用限制 |
|---|---|---|
| 免费 | 允许的地理区域内 | $100/月 |
| Tier 1 | 已支付 $5 | $100/月 |
| Tier 2 | 已支付 $50 | $500/月 |
| Tier 3 | 已支付 $100 | $1,000/月 |
| Tier 4 | 已支付 $250 | $5,000/月 |
| Tier 5 | 已支付 $1,000 | $200,000/月 |

每模型速率限制的详细摘要看模型页面。

## 请求头里的速率限制信息

HTTP 响应头携带剩余次数与重置时间等元数据：

| 字段 | 示例值 | 含义 |
|---|---|---|
| Retry-After | 56 | 出现临时速率限制错误时，重试前至少要等待的秒数 |
| x-ratelimit-limit-requests | 60 | 触顶前允许的最大请求数 |
| x-ratelimit-limit-tokens | 150000 | 触顶前允许的最大 token 数 |
| x-ratelimit-remaining-requests | 59 | 剩余请求数 |
| x-ratelimit-remaining-tokens | 149984 | 剩余 token 数 |
| x-ratelimit-reset-requests | 1秒 | 请求类限制重置回初始状态所需时间 |
| x-ratelimit-reset-tokens | 6分0秒 | token 类限制重置所需时间 |
| x-ratelimit-limit-project-tokens | 60000 | 项目 token 限制 |
| x-ratelimit-remaining-project-tokens | 57000 | 项目范围 token 限制剩余量 |
| x-ratelimit-reset-project-tokens | 3秒 | 项目范围 token 限制重置所需时间 |

适用项目范围 token 限制时出现 project-token 头。429 响应可能带 Retry-After；配额、账单或其他需要用户干预的错误不因重试而解决。

## 微调速率限制

微调速率限制在控制面板查看，也可用 API 获取：

```bash
curl https://api.openai.com/v1/fine_tuning/model_limits \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## 错误缓解

### 使用指数退避重试

请求超临时限制时 API 返回 429。响应可能带 Retry-After 头，告知重试前要等多少秒。把它当最小值：至少等这么久，再加一点随机延迟，防止多个客户端同一时间重试。

每个官方 OpenAI SDK 在符合条件时自动重试速率限制错误，Retry-After 存在时自动遵循。标准 API 调用不需要手动解析这个头，也不需要另加重试循环。用自己 HTTP 客户端时：头存在且有效就遵循；缺失或无效用带抖动的指数退避（exponential backoff with jitter）；限制尝试次数与总耗时；加了应用级重试时把 SDK 已做的重试计算在内；配额、账单类错误不重试。

指数退避指请求失败后稍等，每次重试失败后拉长延迟，直到成功或达到重试上限。三个好处：自动重试从速率限制错误恢复而不崩溃丢数据；前几次重试快、失败后仍有更长延迟兜底；随机抖动防止所有重试同时发生。

失败的请求仍计入每分钟限制，持续不间断重发无效。

### 三个 Python 重试实现

官方给了三个示例。示例 1 用 Tenacity 库（Apache 2.0 许可的重试库），`@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))` 装饰请求函数；示例 2 用 backoff 库，`@backoff.on_exception(backoff.expo, openai.RateLimitError)` 装饰；示例 3 手写 `retry_with_exponential_backoff` 装饰器：初始延迟 1 秒、指数基数 2、抖动开关、最多 10 次重试、只捕 `openai.RateLimitError`，其余异常直接抛出。前两个是第三方库，OpenAI 不为其可靠性或安全性作保证；第三个是自制方案的起点，同样无保证。

### 减小 max_tokens

速率限制按 max_tokens 与基于请求字符数估算的 token 数两者取大计算。把 max_tokens 设得尽量接近预期响应大小。

### 批量处理请求

用例不需要即时响应时，用 Batch API 提交大量请求，不占同步请求的速率限制。需要同步响应时，每分钟请求数与每分钟 token 数限制各自独立：RPM 触顶但 TPM 有余量时，把多个任务合并进每个请求提高吞吐，用小模型时尤其明显。发一批 prompt 与普通调用相同，区别是 prompt 参数传字符串列表。详见官方 Batch API 指南。

> 包内互引：Batch API 的独立速率池与三种批处理限制见 openai-batch-api.md；Claude 侧缓存断点保持稳定以避免缓存失效的纪律见 claude-troubleshooting-tool-use.md；并发上限压缩墙上时钟时间、吞吐不越速率限制的判例见 claude-plugin-evals.md。
