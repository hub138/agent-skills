# 已验证图片资源库

下面每一张都在 2026 年 9 月实测过：地址可直接外链、尺寸与体积已量出、画面内容已核对。需要某类图时先在这里找，找不到再按 `sources.md` 的页面清单去检索。

用法：选定图片后，把地址写进 Markdown 图片语法，图注写明下方给出的来源页面。

## 存储与数据库

页面：RocksDB 官方仓库 wiki 的层级压缩页
来源地址：https://github.com/facebook/rocksdb/wiki/Leveled-Compaction

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 分层存储的整体形态，每层内部文件按键值范围划分 | 讲分层存储布局 | 2428×1279 | 71KB | `https://github.com/facebook/rocksdb/raw/gh-pages-old/pictures/level_structure.png` |
| 各层容量上限的设定方式 | 讲写放大与层容量 | 2162×749 | 58KB | `https://github.com/facebook/rocksdb/raw/gh-pages-old/pictures/level_targets.png` |
| L0 文件重叠导致不得不合并的状态 | 讲压缩触发条件 | 1800×1174 | 51KB | `https://github.com/facebook/rocksdb/raw/gh-pages-old/pictures/pre_l0_compaction.png` |
| 多组压缩并行执行 | 讲后台压缩与并行 | 1800×926 | 68KB | `https://github.com/facebook/rocksdb/raw/gh-pages-old/pictures/multi_thread_compaction.png` |
| 数据在最后一层的分布比例 | 讲空间放大 | 2469×1443 | 85KB | `https://github.com/facebook/rocksdb/raw/gh-pages-old/pictures/dynamic_level.png` |

同一页面另有 7 张，分别是压缩前后的各层状态对照（`pre_l0_compaction`、`post_l0_compaction`、`pre_l1_compaction`、`post_l1_compaction`、`pre_l2_compaction`、`post_l2_compaction`、`subcompaction`），适合讲一次压缩逐步向下传导的过程。

## 性能与底层

页面：Brendan Gregg 的火焰图页
来源地址：https://www.brendangregg.com/FlameGraphs/cpuflamegraphs.html

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 真实采集的火焰图，宽度代表占用时间 | 讲性能分析取样 | 500×312 | 132KB | `https://www.brendangregg.com/FlameGraphs/cpu-mysql-filt-500.png` |
| 中断负载在火焰图上的表现 | 讲中断与内核开销 | 1195×718 | 280KB | `https://www.brendangregg.com/FlameGraphs/numa-rebalance01.png` |
| 同一中断在两张图上的对照 | 讲性能问题定位 | 1196×800 | 159KB | `https://www.brendangregg.com/FlameGraphs/numa-rebalance02.png` |
| 文件读取过程的调用链分布 | 讲文件系统开销 | 1199×418 | 149KB | `https://www.brendangregg.com/FlameGraphs/cpu-linux-tar.png` |

页面：Brendan Gregg 的等待分析页
来源地址：https://www.brendangregg.com/offcpuanalysis.html

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 线程状态划分，在处理器上运行与等待分开 | 讲线程等待 | 1400×886 | 155KB | `https://www.brendangregg.com/Perf/thread_states.png` |
| 等待时间的火焰图 | 讲等待分析 | 2392×1428 | 539KB | `https://www.brendangregg.com/FlameGraphs/off-mysqld1.png` |
| 按等待原因归并后的火焰图 | 讲等待原因归类 | 2390×1462 | 747KB | `https://www.brendangregg.com/FlameGraphs/off-mysqld2.png` |

这一页的线程状态图是「在处理器上运行」与「等待」两分的经典画法，讲排队、连接池、锁等待时可直接引用。

## 分布式与一致性

页面：etcd 官方文档的学习设计页
来源地址：https://etcd.io/docs/v3.5/learning/design-learner/

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 3 节点集群 leader 被隔离，新旧 leader 两幅对照 | 讲分区下的选举与旧 leader 降级 | 1075×792 | 112KB | `https://etcd.io/docs/v3.5/learning/img/server-learner-figure-03.png` |
| 3 节点集群单个 follower 被隔离，集群继续服务 | 讲分区不触发选举的条件 | 1052×462 | 104KB | `https://etcd.io/docs/v3.5/learning/img/server-learner-figure-02.png` |
| quorum 不存在时双方都停滞 | 讲无多数派不推进 | 814×632 | 128KB | `https://etcd.io/docs/v3.5/learning/img/server-learner-figure-04.png` |

