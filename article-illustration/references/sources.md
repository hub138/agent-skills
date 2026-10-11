# 找图来源手册

## 一、什么时候找现成图

一条标准：图里的信息能否用文字或 mermaid 准确表达。能，自绘；不能，找现成图。

需要找图的五类内容：

1. 官方仓库、官方文档、规范里公布的架构图、模块图、演进图
2. 原始论文里的结构图、处理流程、性能曲线
3. 真实产品界面、命令行输出、监控面板的截图
4. 厂商公布的硬件结构、内存布局
5. 权威机构公布的对比表、参数表

自绘会丢信息的原因：真实的层次比例、模块边界、界面形态、实测曲线的转折点，这些细节用 mermaid 复刻时全部丢失，读者看到的是画者的理解，不是原始形态。

不要的：与文章结论无关的装饰插画；二手自媒体重绘且无出处的图；带水印、带广告、带宣传语而无实质信息的图；分辨率不足的位图。

## 二、图源分级

| 级别 | 图源 | 使用方式 |
| --- | --- | --- |
| P0 | 官方仓库、官方文档、规范、标准 | 直接引用，注明版本或页面 |
| P1 | 原始论文、维护者博客、官方基准测试 | 引用并注明论文编号或页面 |
| P2 | 知名工程师文章、技术会议演讲 | 回溯 P0/P1 确认无出入后引用 |
| P3 | 社交媒体、二手总结、营销材料 | 不采用 |

## 三、按知识领域定位页面

每一条都实测过，列出可用图的数量。找不到图时按这张表往下换。

存储与数据库：

| 页面 | 实测结果 |
| --- | --- |
| RocksDB 官方仓库 wiki 层级压缩页 | 12 张全部合格，最宽 2469px。层级结构与压缩过程最集中的一页 |
| RocksDB 官方仓库 wiki 通用压缩页 | 无可用图，页面里的矢量标签全是界面图标 |
| PostgreSQL 官方文档 WAL 内部结构页 | 不含配图 |
| MySQL 官方文档 InnoDB 架构页 | 服务器拒绝抓取，返回 403，浏览器可正常打开 |
| USENIX FAST'21 论文《The RocksDB Experience》PDF（usenix.org/system/files/fast21-dong.pdf） | 2026-09-28 实测：论文 PDF 直链可下载（582KB），PyMuPDF 定位 Figure 1（页 3 左栏，坐标裁剪 Rect(50,58,296,166) 300dpi 得 1026×451 PNG）——MemTable + Level 0-4 的 LSM 分层结构官方图，讲 LSM 树、存储引擎、RocksDB 主题首选；PDF 裁图路线对无 HTML 版的系统论文（OSDI/FAST/SOSP）通用 |
| ZOOZ 工程博客《Designing DDD aggregates》（engineering.zooz.com/@allousas/designing-ddd-aggregates-db633f1caf88，Medium 托管） | 2026-09-28 实测：正文图在 miro.medium.com（懒加载），直链 `miro.medium.com/v2/resize:fit:1400/<id>` 下载 8 张中 4 张成功（a/b/g/h 报 cannot identify image file，疑 webp 伪装或防盗链）；zooz-c 是「big ball of mud」实体纠结网、zooz-d 是四聚合虚线椭圆结构图（聚合根/实体/值对象），DDD 聚合边界主题首选，图注需带英文标签中文对照 |

性能与底层：

| 页面 | 实测结果 |
| --- | --- |
| Brendan Gregg 火焰图页 | 9 张可用，含真实火焰图与中断负载对照 |
| Brendan Gregg 等待分析页 | 4 张可用，含线程状态划分图 |
| Brendan Gregg 文件系统页与可视化总览页 | 无可用图 |
| kernel.org 多队列块层文档 | 不含配图 |
| LWN 内存管理长文 | 正文以代码与表格为主 |
| Prometheus 官网 overview 页（prometheus.io/docs/introduction/overview/） | 2026-09-28 实测：`assets/architecture.png` 直链 404 返回 HTML 页；真实路径是 `/assets/docs/architecture.svg`（抓 overview 页 HTML 找到），cairosvg 转 PNG 1600×960 合格，监控体系与架构主题首选 |
| Anthropic 官方文档 Prompt caching 页（docs.anthropic.com/en/docs/build-with-claude/prompt-caching） | 2026-09-28 实测：docs 图片走 mintlify CDN 直链可下（prompt-cache-mixed-ttl.png 1400×993），官方机制图带英文标签；讲上下文缓存、KV 缓存 TTL、成本结构主题首选 |

分布式与一致性：