同一页面另有 10 张（`server-learner-figure-01`、`05` 到 `13`），覆盖 learner 加入、误配额与晋升场景。该页 13 张在 2026 年 9 月经 `find_images.py` 全部量测通过。

页面：raft-zh_cn 仓库的论文配图目录
来源地址：https://github.com/maemual/raft-zh_cn

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 论文 Figure 2 浓缩规范卡：状态字段、RequestVote、AppendEntries 与服务器规则 | 讲 Raft 实现参照与逐条核对 | 1908×2284 | 702KB | `https://cdn.jsdelivr.net/gh/maemual/raft-zh_cn@master/images/raft-图2.png` |
| 论文 Figure 3 五条安全性性质文字框 | 讲选举安全与日志匹配性质汇总 | 930×686 | 128KB | `https://cdn.jsdelivr.net/gh/maemual/raft-zh_cn@master/images/raft-图3.png` |

该目录 16 张按论文章节命名，图7、图12、图14 宽度低于 706px 不采用，其余场景讲论文机制时逐张核对后取用。

## AI 与 Agent

页面：ReAct 论文的 arxiv HTML 版
来源地址：https://arxiv.org/abs/2210.03629

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 论文 Figure 1 四宫格：Standard、CoT、Act-Only 与 ReAct 在同一任务上的对照，失败与成功路径逐行标注 | 讲 ReAct 循环形态、推理与行动交错为什么有效 | 856×700 | 572KB | `https://arxiv.org/html/2210.03629v3/teaser-new.svg` |

同页 Figure 3（hotpot_finetune.svg，854×360）是模型规模与学习方式的实测曲线，讲范式选择时不采用；Figure 4、5 是附录示例。该页在 2026 年 9 月经 `find_images.py` 提取并逐张过目。

| 论文 Figure 1 三领域反思循环：决策、编程、推理各走一遍任务-轨迹-评估-反思-下条轨迹，Evaluation 行标注 internal/external 分野 | 讲反思有效性、外部锚点、自评不可信 | 1123×421 | 87KB | `https://arxiv.org/html/2303.11366v4/reflexion_tasks.svg` |

同页 Figure 2（reflexion_rl.svg，396×344）是 Actor-Evaluator-Self-Reflection 架构图，讲组件分工可用；Figure 3 到 6 是实测曲线与逐任务小图，讲机制时不采用。该页在 2026 年 9 月经 `find_images.py` 提取并逐张过目。

页面：Anthropic 的 Building effective agents
来源地址：https://www.anthropic.com/research/building-effective-agents

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 编排者-工作者工作流：编排者分解任务给三个并行调用，末端 Synthesizer 合并结论 | 讲多智能体拓扑、编排者-工作者、汇总环节 | 2401×1000 | 15KB | `https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F8985fc683fae4780fb34eab1365ab78c7e51bc8e-2401x1000.png&w=3840&q=75` |
| 并行化工作流：任务分流到多个调用再汇聚 | 讲并行拆分、分段并行 | 2401×1000 | 14KB | `https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F406bb032ca007fd1624f261af717d70e6ca86286-2401x1000.png&w=3840&q=75` |
| 评估者-优化者工作流：一稿一评循环 | 讲反思、双角色迭代 | 2401×1000 | 16KB | `https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F14f51e6406ccb29e695da48b17017e899a6119c7-2401x1000.png&w=3840&q=75` |

同页另有增强型 LLM、提示链、路由、自主 Agent 四张图，讲对应工作流时逐张核对后取用。该页 9 张在 2026 年 9 月经 `find_images.py` 全部量测通过。

页面：WebAgents 综述论文的 arxiv HTML 版
来源地址：https://arxiv.org/html/2503.23350

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| WebAgents 全景框架：感知（截图/文本/多模态）、规划与推理、执行（坐标定位与浏览器操作）三段流程带实例 | 讲 Web Agent 或浏览器 Agent 的整体框架、感知与动作分工 | 1186×456 | 189KB | `https://arxiv.org/html/2503.23350v4/Targets.png` |

同页 Figure 1（Intro.png，567×497）与 Figure 3（TrainingData.png，560×244）宽度低于 706px，只在讲基础概念与训练数据时按原始输出使用。该页 3 张在 2026 年 9 月经 `find_images.py` 提取并逐张过目。

页面：Outlines 论文的 arxiv HTML 版（Efficient Guided Generation for LLMs）
来源地址：https://arxiv.org/abs/2307.09702

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| FSM 逐 token 屏蔽机制：正则编译成四状态自动机，logits 里允许的 token 保留其余涂黑，采样不同 token 各推进到不同状态 | 讲约束解码、schema 编译成状态机、logit 屏蔽、逐 token 合法性保证 | 603×454（矢量） | 61KB | `https://arxiv.org/html/2307.09702v4/fsm-logits-mask.svg` |

该图在 2026 年 9 月下载渲染成 PNG 逐张过目，矢量图放大不损失清晰度；同页 guidance-comparisons.svg（460×345）宽度不足只讲方法对比时用。

页面：Design Patterns for Securing LLM Agents 论文的 arxiv HTML 版
来源地址：https://arxiv.org/abs/2506.08837

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| dual-LLM 模式：Privileged LLM 持 Tools、只接用户 Prompt，Quarantined LLM 关在砖墙里读不可信内容，输出只能经符号内存（$VAR）回流，红色标注不可信数据 | 讲权限最小化、双模型隔离、注入够不到工具、把概率防御变工程防御 | 720×261（矢量） | 290KB | `https://arxiv.org/html/2506.08837v2/dual_llm.svg` |
| action-selector 模式：LLM agent 从预定义动作列表选择后调 Tools，不可信 Data 与 Environment 经红色路径进 Tools | 讲动作白名单、能力收窄 | 720×261（矢量） | 390KB | `https://arxiv.org/html/2506.08837v2/action_selection.svg` |
| plan-then-execute 模式：处理不可信数据前先规划 | 讲规划与执行分离 | 1177×405 | 64KB | `https://arxiv.org/html/2506.08837v2/plan_execute.png` |
| LLM map-reduce 模式：不可信文档独立分片处理 | 讲分片隔离 | 720×261（矢量） | 413KB | `https://arxiv.org/html/2506.08837v2/map_reduce.svg` |
| code-then-execute 模式：LLM 写代码调工具 | 讲代码执行隔离 | 720×261（矢量） | 243KB | `https://arxiv.org/html/2506.08837v2/code_execute.svg` |

五张图在 2026 年 9 月下载过目（SVG 经 cairosvg 转 PNG）；dual_llm.svg 在红队测试文章实插验收通过。注意这组图讲的是「结构性隔离模式」，讲「层层串行过滤」的防御纵深清单不适用。

页面：FlashAttention 论文的 arxiv HTML 版（2205.14135）
来源地址：https://arxiv.org/abs/2205.14135

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 三面板概览：左存储层级（SRAM 19TB/s、HBM 1.5TB/s、DRAM 12.8GB/s 带宽差）、中 tiling 数据流（Q/K/V 切块进 SRAM、Output 才回写 HBM）、右 GPT-2 实测时间对比（PyTorch 分段 vs FlashAttention fused kernel） | 讲 IO 感知注意力、tiling 不物化、访存受限优化、算子融合提速 | 矢量可放大 | 106KB | `https://arxiv.org/html/2205.14135v2/banner_pdf.svg` |

该图在 2026 年 9 月 cairosvg 放大到 1600px 逐面板过目，文字全部清晰；脚本对它的声明宽度 WARN（396px）不适用。同页 flashattn_micros.svg（216×72）与 attention_benchmarks.svg（396×120）声明宽度过小，讲实测曲线时慎用；figs/flashattn_speedup.jpg（2013×932）讲各序列长度加速比时用。

页面：PagedAttention 论文的 ar5iv HTML 版（2309.06180）
来源地址：https://arxiv.org/abs/2309.06180

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| block table 翻译图：左逻辑 KV 块（token 连续）、中块表（物理块号+已填槽数）、右 GPU 显存物理块池（分散落位），生成填满才领新块 | 讲 KV cache 分页、块表映射、逻辑连续物理分散、按需分配 | 矢量可放大 | 154KB | `https://arxiv.org/html/2309.06180v1/logical-and-physical-block-table.svg` |

该图在 2026 年 9 月下载过目并实插验收通过。同页 baseline-memory-management.svg（Figure 3）1054×159 过扁、正文宽度下密集文字不可读；pagedattention.svg（Figure 5）讲 kernel 逐块计算时用；system-overview.png（Figure 4）讲 vLLM 调度器与 KV 管理器分工时用。图片引用优先用官方 arxiv html 路径。