| 页面 | 实测结果 |
| --- | --- |
| Pulsar 官方文档架构概览页 | 10 张位图加 18 个矢量图，含分层架构与消息流向 |
| ZooKeeper 官方文档概览页 | 6 张位图，含集群角色与服务流程 |
| Raft 官网 | 首页 img 全是 logo 与视频缩略图，角色状态与日志复制示意在演示 PDF 内，不作为位图来源 |
| etcd 官方文档数据模型页 | 抓取时内容编码异常，需换用浏览器 |
| etcd 官方文档学习设计页 | 13 张候选全部合格，分区场景图（server-learner-figure-01 到 09）画 leader 被隔离与新旧 leader 对照，一致性主题最集中的页面 |
| raft-zh_cn 仓库 images 目录 | 论文 16 张配图按章节命名（raft-图1 到 图16），经 jsDelivr 直链可用；图2 是状态与 RPC 浓缩规范卡，图7、12、14 宽度低于 706px 不采用 |
| arxiv 原生 HTML 版（arxiv.org/html/<id>） | 论文正文图在 HTML 里的引用是 `object type="image/svg+xml"` 元素，`find_images.py` 现已支持；页面直取即可拿全 Figure 列表与图注。ReAct（2210.03629v3）实测 4 张入选：teaser-new.svg 是 Figure 1 四宫格方法对照，hotpot_finetune.svg 是 Figure 3 实测曲线，date.svg 与 human_edit.svg 是附录示例 |

AI 与 Agent：