页面：Anthropic containment 官方架构图（经 7minai 转载，原始出处 Anthropic Engineering "How we contain Claude across products"）
来源地址：https://7minai.com/news/anthropic-claude-sandbox-containment/

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 确定性边界包住概率模型：Inputs in 与 Actions out 两侧 External audit/scan，中间 Environment hard ceiling 包住 Model probabilistic | 讲「模型是概率的、边界是确定的」、containment 主题、爆炸半径控制 | 1200×675 | 93KB | `https://7minai.com/images/anthropic-claude-sandbox-containment/defense-components.png` |
| Full-VM 模式与 host-loop 模式对比：Cowork 两种隔离模式的取舍 | 讲隔离模式选择、VM 边界位置取舍 | 1200×675 | 108KB | `https://7minai.com/images/anthropic-claude-sandbox-containment/host-vs-vm.png` |
| 攻击与修复对照：恶意文件借 api.anthropic.com 允许域名外泄，出口代理验 token 后修复 | 讲「允许域名也能外泄」、出口代理、egress 控制 | 1200×675 | 152KB | `https://7minai.com/images/anthropic-claude-sandbox-containment/egress-proxy.png` |

三张图在 2026 年 9 月下载过目；注意官方图讲的是包裹型确定性边界，讲「多层并行拦截、单层失效另一层兜底」的文章不适用。

页面：Hugging Face 博客 Common AI Model Formats
来源地址：https://huggingface.co/blog/ngxson/common-ai-model-formats

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| safetensors 格式结构：8 字节头长度、JSON 头声明每个张量的 dtype/shape/字节区间、其余为原始张量数据 | 讲模型权重文件格式、信任边界、格式即边界、加载路径安全 | 2000×1523 | 158KB | `https://cdn-gcs.ngxson.com/nuiblog2/2025/2/1740665538210_94e230e8.jpg` |

同页 GGUF 结构图（2000×1456）讲 GGUF 布局时用；pickle 十六进制视图截图（1326×296）画面是无害字典的序列化字节，没有操作码，讲「加载即执行」不适用。该页 7 张在 2026 年 9 月经 `find_images.py` 提取并逐张过目。

## 缺陷与故障分析

页面：perfmatrix 的线程转储分析页
来源地址：https://perfmatrix.com/thread-dump-analysis/

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 线程互相等待的传递关系图 | 讲互相等待 | 927×349 | 16KB | `https://perfmatrix.com/wp-content/uploads/2019/11/Thread-Dump-Blocked-Thread-Transitive-Graph.png` |
| 三个线程构成的循环等待 | 讲循环等待 | 711×881 | 123KB | `https://perfmatrix.com/wp-content/uploads/2019/11/Thread-Dump-Deadlock-Complex_DeadLock.png` |
| 被阻塞线程的调用链快照 | 讲阻塞定位 | 771×779 | 154KB | `https://perfmatrix.com/wp-content/uploads/2019/11/Thread-Dump-Blocked-Thread-Stack-Trace.png` |
| 线程数量汇总面板 | 讲线程数异常 | 945×598 | 26KB | `https://perfmatrix.com/wp-content/uploads/2019/11/Thread-Dump-Normal-Thread-Count-Summary.png` |
| 阻塞线程的分析面板 | 讲连接池耗尽 | 854×585 | 21KB | `https://perfmatrix.com/wp-content/uploads/2019/11/Thread-Dump-Blocked-Thread-Dashboard.png` |

这一页共 17 张可用图，是故障分析类文章命中率最高的一页。传递关系图与循环等待图适合讲争用与互相等待，分析面板截图适合讲定位过程。

## 操作系统与并发

页面：preshing 的无锁编程入门
来源地址：https://preshing.com/20120612/an-introduction-to-lock-free-programming/

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 三类并发控制手段的分类 | 讲无锁与互斥 | 524×664 | 21KB | `https://preshing.com/images/techniques.png` |
| 读改写操作让线程依次通过的示意 | 讲原子操作 | 154×132 | 7KB | `https://preshing.com/images/rmw-turnstile-2.png` |

页面：preshing 的内存重排序实测页
来源地址：https://preshing.com/20120515/memory-reordering-caught-in-the-act/

| 画面内容 | 适配的文章场景 | 尺寸 | 体积 | 图片地址 |
| --- | --- | --- | --- | --- |
| 两个线程读写共享变量的汇编片段 | 讲内存重排序 | 479×56 | 3KB | `https://preshing.com/images/marked-example2.png` |
| 重排序出现的实测输出 | 讲重排序复现 | 490×292 | 6KB | `https://preshing.com/images/cygwin-output.png` |

最后两张尺寸低于清晰显示下限 706px，只在讲指令级细节、且读者需要看到原始输出时使用，其余场景自绘。

## 网络与代理

页面：Cloudflare 博客的 Pingora 开源文章
来源地址：https://blog.cloudflare.com/pingora-open-source/