| 页面 | 实测结果 |
| --- | --- |
| Anthropic 的 Building effective agents | 9 张全部合格，工作流图组覆盖提示链、路由、并行化、编排者-工作者、评估者-优化器与自主 Agent 六种形态，多智能体主题最集中的一页 |
| Anthropic 官方文档 Claude Code Hooks 页（docs.anthropic.com/en/docs/claude-code/hooks） | 2026-09-28 实测：官方配图 hooks-lifecycle.svg 直链在 mintcdn.com（`https://mintcdn.com/claude-code/x7pO8l4XcvAXCoVc/images/hooks-lifecycle.svg?w=1650&fit=max`，需带 UA），cairosvg 转 PNG 得 1650×4239 超长竖图；站点正文图有 max-height:760px 约束，直接用会被等比缩到约 295px 宽（文字偏小），须按节点边界裁成分段图再入库（裁剪点选 SubagentStop/TaskCreated 之间）；hook-resolution.svg 同路径可得，讲 hooks 匹配优先级时用。讲 hooks、生命周期事件、PreToolUse/PostToolUse 拦截点主题首选 |
| OpenMAIC 项目官网（openmaic.stanford.edu） | 2026-09-28 实测：官网首页实拍（playwright viewport 1600×1000）可得带界面信息的实拍图；陷阱是 v1.1.0 release 弹窗会挡住首屏，先点 "Got it" 关闭再截；首页 banner 是纯宣传插画（无界面信息）不要用，要截带课程列表/界面元素的区域。AI 教育工具主题可用 |
| Reflexion 论文的 arxiv HTML 版（2303.11366v4） | 9 张入选：reflexion_tasks.svg 是 Figure 1 三领域循环，reflexion_rl.svg 是 Figure 2 架构图，其余为实测曲线与逐任务小图 |
| LangGraph 官方文档 persistence 页 | 正文以代码与表格为主，无内容配图 |
| OpenAI Agents SDK 文档 running agents 页 | 无内容配图 |
| WebAgents 综述的 arxiv HTML 版（2503.23350） | 3 张正文位图（Intro、Targets、TrainingData，相对路径 `2503.23350v4/` 下），Figure 2 是感知/规划/执行全景图；论文页位图的宽度声明是显示宽度，硬过滤会漏抓，脚本已修 |
| WAAA 攻击面论文的 arxiv HTML 版（2605.05509） | 4 张候选，See→Act 模型图（tm_seeact.svg）只画 Browser-Agent-User 三方循环，讲验证分支不适用，抽象循环图 mermaid 可复刻，不作为图源 |
| Outlines 论文的 arxiv HTML 版（2307.09702） | 2 张候选：fsm-logits-mask.svg 是 Figure 1 FSM 逐 token 屏蔽机制图（603×454 SVG，矢量可放大），讲约束解码、schema 编译状态机、logit 屏蔽时的首选；guidance-comparisons.svg 460×345 宽度不足，只讲方法对比时用。同主题常被错引的 2307.08674 是 TableGPT 论文，与约束解码无关 |
| Anthropic 沙箱 containment 相关页（官方图经 7minai 转载，1200×675 PNG） | defense-components.png 是「确定性边界包住概率模型」架构图（输入/输出 audit + 环境天花板 hard ceiling），适合讲「模型是概率的、边界是确定的」主题；讲「多层防御各自拦什么、单层失效另一层兜底」的文章不对位——它画的是包裹关系，并行拦截与兜底关系没有现成图，直接自绘双路径分岔。host-vs-vm.png（Full-VM vs host-loop）讲隔离模式取舍时用；egress-proxy.png 讲「允许域名也能外泄、出口代理验 token」时用。搜到的 5/6/8 层防御堆栈图（scixa、dev.to、aidev8 等）全是层层堆叠形态，与「两层并行各拦一段」结构不同，此类主题不必再搜 |
| Hugging Face 博客 Common AI Model Formats（ngxson） | 7 张候选全部合格：safetensors 结构图（2000×1523）讲模型文件格式与信任边界首选；GGUF 结构图（2000×1456）讲 GGUF 布局；pickle 十六进制视图（1326×296）画面是无害字典字节，讲「加载即执行」不适用；ONNX 计算图（1862×1062）讲 ONNX 时用。模型文件格式主题最集中的一页 |
| Livshits 约束解码博客（ben-livshits.org） | 3 张候选全通过脚本过滤：expressiveness-ladder.svg（760×600 SVG）是形式化验证四级阶梯（正则→CFG→类型系统→定理证明器），讲「保证的档次上限」适配，讲文法谱系本身会答非所问；gcd-principles.png（2702×1325）讲约束束采样安全增强，cars-trie-pruning.png（1059×585）讲剪枝，均只适配各自小节。docs.lmjobs.ai 域名已死（DNS 解析失败，wayback 429），约束解码类文章的引用换成 docs.vllm.ai 的 structured_outputs 页 |
| Prompt Flow Integrity 论文的 arxiv HTML 版（2503.15547） | 27 张候选：机制节 Figure 2 攻击流图（prompt-injection.png 自然宽 452px）把注入与提权串成单链，讲「注入如何演变为提权」适配，讲两类威胁独立性论点的文章不适用（角度错位）；Figure 4 PFI 总览图 700×559、Figure 5 架构图 1749×617 讲防御架构时可用。此页多面板子图（ltx_flex_figure）自然宽 409-504px，曾因位图静默丢弃线 560px 整组漏抓，脚本已修为警告保留 |
| Hugging Face 博客 Common AI Model Formats | 7 张候选全部合格：safetensors 结构图（2000×1523，画 8 字节头长度、JSON 头 dtype/shape/offsets、原始张量数据）是讲模型文件格式与信任边界主题的首选；pickle 十六进制视图截图（1326×296）内容只是无害字典的序列化字节，画面里没有 GLOBAL/REDUCE 操作码，讲「加载即执行」不适用；GGUF 结构图（2000×1456）讲 GGUF 布局时用；ONNX 计算图（1862×1062）讲 ONNX 时用 |
| SLSA 官网 slsa.dev 与搜索到的 SLSA 解读页 | slsa.dev/spec/v1.0/ 正文纯文字加徽章，无内容配图；搜索命中的 SLSA 图（cleanstart 的 L0-L4 阶梯、NIST SCITT PDF 的攻击面图、khimananda 的流水线图）全部是「构建完整性档次」或「无失败路径的流水线」，讲供应链门禁的准入分岔（候选输入→验证→进生产/停止发布）没有现成图，此主题直接自绘；CISA 的 AI 协作 playbook 页带浏览器 UA 仍 403，定性为反爬拦截非死链，链接保留 |
| Design Patterns for Securing LLM Agents 论文的 arxiv HTML 版（2506.08837） | 5 张候选全是安全设计模式架构图：dual_llm.svg（Figure 4，720×261 矢量）Privileged LLM 持工具、Quarantined LLM 读不可信内容、中间只走符号内存，讲权限最小化、双模型隔离、注入够不到工具时首选；action_selection.svg（Figure 1）讲动作白名单可用；plan_execute、map_reduce、code_execute 三张讲对应模式时用。algomox 五层防御页候选 0 张（图是文字排版非图片标签）；singhajit 七层、lushbinary 十层、zylver 五闸门、freebuf 多层漏斗类全是「层层串行过滤」形态，讲「权限最小化把概率防御变工程防御」的结构性论点不对位，此类主题不必再搜 |
| FlashAttention 论文的 arxiv HTML 版（2205.14135） | 9 张候选：banner_pdf.svg（Figure 1 三面板概览，矢量）左存储层级带宽差、中 tiling 数据流、右 GPT-2 实测时间对比，讲 IO 感知、tiling 不物化、推理算子提速时首选；flashattn_micros.svg（Figure 2，216×72）与 attention_benchmarks.svg（Figure 3，396×120）声明宽度过小讲实测曲线时慎用；figs/flashattn_speedup.jpg（2013×932）讲各序列长度加速比时用。脚本对矢量图的声明宽度 WARN 不适用，cairosvg 放大到 1600px 文字清晰 |
| PagedAttention 论文的 ar5iv HTML 版（2309.06180） | 28 张候选：logical-and-physical-block-table.svg（Figure 6 块表翻译图，矢量）讲「块不必连续」机制首选；baseline-memory-management.svg（Figure 3 现有系统浪费图）1054×159 过扁，正文宽度下密集文字不可读，讲三分区浪费时改用文字；pagedattention.svg（Figure 5）讲 kernel 逐块计算时用；system-overview.png（Figure 4 vLLM 系统总览）讲调度器与 KV 管理器分工时用。官方 arxiv.org/html/2309.06180v1 路径同图可达，图片引用优先用官方路径 |
| Orca 论文（OSDI 2022） | 无 arxiv 版本，arxiv 搜 Orca 出的 2205.13515 是 Green Hierarchical Vision Transformer（错引陷阱），引用地址用 usenix.org/conference/osdi22/presentation/yu，PDF 在 usenix.org/system/files/osdi22-yu.pdf；PDF 截图提取麻烦，讲 static vs continuous batching 对比时直接自绘双路径图，不必再搜 |
| openai.com 定价页 | openai.com/api/pricing 带 UA 仍 403，反爬拦截非死链；陷阱：platform.openai.com/docs/pricing 返回 200 但页面标题是 Cloudflare「Attention Required」挑战页，探 200 不够，状态码之外必须核标题或正文再判可达；讲 token 定价与单位成本时没有可静态嵌入的现成图，公式与算例自足 |
| FrugalGPT 论文的 ar5iv HTML 版（2305.05176） | 8 张候选：FGPTcasestudy.png（Figure 3 三面板，1176×432）级联策略＋GPT-4 答错级联答对的实例＋成本精度总账，讲级联结构首选；methodexample.svg（Figure 2 五策略，597×551 矢量）级联只占五分之一面板，讲级联本身答非所问，讲提示裁剪/查询合并/缓存/微调各档时用；headlines/overruling/coqa_acc_bound.png 与 tradeoffs_full.png 是成本精度权衡曲线，讲权衡曲线时用。arxiv 官方 html 路径 404，取图用 ar5iv 路径。级联链图（M1→打分→M2→…）此页没有独立单图，需要干净单链时自绘 |
| RouteLLM 论文的 arxiv HTML 版（2406.18665） | 12 张候选全是路由器性能/成本权衡曲线（gsm8k、mt-bench、mmlu 各基准的 router 表现），讲「路由器值不值」的实测证据时用；没有路由分发结构图，讲「先判难度再分发」的结构直接自绘。Bedrock model-routing 文档页 img 标签确认为 0，讲产品级路由规则用文字 |
| Sarathi-Serve 论文的 arxiv HTML 版（2403.02310，OSDI 24） | 15 张候选全矢量：sarathi_server_timeline.svg（Figure 4，669×394）四行调度时间线（vLLM/Orca decode 停摆、FasterTransformer prefill 饿死、Sarathi-Serve 分块交错 no stalls）一张图同时覆盖干扰两难与分块解法，讲两阶段调度首选；yi-arxiv-banner.svg（Figure 1a）与 banner-latency.svg（Figure 1b）是 token 流停摆与 P99 尾延迟实测曲线，讲现象证据时用；analysis_pd_breakdown.svg（Figure 5，864×360）、arithmetic_intensity.svg（Figure 6）是算术强度与耗时占比，讲计算/访存受限画像时用；tradeoff_space.svg 讲吞吐延迟权衡空间 |
| Sarathi 论文的 ar5iv HTML 版（2308.16369） | 21 张候选：intro_fig.png（Figure 1 两级流水线调度对比 2551×1984 位图）与 bubbles.png（Figure 5 流水线气泡）讲 pipeline parallelism 气泡时用；chunking_attn_mask.svg（Figure 6）讲分块后 attention mask 结构时用；tilecurve.svg（Figure 7）讲 chunk 大小的 tile 量化效应时用；两篇与调度时间线主题重复的图以 Sarathi-Serve 的 Figure 4 更全 |
| AWQ 论文的 arxiv HTML 版（2306.00978，MLSys 24） | 10 张候选全可用：method.svg（Figure 2，1600×359 矢量三面板：RTN 直压 PPL 43.2 / 按激活保 1% 显著通道 FP16 PPL 13.0 但混精度伤硬件效率 / 量化前按 α 等比缩放权重全 INT3 同样 13.0）讲激活感知保护机制的首选，一张图同时给出错误做法与两条改进路径的实测对照；teaser.png（Figure 1，1700×567 位图）是方法总览与端侧加速结果，讲 AWQ 全貌时用；memory_bound_analysis.svg（Figure 3，1300×265）是 RTX 4090 访存瓶颈分解，讲量化为什么加速 decode 时用；weight_packing.svg（Figure 4）讲 SIMD 打包细节时用；vicuna_gpt4_eval_small.svg（Figure 5）与 visual_reasoning.png（Figure 6）是质量评测证据。ar5iv 版 assets 路径同图（assets/method.svg） |
| MLMD 官方文档（tensorflow.org/tfx/guide/mlmd，注意 guide/ml_metadata 旧路径 404）与 TFX 论文页（research.google/pubs/tfx-a-tensorflow-based-production-scale-machine-learning-platform） | MLMD 文档仅一张组件总览图（MetadataStore 架构概览），讲 artifact/execution/event 数据模型概念时可用，讲具体排查或血缘故事时是产品架构档次不对位；TFX 论文页纯文本无图。陷阱：TFX 是 KDD 2017 系统论文无 arxiv 版，按主题搜 arxiv 会命中同名术语无关论文（2010.02055 是 Automata 量化验证、2203.10050 是 SURF 强化学习），引用走 research.google 官方页；ACM doi 页 403 反爬非死链 |
| AWQ 论文的 ar5iv HTML 版（2306.00978） | 11 张候选全宽幅：method.svg（Figure 2，1600×359 矢量）三面板 RTN PPL 43.2 → 保 1% 显著权重 PPL 13.0 混合精度低效 → 缩放后 INT3 PPL 13.0，讲离群值激活感知保护机制首选，一张图自带三组对照数字；teaser.png（Figure 1）讲 TinyChat 部署成果时用；memory_bound_analysis.svg（Figure 3）讲 W4A16 瓶颈分析时用；weight_packing.svg（Figure 4）讲 SIMD 打包时用；vicuna_gpt4_eval_small.svg、visual_reasoning.png、coco_caption_samples_w4.png 是 GPT-4 评测与视觉推理样例（质量证据）；calib_set_ablation_small.svg（Figure 8）讲校准集规模敏感性时用；speedup.png、speedup_comparisons.png 是 TinyChat 加速实测 |
| SmoothQuant 论文的 ar5iv HTML 版（2211.10438） | 主图 Figure 5（X·diag(s)⁻¹ 与 diag(s)·W 的难度迁移示意，α=0.5）讲「量化难度从激活迁到权重」的 W8A8 机制时用；Figure 3 是 OPT-13B 线性层激活/权重幅度前后对照（数值表形态）；Figure 6 是 Transformer 块精度映射图（哪些算子 INT8 哪些 FP16）；Figure 10 是迁移强度 α 的 sweet spot 曲线，讲 α 调参时用。与 AWQ 机制图主题相邻（一个 W4A16 一个 W8A8），同篇不重复插 |

网络与代理：
| 模型服务架构演进主题的搜索命中页 | NVIDIA Dynamo docs、llm-d（Red Hat）、turion、haoailab、DistServe 相关全是「Router→Prefill 池→Decode 池」分离式单级架构图，只覆盖演进链最后一级；「单进程→多副本→分离式」三级演进阶梯与「决定者上移」没有现成静态图，此主题直接自绘谱系阶梯，不必再搜；arxiv 2511.07422 的聚合 vs 分离对比表与文章自带表格重复。docs.ray.io 探活返回 200 但标题是 Cloudflare「Just a moment...」拦截页，按不可达处理 |

网络与代理：

| 页面 | 实测结果 |
| --- | --- |
| Cloudflare 博客 Pingora 文章 | 6 张可用，含代理线程模型与请求路径 |
| nginx 官方文档 | 不含配图 |
| Envoy 官方文档架构概览页 | 无可用位图 |

缺陷与故障分析：

| 页面 | 实测结果 |
| --- | --- |
| perfmatrix 线程转储分析页 | 17 张可用，含传递关系图、循环等待图、分析面板截图。这一类命中率最高的一页 |

操作系统与并发：

| 页面 | 实测结果 |
| --- | --- |
| preshing 无锁编程入门 | 5 张可用，其中 2 张尺寸达标 |
| preshing 内存重排序实测页 | 2 张可用，尺寸偏小，只在讲原始输出时使用 |
| Wikimedia Commons PDP-7 实物照（File:PDP-7-oslo.jpg） | 2026-09-28 实测：1280×960，公库历史机照，讲 Unix 诞生、早期硬件、词源类文章的实物配图首选（PDP-7 是 Unix 诞生机器，比 teletype 更贴题） |