该页图片地址带签名参数，直接把整条地址复制到文章里即可，参数中的宽度档位（`w=2400`、`w=715`）不要改动。讲代理的线程模型、连接复用、请求往返时可从这一页取图。

## 按场景的取图建议

| 文章场景 | 优先取图 |
| --- | --- |
| 讲分层存储、写放大、空间放大 | RocksDB 官方仓库 wiki 的层级压缩页 |
| 讲性能取样、调用链、热点定位 | Brendan Gregg 的火焰图页 |
| 讲排队、等待、连接池耗尽 | Brendan Gregg 的等待分析页 |
| 讲互相等待、循环等待、阻塞定位 | perfmatrix 的线程转储分析页 |
| 讲原子操作、无锁、内存可见性 | preshing 的无锁编程入门与内存重排序实测页 |
| 讲共识、选举、分区与脑裂 | etcd 官方文档的学习设计页与 raft-zh_cn 仓库的论文配图目录 |
| 讲 ReAct、提示法对照、Agent 循环形态 | ReAct 论文的 arxiv HTML 版（teaser-new.svg，Figure 1 四宫格） |
| 讲 Web Agent 整体框架、感知与动作分工 | WebAgents 综述论文的 arxiv HTML 版（Targets.png，Figure 2 全景图） |
| 讲反思、外部锚点、模型自评不可信 | Reflexion 论文的 arxiv HTML 版（reflexion_tasks.svg，Figure 1 三领域循环） |
| 讲模型权重文件格式、信任边界、格式安全 | Hugging Face 博客 Common AI Model Formats（safetensors 结构图） |
| 讲「模型是概率的、边界是确定的」、爆炸半径控制 | Anthropic containment 架构图（7minai 转载 defense-components.png） |
| 讲权限最小化、注入够不到工具、双模型隔离 | Design Patterns for Securing LLM Agents 论文（dual_llm.svg，Figure 4） |
| 讲 IO 感知注意力、tiling 不物化、算子融合提速 | FlashAttention 论文（banner_pdf.svg，Figure 1 三面板） |
| 讲 KV cache 分页、块表映射、按需分配 | PagedAttention 论文（logical-and-physical-block-table.svg，Figure 6） |
| 讲静态批 vs 连续批处理、迭代级调度 | 自绘双路径图（Orca 无 arxiv 版，PDF 截图提取麻烦） |
| 讲分离式 serving、P/D 分离、KV 传输 | NVIDIA Dynamo docs 分离式架构图（Client→Frontend/Router→Prefill/Decode workers，矢量）；讲「单进程→多副本→分离式」演进与决定者上移直接自绘谱系阶梯，无现成图 |
| 讲 LLM 级联、小模型先答大模型兜底 | FrugalGPT 论文 FGPTcasestudy.png（Figure 3 三面板：级联策略＋质量对照＋成本对照）；讲路由器分发结构直接自绘（RouteLLM 全是性能曲线，无结构图） |
| 讲 prefill/decode 两阶段调度、干扰、分块 prefill | Sarathi-Serve 论文 sarathi_server_timeline.svg（Figure 4 四调度器时间线，干扰两难与分块解法一张图全覆盖）；讲 token 流停摆现象配 yi-arxiv-banner.svg（Figure 1a 实测曲线） |
| 讲模型量化、PTQ 精度损失、激活感知保护 | AWQ 论文 method.svg（Figure 2 三面板：RTN 43.2 / 保显著通道 13.0 / 缩放后全 INT3 13.0，错误做法与两条改进路径带实测 PPL 全在图里）；讲量化加速 decode 的访存原因配 memory_bound_analysis.svg（Figure 3） |
| 讲权重量化离群值、激活感知保护（AWQ） | AWQ 论文 method.svg（Figure 2 三面板，RTN 43.2 / 保显著权重 13.0 / 缩放 13.0，机制与数字证据同图）；W8A8 难度迁移主题用 SmoothQuant 论文 Figure 5，两者一 W4A16 一 W8A8 不同篇复用 |
| 讲多智能体拓扑、编排者-工作者、并行拆分 | Anthropic 的 Building effective agents（工作流图组） |
| 讲代理、连接复用、请求路径 | Cloudflare 博客的 Pingora 文章 |

## 使用约束

地址必须用 https。图注写明上表的来源地址。图片宽度低于 706px 的只在讲原始输出时使用。单张体积超过 1.5MB 的不采用。同一篇文章引入多张外链图时，核对画风是否接近，黑白线稿与彩色面板混用会让版面显得零散。