## 四、找图流程

1. 定问题：这一处要回答什么，是结构、演进、真实形态还是实测数据
2. 查 `assets.md`：先看已验证清单里有没有现成的
3. 定关键字：**中文图优先**——搜两轮，第一轮用中文核心名词加「架构图」「原理图」「流程图」「示意图」，第二轮才用英文技术名词加 figure、architecture、diagram、evolution、layout、benchmark。中文读者扫图先看标签，中文图省掉一层翻译，同名概念的中文图与英文图对位时取中文图。中文图的来源：技术团队公众号与团队博客（美团技术团队、字节跳动技术团队、阿里技术、腾讯云开发者社区这类）、中文技术社区专栏、论文中文版与配套仓库的 images 目录（如 raft-zh_cn，图按「图1」到「图16」命名）、国内厂商的官方技术文档。英文候选仍按主题搜，搜到同主题的中文图时改取中文图。GitHub API 限流时列目录用 jsDelivr 接口，中文文件名先做 URL 编码
4. 搜候选页面：按上表优先官方仓库与官方文档，其次维护者博客
5. 提取候选：用 `scripts/find_images.py` 拉出页面里的图片、尺寸、所属小节、图注、许可
6. 判相关性：读候选图的小节标题、图注、替代文字，确认它回答的正是第 1 步定下的问题
7. 量尺寸与体积：线条示意图不低于 706px，含密集文字的截图不低于 1480px，单张不超过 1.5MB
8. 写入文章：图前一句话引出问题，图后一段收束结论，图注写明来源页面名称与地址

## 五、相关性判断

脚本量不出相关性。判断依据是候选图的三段上下文。

同一小节有多个候选时按此取舍：

1. 直接画出文章讨论对象的（结构图、布局图）优先
2. 画出对象随时间变化的（演进图、阶段图）次之
3. 只画出相邻概念的（外围模块图）再次
4. 画风与站点不协调的（高饱和配色、三维拟物、大量装饰）不采用
5. 带水印、带宣传语、带广告的，即使技术内容合适也不采用

## 六、技术判据

| 项 | 判据 | 依据 |
| --- | --- | --- |
| 协议 | 必须 https | 站点的图片内容安全策略只放行 https 与 data，明文 http 显示成破图 |
| 线条示意图宽度 | ≥ 706px | 等于正文栏宽 |
| 含细节文字截图宽度 | ≥ 1480px | 正文栏宽的两倍，覆盖高密度屏幕 |
| 矢量图宽度 | 无像素下限 | 放大不损失清晰度 |
| 文件体积 | ≤ 1.5MB | 单张上限 |
| 格式 | svg png jpg jpeg webp gif | 其余格式不采用 |
| 地址特征 | 不含 logo、icon、avatar、badge | 这类地址通常是页面装饰 |
| 每篇数量 | 位图不超过 4 张 | 超过后文字密度被压缩 |

## 七、引用写法

```markdown
![Leveled Compaction 的层级结构](https://github.com/facebook/rocksdb/raw/gh-pages-old/pictures/level_structure.png)

上图展示 L0 的文件键范围相互重叠、L1 以下每层内部不再重叠。图取自 [RocksDB 官方仓库 wiki](https://github.com/facebook/rocksdb/wiki/Leveled-Compaction)。
```

外链是位图唯一可行的方式。本库的版本管理忽略 `vault` 目录下的 png、jpg、jpeg、pdf，本地位图不进入版本历史，也不会随部署分发到线上实例。

许可允许再分发时直接引用；要求署名时图注带上作者与许可名称；许可不明或禁止引用时不予采用。

## 八、抓取会遇到的阻碍

GitHub API 对未登录请求限流很快触顶，列仓库目录改用 jsDelivr 的目录接口（`https://data.jsdelivr.com/v1/packages/gh/<owner>/<repo>@<branch>`）或直接抓 GitHub 网页版文件列表；图片直链用 `https://cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/<路径>`，中文文件名先做 URL 编码。

2026-09-28 补充三条实测路线：

**Spring 官方中文站相对路径图**：docs.spring.io 的文档页 img 用相对路径（`../images/xxx.png`），直接拼 URL 会 404；用 playwright 打开页面后 `page.evaluate` 解析 img 的完整 resolved URL，再 `page.request.get` 下载。实测 Spring AOP 两张代理调用对比图（508×192、468×190）此路线可得。

**GitHub commit 页实拍**：讲「上游修复了什么」的缺陷案例文章，直接 playwright 实拍 commit 页（github.com/<org>/<repo>/commit/<sha>，viewport 1600×1100、等待 5s）比解析 diff 文本更直观，一图同时呈现改了哪个文件哪几行。已用于 Pulsar 两个 commit 实拍。

**Medium 系（含 engineering.zooz.com 托管文）懒加载图**：正文 img 的 data-src 与 src 均是 miro.medium.com 变换链，直接 GET src 会拿到 1×1 占位或报 cannot identify image file；稳定路线是枚举页面全部 img 后按 `miro.medium.com/v2/resize:fit:1400/<hash>` 重组 URL 下载，成功率约一半（8 张成 4 张），失败的多为 webp 伪装，改用 playwright 元素截图兜底。

维基媒体的限流区分客户端。命令行工具以浏览器标识请求缩略图地址返回 200，Python 请求库以同一标识请求同一地址返回 403。`find_images.py` 校验维基图地址时会报失败，浏览器实际能正常加载。以浏览器的实际结果为准。

维基共享资源按英文技术名词检索时命中的多是同形异义词。检索 `false sharing` 返回蝴蝶照片，检索 `lock contention` 返回挂锁照片。要用维基共享的图，需要知道确切文件名。

部分站点拒绝脚本抓取。MySQL 官方文档、fastThread 博客、DZone 对脚本请求返回 403，浏览器能正常打开。这类页面改用检索结果里的标题与小节判断相关性。

文档路径改版很常见。拿到 404 时回到检索结果页取当前地址。

arxiv 摘要页（abs 路径）只有论文标题与摘要，没有正文图；要取论文配图必须换 HTML 全文页（`arxiv.org/html/<id>`）。arxiv 站点页头有基金 logo 作为公共资源，每个 abs 页都会贡献同一张候选，用它填充候选清单时注意去重。

矢量图标以 `<svg>` 标签内联在页面里，与配图混在一起。GitHub 页面 430 个矢量标签全是界面图标。判断依据是标签里有没有尺寸与说明文字。

地址里没有 logo、icon 字样的站点 logo 照样存在：站点页头 logo 以正文小节的身份进候选清单，替代文字写着 logo 仍能通过过滤。判据是替代文字与小节身份，地址特征只是初筛。

## 九、脚本用法

```bash
# 从一个页面提取图片，量尺寸并读上下文
python3 scripts/find_images.py --page "https://github.com/facebook/rocksdb/wiki/Leveled-Compaction"

# 一次给多个页面，输出报告
python3 scripts/find_images.py --page URL1 --page URL2 --json report.json

# 检索维基共享资源
python3 scripts/find_images.py --commons "lsm tree"

# 含密集文字的截图按细节图标准卡宽度下限
python3 scripts/find_images.py --page URL --min-width 1480
```

输出每张候选的判定档位、尺寸、格式、体积、所属小节、图注、替代文字、许可。判定档位只反映技术指标，相关性由人依据上下文判断。

找图阶段的候选提取用 `find_images.py`，写入文章后用 `scripts/audit_bitmap.py` 复查地址、宽度与来源标注。

## 十、两条实测踩出来的硬规则

**Wikimedia 的缩略图地址不许手拼。** 地址里那段 hash 目录（`thumb/7/71/`、`thumb/6/60/`）猜不出来——实测手拼两次全部 404。正确做法是用 `imageinfo` API 带 `iiurlwidth` 取真实 `thumburl`：

```
https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo
  &iiprop=url|extmetadata&iiurlwidth=1280&titles=File:<文件名>
```

同一个 API 顺带把许可取回来（`extmetadata` 的 `LicenseShortName` / `Artist`），省一次往返。

**许可带 NC（非商业）的一律不用。** 典型是 Pro Git（git-scm.com）的插图：图多、质量高，但整站是 CC BY-NC-SA，私有站点使用有法律风险——遇到就绕开，去找 Commons 上同为 CC BY-SA 4.0 的等价图（实测"Git 分支分叉"就有合规替代）。选图硬标准：**只要 CC0 / CC BY / CC BY-SA / Apache-2.0 / 公有领域，不要带 NC 的。**

## 中文图源实测（2026-09-25 从治理侧同步，真身在本文件）

> **先读这一条，再往下看表。**
>
> **本节 3.1 起的表格全是英文源，定位是兜底，不是来源全集，更不是首选。**
>
> 使用前提（两条都满足才准用）：
> 1. 3.0 的中文图源已查过；
> 2. 按流程第四节的中文两轮（泛搜 + 中文源定向）都搜过，确认没有对口的中文图。
>
> 换句话说：**中文轮次无果，才轮到这张英文表**。中文图与英文图同时命中同一概念时，一律取中文图。
> 理由：中文读者扫图先看标签，中文图省掉一层翻译。
> 失败模式（2026-09-25 实测教训）：把这张英文表当成全部来源，只在表里挑、从不主动搜中文，结果中文源一次都没被用过。
### 3.0 中文图源（先查这里）
**入口命令**（照抄即可，别自己拼 URL）：
```bash
# 1) 搜：中文关键词 + 来源限定词（用会话里的联网检索工具，不要只在静态清单里挑）
#    例："零拷贝 原理图 中文文档 Nacos/Dubbo/RocketMQ/Sentinel/SkyWalking"
#    例："分布式事务 图解 掘金 知乎 腾讯云开发者社区"

# 2) 提：从候选页抓图片地址
python3 scripts/find_images.py --page "https://nacos.io/zh-cn/docs/v2/architecture.html"

# 3) 落：下载 + 判据 + 镜像 + 出图注（一条命令，许可必须自己确认后传入）
python3 scripts/fetch_figure.py --url "<图片直链>" --slug nacos-arch-1 \\
    --source "Nacos 官方中文文档《Nacos 架构》" \
    --source-url "https://nacos.io/zh-cn/docs/v2/architecture.html" \
    --license "Apache-2.0" --alt "Nacos 基本架构"
# 4) 验：到真实页面确认图显示出来了（阻断步骤）
python3 scripts/verify_images_rendered.py --path "<文章相对路径>"
```

中文来源分两类，许可差别很大，**判定顺序永远是：先判许可，再判相关性**。
A 类 · 开源项目官方中文文档（许可 Apache-2.0/MIT，可镜像并署名，首选）：
| Nacos 中文架构文档（nacos.io/zh-cn/docs/v2/architecture.html） | 可抓；基本架构图、逻辑架构图、数据模型、服务/配置领域模型等中文图；Alibaba Middleware 开源，Apache-2.0。已用于「模型发布需要注册、灰度与回滚」 |
| 微软 Learn 中文文档（learn.microsoft.com/zh-cn/azure/architecture/） | 2026-09-28 实测：`_images/*.svg` 直链全部 404（图在私有仓库），jsDelivr/GitHub raw/canonical 路径均不可达；替代路线是 playwright 打开中文 canonical 页面（如 transactional-out-box-cosmos）实拍 img 元素，得中文标签图（outbox 模式中文实拍已入库 ms-outbox-pattern-zh.png）。中文架构模式图首选源，每篇一个模式页 |
| raft-zh_cn 仓库 images 目录（jsDelivr 直链，中文文件名需 URL 编码） | 16 张中文图（raft-图1 到 图16）。图2「状态与 RPC 规范卡」1908×2284 可用；**图5 只有 519×204，低于 706px 线，不采用**（同类的图7/12/14 同理） |
| SkyWalking 文档（skywalking.apache.org） | 可抓；images/home/architecture_2160x720.png 等，Apache-2.0 |
| Sentinel 中文站（sentinelguard.io/zh-cn/docs/） | 页面声明 Apache-2.0，但 **docs/img/ 下的图 URL 全部 404**（站点改版），需回到站内找当前路径 |
| Apache APISIX 中文文档架构设计页（apisix.apache.org/zh/docs/apisix/architecture-design/apisix/） | 可抓；图在 `raw.githubusercontent.com/apache/apisix/master/docs/assets/images/`（flow-software-architecture、flow-load-plugin、flow-plugin-internal），Apache-2.0，网关/插件/路由主题首选 |
| Dubbo 中文站 / CloudWeGo 中文站 | 抓到的只有 logo 与图标，无机制图 |
| RocketMQ 中文站 | 文档正文页抓取命中 0 |
B 类 · 技术社区与团队博客（**默认禁止转载，不镜像**）：
| 来源 | 实测结果 |
| 腾讯云开发者社区 | 图能抓到，但页脚写「本文系作者授权腾讯云开发者社区发表，**未经许可，不得转载**」→ 判定不采用 |
| 掘金（article.juejin.cn）、知乎专栏、阿里云开发者社区 | 正文是 JS 渲染，脚本抓不到图（只有站点图标）；且文章多标原创禁转 |
| 美团技术团队、字节跳动技术团队、淘宝技术、公众号文章 | 图质量高、中文标注，但许可绝大多数不明或禁转。**只作"知道有这类图"的线索，不镜像**；确要用时走"外链 + 署名 + 来源"，且需负责人确认 |
**可转载性判定**（拿不准就当不可用）：
1. 看许可：开源项目看 LICENSE（Apache-2.0/MIT 可用）；社区文章看页脚/文首声明，出现「未经许可不得转载」「原创」「版权归作者」 → **不采用**
2. 许可不明 → 按 skill 第七节：「许可不明或禁止引用时不予采用」
3. 只有同时满足"许可允许 + 主题对位 + 尺寸达标"，才下载镜像
**来源清单要维护**：每次找图，凡是新验证可用的源、新确认失效的源（404/改版/禁转），**必须写回本文件**再收工。不写回，下次就会重复踩一遍同样的坑——上面每一行实测都是这么攒出来的。
### 3.1 关于英文图源
英文源已按使用者要求整体移除，不再作为图源清单的一部分。
找图的顺序因此简化为：**3.0 中文图源 → 中文两轮联网搜索 → 仍无对口图时，自绘解释图（按 `patterns.md`）或保留无图并写明理由**。
不得因为没有现成图就降低相关性标准去凑图。
3. **先搜，再查表**——这是硬要求，不是建议。
   - 用联网检索工具（`web_search`）主动搜，**不要只在本节的静态表格里挑**。表格里的条目会过期（实测 Sentinel 图已 404、Dubbo 站已无机制图），而新源只能靠搜。
   - **第一轮（中文，必做）**：`<中文核心名词> + 架构图 / 原理图 / 流程图 / 示意图`，可加来源限定词缩小范围：`掘金 知乎 腾讯云开发者社区 阿里云开发者社区 美团技术团队 字节跳动技术团队 淘宝技术 公众号`。
   - **第二轮（中文源定向）**：`<中文核心名词> + 中文文档 / 官方文档 / github 中文`，定向开源项目中文站（Nacos、Dubbo、RocketMQ、Sentinel、SkyWalking、Kitex/Hertz、TARS、TDengine、OceanBase、APISIX、Milvus 的中文文档）。
   - **第三轮（英文兜底）**：`<英文技术名词> + figure / architecture / diagram / evolution / layout / benchmark`。
   - 三轮都出过候选后，同名概念**取中文图**。
   - 中文图的高价值来源：开源项目官方中文文档（A 类，可镜像）、论文中文版与配套仓库 images 目录（如 raft-zh_cn，图按「图1」到「图16」命名）、国内厂商官方技术文档。技术团队公众号/团队博客/社区专栏属 B 类，质量高但通常禁转，按 3.0 的可转载性判定处理。
   - GitHub API 限流时列目录用 jsDelivr 接口（`data.jsdelivr.com/v1/packages/gh/<owner>/<repo>@<branch>?structure=flat`），直链用 `cdn.jsdelivr.net/gh/...`，**中文文件名先做 URL 编码**（如 `raft-%E5%9B%BE2.png`）
| 每篇数量 | 位图宜控制在 4 张内 | 节奏建议，不是硬上限，也不作为文章合格判据 |
![Nacos 基本架构：服务提供方注册到注册中心，消费方从注册中心查询可用实例，配置中心统一管理配置](/static/figures/nacos-arch-1.jpeg)
*图源：Nacos 官方中文文档《Nacos 架构》（Alibaba Middleware 开源项目，Apache-2.0），https://nacos.io/zh-cn/docs/v2/architecture.html。*
中文社区站点大多是前端渲染，脚本直接取 HTML 抓不到正文图：掘金（article.juejin.cn）、知乎专栏、阿里云开发者社区实测都只拿到站点图标。这类页面改用 `web_search` 的标题与摘要判断相关性，或换它的开源官方中文文档（A 类）。
文档路径改版很常见。拿到 404 时回到检索结果页取当前地址（Sentinel 中文站的 `docs/img/` 已整目录 404，就是这么发现的）。
中文文件名做直链时先 URL 编码：`raft-图2.png` 写成 `raft-%E5%9B%BE2.png`，否则 jsDelivr 取不到。
# 从一个中文文档页提取图片，量尺寸并读上下文
python3 scripts/find_images.py --page "https://nacos.io/zh-cn/docs/v2/architecture.html"
注：`--commons`（维基共享资源）属英文图库，已不再作为图源使用。

找图阶段的候选提取用 `find_images.py`，写入文章后用 `scripts/audit_bitmap.py` 复查地址、宽度与来源标注。
